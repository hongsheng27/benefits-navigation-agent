"""驗證規則引擎轉接層。"""

from app.orchestration.data_contracts import EligibilityDecision
from app.orchestration.rule_adapter import (
    adapt_result,
    apply_decision,
    downgrade_unexplained_ineligible,
)
from app.orchestration.state import (
    CandidateItem,
    DecisiveCondition,
    ItemKind,
    ItemStatus,
)
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


def test_ineligible_without_decisive_conditions_is_downgraded() -> None:
    """「不符合」但說不出決定性條件時，必須降級為需人工協助（Req 12.3）。

    這個測試原本叫 test_ineligible_status_is_mapped，斷言 ineligible 會原樣映射成
    INELIGIBLE。那把違反 Req 12.3 的行為釘成了期望值：規則引擎目前不輸出結構化的
    決定性條件，所以那條路徑會把「你不符合，但我不能說是哪一條」送到使用者面前。

    因為 decisive_conditions 目前恆為空，這實際上意味著現階段不會有任何項目回報
    「不符合資格」。等資料層開始輸出結構化條件，降級就會自動停止觸發。
    """
    item = adapt_result(_result(status="ineligible"))

    assert item.status is ItemStatus.NEEDS_HUMAN_REVIEW


def test_ineligible_with_decisive_conditions_keeps_its_status() -> None:
    """有決定性條件的「不符合」不該被降級 —— 降級的理由是說不出原因，不是結論本身。

    直接測降級規則本身：`adapt_result` 目前永遠產生空的 decisive_conditions，
    所以從它那邊走不到這一半的規則。
    """
    condition = DecisiveCondition(
        field_id="deceased_insurance_type",
        expected="labor_insurance",
        actual="none_or_unsure",
    )

    kept = downgrade_unexplained_ineligible(ItemStatus.INELIGIBLE, (condition,))
    downgraded = downgrade_unexplained_ineligible(ItemStatus.INELIGIBLE, ())

    assert kept is ItemStatus.INELIGIBLE
    assert downgraded is ItemStatus.NEEDS_HUMAN_REVIEW


def test_downgrade_leaves_other_statuses_alone() -> None:
    """降級只針對「不符合」，其他狀態不受影響。"""
    for status in (
        ItemStatus.ELIGIBLE,
        ItemStatus.NEEDS_INFORMATION,
        ItemStatus.NEEDS_HUMAN_REVIEW,
    ):
        assert downgrade_unexplained_ineligible(status, ()) is status


def test_needs_information_status_is_mapped() -> None:
    item = adapt_result(_result(status="needs_information"))
    assert item.status is ItemStatus.NEEDS_INFORMATION


def test_apply_decision_uses_the_decisions_missing_field_ids() -> None:
    item = CandidateItem(
        item_id="test_program",
        kind=ItemKind.BENEFIT,
        missing_field_ids=("old_field",),
    )
    decision = EligibilityDecision(
        item_id="test_program",
        status="needs_information",
        amount_min=None,
        amount_max=None,
        amount_period=None,
        amount_currency=None,
        missing_field_ids=("field_a", "field_b"),
        reasons=(),
    )

    updated = apply_decision(item, decision)

    assert updated.status is ItemStatus.NEEDS_INFORMATION
    assert updated.missing_field_ids == ("field_a", "field_b")


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


def test_chinese_reasons_do_not_count_as_decisive_conditions() -> None:
    """規則引擎的中文句子不是結構化條件，所以「不符合」仍然要降級。

    這個測試原本叫 test_decisive_conditions_are_empty_for_now，只斷言
    `decisive_conditions == ()`，等於把違反 Req 12.3 的行為（帶著 reasons 的
    ineligible 直接送出去）釘成期望值。

    現在改成同時斷言兩件事：條件確實是空的（資料層還沒配合），而且正因為它是空的，
    status 被降級為需人工協助。有理由的「不符合」與有結構化條件的「不符合」是兩件
    不同的事，只有後者能對使用者說「你差在這一條」。
    """
    item = adapt_result(_result(status="ineligible", reasons=["需設籍該縣市"]))

    assert item.decisive_conditions == ()
    assert item.status is ItemStatus.NEEDS_HUMAN_REVIEW


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
