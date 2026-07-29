"""跨層交換的資料形狀（storage-neutral domain contracts）。

這個模組逐字實作 `tmp/sqlite-runtime-alignment-proposal.md` 第 7 節的
「Shared data contracts」。它是**資料層與 workflow 之間的邊界格式**，不是 SQLite
schema，也不是對外 API 契約。

## 為什麼是新增，而不是取代 `state.py` 的同名型別

提案第 7 節自己寫「以下 dataclasses 表示跨層交換資料，不等同 SQLite schema」，
第 13 節寫「不可為了符合本文件而直接改 code」。所以這裡是**新增一組邊界型別**，
`app.orchestration.state` 的 `CandidateItem`、`Citation`、`DecisiveCondition` 全部
保留原樣。名稱衝突用模組路徑區分：

- `data_contracts.CandidateItem`：資料層交出來的候選方案，帶**資料治理狀態**
  （`program_status`、`relevance_score`、圖上的前後關係）
- `state.CandidateItem`：workflow 對某一項的**判定狀態**（`ItemStatus`、缺哪些欄位、
  決定性條件、金額）

兩者不能互換：前者回答「資料層有什麼、可信到什麼程度」，後者回答「這位使用者這
一項的結論是什麼」。`program_id` ↔ `item_id` 的命名轉換與型別轉換都屬於 adapter
（見 `rule_adapter.py`），workflow 不因為資料表欄名改變而改 domain contract。

## 為什麼用 frozen dataclass 而不是 Pydantic

這些形狀是**跨層傳遞用的值物件**，不需要驗證外部輸入，也不需要序列化成 API 回應
（那是 `app.schemas.session` 的責任）。提案第 7 節給的就是
`@dataclass(frozen=True, slots=True)`，照抄可以讓兩邊對照時不必先在腦中做一次翻譯。

## 提案第 7 節的契約規則

以下幾條是**規則**，不是建議，改動前請回頭看提案：

- `CandidateItem` 必須提供 `item_id`、`display_name`、`program_status`、
  `relevance_score`、`missing_field_ids`、`prerequisites`、`produces`。
- `EligibilityDecision` 必須提供結構化原因，不得只提供展示文字。
- `StructuredReason.actual` 可以回傳給**提出該請求的使用者**，用來解釋「你的情況」
  與「規則要求」的差異；但 **`actual` 值永遠不得寫入 log、trace、metric、
  exception message 或持久化 audit event**。`app.observability.logging` 的
  `ALLOWED_FIELDS` 裡沒有任何欄位能容納它，照規定使用 `log_event` 就足夠。
- `Citation` 必須保留文件識別、標題、發布者、發布／生效時間、URL、引用段落與
  擷取時間，不得退化成單一 `source_url`。
- Field registry 是 workflow 提問的共同詞彙表，包含型別、合法值、提問文字、
  為何需要及 PII 分類。
- Coverage metadata 表示**可量測的**來源進度，不代表法律或網站內容的絕對完整性。
- `relevance_score` 只代表相關性，**不代表符合資格的機率或程度**。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

ProgramStatus = Literal[
    "candidate",
    "under_review",
    "verified",
    "stale",
    "rejected",
    "inactive",
]
"""資料治理狀態。決定 runtime 可以對這筆方案做到什麼程度（見 `determination.py`）。"""

CrawlStatus = Literal["pending_crawl", "crawled", "error"]
"""單一來源可回報的三種可量測抓取狀態。"""


def _require_aware_datetime(value: datetime | None, field_name: str) -> None:
    """拒絕沒有時區的時間，避免跨 adapter 後失去觀測時間的語意。"""
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must be timezone-aware")


EligibilityStatus = Literal[
    "eligible",
    "ineligible",
    "needs_information",
    "needs_human_review",
]
"""確定性規則引擎唯一允許產生的四種結論。LLM 不得決定或覆寫其中任何一種。"""

AmountPeriod = Literal["one_time", "monthly", "annual"]
"""金額的發放性質。

