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
    """建立一個「已經走到追問欄位、有待確認項目」的狀態。

    只放 survivor_pension，因為它需要三個欄位（deceased_insurance_type、
    has_dependent_children、applicant_age_band）才會就緒。這樣測試可以精確控制
    「只答一個欄位不會讓它就緒」的情況。

    這些測試送出的答案都必須用**登記表上真的存在**的欄位代號，否則會先被欄位
    allowlist 擋下來（Req 9），根本走不到護欄。

    `program_status` 明確設成 `"verified"`：`CandidateItem` 的預設值是 `"candidate"`，
    而候選資料一進判定就被安全閘門定案為需人工協助（提案第 8 節）。那樣項目永遠不會
    停在待確認，迴圈根本不會繞第二圈，這裡的兩道護欄就都測不到。已審查的方案才會
    因為「欄位還沒湊齊」而留在待確認，也才是護欄真正要處理的情況。
    """
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    return SessionState(
        session_id="s_test",
        workflow_state=WorkflowState.COLLECT_MISSING_FIELDS,
        life_event="spouse_death",
        attributes=attributes or {},
        items=(
            CandidateItem(
                item_id="survivor_pension",
                kind=ItemKind.BENEFIT,
                program_status="verified",
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
    result = advance(
        state, AttributeAnswersInput(answers={"has_dependent_children": True})
    )

    assert result.exit_reason is ExitReason.LOOP_LIMIT_REACHED
    assert result.loop_iterations == MAX_LOOP_ITERATIONS


def test_loop_limit_downgrades_unsettled_items() -> None:
    """上限觸發時，未定案的項目必須降級為需人工協助。

    只設 exit_reason 而讓項目停在 PENDING，使用者會拿到一份「永遠不會有答案」的
    清單（違反 Req 17.4：流程結束後所有項目都要有非 PENDING 的狀態）。
    已定案的項目與使用者放棄的項目不受影響。

    survivor_pension 標成 `"verified"`，這樣它是因為「欄位沒湊齊」而留在待確認，
    降級才是護欄做的事 —— 用預設的 `"candidate"` 會被安全閘門先定案，測到的就變成
    閘門而不是護欄。
    """
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    state = SessionState(
        session_id="s_test",
        workflow_state=WorkflowState.COLLECT_MISSING_FIELDS,
        life_event="spouse_death",
        items=(
            CandidateItem(
                item_id="survivor_pension",
                kind=ItemKind.BENEFIT,
                program_status="verified",
            ),
            CandidateItem(
                item_id="funeral_benefit",
                kind=ItemKind.BENEFIT,
                status=ItemStatus.NEEDS_INFORMATION,
            ),
            CandidateItem(
                item_id="death_registration",
                kind=ItemKind.ADMINISTRATIVE,
                status=ItemStatus.ELIGIBLE,
            ),
            CandidateItem(
                item_id="health_insurance_change",
                kind=ItemKind.ADMINISTRATIVE,
                status=ItemStatus.DECLINED_BY_USER,
            ),
        ),
        loop_iterations=MAX_LOOP_ITERATIONS - 1,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )

    result = advance(
        state, AttributeAnswersInput(answers={"has_dependent_children": True})
    )

    assert result.exit_reason is ExitReason.LOOP_LIMIT_REACHED
    by_id = {item.item_id: item.status for item in result.items}
    assert by_id["survivor_pension"] is ItemStatus.NEEDS_HUMAN_REVIEW
    assert by_id["funeral_benefit"] is ItemStatus.NEEDS_HUMAN_REVIEW
    assert by_id["death_registration"] is ItemStatus.ELIGIBLE
    assert by_id["health_insurance_change"] is ItemStatus.DECLINED_BY_USER


def test_loop_does_not_exit_before_the_limit() -> None:
    """還沒到上限時，不設 exit_reason。"""
    state = _state_at_collect(loop_iterations=MAX_LOOP_ITERATIONS - 2)

    result = advance(
        state, AttributeAnswersInput(answers={"has_dependent_children": True})
    )

    assert result.exit_reason is None
    # 回到 collect_missing_fields 等使用者。
    assert result.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS


def test_loop_exits_when_no_progress_is_made() -> None:
    """繞了一圈但「沒有任何項目狀態改變」也「沒有收到新屬性」，設 exit_reason。

    模擬方式：項目需要 deceased_insurance_type（在登記表上），使用者已經答過了，
    但還需要其他欄位（survivor_pension 還需要 has_dependent_children 和
    applicant_age_band）。這次送的是同一個 key 的新值 —— key 數量沒增加，
    而 stub 判斷 survivor_pension 還沒湊齊所以不會改狀態。
    """
    state = _state_at_collect(
        loop_iterations=1,
        attributes={"deceased_insurance_type": "labor_insurance"},
    )

    # 送同一個 key 的新值 —— key 數量沒有增加。
    result = advance(
        state,
        AttributeAnswersInput(answers={"deceased_insurance_type": "national_pension"}),
    )

    assert result.exit_reason is ExitReason.NO_PROGRESS


def test_new_attribute_counts_as_progress() -> None:
    """送了一個之前沒有的 key，屬於「有進展」。"""
    state = _state_at_collect(
        loop_iterations=1,
        attributes={"deceased_insurance_type": "labor_insurance"},
    )

    result = advance(
        state, AttributeAnswersInput(answers={"applicant_age_band": "25_to_55"})
    )

    assert result.exit_reason is None
    assert result.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS


def test_first_iteration_never_triggers_no_progress() -> None:
    """第一圈不檢查進展（因為沒有前一圈可以比較）。"""
    state = _state_at_collect(
        loop_iterations=0,
        attributes={"deceased_insurance_type": "labor_insurance"},
    )

    # 送同一個 key。loop_iterations 從 0 變成 1，這是第一圈，不觸發。
    result = advance(
        state,
        AttributeAnswersInput(answers={"deceased_insurance_type": "national_pension"}),
    )

    assert result.exit_reason is None


def test_all_items_settled_skips_loop_even_at_low_iterations() -> None:
    """如果所有項目都已定案，不繞回追問。"""
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    state = SessionState(
        session_id="s_test",
        workflow_state=WorkflowState.COLLECT_MISSING_FIELDS,
        life_event="spouse_death",
        attributes={"deceased_insurance_type": "labor_insurance"},
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

    result = advance(
        state, AttributeAnswersInput(answers={"has_dependent_children": False})
    )

    # 全部定案，不繞回。自動推進到 COMPLETE（跳過 EXPLAIN_RESULT 和 CONFIRM
    # 因為守門條件：explain 需要有非 pending 項目，confirm 需要有人工協助項目）。
    assert result.exit_reason is None
    assert result.workflow_state is WorkflowState.COMPLETE
