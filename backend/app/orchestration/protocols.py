"""狀態機與資料層之間的接縫（seams）。

這個模組只定義**形狀**：workflow 需要從資料層拿到什麼、用什麼方法拿。真正去讀
SQLite、entitlement graph 或官方文件的程式碼不在這裡。

介面依 `tmp/sqlite-runtime-alignment-proposal.md` 第 6 節逐字定義。四個接縫對應
資料層的四項責任：

- `EntitlementGraphRepository`：事件展開、圖上的前後關係。
  離線實作 `FixtureEntitlementGraphRepository`
- `EligibilityService`：必要欄位、確定性資格判定。
  離線實作 `FixtureEligibilityService`
- `EvidenceRepository`：官方依據。離線實作 `FixtureEvidenceRepository`
- `SourceRefreshService`：coverage 狀態與 on-demand refresh。
  離線實作 `LocalSourceRefreshService`
- `PrivacyGate`：屬性值進入 state 前的檢查。離線實作 `PassThroughPrivacyGate`

## 為什麼要先定形狀

8/1 前不能建立任何 live AWS 資源，資料層的 SQLite repository 也還在做。如果狀態機
直接開 SQLite 連線或讀模組層常數，替換的時候就得改狀態機本身 —— 而狀態機是整條
流程的權威，每次改動都要重新驗證所有轉換。

把依賴倒過來（workflow 宣告它要什麼，呼叫端決定給什麼）之後，換成 SQLite adapter
或之後的雲端 adapter，狀態機一行都不用改。

## 回傳型別的硬規則

依提案第 6 節：**repository 一律回傳 `app.orchestration.data_contracts` 的 domain
dataclass**，不得回傳 `sqlite3.Row`、SQL tuple 或未解碼的 `metadata_json`。這條規則
是「workflow 不依賴資料表欄名」的具體執行方式 —— 只要回傳型別是 domain dataclass，
資料表改名就不會傳染到 workflow。

## 為什麼用 Protocol 而不是抽象基底類別

`Protocol` 是結構型別：只要方法簽章對得上就算實作，不需要繼承。這讓測試可以直接
用幾行的假物件，也讓資料層的 SQLite 實作不必為了滿足型別而 import 這個模組。

## 這裡的離線實作全部不需要 SQLite

每個接縫都有一個不碰資料庫的實作，所以 workflow 的測試可以獨立執行（提案第 10 節
檢查清單的其中一項）。它們也刻意**不編造**資料：`FixtureEvidenceRepository` 預設
回空，`FixtureEligibilityService` 對沒有已核准條件的項目回 `needs_human_review`。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from app.orchestration.data_contracts import (
    CandidateItem,
    Citation,
    CoverageMetadata,
    EligibilityDecision,
    FieldRegistryEntry,
    GraphRelation,
)
from app.orchestration.state import AttributeValue

UserAttributes = Mapping[str, Any]
"""去識別化的資格答案，以欄位代號為鍵。

