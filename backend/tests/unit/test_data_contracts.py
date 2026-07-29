"""驗證跨層交換的資料形狀。

這些 dataclass 是資料層與 workflow 之間的邊界格式（提案第 7 節）。測試守住兩件事：
每一個都建得起來、而且都是 frozen —— 邊界資料被下游偷偷改掉，會讓「這筆資料是誰給的」
變得無法追查。

也順便釘住兩個容易被「順手改良」的決定：`StructuredReason.expected`／`actual` 的型別
是 `Any`（條件的值形狀由資料層決定），而 `Citation` 的發布機關欄位叫 `publisher`。
"""

import dataclasses
from datetime import UTC, datetime

import pytest

from app.orchestration.data_contracts import (
    CandidateItem,
    Citation,
    CoverageMetadata,
    EligibilityDecision,
    FieldRegistryEntry,
    GraphRelation,
    StructuredReason,
)

_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def _relation() -> GraphRelation:
    return GraphRelation(item_id="death_registration", display_name="死亡登記")


def _candidate() -> CandidateItem:
    return CandidateItem(
        item_id="funeral_benefit",
        display_name="喪葬給付",
        program_status="candidate",
        relevance_score=None,
        missing_field_ids=("deceased_insurance_type",),
        prerequisites=(_relation(),),
        produces=(),
    )


def _reason(expected: object = "labor_insurance", actual: object = "none_or_unsure"):
    return StructuredReason(
        condition_id="cond_1",
        field_id="deceased_insurance_type",
        operator="equals",
        expected=expected,
        actual=actual,
        label="〈條件說明〉",
        source_reference="doc_1#section_2",
    )


def _decision() -> EligibilityDecision:
    return EligibilityDecision(
        item_id="funeral_benefit",
        status="ineligible",
        amount_min=10000,
        amount_max=10000,
        amount_period="one_time",
        amount_currency="TWD",
        reasons=(_reason(),),
    )


def _citation() -> Citation:
    return Citation(
        document_id="doc_1",
        title="〈條例名稱〉",
        publisher="〈機關〉",
        published_at="2026-01-01",
        effective_at="2026-02-01",
        url="https://example.gov.tw/rule",
        excerpt="〈引用段落〉",
        retrieved_at="2026-07-28",
    )


def _field_entry() -> FieldRegistryEntry:
    return FieldRegistryEntry(
        field_id="deceased_insurance_type",
        data_type="code",
        allowed_values=("labor_insurance", "national_pension"),
        prompt_label="〈提問文字〉",
        why_needed="投保身分決定由哪個機關受理",
        pii_classification="non_identifying",
    )


def _coverage() -> CoverageMetadata:
    return CoverageMetadata(
        source_id="src_1",
        crawl_status="pending_crawl",
        last_crawled_at=None,
        indexed_document_count=0,
        domain_tags=("funeral",),
    )


def test_a_graph_relation_defaults_to_order_zero() -> None:
    assert _relation().order == 0


def test_a_candidate_item_carries_governance_state_not_a_verdict() -> None:
    """資料層交出的候選方案帶治理狀態，不帶使用者的判定結果。"""
    candidate = _candidate()

    assert candidate.program_status == "candidate"
    assert not hasattr(candidate, "status")


def test_a_relevance_score_may_be_absent() -> None:
    """`relevance_score` 只代表相關性，沒有算的時候就是 None。"""
    assert _candidate().relevance_score is None


def test_a_structured_reason_accepts_values_of_any_shape() -> None:
    """`expected`／`actual` 的型別是 `Any`，條件的值形狀由資料層決定。"""
    coded = _reason()
    numeric = _reason(expected=15, actual=5)
    nested = _reason(expected={"any_of": ["a", "b"]}, actual=["a"])

    assert coded.actual == "none_or_unsure"
    assert numeric.expected == 15
    assert nested.expected == {"any_of": ["a", "b"]}


def test_a_decision_keeps_the_amount_split_into_four_fields() -> None:
    """「5,000 元」與「每月 5,000 元」意義不同，不能讓前端從數字猜。"""
    decision = _decision()

    assert (decision.amount_min, decision.amount_max) == (10000, 10000)
    assert decision.amount_period == "one_time"
    assert decision.amount_currency == "TWD"


def test_a_decision_carries_structured_reasons_not_display_text() -> None:
    decision = _decision()

    assert decision.reasons[0].field_id == "deceased_insurance_type"
    assert decision.reasons[0].operator == "equals"


def test_a_citation_keeps_all_eight_fields() -> None:
    """Citation 不得退化成單一 source_url。"""
    citation = _citation()

    assert citation.publisher == "〈機關〉"
    assert citation.effective_at == "2026-02-01"
    assert citation.retrieved_at == "2026-07-28"


def test_a_field_registry_entry_records_why_it_is_needed() -> None:
    """新增一個資格欄位是隱私決策，理由與 PII 分類都要在契約裡。"""
    entry = _field_entry()

    assert entry.why_needed
    assert entry.pii_classification == "non_identifying"


def test_coverage_metadata_reports_measurable_progress() -> None:
    coverage = _coverage()

    assert coverage.crawl_status == "pending_crawl"
    assert coverage.last_crawled_at is None
    assert coverage.indexed_document_count == 0


@pytest.mark.parametrize(
    "instance",
    [
        _relation(),
        _candidate(),
        _reason(),
        _decision(),
        _citation(),
        _field_entry(),
        _coverage(),
    ],
)
def test_every_contract_is_frozen(instance: object) -> None:
    """邊界資料被下游偷偷改掉，會讓「這筆資料是誰給的」變得無法追查。"""
    field_name = dataclasses.fields(instance)[0].name

    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field_name, "mutated")


def test_coverage_metadata_can_carry_a_crawl_timestamp() -> None:
    coverage = dataclasses.replace(
        _coverage(),
        crawl_status="crawled",
        last_crawled_at=_NOW,
        indexed_document_count=3,
    )

    assert coverage.last_crawled_at == _NOW
