"""Unit tests for fail-closed observability pipeline.

Tests verify:
- sanitize → serialize → emit flow
- Sanitization failure → original payload never serialized or emitted
- Only sanitization_failed indicator emitted on failure
- Serializer/emitter call counts
- Exception emission safety
- Audit event pre-filtering

Requirements: 9.3–9.8, 9.12, 9.13, 13.8.
"""

from __future__ import annotations

import json
from typing import Any

from app.observability.pipeline import (
    _SANITIZATION_FAILED_INDICATOR,
    _SERIALIZATION_FAILED_INDICATOR,
    ObservabilityPipeline,
)


class TestPipelineHappyPath:
    """Normal flow: sanitize → serialize → emit."""

    def test_safe_payload_emitted(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        pipeline.emit_event({"event": "state_transitioned", "session_id": "abc"})

        assert len(emitted) == 1
        parsed = json.loads(emitted[0])
        assert parsed["event"] == "state_transitioned"
        assert parsed["session_id"] == "abc"

    def test_counters_increment_on_success(self) -> None:
        pipeline = ObservabilityPipeline(emitter=lambda _: None)

        pipeline.emit_event({"event": "test"})

        assert pipeline.sanitize_count == 1
        assert pipeline.serialize_count == 1
        assert pipeline.emit_count == 1
        assert pipeline.sanitization_failures == 0

    def test_denylisted_keys_removed_before_emission(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        pipeline.emit_event(
            {
                "event": "test",
                "session_id": "abc",
                "actual": "sensitive_user_value",
                "text": "raw user text",
            }
        )

        parsed = json.loads(emitted[0])
        assert "actual" not in parsed
        assert "text" not in parsed
        assert parsed["session_id"] == "abc"


class TestPipelineFailClosed:
    """Sanitization failure → fail-closed: no serialize, no emit of original."""

    def test_unsupported_type_triggers_fail_closed(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        # Sets are unsupported → SanitizationError
        pipeline.emit_event({"event": "test", "data": {1, 2, 3}})

        # Only the sanitization_failed indicator is emitted
        assert len(emitted) == 1
        assert emitted[0] == _SANITIZATION_FAILED_INDICATOR
        assert pipeline.sanitization_failures == 1
        assert pipeline.serialize_count == 0  # Never serialized the original

    def test_original_payload_never_in_output_on_failure(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        secret = "超級敏感的使用者資料"
        pipeline.emit_event({"event": "test", "data": {1, 2}, "secret": secret})

        # Verify secret never reaches output
        for output in emitted:
            assert secret not in output

    def test_serializer_not_called_on_sanitization_failure(self) -> None:
        serialize_calls: list[Any] = []

        def tracking_serializer(payload: dict[str, Any]) -> str:
            serialize_calls.append(payload)
            return json.dumps(payload)

        pipeline = ObservabilityPipeline(
            serializer=tracking_serializer,
            emitter=lambda _: None,
        )

        pipeline.emit_event({"data": {1, 2, 3}})  # Will fail sanitization

        assert len(serialize_calls) == 0
        assert pipeline.serialize_count == 0

    def test_serialization_failure_emits_safe_indicator(self) -> None:
        emitted: list[str] = []

        def bad_serializer(payload: dict[str, Any]) -> str:
            raise TypeError("cannot serialize")

        pipeline = ObservabilityPipeline(
            serializer=bad_serializer,
            emitter=emitted.append,
        )

        pipeline.emit_event({"event": "test"})

        assert len(emitted) == 1
        assert emitted[0] == _SERIALIZATION_FAILED_INDICATOR


class TestPipelineExceptionEmission:
    """Exception emission safety."""

    def test_exception_message_not_in_output(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        user_text = "我先生陳大明上週過世了"
        exc = ValueError(user_text)

        pipeline.emit_exception(exc, context_ids={"session_id": "s1"})

        assert len(emitted) == 1
        output = emitted[0]
        assert user_text not in output
        parsed = json.loads(output)
        assert parsed["error_type"] == "ValueError"
        assert parsed["event"] == "exception_recorded"
        assert parsed["session_id"] == "s1"

    def test_exception_without_context(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        pipeline.emit_exception(RuntimeError("oops"))

        parsed = json.loads(emitted[0])
        assert parsed["error_type"] == "RuntimeError"
        assert "oops" not in emitted[0]


class TestPipelineAuditEmission:
    """Audit event pre-filtering."""

    def test_audit_only_allowed_keys_emitted(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        pipeline.emit_audit(
            {
                "event": "eligibility_evaluated",
                "item_id": "benefit_1",
                "rule_version": "v3",
                "actual": "sensitive",
                "user_attributes": {"age": 65},
            }
        )

        parsed = json.loads(emitted[0])
        assert "actual" not in parsed
        assert "user_attributes" not in parsed
        assert parsed["item_id"] == "benefit_1"

    def test_audit_default_event_name(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        pipeline.emit_audit({"item_id": "x"})

        parsed = json.loads(emitted[0])
        assert parsed["event"] == "audit_recorded"


class TestPipelineMultipleEvents:
    """Multiple events through the pipeline."""

    def test_multiple_events_counted(self) -> None:
        pipeline = ObservabilityPipeline(emitter=lambda _: None)

        pipeline.emit_event({"event": "a"})
        pipeline.emit_event({"event": "b"})
        pipeline.emit_event({"event": "c"})

        assert pipeline.sanitize_count == 3
        assert pipeline.serialize_count == 3
        assert pipeline.emit_count == 3

    def test_mixed_success_and_failure(self) -> None:
        emitted: list[str] = []
        pipeline = ObservabilityPipeline(emitter=emitted.append)

        pipeline.emit_event({"event": "ok"})
        pipeline.emit_event({"event": "bad", "data": {1, 2}})  # Fails
        pipeline.emit_event({"event": "ok2"})

        assert pipeline.sanitize_count == 3
        assert pipeline.serialize_count == 2  # Only 2 succeeded
        assert pipeline.sanitization_failures == 1
        assert pipeline.emit_count == 3  # All emit (2 real + 1 indicator)
