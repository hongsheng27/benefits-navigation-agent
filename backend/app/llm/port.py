"""語言模型的邊界形狀與呼叫契約（ADR-0015）。

這個模組定義「怎麼問模型、模型要回什麼形狀」，**不包含任何廠商細節**，也不知道什麼是
生命事件或喪葬給付。廠商實作放在自己的模組（目前是 `bedrock.py`），任務的指示文字放在
`tasks/`。

## 為什麼是一個窄的 port，不是 agent runner

ADR-0004 原本規劃 `AgentRunner` —— 一個模型可以自己選擇並呼叫工具的迴圈。ADR-0015 改成
這個窄 port，理由是：系統裡的模型任務都是問一次答一次（事件辨識、結果白話、依摘錄說明），
沒有工具迴圈；而讓模型能呼叫工具，等於開出一條它可以影響資格判定的路，那是 ADR-0003
明文禁止的。

**不存在的能力不需要用 prompt 或護欄去防守。** 所以這裡沒有工具登記表，也沒有迴圈。

## 為什麼是同步而不是 async

`api/sessions.py` 的端點與 `orchestration/state_machine.py` 的 `advance()` 目前都是同步
函式。把 port 設計成 async 會逼整條呼叫鏈改成 async，那是一次大範圍改動，而收益（單一
請求裡沒有可並行的模型呼叫）等於零。廠商 adapter 內部要怎麼發請求是它自己的事。

## 沒有對話歷史

`LlmRequest` 只帶一段指示與一段使用者內容，**刻意不帶前幾輪的對話**。三個理由：兩個任務
本來就是單次問答；沒有歷史就沒有「歷史被存在哪裡」的問題（ADR-0007）；不帶歷史也讓
Bedrock 請求最單純，資料外送範圍容易檢查。

## 錯誤裡不會有內容

`LanguageModelError` 及其子類別**不得**把使用者送來的文字或模型回覆的原文放進訊息。
例外訊息會進紀錄檔與錯誤回應，而 ADR-0007 規定那兩個地方都不能出現使用者的值。
需要知道「模型回了什麼」時，用本機除錯，不要靠例外訊息。

## 這裡不驗證 payload 的內容

`generate_structured` 回傳的 `payload` 只保證「是一個從 JSON 解析出來的物件」。
**呼叫端必須自己把它解析成自己的模型**（例如 Pydantic），不能假設欄位一定齊全 ——
廠商說它會遵守 schema，那是廠商的說法，不是我們的保證。

不在這裡做通用驗證的理由是：真正的驗證需要知道任務的語意（例如「這個事件代號必須在
登記表上」），而那是 `tasks/` 的知識，不是 port 的知識。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# 任務與結束原因
# ---------------------------------------------------------------------------


class LlmTask(StrEnum):
    """哪一個任務在呼叫模型。

    刻意用列舉而不是自由字串：這個值會進紀錄檔，而 `observability/logging.py` 的欄位
    允許清單只接受代號。列舉讓「不小心把一段描述當成 task id 傳進來」不可能發生。
    """

    RESOLVE_LIFE_EVENT = "resolve_life_event"  # 把一段話變成事件代號與屬性
    EXPLAIN_RESULT = "explain_result"  # 把已定案的判定換成白話
    ANSWER_WITH_REFERENCES = "answer_with_references"  # 依提供摘錄回答諮詢後問題


class FinishReason(StrEnum):
    """模型為什麼停止輸出。

    只保留三種，因為呼叫端只需要區分「拿到完整答案」「被長度截斷」「其他」。
    廠商各自的細分值由 adapter 映射進來，未知的值一律歸到 `OTHER` ——
    猜一個語意比誠實說「不知道」更糟。
    """

    STOP = "stop"  # 正常結束
    MAX_TOKENS = "max_tokens"  # 撞到長度上限，答案可能不完整
    OTHER = "other"  # 其他或未知


# ---------------------------------------------------------------------------
# 請求與結果
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LlmRequest:
    """一次模型呼叫的完整輸入。

    `instruction` 與 `user_content` 分成兩個欄位，不是為了整齊，是因為兩者的性質完全
    不同：`instruction` 是我們寫的、可以進紀錄檔；`user_content` 是使用者打的字，
    **不得**進紀錄檔、不得寫入 state、不得回傳前端。分開放讓這個界線在型別上看得見。
    """

    task: LlmTask
    instruction: str
    """給模型的指示。本專案自己的資產，內容放在 `tasks/`，不放在廠商 adapter 裡。"""

    user_content: str
    """使用者提供的文字。**整個系統唯一持有原文的地方，用完即丟。**"""

    output_schema: Mapping[str, Any]
    """答案要長成什麼形狀，用 JSON Schema 描述。

    必須通過 `validate_portable_schema()` —— 只能用 Bedrock 也支援的那個子集，
    否則換到 Bedrock 那天會收到 400 錯誤（ADR-0015）。
    """

    schema_name: str
    """這份 schema 的代號。

    Bedrock Converse 的 forced tool choice 需要一個穩定的 tool 名稱。放在請求裡而不是
    讓 adapter 自己編，是為了讓任務定義和送出的結構化輸出契約一致。
    """

    max_output_tokens: int = 1024
    """答案的長度上限。撞到上限時 `finish_reason` 會是 `MAX_TOKENS`，而且 JSON 通常
    會不完整、解析失敗 —— 那時應該調高上限或簡化 schema，不是重試。"""

    temperature: float = 0.0
    """輸出的隨機程度。預設 0 是刻意的：兩個任務都是抽取與改寫，不是創作，
    同樣的輸入應該盡量得到同樣的輸出，否則行為無法重現也無法測。"""

    timeout_seconds: float = 20.0
    """等多久放棄。使用者正在等畫面，沒有上限等於讓他無限期卡住。"""


@dataclass(frozen=True)
class LlmResult:
    """一次模型呼叫的結果。

    **刻意不帶模型回覆的原始文字。** 原文可能夾帶使用者說的話，帶著它等於給它一條進入
    紀錄檔或錯誤回應的路。需要看原文時用本機除錯。
    """

    task: LlmTask
    payload: Mapping[str, Any]
    """從模型回覆解析出來的 JSON 物件。內容尚未驗證，呼叫端必須自己解析成自己的模型。"""

    finish_reason: FinishReason = FinishReason.STOP


# ---------------------------------------------------------------------------
# 錯誤
# ---------------------------------------------------------------------------


class LanguageModelError(RuntimeError):
    """模型呼叫相關錯誤的共同基底。

    子類別分成「服務問題」與「輸出問題」兩種，因為呼叫端的處理方式不同：服務問題可能
    值得換一條路（請使用者自己選），輸出問題通常代表 schema 或指示要改。

    **任何子類別的訊息都不得包含使用者送來的文字或模型回覆的原文。**
    """


class LanguageModelUnavailableError(LanguageModelError):
    """連不上、超時、被拒絕、或回了非預期的狀態碼。

    也涵蓋「沒有設定金鑰」—— 那同樣是「現在沒有可用的模型」，呼叫端不需要區分。
    """


class LanguageModelOutputError(LanguageModelError):
    """模型有回應，但不是一個可以解析的 JSON 物件。

    這是「格式壞掉」，不是「內容不對」。內容對不對由呼叫端自己解析時判斷。
    """


# ---------------------------------------------------------------------------
# Port
# ---------------------------------------------------------------------------


class LanguageModelPort(Protocol):
    """呼叫語言模型的唯一入口。

    用 `Protocol`（結構型別）而不是抽象基底類別：只要方法簽章對得上就算實作，
    不需要繼承。這讓測試可以用幾行的假物件，也讓 adapter 不必為了滿足型別而 import
    這個模組。與 `orchestration/protocols.py` 的四個資料層接縫一致。
    """

    def generate_structured(self, request: LlmRequest) -> LlmResult:
        """送一次請求，拿回解析好的結構化結果。

        失敗時拋 `LanguageModelUnavailableError`（服務問題）或
        `LanguageModelOutputError`（回覆不是可解析的 JSON 物件），不回 `None` ——
        「沒有答案」與「答案是空的」必須能分開。
        """
        ...


# ---------------------------------------------------------------------------
# 可攜性檢查：只能用 Bedrock 也支援的 JSON Schema 子集
# ---------------------------------------------------------------------------

# Bedrock 的結構化輸出只支援 JSON Schema Draft 2020-12 的一個子集。這裡用**允許清單**
# 而不是禁止清單，因為 AWS 的文件是以「支援哪些」的方式列出的 —— 沒被列到的關鍵字
# 應當視為不支援，而不是視為可用。
#
# 這份檢查把 ADR-0015 的規則從「文件上的約定」變成「跑起來會擋」。不做這件事的話，
# 違規只會在切換到 Bedrock 的那天以 400 錯誤出現，而那時每一份 schema 都要同時重寫。
ALLOWED_SCHEMA_KEYWORDS: frozenset[str] = frozenset(
    {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "const",
        "anyOf",
        "allOf",
        "$ref",
        "$defs",
        "definitions",
        "additionalProperties",
        "format",
        "minItems",
        # 純說明用，不影響驗證行為，但對模型理解欄位很有幫助。
        "title",
        "description",
    }
)

ALLOWED_STRING_FORMATS: frozenset[str] = frozenset(
    {
        "date-time",
        "time",
        "date",
        "duration",
        "email",
        "hostname",
        "uri",
        "ipv4",
        "ipv6",
        "uuid",
    }
)

# Bedrock 對陣列只支援 minItems 為 0 或 1。
ALLOWED_MIN_ITEMS: frozenset[int] = frozenset({0, 1})


class SchemaNotPortableError(ValueError):
    """schema 用了 Bedrock 不支援的寫法。

    在**送出請求之前**就拋出，而不是等廠商回錯誤 —— 目的是讓違規在開發時就被發現，
    而不是等到換廠商那天。
    """


def validate_portable_schema(
    schema: Mapping[str, Any],
    *,
    _path: str = "$",
) -> None:
    """確認這份 schema 在 Bedrock 上能用。不合規就拋例外。

    檢查五件事：關鍵字在允許清單上、物件必須明寫 `additionalProperties: false`、
    `format` 在支援清單上、`minItems` 只能是 0 或 1、`$ref` 只能指向同一份文件內部。

    `_path` 只用來讓錯誤訊息指出是哪一層出問題，呼叫端不需要傳。
    """
    for keyword in schema:
        if keyword not in ALLOWED_SCHEMA_KEYWORDS:
            msg = (
                f"{_path}: 關鍵字 {keyword!r} 不在 Bedrock 支援的子集內。"
                f"允許的關鍵字：{sorted(ALLOWED_SCHEMA_KEYWORDS)}"
            )
            raise SchemaNotPortableError(msg)

    schema_type = schema.get("type")

    # 物件必須明寫不允許多餘欄位。Bedrock 不接受 additionalProperties 為 false 以外的
    # 值，而「沒寫」在 JSON Schema 裡等於允許 —— 所以沒寫也不行。
    if schema_type == "object":
        if schema.get("additionalProperties") is not False:
            msg = f"{_path}: type 是 object 時必須明寫 additionalProperties: false"
            raise SchemaNotPortableError(msg)
    elif (
        "additionalProperties" in schema and schema["additionalProperties"] is not False
    ):
        msg = f"{_path}: additionalProperties 只能是 false"
        raise SchemaNotPortableError(msg)

    string_format = schema.get("format")
    if string_format is not None and string_format not in ALLOWED_STRING_FORMATS:
        msg = (
            f"{_path}: format {string_format!r} 不在支援清單內。"
            f"支援的格式：{sorted(ALLOWED_STRING_FORMATS)}"
        )
        raise SchemaNotPortableError(msg)

    min_items = schema.get("minItems")
    if min_items is not None and min_items not in ALLOWED_MIN_ITEMS:
        msg = f"{_path}: minItems 只能是 0 或 1，收到 {min_items!r}"
        raise SchemaNotPortableError(msg)

    reference = schema.get("$ref")
    if reference is not None and not str(reference).startswith("#"):
        msg = f"{_path}: $ref 只能指向同一份文件內部（以 # 開頭），收到 {reference!r}"
        raise SchemaNotPortableError(msg)

    _validate_nested(schema, _path)


def _validate_nested(schema: Mapping[str, Any], path: str) -> None:
    """遞迴檢查所有子 schema。

    分成獨立函式只是為了讓 `validate_portable_schema` 讀起來是一串平的檢查，
    不必在中間夾三個迴圈。
    """
    for keyword in ("properties", "$defs", "definitions"):
        nested = schema.get(keyword)
        if isinstance(nested, Mapping):
            for name, sub_schema in nested.items():
                if isinstance(sub_schema, Mapping):
                    validate_portable_schema(
                        sub_schema, _path=f"{path}.{keyword}.{name}"
                    )

    items = schema.get("items")
    if isinstance(items, Mapping):
        validate_portable_schema(items, _path=f"{path}.items")

    for keyword in ("anyOf", "allOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            for index, branch in enumerate(branches):
                if isinstance(branch, Mapping):
                    validate_portable_schema(branch, _path=f"{path}.{keyword}[{index}]")
