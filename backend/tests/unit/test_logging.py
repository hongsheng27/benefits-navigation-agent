"""Verify that the logging pipeline enforces the ADR-0007 field allowlist."""

import json
import logging

import pytest

from app.observability.logging import (
    ALLOWED_FIELDS,
    DisallowedLogFieldError,
    configure_logging,
    log_event,
)
from app.orchestration.data_contracts import StructuredReason


@pytest.fixture(autouse=True)
def _json_logging() -> None:
    configure_logging()


def _emitted(caplog: pytest.LogCaptureFixture) -> dict:
    """Format the single captured record the way a handler would."""
    handler = logging.getLogger().handlers[0]
    return json.loads(handler.formatter.format(caplog.records[0]))


def test_allowed_fields_are_emitted_as_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        log_event(
            "state_transitioned",
            session_id="a3f2",
            state="UNDERSTAND_EVENT",
            next_state="RESOLVE_ENTITLEMENTS",
            duration_ms=42,
        )

    payload = _emitted(caplog)

    assert payload["event"] == "state_transitioned"
    assert payload["level"] == "info"
    assert payload["session_id"] == "a3f2"
    assert payload["next_state"] == "RESOLVE_ENTITLEMENTS"
    assert payload["duration_ms"] == 42


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(DisallowedLogFieldError):
        log_event("message_received", session_id="a3f2", unknown_field="x")


def test_user_text_field_is_rejected() -> None:
    """The failure mode this module exists to prevent."""
    with pytest.raises(DisallowedLogFieldError) as excinfo:
        log_event("message_received", text="我先生陳大明上週過世了")

    assert "text" in str(excinfo.value)


def test_rejection_names_every_offending_field() -> None:
    with pytest.raises(DisallowedLogFieldError) as excinfo:
        log_event("message_received", prompt="...", answer="...")

    message = str(excinfo.value)
    assert "answer" in message
    assert "prompt" in message


def test_exception_records_type_and_stack_without_the_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exception messages can quote user input, so only the type is kept."""
    secret = "我先生陳大明上週過世了"

    with caplog.at_level(logging.ERROR):
        try:
            raise ValueError(secret)
        except ValueError:
            log_event("extraction_failed", level=logging.ERROR, exc_info=True)

    payload = _emitted(caplog)

    assert payload["error_type"] == "ValueError"
    assert payload["stack"]
    assert secret not in json.dumps(payload, ensure_ascii=False)


def test_free_text_field_names_are_absent_from_the_allowlist() -> None:
    forbidden = {"text", "message", "prompt", "response", "question", "answer"}

    assert forbidden.isdisjoint(ALLOWED_FIELDS)


def test_an_actual_eligibility_value_cannot_be_logged() -> None:
    """`StructuredReason.actual` is the user's own situation.

    The shared data contract allows it to travel back to the user who asked, but
    it must never reach a log, trace, metric, exception message, or persisted
    audit event. Every plausible field name for it is rejected, so a caller
    cannot smuggle it in under a different label.
    """
    reason = StructuredReason(
        condition_id="cond_1",
        field_id="deceased_insured_years_band",
        operator="at_least",
        expected="fifteen_years_or_more",
        actual="five_to_fifteen_years",
        label="〈condition label〉",
        source_reference="doc_1#section_2",
    )

    for field_name in ("actual", "actual_value", "expected", "reason", "reasons"):
        with pytest.raises(DisallowedLogFieldError):
            log_event("eligibility_evaluated", **{field_name: reason.actual})


def test_no_allowlisted_field_is_named_after_an_eligibility_value() -> None:
    """Guards the allowlist itself, not just today's call sites."""
    forbidden = {"actual", "actual_value", "expected", "expected_value", "value"}

    assert forbidden.isdisjoint(ALLOWED_FIELDS)
