"""驗證佔位推進的行為。

這些測試守住的不是最終的流程規則（那屬於狀態機），而是「前端接上之後看到的東西
是可預期的」，以及佔位資料被明確標示為佔位。
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.orchestration import mock_advance
from app.orchestration.state import (
    ExitReason,
    ItemStatus,
    SessionState,
    WorkflowState,
)
from app.schemas.session import (
    AttributeAnswersInput,
    EventConfirmationInput,
    HelpRequestInput,
    ItemDeclineInput,
    LifeEventTextInput,
    PendingCapability,
    ReferralChoiceInput,
    ReviewConfirmationInput,
)


def _state() -> SessionState:
    now = datetime(2026, 7, 26, 15, 30, tzinfo=UTC)
    return SessionState(
        session_id="s_test",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )


def _confirmed() -> SessionState:
    """走到「已確認事件、已展開項目」的狀態。"""
    after_text = mock_advance.advance(_state(), LifeEventTextInput(text="測試輸入"))
    return mock_advance.advance(after_text, EventConfirmationInput(confirmed=True))


def test_the_notice_declares_the_response_as_mock() -> None:
    notice = mock_advance.implementation_notice()

    assert notice.is_mock is True
    assert notice.placeholder_notice
    assert set(notice.pending) == set(PendingCapability)


def test_free_text_yields_a_fixed_event_code_awaiting_confirmation() -> None:
    """不管輸入什麼都回同一個代號，因為還沒有事件辨識。"""
    advanced = mock_advance.advance(_state(), LifeEventTextInput(text="任何內容"))

    assert advanced.life_event == mock_advance.PLACEHOLDER_LIFE_EVENT
    assert advanced.workflow_state is WorkflowState.UNDERSTAND_EVENT
    assert advanced.items == ()


def test_the_original_text_is_not_stored_anywhere() -> None:
    """ADR-0007：抽取後即丟棄。state 上沒有欄位可以放它。"""
    advanced = mock_advance.advance(
        _state(), LifeEventTextInput(text="我先生上週過世了")
    )

    assert "我先生上週過世了" not in advanced.model_dump_json()


def test_confirming_the_event_reveals_the_placeholder_items() -> None:
    advanced = _confirmed()

    assert advanced.workflow_state is WorkflowState.RESOLVE_ENTITLEMENTS
    assert [item.item_id for item in advanced.items] == [
        "death_registration",
        "funeral_benefit",
        "survivor_pension",
        "health_insurance_change",
    ]
    assert all(item.status is ItemStatus.PENDING for item in advanced.items)


def test_no_item_carries_a_decision_or_evidence_yet() -> None:
    """沒有規則引擎也沒有檢索，所以判定與依據必須是空的。"""
    for item in _confirmed().items:
        assert item.decisive_conditions == ()
        assert item.citations == ()
        assert item.rule_id is None
        assert item.amount_min is None


def test_rejecting_the_event_clears_it_and_counts_the_retry() -> None:
    after_text = mock_advance.advance(_state(), LifeEventTextInput(text="測試"))

    retried = mock_advance.advance(after_text, EventConfirmationInput(confirmed=False))

    assert retried.life_event is None
    assert retried.event_retry_count == 1
    assert retried.exit_reason is None


def test_exceeding_the_retry_limit_offers_human_help() -> None:
    state = _state()

    for _ in range(mock_advance.MAX_EVENT_RETRIES + 1):
        state = mock_advance.advance(state, LifeEventTextInput(text="測試"))
        state = mock_advance.advance(state, EventConfirmationInput(confirmed=False))

    assert state.exit_reason is ExitReason.EVENT_RETRY_LIMIT_REACHED


def test_free_text_is_rejected_once_the_event_is_settled() -> None:
    with pytest.raises(mock_advance.NotAllowedInStateError):
        mock_advance.advance(_confirmed(), LifeEventTextInput(text="又一段文字"))


def test_answers_are_merged_rather_than_replaced() -> None:
    state = mock_advance.advance(
        _confirmed(), AttributeAnswersInput(answers={"first": "a"})
    )

    state = mock_advance.advance(
        state, AttributeAnswersInput(answers={"second": True, "first": "b"})
    )

    assert state.attributes == {"first": "b", "second": True}
    assert state.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS


def test_declining_an_item_marks_only_that_item() -> None:
    state = mock_advance.advance(
        _confirmed(), ItemDeclineInput(item_id="survivor_pension")
    )

    statuses = {item.item_id: item.status for item in state.items}
    assert statuses["survivor_pension"] is ItemStatus.DECLINED_BY_USER
    assert statuses["funeral_benefit"] is ItemStatus.PENDING


def test_declining_an_unknown_item_fails() -> None:
    with pytest.raises(mock_advance.UnknownItemError):
        mock_advance.advance(_confirmed(), ItemDeclineInput(item_id="not_a_real_item"))


def test_referral_choice_is_recorded() -> None:
    state = mock_advance.advance(_confirmed(), ReferralChoiceInput(requested=True))

    assert state.referral_requested is True


def test_a_help_request_ends_the_session_with_a_reason() -> None:
    state = mock_advance.advance(_confirmed(), HelpRequestInput())

    assert state.exit_reason is ExitReason.USER_REQUESTED_HELP


def test_confirming_the_review_reaches_completion() -> None:
    state = mock_advance.advance(_confirmed(), ReviewConfirmationInput(confirmed=True))

    assert state.workflow_state is WorkflowState.COMPLETE


def test_declining_the_review_returns_to_answering() -> None:
    state = mock_advance.advance(_confirmed(), ReviewConfirmationInput(confirmed=False))

    assert state.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS
