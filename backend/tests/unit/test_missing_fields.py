"""驗證缺漏欄位計算與主題分組。"""

from datetime import UTC, datetime, timedelta

from app.orchestration.field_registry import FieldRegistry
from app.orchestration.missing_fields import compute_question_groups
from app.orchestration.state import (
    CandidateItem,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)
from app.schemas.session import AttributeValueKind


def _registry() -> FieldRegistry:
    """用種子資料建一個 registry。"""
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
        workflow_state=WorkflowState.COLLECT_MISSING_FIELDS,
        life_event="spouse_death",
        attributes=attributes or {},
        items=items if items is not None else default_items,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )


def test_all_fields_missing_produces_four_groups() -> None:
    """種子資料分屬四個主題（含所在地），沒答過任何題，應該產出四組。"""
    groups = compute_question_groups(_state(), _registry())

    assert len(groups) == 4
    assert groups[0].group_index == 1
    assert groups[0].group_total == 4


def test_answering_a_field_removes_it_from_the_output() -> None:
    """回答了 deceased_insurance_type 之後，那一組應該消失。"""
    state = _state(attributes={"deceased_insurance_type": "labor_insurance"})
    groups = compute_question_groups(state, _registry())

    all_field_ids = [q.field_id for g in groups for q in g.questions]
    assert "deceased_insurance_type" not in all_field_ids


def test_answering_all_fields_returns_empty() -> None:
    """所有欄位都答完了，不需要再問。"""
    state = _state(
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
            "has_dependent_children": True,
            "applicant_age_band": "25_to_55",
        }
    )
    groups = compute_question_groups(state, _registry())

    assert groups == ()


def test_declined_items_are_excluded() -> None:
    """被 decline 的項目不計入，所以它需要的欄位也不會問。"""
    items = (
        CandidateItem(
            item_id="funeral_benefit",
            kind=ItemKind.BENEFIT,
            status=ItemStatus.DECLINED_BY_USER,
        ),
        CandidateItem(
            item_id="survivor_pension",
            kind=ItemKind.BENEFIT,
            status=ItemStatus.DECLINED_BY_USER,
        ),
    )
    groups = compute_question_groups(_state(items=items), _registry())

    # 兩個項目都被 decline 了，沒有任何 active 項目。
    assert groups == ()


def test_only_fields_for_active_items_are_included() -> None:
    """只有 funeral_benefit 在等，survivor_pension 已被 decline。

    deceased_insurance_type 被兩者都需要，但只有 funeral_benefit 是 active，
    所以它仍然要問。has_dependent_children 只被 survivor_pension 需要，
    survivor_pension 已 decline，所以不問。
    """
    items = (
        CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
        CandidateItem(
            item_id="survivor_pension",
            kind=ItemKind.BENEFIT,
            status=ItemStatus.DECLINED_BY_USER,
        ),
    )
    groups = compute_question_groups(_state(items=items), _registry())

    all_field_ids = {q.field_id for g in groups for q in g.questions}
    assert "applicant_jurisdiction" in all_field_ids
    assert "deceased_insurance_type" in all_field_ids
    assert "has_dependent_children" not in all_field_ids
    assert "applicant_age_band" not in all_field_ids


def test_questions_carry_option_ids_and_value_kind() -> None:
    groups = compute_question_groups(_state(), _registry())

    insurance_q = None
    for g in groups:
        for q in g.questions:
            if q.field_id == "deceased_insurance_type":
                insurance_q = q
                break

    assert insurance_q is not None
    assert insurance_q.value_kind is AttributeValueKind.CODE
    assert "labor_insurance" in insurance_q.option_ids
    assert insurance_q.required is True


def test_unlocks_item_ids_lists_active_items_that_need_the_field() -> None:
    """unlocks_item_ids 只列 active 的項目。"""
    groups = compute_question_groups(_state(), _registry())

    insurance_q = None
    for g in groups:
        for q in g.questions:
            if q.field_id == "deceased_insurance_type":
                insurance_q = q

    assert insurance_q is not None
    # 種子資料裡 used_by 是 funeral_benefit 和 survivor_pension，兩者都 active。
    assert set(insurance_q.unlocks_item_ids) == {"funeral_benefit", "survivor_pension"}


def test_group_total_reflects_only_groups_with_missing_fields() -> None:
    """group_total 是「有缺漏欄位的主題數」，不是全部主題數。"""
    state = _state(
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
        }
    )
    groups = compute_question_groups(state, _registry())

    # 答了兩個主題的欄位，只剩兩組。
    assert all(g.group_total == 2 for g in groups)
    assert groups[0].group_index == 1
    assert groups[1].group_index == 2


def test_topic_order_follows_registry_declaration() -> None:
    """主題順序跟登記表裡的宣告順序一致。"""
    groups = compute_question_groups(_state(), _registry())
    topic_ids = [g.topic_id for g in groups]

    assert topic_ids == [
        "location",
        "deceased_insurance",
        "family_situation",
        "applicant_situation",
    ]
