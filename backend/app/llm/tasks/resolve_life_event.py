"""把一段自由文字對應到一個生命事件代號。

這是整條流程的第一步，也是**系統唯一持有使用者原文的地方**。原文送給模型、拿回一個
代號、然後丟掉：不寫入 `SessionState`（那裡結構上沒有欄位放它）、不寫入紀錄檔
（`observability/logging.py` 的允許清單沒有任何欄位能容納它）、不回傳前端。
這也完成了先前延後的 T13。

## 模型只能回登記表上的代號

輸出 schema 用 `enum` 把 `event_id` 限制在 `data/life_events/events.v0.1.json` 的清單
內，外加一個 `unrecognised`。所以**模型在結構上無法回一個我們不認得的事件** ——
不是事後攔下來，是它沒有那個選項。

`unrecognised` 是刻意給的：面對閒聊或完全對不上清單的描述時，模型有誠實出口，
不必硬塞一個無關代號。

細節不足但仍明顯屬於某一類（例如「親人過世了」）時，應選該類通用代號
（如 `other_relative_death`），再靠後續「確認理解」讓使用者否認並重說。

以下三種情況拋 `LifeEventNotRecognisedError`，由端點轉成 `event_not_recognized`：

1. 模型回 `unrecognised`
2. 模型回的代號不在登記表上（理論上 schema 會擋，但廠商不保證遵守，所以再查一次）
3. 模型服務不可用

第三種也歸在這裡：對使用者而言都是「系統這次沒看懂」。差別記在紀錄檔裡給我們看。

## 這一批沒有做屬性抽取

ADR-0003 允許模型抽取去識別化的資格屬性，那會讓使用者說過的事不必再問一次。
沒有一起做的原因是它需要**從欄位登記表動態生成 schema**：Bedrock 要求
`additionalProperties: false`，所以不能有「任意鍵值對」的欄位，每個允許的屬性都必須
明列。那是獨立的一批（T21b）。
"""

import logging

from app.llm.port import (
    LanguageModelError,
    LanguageModelPort,
    LlmRequest,
    LlmTask,
    validate_portable_schema,
)
from app.observability.logging import log_event
from app.orchestration.life_events import LifeEventRegistry

UNRECOGNISED = "unrecognised"
"""模型用來表示「這段描述對應不到任何已登記事件」的值。

刻意不用空字串或 `null`：兩者都可能是「模型漏填」而不是「模型判斷不出來」，
而那兩件事的意義不同。一個明確的值讓「我不知道」是一個主動的回答。
"""

SCHEMA_NAME = "life_event_resolution"

# 高信心口語備援：模型回 unrecognised、或 Bedrock 瞬間失敗（含節流）時使用。
# 只覆蓋非常明確、短句常踩雷的說法；細節仍以模型為主，確認步驟可糾正。
_KEYWORD_FALLBACKS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("失業", "被資遣", "裁員", "解雇", "被炒"), "job_loss"),
    (("無薪假", "減班休息"), "unpaid_leave"),
    (("職災", "上班受傷", "做工受傷"), "occupational_injury"),
    (("我生病", "生病了", "重大傷病", "住院"), "serious_illness"),
    (("長照", "失智", "外籍看護"), "long_term_care_need"),
    (("家暴", "被打", "保護令"), "domestic_violence"),
    (("懷孕", "有喜"), "pregnancy"),
    (("剛生", "生了小孩", "生育給付"), "childbirth"),
    (("單親",), "single_parent_hardship"),
    (("離婚", "分居"), "divorce"),
    (("先生過世", "太太過世", "老公過世", "老婆過世", "配偶過世"), "spouse_death"),
    (("爸爸過世", "媽媽過世", "父親過世", "母親過世"), "parent_death"),
    (("親人過世", "家人過世", "家裡有人過世", "有人過世"), "other_relative_death"),
)

INSTRUCTION = """你的工作是把一段中文描述對應到一個事件代號。

規則：
1. 只能回答下面清單裡的代號，或 `unrecognised`。
2. 預設要選一個最接近的代號。短句也要對，例如「我失業了」→ `job_loss`，「我生病了」→ `serious_illness`，「親人過世了」→ `other_relative_death`。
3. 有講清楚關係或細節時，選更精確的代號（「媽媽過世」→ `parent_death`，「先生過世」→ `spouse_death`）。
4. 幾乎只有在完全無關（聊天、天氣、沒有生活變故）時才回 `unrecognised`。不要因為句子短就回 `unrecognised`。
5. 只輸出工具參數，不要解釋。

可選的事件代號：
{event_lines}"""
"""給模型的指示。

使用者常說得很短（「親人過世了」「我生病了」）。若一律要求關係細節才給代號，
第一步會反覆失敗，產品等於不能用。因此細節不足時改走該類通用代號；
`unrecognised` 只留給真的對不上任何事件的描述。

後續仍有「確認理解」步驟：選到通用代號後，使用者可以否認並重說得更具體。
"""


