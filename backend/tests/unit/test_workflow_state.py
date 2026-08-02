"""驗證 workflow state 的形狀，以及它們應該承載的約束。

這些測試守住三件容易不小心破壞的事：workflow state 的集合、「狀態欄位不得存放
使用者文字」這條隱私規則，以及讓狀態轉換只能發生在 state machine 裡的不可變性。
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.orchestration.state import (
    RULE_ENGINE_STATUSES,
    AmountPeriod,
    CandidateItem,
    Citation,
    DecisiveCondition,
    ExitReason,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)

# 出現以下字串片段的欄位名稱，代表那裡可能被用來存放使用者打的字。
# ADR-0007 規定自由文字在抽取後即丟棄，所以狀態欄位都不得存放它。
_FREE_TEXT_MARKERS = (
    "text",
    "raw",
    "input",
    "message",
    "description",
    "prose",
    "note",
    "comment",
    "query",
    "prompt",
)

# 依 ADR-0005，直接識別資料留在使用者裝置上。
_IDENTIFIER_MARKERS = (
    "name",
    "national_id",
    "id_number",
    "address",
    "phone",
    "email",
    "birth",
)


def _state() -> SessionState:
    now = datetime(2026, 7, 26, 15, 30, tzinfo=UTC)
    return SessionState(
        session_id="s_test",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )


def test_workflow_states_match_the_documented_flow() -> None:
    assert [state.value for state in WorkflowState] == [
        "understand_event",
        "resolve_entitlements",
        "collect_missing_fields",
        "retrieve_rules",
        "evaluate_eligibility",
        "explain_result",
        "confirm",
        "complete",
    ]


def test_rule_engine_may_only_return_the_four_decision_statuses() -> None:
    assert RULE_ENGINE_STATUSES == {
        ItemStatus.ELIGIBLE,
        ItemStatus.INELIGIBLE,
        ItemStatus.NEEDS_INFORMATION,
        ItemStatus.NEEDS_HUMAN_REVIEW,
    }
    assert ItemStatus.PENDING not in RULE_ENGINE_STATUSES
    assert ItemStatus.DECLINED_BY_USER not in RULE_ENGINE_STATUSES


@pytest.mark.parametrize(
    "model",
    [SessionState, CandidateItem, DecisiveCondition, Citation],
)
def test_no_state_field_can_hold_free_text_or_identifiers(model: type) -> None:
    """有人加入會誘使人塞入文字或身分資料的欄位時，要立刻失敗。

    有兩種文字在這裡是正當的，因此以「明確列出例外」處理，而不是放寬上面的
    字串片段清單：

    - `Citation.excerpt` 與 `Citation.publisher_name` 描述的是官方文件與發布機關。
      機關不是個人。
    - `CandidateItem.explanation` 存的是從「已定案結果」衍生出來的模型輸出。它不會
      命中任何片段，但它確實是文字，所以任何對它的改動都應該回頭對照 ADR-0007 的
      保存規則。
    - `CandidateItem.display_name` 與 `summary` 來自 curated benefit catalog，
      讓 UUID program ID 仍能顯示；它們不是使用者輸入，也不能由 LLM 寫入。
    """
    exempt = {
        ("Citation", "excerpt"),
        ("Citation", "publisher_name"),
        ("CandidateItem", "display_name"),
        ("CandidateItem", "summary"),
    }

    for field_name in model.model_fields:
        if (model.__name__, field_name) in exempt:
            continue
        for marker in _FREE_TEXT_MARKERS + _IDENTIFIER_MARKERS:
            assert marker not in field_name, (
                f"{model.__name__}.{field_name} 看起來可能存放使用者文字或識別資料。"
                "新增之前請先確認 ADR-0005 與 ADR-0007。"
            )


def test_state_is_frozen_so_transitions_must_produce_a_new_state() -> None:
    state = _state()

    with pytest.raises(ValidationError):
        state.workflow_state = WorkflowState.COMPLETE

    advanced = state.model_copy(
        update={"workflow_state": WorkflowState.RESOLVE_ENTITLEMENTS}
    )

    assert state.workflow_state is WorkflowState.UNDERSTAND_EVENT
    assert advanced.workflow_state is WorkflowState.RESOLVE_ENTITLEMENTS


def test_unknown_fields_are_rejected() -> None:
    now = datetime(2026, 7, 26, tzinfo=UTC)

    with pytest.raises(ValidationError):
        SessionState(
            session_id="s_test",
            created_at=now,
            updated_at=now,
            expires_at=now,
            user_text="我先生上週過世了",
        )


def test_a_new_session_starts_empty_and_unresolved() -> None:
    state = _state()

    assert state.workflow_state is WorkflowState.UNDERSTAND_EVENT
    assert state.life_event is None
    assert state.attributes == {}
    assert state.items == ()
    assert state.loop_iterations == 0
    assert state.event_retry_count == 0
    assert state.exit_reason is None
    assert state.referral_requested is False
    assert state.is_processing is False


def test_boolean_answers_do_not_collapse_into_integers() -> None:
    state = _state().model_copy(
        update={"attributes": {"has_dependent_children": True, "child_count": 2}}
    )

    assert state.attributes["has_dependent_children"] is True
    assert state.attributes["child_count"] == 2


def test_items_carry_independent_statuses() -> None:
    state = _state().model_copy(
        update={
            "items": (
                CandidateItem(
                    item_id="death_registration",
                    kind=ItemKind.ADMINISTRATIVE,
                    status=ItemStatus.ELIGIBLE,
                ),
                CandidateItem(
                    item_id="funeral_benefit",
                    kind=ItemKind.BENEFIT,
                    status=ItemStatus.ELIGIBLE,
                ),
                CandidateItem(
                    item_id="survivor_pension",
                    kind=ItemKind.BENEFIT,
                    status=ItemStatus.NEEDS_INFORMATION,
                    missing_field_ids=("deceased_insured_years_band",),
                ),
            )
        }
    )

    statuses = {item.item_id: item.status for item in state.items}

    assert statuses["death_registration"] is ItemStatus.ELIGIBLE
    assert statuses["funeral_benefit"] is ItemStatus.ELIGIBLE
    assert statuses["survivor_pension"] is ItemStatus.NEEDS_INFORMATION


def test_an_ineligible_item_can_name_its_decisive_condition() -> None:
    item = CandidateItem(
        item_id="survivor_pension",
        kind=ItemKind.BENEFIT,
        status=ItemStatus.INELIGIBLE,
        decisive_conditions=(
            DecisiveCondition(
                field_id="deceased_insured_years_band",
                expected="fifteen_years_or_more",
                actual="five_to_fifteen_years",
            ),
        ),
        citations=(
            Citation(
                document_id="doc_1",
                title="〈條例名稱〉",
                publisher_name="〈機關〉",
                url="https://example.gov.tw/rule",
            ),
        ),
        rule_id="survivor_pension_insured_years",
        rule_version="v0.1",
    )

    assert item.status in RULE_ENGINE_STATUSES
    assert item.decisive_conditions[0].field_id == "deceased_insured_years_band"


def test_session_level_exits_are_distinct_from_item_level_review() -> None:
    """找不到官方依據只標記單一項目，不會讓整次諮詢停止。"""
    assert "missing_official_evidence" not in {reason.value for reason in ExitReason}
    assert ItemStatus.NEEDS_HUMAN_REVIEW in RULE_ENGINE_STATUSES


def test_amount_is_absent_until_a_rule_supplies_one() -> None:
    item = CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE)

    assert item.amount_min is None
    assert item.amount_max is None
    assert item.amount_period is None
    assert item.amount_currency is None


def test_a_fixed_amount_repeats_the_same_bound() -> None:
    item = CandidateItem(
        item_id="funeral_benefit",
        kind=ItemKind.BENEFIT,
        status=ItemStatus.ELIGIBLE,
        amount_min=10000,
        amount_max=10000,
        amount_period=AmountPeriod.ONE_TIME,
        amount_currency="TWD",
    )

    assert item.amount_min == item.amount_max == 10000
    assert item.amount_period is AmountPeriod.ONE_TIME


def test_a_ranged_monthly_amount_keeps_both_bounds() -> None:
    """資料層的 min_amount 與 max_amount 是兩個欄位，範圍不應被壓成單一數字。"""
    item = CandidateItem(
        item_id="survivor_pension",
        kind=ItemKind.BENEFIT,
        status=ItemStatus.ELIGIBLE,
        amount_min=3000,
        amount_max=8000,
        amount_period=AmountPeriod.MONTHLY,
        amount_currency="TWD",
    )

    assert (item.amount_min, item.amount_max) == (3000, 8000)
    assert item.amount_period is AmountPeriod.MONTHLY


def test_no_display_ready_amount_text_is_stored() -> None:
    """金額文案屬於前端。後端不得出現 amount_label 這類欄位。"""
    assert "amount_label" not in CandidateItem.model_fields
    assert "amount_text" not in CandidateItem.model_fields
