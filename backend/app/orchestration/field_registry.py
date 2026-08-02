"""欄位登記表的讀取與驗證。

這個模組負責「讀取一份 JSON 檔案，驗證它的格式，然後提供查詢方法」。

它**不負責**登記表的內容 —— 有哪些欄位、每個欄位有什麼選項、為什麼需要問，
那些都是由政策資料負責人維護的資料，放在 `data/eligibility_fields/` 底下。

## 為什麼用 JSON 而不是寫在 Python 裡

改欄位是改資料，不是改程式。加一個欄位的門檻應該是「編輯一份 JSON、跑測試」，
不是「改程式、做 code review」。之後如果換情境（從配偶過世換成家人重病），
只要換一份 JSON，不用改程式。

## 欄位結構

每一筆欄位包含：

- `field_id`：唯一代號
- `value_kind`：四種之一（code / boolean / band / integer）
- `option_ids`：code 和 band 型別的合法選項清單
- `required`：是不是一定要回答
- `purpose`：為什麼需要問這個（強制填寫，不能空白）
- `used_by`：哪些項目需要這個欄位（目前選填，之後規則進來要改必填）
- `topic_id`：屬於哪個主題分組
- `status`：draft 或 active

## purpose 為什麼不能空白

新增一個資格欄位是隱私決策，不是方便性決策。強迫填「為什麼需要」等於把審查
變成流程的一部分，而不是靠人記得要審。
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.session import AttributeValueKind

# 預設的登記表路徑。
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "eligibility_fields"
    / "fields.v0.1.json"
)


PII_CLASSIFICATIONS: frozenset[str] = frozenset(
    {"none", "eligibility_sensitive", "direct_identifier"}
)
"""欄位的隱私分級。與 SQLite `field_registry.pii_classification` 的 CHECK 一致。

- `none`：級距、是非題等，單獨看不指向特定個人
- `eligibility_sensitive`：健康、族群、經濟身分、居住地等
- `direct_identifier`：姓名、身分證字號等。**目前沒有任何欄位該用這一級**
"""


class FieldDefinition(BaseModel):
    """登記表裡一個欄位的完整定義。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_id: str
    value_kind: AttributeValueKind
    option_ids: tuple[str, ...] = ()
    required: bool = True
    purpose: str = Field(min_length=1)  # 不能空白
    used_by: tuple[str, ...] = ()  # 目前選填
    topic_id: str
    status: str = "draft"  # draft 或 active

    # 預設值刻意是 `eligibility_sensitive` 而不是 `none`：忘記標的時候要往
    # 「當作敏感」的方向倒。過度保護的代價是多一道確認，反過來的代價是把敏感
    # 資訊當成一般欄位處理。
    pii_classification: str = "eligibility_sensitive"

    @field_validator("purpose")
    @classmethod
    def purpose_not_blank(cls, v: str) -> str:
        if not v.strip():
            msg = "purpose 不能是空白字串。新增欄位是隱私決策，必須寫出理由。"
            raise ValueError(msg)
        return v

    @field_validator("pii_classification")
    @classmethod
    def pii_is_known(cls, v: str) -> str:
        if v not in PII_CLASSIFICATIONS:
            msg = (
                f"pii_classification 必須是 {sorted(PII_CLASSIFICATIONS)} 之一，"
                f"得到 {v!r}。"
            )
            raise ValueError(msg)
        return v


class FieldRegistry:
    """欄位登記表的查詢介面。

    建立時讀取並驗證整份 JSON。格式錯誤會在建立時就拋出，不會延後到第一次查詢。
    """

    def __init__(self, definitions: tuple[FieldDefinition, ...]) -> None:
        self._by_id: dict[str, FieldDefinition] = {d.field_id: d for d in definitions}
        self._by_topic: dict[str, list[FieldDefinition]] = {}
        for d in definitions:
            self._by_topic.setdefault(d.topic_id, []).append(d)

    @classmethod
    def from_json(cls, path: Path = DEFAULT_REGISTRY_PATH) -> "FieldRegistry":
        """從 JSON 檔案建立。格式錯誤會在這裡拋出。"""
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        definitions = tuple(
            FieldDefinition.model_validate(entry) for entry in raw["fields"]
        )
        return cls(definitions)

    def get(self, field_id: str) -> FieldDefinition | None:
        """依代號取得定義。找不到回 None。"""
        return self._by_id.get(field_id)

    def has(self, field_id: str) -> bool:
        """這個代號在不在登記表上。"""
        return field_id in self._by_id

    def all_field_ids(self) -> frozenset[str]:
        """所有已登記的欄位代號。"""
        return frozenset(self._by_id.keys())

    def fields_for_items(self, item_ids: frozenset[str]) -> tuple[FieldDefinition, ...]:
        """取出被指定項目需要的所有欄位。"""
        return tuple(d for d in self._by_id.values() if set(d.used_by) & item_ids)

    def topics(self) -> tuple[str, ...]:
        """所有主題代號，按登記順序。"""
        seen: dict[str, None] = {}
        for d in self._by_id.values():
            seen.setdefault(d.topic_id, None)
        return tuple(seen.keys())

    def fields_in_topic(self, topic_id: str) -> tuple[FieldDefinition, ...]:
        """某個主題下的所有欄位。"""
        return tuple(self._by_topic.get(topic_id, []))

    def count(self) -> int:
        """登記的欄位總數。"""
        return len(self._by_id)
