"""驗證規則引擎轉接層。"""

from app.orchestration.rule_adapter import adapt_result
from app.orchestration.state import ItemKind, ItemStatus
from app.rules.engine import EligibilityResult


def _result(**overrides) -> EligibilityResult:
    base = {
        "program_id": "test_program",
        "program_name": "測試方案",
        "status": "eligible",
        "relevance_score": 80,
        "amount": None,
        "amount_label": "",
        "missing_inputs": [],
        "reasons": [],
        "source_url": "",
    }
    base.update(overrides)
    return EligibilityResult(**base)


def test_eligible_status_is_mapped() -> None:
    item = adapt_result(_result(status="eligible"))
    assert item.status is ItemStatus.ELIGIBLE


def test_ineligible_status_is_mapped() -> None:
    item = adapt_result(_result(status="ineligible"))
    assert item.status is ItemStatus.INELIGIBLE


def test_needs_information_status_is_mapped() -> None:
    item = adapt_result(_result(status="needs_information"))
    assert item.status is ItemStatus.NEEDS_INFORMATION


def test_unknown_status_falls_back_to_human_review() -> None:
    item = adapt_result(_result(status="something_unexpected"))
    assert item.status is ItemStatus.NEEDS_HUMAN_REVIEW


def test_amount_is_mapped_to_both_bounds() -> None:
    item = adapt_result(_result(amount=10000))
    assert item.amount_min == 10000
    assert item.amount_max == 10000
    assert item.amount_currency == "TWD"


def test_no_amount_leaves_fields_empty() -> None:
    item = adapt_result(_result(amount=None))
    assert item.amount_min is None
    assert item.amount_max is None
    assert item.amount_currency is None


def test_missing_inputs_become_missing_field_ids() -> None:
    item = adapt_result(_result(missing_inputs=["field_a", "field_b"]))
    assert item.missing_field_ids == ("field_a", "field_b")


def test_decisive_conditions_are_empty_for_now() -> None:
    """等資料層配合輸出後再補。"""
    item = adapt_result(_result(status="ineligible", reasons=["需設籍該縣市"]))
    assert item.decisive_conditions == ()


def test_source_url_becomes_a_minimal_citation() -> None:
    item = adapt_result(_result(source_url="https://example.gov.tw/rule"))
    assert len(item.citations) == 1
    assert item.citations[0].url == "https://example.gov.tw/rule"


def test_empty_source_url_means_no_citations() -> None:
    item = adapt_result(_result(source_url=""))
    assert item.citations == ()


def test_item_kind_is_passed_through() -> None:
    item = adapt_result(_result(), item_kind=ItemKind.ADMINISTRATIVE)
    assert item.kind is ItemKind.ADMINISTRATIVE


def test_item_id_comes_from_program_id() -> None:
    item = adapt_result(_result(program_id="my_program"))
    assert item.item_id == "my_program"


def test_resolved_at_is_set_for_terminal_statuses() -> None:
    item = adapt_result(_result(status="eligible"))
    assert item.resolved_at is not None


def test_resolved_at_is_none_for_needs_information() -> None:
    item = adapt_result(_result(status="needs_information"))
    assert item.resolved_at is None
