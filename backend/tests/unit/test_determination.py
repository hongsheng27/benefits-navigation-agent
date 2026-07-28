"""驗證逐項判定組裝：找出就緒項目並判定。"""

from datetime import UTC, datetime, timedelta

from app.orchestration.determination import (
    evaluate_ready_items_stub,
    find_ready_item_ids,
    find_undeclared_item_ids,
)
from app.orchestration.field_registry import FieldRegistry
from app.orchestration.state import (
    CandidateItem,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)


def _registry() -> FieldRegistry:
    return FieldRegistry.from_json()


def _state(
    *,
    attributes: dict | None = None,
    items: tuple[CandidateItem, ...] | None = None,
) -> SessionState:
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    default_items = (
        CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
        CandidateItem(item_id="survivor_pension", kind=ItemKind.BENEFIT),
    )
    return SessionState(
        session_id="s_test",
        workflow_state=WorkflowState.EVALUATE_ELIGIBILITY,
        life_event="spouse_death",
        attributes=attributes or {},
        items=items if items is not None else default_items,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )


def test_no_items_ready_when_nothing_answered() -> None:
    ready = find_ready_item_ids(_state(), _registry())
    assert ready == frozenset()


def test_funeral_benefit_ready_when_its_field_answered() -> None:
    """funeral_benefit 只需要 deceased_insurance_type。"""
    state = _state(attributes={"deceased_insurance_type": "labor_insurance"})
    ready = find_ready_item_ids(state, _registry())

    assert "funeral_benefit" in ready


def test_survivor_pension_needs_all_three_fields() -> None:
    """survivor_pension 需要三個欄位，只答一個還不算就緒。"""
    state = _state(attributes={"deceased_insurance_type": "labor_insurance"})
    ready = find_ready_item_ids(state, _registry())

    assert "survivor_pension" not in ready


def test_survivor_pension_ready_with_all_fields() -> None:
    state = _state(
        attributes={
            "deceased_insurance_type": "labor_insurance",
            "has_dependent_children": True,
            "applicant_age_band": "25_to_55",
        }
    )
    ready = find_ready_item_ids(state, _registry())

    assert "survivor_pension" in ready
    assert "funeral_benefit" in ready


def test_already_resolved_items_are_skipped() -> None:
    """已經定案的項目不會被找出來。"""
    items = (
        CandidateItem(
            item_id="funeral_benefit",
            kind=ItemKind.BENEFIT,
            status=ItemStatus.ELIGIBLE,
        ),
        CandidateItem(item_id="survivor_pension", kind=ItemKind.BENEFIT),
    )
    state = _state(
        attributes={"deceased_insurance_type": "labor_insurance"},
        items=items,
    )
    ready = find_ready_item_ids(state, _registry())

    assert "funeral_benefit" not in ready


def test_stub_marks_ready_items_as_eligible() -> None:
    state = _state(attributes={"deceased_insurance_type": "labor_insurance"})
    result = evaluate_ready_items_stub(state, _registry())

    statuses = {item.item_id: item.status for item in result.items}
    assert statuses["funeral_benefit"] is ItemStatus.ELIGIBLE
    # survivor_pension 還沒湊齊，維持 PENDING。
    assert statuses["survivor_pension"] is ItemStatus.PENDING


def test_stub_sets_resolved_at() -> None:
    state = _state(attributes={"deceased_insurance_type": "labor_insurance"})
    result = evaluate_ready_items_stub(state, _registry())

    funeral = next(i for i in result.items if i.item_id == "funeral_benefit")
    assert funeral.resolved_at is not None


def test_stub_does_nothing_when_no_items_ready() -> None:
    state = _state(attributes={})
    result = evaluate_ready_items_stub(state, _registry())

    assert result is state  # 沒有變，回的是同一個物件


def test_items_with_no_declared_fields_are_flagged_as_undeclared() -> None:
    """登記表沒有宣告任何欄位的項目，屬於資料缺漏。"""
    items = (
        CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
        CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),
    )
    state = _state(items=items)

    undeclared = find_undeclared_item_ids(state, _registry())

    # death_registration 在種子登記表裡沒有任何欄位宣告 used_by 包含它。
    assert "death_registration" in undeclared
    assert "funeral_benefit" not in undeclared


def test_undeclared_items_are_not_counted_as_ready() -> None:
    """沒有宣告欄位不等於「沒有條件所以就緒」。"""
    items = (CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),)
    state = _state(items=items, attributes={"anything": "value"})

    ready = find_ready_item_ids(state, _registry())

    assert "death_registration" not in ready


def test_undeclared_items_become_needs_human_review() -> None:
    """資料缺漏的項目標成需人工協助，不是符合資格。

    把資料缺漏誤判成「你符合資格」比誠實說「需要人看一下」危險 ——
    使用者可能因此白跑一趟。
    """
    items = (
        CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),
        CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
    )
    state = _state(
        items=items,
        attributes={"deceased_insurance_type": "labor_insurance"},
    )

    result = evaluate_ready_items_stub(state, _registry())
    statuses = {i.item_id: i.status for i in result.items}

    assert statuses["death_registration"] is ItemStatus.NEEDS_HUMAN_REVIEW
    assert statuses["funeral_benefit"] is ItemStatus.ELIGIBLE


def test_undeclared_items_alone_still_change_state() -> None:
    """只有資料缺漏的項目時，也要回傳新的狀態（不是原封不動）。"""
    items = (CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),)
    state = _state(items=items)

    result = evaluate_ready_items_stub(state, _registry())

    assert result is not state
    assert result.items[0].status is ItemStatus.NEEDS_HUMAN_REVIEW