型別別名照提案第 6 節。值標成 `Any` 而不是 `AttributeValue`，因為資料層的規則條件
可能接受比 workflow 目前允許的三種型別更寬的值；收窄它會讓 SQLite adapter 為了符合
workflow 的型別而先做一次轉換。
"""


# ---------------------------------------------------------------------------
# 接縫定義（提案第 6 節）
# ---------------------------------------------------------------------------


class EntitlementGraphRepository(Protocol):
    """entitlement graph 的唯讀查詢。"""

    def expand_from_event(
        self,
        event_id: str,
        user_attributes: UserAttributes,
    ) -> Sequence[CandidateItem]:
        """展開某個事件對應的候選方案。

        認不出事件時回空序列，而不是猜一組項目 —— 猜錯會讓使用者白跑一趟。
        """
        ...

    def get_prerequisites(self, item_id: str) -> Sequence[GraphRelation]:
        """這一項要先辦哪些事。"""
        ...

    def get_produces(self, item_id: str) -> Sequence[GraphRelation]:
        """辦完這一項會讓哪些事變成可辦。"""
        ...

    def get_programs_by_system(self, system_id: str) -> Sequence[CandidateItem]:
        """某個制度（例如勞保）底下的方案。"""
        ...


class EligibilityService(Protocol):
    """確定性資格判定。

    內部可以呼叫規則 repository 與規則引擎，但 workflow 不應該知道規則存在哪張表。
    """

    def get_required_fields(self, item_id: str) -> Sequence[FieldRegistryEntry]:
        """判定這一項需要哪些欄位。"""
        ...

    def evaluate(
        self,
        item_id: str,
        user_attributes: UserAttributes,
    ) -> EligibilityDecision:
        """判定單一項目。"""
        ...

    def evaluate_many(
        self,
        item_ids: Sequence[str],
        user_attributes: UserAttributes,
    ) -> Sequence[EligibilityDecision]:
        """一次判定多個項目。"""
        ...


class EvidenceRepository(Protocol):
    """官方依據的唯讀查詢。"""

    def get_citations(self, item_id: str) -> Sequence[Citation]:
        """取出一個項目的官方依據。找不到時回空序列。

        找不到依據不是「沒有限制」，呼叫端應該把該項目降級為需人工協助。
        """
        ...


@dataclass(frozen=True)
class RefreshRequest:
    """一次 on-demand refresh 的請求。欄位照提案第 6 節。"""

    event_id: str
    source_ids: tuple[str, ...]
    requested_at: datetime


@dataclass(frozen=True)
class RefreshReceipt:
    """refresh 請求的收據。

    `accepted` 表示是否真的排入了工作；`deduplicated` 表示是否因為同一天已經觸發過
    而被去重。兩者分開，因為「沒排入」有兩種原因（沒有來源到期／今天已經跑過），
    呼叫端的處理方式不同。
    """

    job_id: str
    accepted: bool
    deduplicated: bool


class SourceRefreshService(Protocol):
    """官方來源的 coverage 狀態與 on-demand refresh。

    依提案第 6 節與第 9 節：必須**先回傳目前 coverage 狀態**，再以非阻塞方式排入
    refresh。使用者請求不得等待 crawl、附件處理或 LLM 完成。
    """

    def get_coverage_status(self, event_id: str) -> Sequence[CoverageMetadata]:
        """查與這個事件相關的來源目前抓到什麼程度。"""
        ...

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        """排入 refresh 工作，立刻回收據，不等工作完成。"""
        ...


class PrivacyGate(Protocol):
    """屬性值進入 state 之前的最後一道檢查。"""

    def validate_attributes(
        self,
        answers: dict[str, AttributeValue],
        registry: Any,
    ) -> dict[str, AttributeValue]:
        """回傳可以寫進 state 的答案，或在不合法時拋出例外。

        `registry` 的型別是 `app.orchestration.field_registry.FieldRegistry`，但這裡
        標成 `Any`：`field_registry` 會 import `app.schemas.session`，而
        `app.schemas.session` 又 import `app.orchestration.state`。在接縫定義裡加上
        這條 import 只是為了型別註記，卻會讓模組相依圖更難拆。
        """
        ...


class PassThroughPrivacyGate:
    """離線用的隱私閘門：原樣回傳。

    值本身的型別與選項驗證還沒實作。**欄位代號的 allowlist 不靠這個閘門**，它由
    狀態機在 `_record_answers` 裡強制執行，所以即使有人注入一個什麼都不做的閘門，
    未登記的欄位仍然會被拒絕。
    """

    def validate_attributes(
        self,
        answers: dict[str, AttributeValue],
        registry: Any,
    ) -> dict[str, AttributeValue]:
        """原樣回傳。刻意複製一份，避免呼叫端之後改動同一個 dict。"""
        del registry  # 這個實作不查登記表，簽章為了符合 PrivacyGate 才保留它。
        return dict(answers)


# ---------------------------------------------------------------------------
# 離線實作：entitlement graph
# ---------------------------------------------------------------------------

# 寫死的候選方案，取自 README 的 MVP 情境（配偶過世）。
#
# `program_status` 全部是 `"candidate"`，依提案第 14 節：crawler 與 LLM 只能建立
# **候選**資料，人工審查過的狀態才可以控制 runtime 行為。這批 fixture 沒有經過任何
# 人工審查，所以標成 verified 會是假的 —— 代價是離線流程一律回「需人工協助」，那正是
# 誠實的結果。
#
# `relevance_score` 一律是 None：離線 fixture 沒有算相關性，填一個數字會讓下游以為
# 有排序依據。`missing_field_ids` 留空，因為缺漏欄位是由欄位登記表算出來的
# （見 `missing_fields.py`），不是資料層寫死的。
_DEATH_REGISTRATION = GraphRelation(
    item_id="death_registration",
    display_name="死亡登記",
    order=0,
)

_FIXTURE_ITEMS_BY_EVENT: dict[str, tuple[CandidateItem, ...]] = {
    "spouse_death": (
        CandidateItem(
            item_id="death_registration",
            display_name="死亡登記",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(
                GraphRelation(
                    item_id="funeral_benefit",
                    display_name="喪葬給付",
                    order=0,
                ),
                GraphRelation(
                    item_id="survivor_pension",
                    display_name="遺屬年金",
                    order=1,
                ),
            ),
        ),
        CandidateItem(
            item_id="funeral_benefit",
            display_name="喪葬給付",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(_DEATH_REGISTRATION,),
            produces=(),
        ),
        CandidateItem(
            item_id="survivor_pension",
            display_name="遺屬年金",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(_DEATH_REGISTRATION,),
            produces=(),
        ),
        CandidateItem(
            item_id="health_insurance_change",
            display_name="健保投保身分變更",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(_DEATH_REGISTRATION,),
            produces=(),
        ),
    ),
    "occupational_injury": (
        CandidateItem(
            item_id="occupational_injury_recognition",
            display_name="職業災害認定申請",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        ),
        CandidateItem(
            item_id="occupational_disability_benefit",
            display_name="職災失能／傷病給付（示意）",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        ),
        CandidateItem(
            item_id="disability_assessment",
            display_name="身心障礙鑑定",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        ),
    ),
    "job_loss": (
        CandidateItem(
            item_id="unemployment_benefit",
            display_name="失業給付",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        ),
        CandidateItem(
            item_id="employment_service",
            display_name="就業服務／職訓諮詢",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        ),
    ),
}

# 制度 → 方案代號。制度分類屬於資料層，這裡只是離線示範。
_FIXTURE_SYSTEM_ITEMS: dict[str, tuple[str, ...]] = {
    "household_registration": ("death_registration",),
    "labor_insurance": ("funeral_benefit", "survivor_pension"),
    "national_health_insurance": ("health_insurance_change",),
}


class FixtureEntitlementGraphRepository:
    """離線用的 `EntitlementGraphRepository`：一份寫死的對照表。

    只有 MVP 情境（配偶過世）有資料。其他事件回空 tuple，因為這個實作**沒有**那些
    事件的資料 —— 回一組猜的項目會讓下游誤以為展開成功。

    取代之前的 `FixtureEntitlementSource`。差別不只是改名：回傳型別從
    `state.CandidateItem`（workflow 的判定狀態）換成
    `data_contracts.CandidateItem`（資料層的候選方案），因為展開事件是資料層的動作，
    它不知道也不該決定使用者的判定結果。
    """

    def expand_from_event(
        self,
        event_id: str,
        user_attributes: UserAttributes,
    ) -> tuple[CandidateItem, ...]:
        """查對照表，並在有所在地時附上對應地方方案。

        全國項目一律展開；地方項目由 `jurisdiction_items` 依
        `applicant_jurisdiction` 收斂。事件不在表上時回空 tuple。
        """
        from app.orchestration.jurisdiction_items import local_items_for_attributes

        base = _FIXTURE_ITEMS_BY_EVENT.get(event_id, ())
        if not base:
            return ()
        local = local_items_for_attributes(
            user_attributes, life_event_ids=(event_id,)
        )
        if not local:
            return base
        return base + local

    def _find(self, item_id: str) -> CandidateItem | None:
        for items in _FIXTURE_ITEMS_BY_EVENT.values():
            for item in items:
                if item.item_id == item_id:
                    return item
        return None

    def get_prerequisites(self, item_id: str) -> tuple[GraphRelation, ...]:
        """查前置事項。項目不在表上時回空 tuple。"""
        item = self._find(item_id)
        return item.prerequisites if item is not None else ()

    def get_produces(self, item_id: str) -> tuple[GraphRelation, ...]:
        """查後續解鎖的事項。項目不在表上時回空 tuple。"""
        item = self._find(item_id)
        return item.produces if item is not None else ()

    def get_programs_by_system(self, system_id: str) -> tuple[CandidateItem, ...]:
        """查某個制度底下的方案。制度不在表上時回空 tuple。"""
        item_ids = _FIXTURE_SYSTEM_ITEMS.get(system_id, ())
        found = (self._find(item_id) for item_id in item_ids)
        return tuple(item for item in found if item is not None)


# ---------------------------------------------------------------------------
# 離線實作：資格判定
# ---------------------------------------------------------------------------


class FixtureEligibilityService:
    """離線用的 `EligibilityService`：判定結果由建構參數帶入。

    刻意沒有內建任何判定結果。沒有已核准的條件與證據時不得產生完整資格結論
    （提案第 8 節），所以查不到的項目回 `needs_human_review` 而不是 `eligible`。

    測試要驗證「verified 走完整判定」時，自己把該項目的 `EligibilityDecision` 傳進來
    —— 那份判定就代表「資料層已經有已核准的規則」。
    """

    def __init__(
        self,
        decisions: Mapping[str, EligibilityDecision] | None = None,
        required_fields: Mapping[str, Sequence[FieldRegistryEntry]] | None = None,
    ) -> None:
        self._decisions = dict(decisions or {})
        self._required_fields = {
            item_id: tuple(entries)
            for item_id, entries in (required_fields or {}).items()
        }

    def get_required_fields(self, item_id: str) -> tuple[FieldRegistryEntry, ...]:
        """查必要欄位。沒有資料時回空 tuple。"""
        return self._required_fields.get(item_id, ())

    def evaluate(
        self,
        item_id: str,
        user_attributes: UserAttributes,
    ) -> EligibilityDecision:
        """回傳已核准的判定。沒有的話回需人工協助，不編一個結論出來。"""
        del user_attributes  # 這個實作不算規則，判定結果是預先給的。
        decision = self._decisions.get(item_id)
        if decision is not None:
            return decision
        return EligibilityDecision(
            item_id=item_id,
            status="needs_human_review",
            amount_min=None,
            amount_max=None,
            amount_period=None,
            amount_currency=None,
            reasons=(),
        )

    def evaluate_many(
        self,
        item_ids: Sequence[str],
        user_attributes: UserAttributes,
    ) -> tuple[EligibilityDecision, ...]:
        """逐項判定，順序與輸入相同。"""
        return tuple(self.evaluate(item_id, user_attributes) for item_id in item_ids)


# ---------------------------------------------------------------------------
# 離線實作：官方依據
# ---------------------------------------------------------------------------


class FixtureEvidenceRepository:
    """離線用的 `EvidenceRepository`：依據由建構參數帶入。

    預設是空的。編造一份「官方依據」比沒有依據更糟：使用者會拿著它去問承辦人。
    """

    def __init__(
        self,
        citations: Mapping[str, Sequence[Citation]] | None = None,
    ) -> None:
        self._citations = {
            item_id: tuple(entries) for item_id, entries in (citations or {}).items()
        }

    def get_citations(self, item_id: str) -> tuple[Citation, ...]:
        """查官方依據。沒有的話回空 tuple，呼叫端應據此降級。"""
        return self._citations.get(item_id, ())


# ---------------------------------------------------------------------------
# 離線實作：來源刷新
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LocalSourceRecord:
    """本機來源表的一列。

    比 `CoverageMetadata` 多一個 `check_frequency_days`：「多久該重抓一次」是來源
    自己的設定，不是可量測的抓取進度，所以提案第 7 節沒有把它放進 coverage 契約。
    判斷到期因此屬於**持有來源表的 service**，不屬於拿到 coverage 的呼叫端。
    """

    source_id: str
    crawl_status: str
    domain_tags: tuple[str, ...]
    check_frequency_days: int
    last_crawled_at: datetime | None = None
    indexed_document_count: int = 0


@dataclass(frozen=True)
class LocalRefreshJob:
    """本機佇列裡的一筆 refresh 工作。

    刻意**沒有**任何可以寫回資料治理狀態的欄位。依提案第 9 節第 6 項，crawl 或 LLM
    的產出不得自動標為 `verified`，也不得靜默修改任何已核准規則；狀態提升必須經人工
    審查。少一個欄位，就少一條讓它自動發生的路。
    """

    job_id: str
    source_id: str
    event_id: str
    requested_at: datetime


class LocalSourceRefreshService:
    """離線用的 `SourceRefreshService`：本機來源表加一個同步佇列。

    8/1 前不能建立 live AWS 資源，也不打算為此引入第三方任務佇列，所以「背景工作」
    目前就是一個 list：`request_on_demand_refresh` 把工作記下來就回，不執行抓取。
    這樣「使用者請求不等待 crawl」在結構上成立 —— 這裡沒有任何會等待的東西。

    Same-day dedup 的鍵是 `source_id + event_id + 日期`（提案第 9 節第 4 項）：
    同一來源同一天不會因為多個請求重複觸發。
    """

    def __init__(
        self,
        sources: Sequence[LocalSourceRecord] = (),
        event_domain_tags: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self._sources = {record.source_id: record for record in sources}
        self._event_domain_tags = {
            event_id: frozenset(tags)
            for event_id, tags in (event_domain_tags or {}).items()
        }
        self._triggered: set[tuple[str, str, str]] = set()
        self._queue: list[LocalRefreshJob] = []

    def get_coverage_status(self, event_id: str) -> tuple[CoverageMetadata, ...]:
        """回傳與這個事件的 `domain_tags` 相關的來源目前狀態。

        依 `source_id` 排序，讓同一份來源表永遠得到同一個順序 —— 呼叫端與測試因此
        不必去猜 dict 的迭代順序。事件沒有登記標籤時回空 tuple，不回全部來源：
        「不知道相關的是哪些」不等於「全部都相關」。
        """
        tags = self._event_domain_tags.get(event_id)
        if not tags:
            return ()

        matched = [
            record
            for record in self._sources.values()
            if tags & frozenset(record.domain_tags)
        ]
        matched.sort(key=lambda record: record.source_id)
        return tuple(
            CoverageMetadata(
                source_id=record.source_id,
                crawl_status=record.crawl_status,
                last_crawled_at=record.last_crawled_at,
                indexed_document_count=record.indexed_document_count,
                domain_tags=record.domain_tags,
            )
            for record in matched
        )

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        """把到期的來源排入本機佇列，立刻回收據。

        `job_id` 以 `事件 + 日期` 命名，所以同一天同一個事件的收據可以互相對照。
        它不含任何使用者提供的值。
        """
        day = request.requested_at.date().isoformat()
        job_id = f"refresh_{request.event_id}_{day}"

        due = tuple(
            source_id
            for source_id in request.source_ids
            if self._is_due(source_id, request.requested_at)
        )
        fresh = tuple(
            source_id
            for source_id in due
            if (source_id, request.event_id, day) not in self._triggered
        )
        deduplicated = len(fresh) < len(due)

        if not fresh:
            # 沒有東西要排：可能是都不到期，也可能是今天已經跑過。兩者由
            # `deduplicated` 區分。
            return RefreshReceipt(
                job_id=job_id,
                accepted=False,
                deduplicated=deduplicated,
            )

        for source_id in fresh:
            self._triggered.add((source_id, request.event_id, day))
            self._queue.append(
                LocalRefreshJob(
                    job_id=job_id,
                    source_id=source_id,
                    event_id=request.event_id,
                    requested_at=request.requested_at,
                )
            )

        return RefreshReceipt(job_id=job_id, accepted=True, deduplicated=deduplicated)

    def pending_jobs(self) -> tuple[LocalRefreshJob, ...]:
        """目前排在本機佇列裡的工作。給測試與開發時檢查用。"""
        return tuple(self._queue)

    def _is_due(self, source_id: str, now: datetime) -> bool:
        """這個來源該重抓了嗎。

        三種情況算到期：還沒抓過（`pending_crawl`）、沒有上次抓取時間、距離上次抓取
        已經超過 `check_frequency_days`。不在來源表上的代號回 False —— 不猜。
        """
        record = self._sources.get(source_id)
        if record is None:
            return False
        if record.crawl_status == "pending_crawl":
            return True
        if record.last_crawled_at is None:
            return True
        return now - record.last_crawled_at >= timedelta(
            days=record.check_frequency_days
        )
