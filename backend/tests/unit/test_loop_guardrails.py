"""驗證迴圈的兩道護欄：迭代上限與必須有進展。

這些測試直接呼叫 state_machine.advance，不經過 HTTP 層。
"""

from datetime import UTC, datetime, timedelta

from app.orchestration.state import (
    CandidateItem,
    ExitReason,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)
from app.orchestration.state_machine import (
    MAX_LOOP_ITERATIONS,
    advance,
)
from app.schemas.session import AttributeAnswersInput


def _state_at_collect(
    *, loop_iterations: int = 0, attributes: dict | None = None
) -> SessionState:
    """建立一個「已經走到追問欄位、有四個待確認項目」的狀態。"""
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    return SessionState(
        session_id="s_test",
        workflow_state=WorkflowState.COLLECT_MISSING_FIELDS,
        life_event="spouse_death",
        attributes=attributes or {},
        items=(
            CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),
            CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
            CandidateItem(item_id="survivor_pension", kind=ItemKind.BENEFIT),
            CandidateItem(
                item_id="health_insurance_change", kind=ItemKind.ADMINISTRATIVE
            ),
        ),
        loop_iterations=loop_iterations,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )


def test_loop_exits_when_iteration_limit_reached() -> None:
    """到了 MAX_LOOP_ITERATIONS 圈，且仍有未定案的項目，設 exit_reason。"""
    state = _state_at_collect(loop_iterations=MAX_LOOP_ITERATIONS - 1)

    # 送一組答案，迭代計數會加一到上限。
    result = advance(state, AttributeAnswersInput(answers={"some_field": "value"}))

    assert result.exit_reason is ExitReason.LOOP_LIMIT_REACHED
    assert result.loop_iterations == MAX_LOOP_ITERATIONS


def test_loop_does_not_exit_before_the_limit() -> None:
    """還沒到上限時，不設 exit_reason。"""
    state = _state_at_collect(loop_iterations=MAX_LOOP_ITERATIONS - 2)

    result = advance(state, AttributeAnswersInput(answers={"new_field": "x"}))

    assert result.exit_reason is None
    # 回到 collect_missing_fields 等使用者。
    assert result.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS


def test_loop_exits_when_no_progress_is_made() -> None:
    """繞了一圈但「沒有任何項目狀態改變」也「沒有收到新屬性」，設 exit_reason。

    模擬方式：已經有 attributes，這次送同樣的 key（覆蓋而非新增），而 auto-step
    不會改變項目狀態（因為目前是空操作）。
    """
    # 第一圈已經走過（loop_iterations=1 代表已繞一圈），有一個屬性。
    state = _state_at_collect(
        loop_iterations=1, attributes={"existing_field": "old_value"}
    )

    # 送的是同一個 key 的新值 —— key 數量沒有增加。
    result = advance(
        state, AttributeAnswersInput(answers={"existing_field": "new_value"})
    )

    assert result.exit_reason is ExitReason.NO_PROGRESS


def test_new_attribute_counts_as_progress() -> None:
    """送了一個之前沒有的 key，屬於「有進展」。"""
    state = _state_at_collect(loop_iterations=1, attributes={"existing_field": "value"})

    result = advance(state, AttributeAnswersInput(answers={"brand_new_field": "x"}))

    assert result.exit_reason is None
    assert result.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS


def test_first_iteration_never_triggers_no_progress() -> None:
    """第一圈不檢查進展（因為沒有前一圈可以比較）。"""
    state = _state_at_collect(loop_iterations=0, attributes={"a": "1"})

    # 送同一個 key。loop_iterations 從 0 變成 1，這是第一圈，不觸發。
    result = advance(state, AttributeAnswersInput(answers={"a": "updated"}))

    assert result.exit_reason is None


def test_all_items_settled_skips_loop_even_at_low_iterations() -> None:
    """如果所有項目都已定案，不繞回追問。"""
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    state = SessionState(
        session_id="s_test",
        workflow_state=WorkflowState.COLLECT_MISSING_FIELDS,
        life_event="spouse_death",
        attributes={"a": "1"},
        items=(
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
                status=ItemStatus.DECLINED_BY_USER,
            ),
            CandidateItem(
                item_id="health_insurance_change",
                kind=ItemKind.ADMINISTRATIVE,
                status=ItemStatus.INELIGIBLE,
            ),
        ),
        loop_iterations=1,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )

    result = advance(state, AttributeAnswersInput(answers={"new": "x"}))

    # 全部定案，不繞回。自動推進到 COMPLETE（跳過 EXPLAIN_RESULT 和 CONFIRM
    # 因為守門條件：explain 需要有非 pending 項目，confirm 需要有人工協助項目）。
    assert result.exit_reason is None
    assert result.workflow_state is WorkflowState.COMPLETE