class LifeEventNotRecognisedError(RuntimeError):
    """無法把描述對應到已登記的事件。

    **訊息不得包含使用者送來的文字。** 這個例外會被轉成錯誤回應，而錯誤回應與紀錄檔
    都不能出現使用者的值（ADR-0007）。
    """


def build_schema(registry: LifeEventRegistry) -> dict:
    """依登記表產生輸出 schema。

    `enum` 的內容來自登記表加上 `unrecognised`，所以新增一個事件只要改 JSON，
    不用改這裡。

    產生後立刻自我檢查一次可攜性。這裡不可能違規（用的關鍵字都在允許清單上），
    檢查的目的是**萬一之後有人在這裡加欄位**時，會在離線測試就撞到而不是等換 Bedrock。
    """
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["event_id"],
        "properties": {
            "event_id": {
                "type": "string",
                "enum": [*registry.all_event_ids(), UNRECOGNISED],
                "description": "對應到的事件代號，判斷不出來時回 unrecognised",
            },
        },
    }
    validate_portable_schema(schema)
    return schema


def build_instruction(registry: LifeEventRegistry) -> str:
    """組出指示文字，把登記表的代號與說明列給模型。

    說明文字直接取自登記表 —— 模型需要知道 `spouse_death` 指的是「配偶過世」，
    光看英文代號的對應關係並不可靠，尤其使用者說的是「我先生上個月走了」。
    """
    event_lines = "\n".join(
        f"- {definition.event_id}：{definition.description}"
        for definition in registry.definitions()
    )
    return INSTRUCTION.format(event_lines=event_lines)


def _keyword_fallback(text: str, registry: LifeEventRegistry) -> str | None:
    """極短、高信心的口語備援。只在模型失敗或回 unrecognised 時使用。"""
    for keywords, event_id in _KEYWORD_FALLBACKS:
        if any(keyword in text for keyword in keywords) and registry.has(event_id):
            return event_id
    return None


def resolve_life_event(
    text: str,
    *,
    model: LanguageModelPort,
    registry: LifeEventRegistry,
) -> str:
    """把 `text` 對應到一個已登記的事件代號。

    成功時回傳代號，其餘一律拋 `LifeEventNotRecognisedError`。**不回 `None`** ——
    「沒看懂」是一個需要被處理的結果，不是一個可以順著往下走的空值。

    `text` 只在這個函式的參數裡存在，回傳值只有代號。呼叫端拿不到原文，
    所以它不可能被存到別的地方去。
    """
    request = LlmRequest(
        task=LlmTask.RESOLVE_LIFE_EVENT,
        instruction=build_instruction(registry),
        user_content=text,
        output_schema=build_schema(registry),
        schema_name=SCHEMA_NAME,
        # 代號很短，但 tool_use 外殼與較長 enum 仍需要一點空間；64 在實務上偶發截斷。
        max_output_tokens=256,
    )
    try:
        result = model.generate_structured(request)
    except LanguageModelError as error:
        # 只記例外**類別**。例外訊息可能引用使用者提供的值，所以走 exc_info，
        # 由格式器只取類別名稱與堆疊。
        root = error.__cause__
        log_event(
            "life_event_resolution_failed",
            level=logging.WARNING,
            exc_info=True,
            tool=LlmTask.RESOLVE_LIFE_EVENT.value,
            error_type=type(root).__name__ if root is not None else type(error).__name__,
        )
        fallback = _keyword_fallback(text, registry)
        if fallback is not None:
            log_event(
                "life_event_resolved",
                level=logging.INFO,
                life_event=fallback,
                tool=LlmTask.RESOLVE_LIFE_EVENT.value,
            )
            return fallback
        msg = "語言模型目前無法處理事件辨識"
        raise LifeEventNotRecognisedError(msg) from error

    event_id = result.payload.get("event_id")

    if event_id == UNRECOGNISED:
        log_event(
            "life_event_unrecognised",
            level=logging.INFO,
            tool=LlmTask.RESOLVE_LIFE_EVENT.value,
        )
        fallback = _keyword_fallback(text, registry)
        if fallback is not None:
            log_event(
                "life_event_resolved",
                level=logging.INFO,
                life_event=fallback,
                tool=LlmTask.RESOLVE_LIFE_EVENT.value,
            )
            return fallback
        msg = "模型判斷這段描述對應不到任何已登記的事件"
        raise LifeEventNotRecognisedError(msg)

    # schema 的 enum 應該已經擋住不合法的代號，但廠商是否遵守 schema 是它的承諾，
    # 不是我們的保證。這裡再查一次，代價是一個 dict 查詢。
    if not isinstance(event_id, str) or not registry.has(event_id):
        log_event(
            "life_event_resolution_rejected",
            level=logging.WARNING,
            tool=LlmTask.RESOLVE_LIFE_EVENT.value,
        )
        # 刻意不把 event_id 放進訊息。它來自模型而不是使用者，但模型可能把使用者的話
        # 原樣塞進那個欄位，所以當成不可信的內容處理。
        msg = "模型回的事件代號不在登記表上"
        raise LifeEventNotRecognisedError(msg)

    log_event(
        "life_event_resolved",
        level=logging.INFO,
        life_event=event_id,
    )
    return event_id
