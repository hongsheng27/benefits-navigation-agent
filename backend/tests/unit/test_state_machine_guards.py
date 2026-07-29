"""驗證狀態機的兩道守門：欄位 allowlist 與「已結束就不再接受輸入」。

這些測試直接呼叫 `state_machine.advance`，不經過 HTTP 層。

fixture 全部使用虛構資料。送出的欄位代號分成兩類：登記表上真的有的
（deceased_insurance_type 等）與明顯不存在的（totally_unknown_field）。
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.orchestration.protocols import LocalSourceRefreshService
from app.orchestration.state import (
    CandidateItem,
    ExitReason,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)
from app.orchestration.state_machine import (
    InvalidTransitionError,
    UnknownFieldError,
    advance,
)
from app.schemas.session import (
    AttributeAnswersInput,
    HelpRequestInput,
    ItemDeclineInput,
    ReviewConfirmationInput,
)

_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def _state(
    *,
    workflow_state: WorkflowState = WorkflowState.COLLECT_MISSING_FIELDS,
    attributes: dict | None = None,
    exit_reason: ExitReason | None = None,
    loop_iterations: int = 0,
) -> SessionState:
    return SessionState(
        session_id="s_test",
        workflow_state=workflow_state,
        life_event="spouse_death",
        attributes=attributes or {},
        items=(CandidateItem(item_id="survivor_pension", kind=ItemKind.BENEFIT),),
        loop_iterations=loop_iterations,
        exit_reason=exit_reason,
        created_at=_NOW,
        updated_at=_NOW,
        expires_at=_NOW + timedelta(hours=2),
    )


def test_an_injected_refresh_service_requires_an_explicit_coverage_scope() -> None:
    """避免 service 已注入，卻因預設空 scope 靜默不查詢也不排工作。"""
    with pytest.raises(ValueError, match="coverage_scope is required"):
        advance(
            _state(),
            HelpRequestInput(),
            source_refresh_service=LocalSourceRefreshService(),
        )


# ---------------------------------------------------------------------------
# 欄位 allowlist（Req 9、Req 16.2、Req 16.5）
# ---------------------------------------------------------------------------


def test_unknown_field_id_is_rejected() -> None:
    """不在登記表上的欄位代號會讓整筆請求被拒。

    沒有這道檢查，任何一段自由文字都能藉著一個編出來的代號寫進 state。
    """
    state = _state()

    with pytest.raises(UnknownFieldError) as caught:
        advance(
            state,
            AttributeAnswersInput(
                answers={"totally_unknown_field": "使用者打的一段話"}
            ),
        )

    assert caught.value.field_ids == ("totally_unknown_field",)


def test_known_field_ids_are_accepted_and_recorded() -> None:
    """全部都在登記表上就接受，並寫進 attributes。"""
    state = _state()

    result = advance(
        state,
        AttributeAnswersInput(
            answers={
                "deceased_insurance_type": "labor_insurance",
                "has_dependent_children": True,
            }
        ),
    )

    assert result.attributes["deceased_insurance_type"] == "labor_insurance"
    assert result.attributes["has_dependent_children"] is True


def test_one_unknown_field_rejects_the_whole_request() -> None:
    """混合情況也是整筆拒絕，已知的那個欄位不會被部分接受。

    部分接受會讓使用者以為答案都收到了；靜默丟棄會讓前端送錯代號的 bug 看起來
    像正常運作。
    """
    state = _state()

    with pytest.raises(UnknownFieldError):
        advance(
            state,
            AttributeAnswersInput(
                answers={
                    "deceased_insurance_type": "labor_insurance",
                    "totally_unknown_field": "一段使用者打的話",
                }
            ),
        )

    assert state.attributes == {}


def test_the_error_carries_field_ids_not_values() -> None:
    """錯誤裡只有欄位代號，不含使用者填的值（Req 16.5）。"""
    secret = "這段文字不應該離開後端"
    state = _state()

    with pytest.raises(UnknownFieldError) as caught:
        advance(
            state,
            AttributeAnswersInput(
                answers={"another_unknown": secret, "totally_unknown_field": secret}
            ),
        )

    # 排序過，所以同一組違規欄位永遠得到同一個順序。
    assert caught.value.field_ids == ("another_unknown", "totally_unknown_field")
    assert secret not in str(caught.value)


# ---------------------------------------------------------------------------
# 已結束的流程不再接受輸入（Req 1.5、Req 5.3）
# ---------------------------------------------------------------------------


def test_a_finished_session_rejects_answers_without_counting_a_loop() -> None:
    """exit_reason 已設定時送答案會被拒，且迭代計數不動。

    沒有這道守門，`loop_iterations` 會在流程結束後繼續增加，design.md 的 Property 4
    （迭代有界）就不成立了。
    """
    state = _state(
        exit_reason=ExitReason.LOOP_LIMIT_REACHED,
        loop_iterations=6,
    )

    with pytest.raises(InvalidTransitionError):
        advance(
            state,
            AttributeAnswersInput(answers={"has_dependent_children": True}),
        )

    assert state.loop_iterations == 6


def test_a_finished_session_rejects_a_help_request() -> None:
    """已經結束的 session 不能再送 help_request 覆寫 exit_reason。

    這是這道守門必須排在 help_request 分支**之前**的原因：否則護欄給出的
    LOOP_LIMIT_REACHED 會被改寫成 USER_REQUESTED_HELP，出口的原因就變成假的。
    """
    state = _state(exit_reason=ExitReason.LOOP_LIMIT_REACHED)

    with pytest.raises(InvalidTransitionError):
        advance(state, HelpRequestInput())

    assert state.exit_reason is ExitReason.LOOP_LIMIT_REACHED


def test_a_finished_session_rejects_item_decline() -> None:
    """其他種類的輸入一樣被拒，不是只擋答案。"""
    state = _state(exit_reason=ExitReason.NO_PROGRESS)

    with pytest.raises(InvalidTransitionError):
        advance(state, ItemDeclineInput(item_id="survivor_pension"))


def test_a_complete_session_rejects_every_input() -> None:
    """走到 COMPLETE 之後不接受任何輸入（Req 2.3）。"""
    state = _state(workflow_state=WorkflowState.COMPLETE)

    for user_input in (
        HelpRequestInput(),
        AttributeAnswersInput(answers={"has_dependent_children": True}),
        ReviewConfirmationInput(confirmed=True),
    ):
        with pytest.raises(InvalidTransitionError):
            advance(state, user_input)


def test_a_running_session_still_accepts_a_help_request() -> None:
    """守門只針對已結束的流程，正常進行中的 session 不受影響。"""
    state = _state()

    result = advance(state, HelpRequestInput())

    assert result.exit_reason is ExitReason.USER_REQUESTED_HELP
    assert result.items[0].status is ItemStatus.PENDING
