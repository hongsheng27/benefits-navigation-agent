"""把一段自由文字對應到一個生命事件代號。

這是整條流程的第一步，也是**系統唯一持有使用者原文的地方**。原文送給模型、拿回一個
代號、然後丟掉：不寫入 `SessionState`（那裡結構上沒有欄位放它）、不寫入紀錄檔
（`observability/logging.py` 的允許清單沒有任何欄位能容納它）、不回傳前端。
這也完成了先前延後的 T13。

## 模型只能回登記表上的代號

輸出 schema 用 `enum` 把 `event_id` 限制在 `data/life_events/events.v0.1.json` 的清單
內，外加一個 `unrecognised`。所以**模型在結構上無法回一個我們不認得的事件** ——
不是事後攔下來，是它沒有那個選項。

`unrecognised` 是刻意給的：如果只給合法代號，模型面對「我想問問看有什麼補助」這種
無法對應的描述時，只能硬選一個。給它一個誠實的出口，比逼它猜好。

## 為什麼失敗時不猜

事件代號決定後面七個步驟展開哪些項目。猜錯的話，使用者會被問一整串跟他無關的問題，
最後拿到一份跟他的處境無關的清單 —— 而他正在辦喪事。

所以三種情況都拋 `LifeEventNotRecognisedError`，由端點轉成
`event_not_recognized`，讓前端請使用者換個說法：

1. 模型回 `unrecognised`
2. 模型回的代號不在登記表上（理論上 schema 會擋，但廠商不保證遵守，所以再查一次）
3. 模型服務不可用

第三種也歸在這裡，理由是**對使用者而言沒有差別** —— 都是「系統這次沒看懂」，
而區分「我們的模型壞了」和「你的描述我們不懂」對他的下一步毫無幫助。差別記在紀錄檔裡
給我們看。

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

INSTRUCTION = """你的工作是把一段中文描述對應到一個事件代號。

規則：
1. 只能回答下面清單裡的代號，或 `unrecognised`。
2. 描述若對應不到清單上任何一個事件，回 `unrecognised`。不要挑一個最接近的。
3. 不確定時回 `unrecognised`。錯的代號比誠實說不知道更糟。
4. 只判斷「發生了什麼事」，不要推測其他資訊。

可選的事件代號：
{event_lines}"""
"""給模型的指示。

第 2 條與第 3 條是刻意重複同一件事的兩種說法。模型傾向於「盡量幫上忙」，
所以「不要挑一個最接近的」必須明講 —— 只寫「不確定就回 unrecognised」不夠。

第 4 條擋的是模型自作主張多回東西。目前 schema 已經用 `additionalProperties: false`
擋住多餘欄位，但把意圖寫進指示可以減少它把推測塞進 `event_id` 的機會。
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
        # 這個任務只回一個短代號，不需要長度預算。壓低上限也讓「模型開始長篇解釋」
        # 這種失控情況更早被截斷。
        max_output_tokens=64,
    )

    try:
        result = model.generate_structured(request)
    except LanguageModelError as error:
        # 只記例外**類別**。例外訊息可能引用使用者提供的值，所以走 exc_info，
        # 由格式器只取類別名稱與堆疊。
        log_event(
            "life_event_resolution_failed",
            level=logging.WARNING,
            exc_info=True,
            tool=LlmTask.RESOLVE_LIFE_EVENT.value,
        )
        msg = "語言模型目前無法處理事件辨識"
        raise LifeEventNotRecognisedError(msg) from error

    event_id = result.payload.get("event_id")

    if event_id == UNRECOGNISED:
        log_event(
            "life_event_unrecognised",
            level=logging.INFO,
            tool=LlmTask.RESOLVE_LIFE_EVENT.value,
        )
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