刻意不重用 `state.AmountPeriod`（StrEnum）：這裡是提案第 7 節逐字宣告的邊界格式，
而 `state.py` 的列舉是 workflow 內部形狀。兩者的**值**相同，所以 adapter 只需要
`AmountPeriod(decision.amount_period)` 一行就能轉換。
"""


@dataclass(frozen=True, slots=True)
class GraphRelation:
    """圖上的一條關係，例如「先辦死亡登記才能請領喪葬給付」。

    `canonical_order` 用來讓資料層決定顯示與辦理順序；順序屬於資料，不該由
    workflow 猜。
    """

    target_id: str
    display_name: str
    canonical_order: int = 0


@dataclass(frozen=True, slots=True)
class CandidateItem:
    """資料層交出來的一筆候選方案。

    與 `state.CandidateItem` 不同：這裡沒有 `ItemStatus`，因為「這位使用者符不符合」
    不是資料層的結論；這裡有 `program_status`，因為「這筆資料可不可信」不是 workflow
    的結論。
    """

    item_id: str
    display_name: str
    program_status: ProgramStatus
    relevance_score: int | float | None
    missing_field_ids: tuple[str, ...]
    prerequisites: tuple[GraphRelation, ...]
    produces: tuple[GraphRelation, ...]


@dataclass(frozen=True, slots=True)
class StructuredReason:
    """造成某個結論的單一條件，拆成可以逐段顯示的結構。

    `expected` 與 `actual` 的型別是 `Any`，因為條件的值可能是代號、布林、數字或
    級距，形狀由資料層的 condition JSON 決定。

    **`actual` 是使用者的實際情況。** 它可以回傳給提出該請求的使用者，但不得寫入
    log、trace、metric、exception message 或持久化 audit event。
    """

    condition_id: str
    field_id: str
    operator: str
    expected: Any
    actual: Any
    label: str
    source_reference: str


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """確定性規則引擎對某一項的判定結果。

    金額分成上下限、發放週期與幣別四個欄位，因為「5,000 元」與「每月 5,000 元」
    對使用者的意義完全不同，不能讓前端從數字或文字猜。
    """

    item_id: str
    status: EligibilityStatus
    amount_min: int | None
    amount_max: int | None
    amount_period: AmountPeriod | None
    amount_currency: str | None
    missing_field_ids: tuple[str, ...]
    reasons: tuple[StructuredReason, ...]

    def __post_init__(self) -> None:
        stable_missing_ids = tuple(sorted(set(self.missing_field_ids)))
        object.__setattr__(self, "missing_field_ids", stable_missing_ids)


@dataclass(frozen=True, slots=True)
class Citation:
    """支撐一項判定的官方依據。

    欄位比 `state.Citation` 多 `effective_at` 與 `retrieved_at`，並把發布機關叫
    `publisher`。差異是刻意的：提案要求邊界格式保留生效時間與擷取時間，讓「這份依據
    是什麼時候抓的、什麼時候生效」可以被追問；`state.Citation` 是既有的 workflow
    形狀，屬於前端契約那一批，晚點才動。
    """

    document_id: str
    title: str
    publisher: str
    published_at: datetime | None
    effective_at: datetime | None
    url: str
    excerpt: str
    retrieved_at: datetime | None

    def __post_init__(self) -> None:
        for field_name in ("published_at", "effective_at", "retrieved_at"):
            _require_aware_datetime(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class FieldRegistryEntry:
    """workflow 提問時的共同詞彙表的一筆。

    `why_needed` 與 `pii_classification` 都是必填：新增一個資格欄位是隱私決策，
    不是方便性決策，強迫填寫等於把審查變成流程的一部分。
    """

    field_id: str
    data_type: str
    allowed_values: tuple[str, ...]
    prompt_label: str
    why_needed: str
    pii_classification: str


@dataclass(frozen=True, slots=True)
class CoverageMetadata:
    """一個官方來源目前的抓取進度。

    這是**可量測**的進度，不是完整性保證。robots.txt、只有 JavaScript 的頁面、
    需要登入、失效連結與掃描檔都會造成缺口，所以這裡只回報數得出來的事實。
    """

    source_id: str
    crawl_status: CrawlStatus
    last_crawled_at: datetime | None
    indexed_document_count: int
    domain_tags: tuple[str, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.crawl_status not in {"pending_crawl", "crawled", "error"}:
            raise ValueError("unsupported crawl_status")
        _require_aware_datetime(self.last_crawled_at, "last_crawled_at")
        _require_aware_datetime(self.observed_at, "observed_at")
        if self.indexed_document_count < 0:
            raise ValueError("indexed_document_count must be non-negative")
