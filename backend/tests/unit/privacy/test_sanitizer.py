"""Unit tests for recursive PrivacySanitizer.

Tests using synthetic markers verify:
- Nested payload sanitization (denylisted keys removed at all depths)
- Stringified JSON parsing and recursive sanitization
- Plain strings pass through unchanged
- Exception sanitization preserves only safe metadata
- Audit event filtering to allowed keys only
- Fail-closed on unsupported types (SanitizationError)
- Removal counting

Requirements: 9.3–9.8, 9.12.
"""

from __future__ import annotations

import json

import pytest

from app.privacy.sanitizer import (
    DENYLISTED_KEYS,
    SanitizationError,
    sanitize_audit_event,
    sanitize_exception,
    sanitize_payload,
)


class TestSanitizePayloadPrimitives:
    """Primitive values pass through unchanged."""

    def test_none(self) -> None:
        result = sanitize_payload(None)
        assert result.sanitized is None
        assert result.removals == 0

    def test_bool(self) -> None:
        assert sanitize_payload(True).sanitized is True
        assert sanitize_payload(False).sanitized is False

    def test_int(self) -> None:
        assert sanitize_payload(42).sanitized == 42

    def test_float(self) -> None:
        assert sanitize_payload(3.14).sanitized == 3.14

    def test_plain_string(self) -> None:
        result = sanitize_payload("hello world")
        assert result.sanitized == "hello world"
        assert result.removals == 0


class TestSanitizePayloadDicts:
    """Dict/mapping sanitization."""

    def test_empty_dict(self) -> None:
        result = sanitize_payload({})
        assert result.sanitized == {}
        assert result.removals == 0

    def test_safe_keys_preserved(self) -> None:
        payload = {"session_id": "abc", "event": "test", "duration_ms": 42}
        result = sanitize_payload(payload)
        assert result.sanitized == payload
        assert result.removals == 0

    def test_denylisted_key_removed_at_top_level(self) -> None:
        payload = {"session_id": "abc", "actual": "sensitive_value"}
        result = sanitize_payload(payload)
        assert "actual" not in result.sanitized
        assert result.sanitized == {"session_id": "abc"}
        assert result.removals == 1

    def test_multiple_denylisted_keys_removed(self) -> None:
        payload = {
            "event": "test",
            "actual": "secret1",
            "raw_text": "secret2",
            "text": "secret3",
        }
        result = sanitize_payload(payload)
        assert result.sanitized == {"event": "test"}
        assert result.removals == 3

    def test_denylisted_key_removed_in_nested_dict(self) -> None:
        payload = {
            "event": "test",
            "details": {
                "item_id": "benefit_1",
                "actual": "user_situation",
                "message": "raw text from user",
            },
        }
        result = sanitize_payload(payload)
        assert result.sanitized == {
            "event": "test",
            "details": {"item_id": "benefit_1"},
        }
        assert result.removals == 2

    def test_deeply_nested_removal(self) -> None:
        payload = {
            "level1": {
                "level2": {
                    "level3": {
                        "safe_key": "ok",
                        "actual": "deeply_hidden",
                    }
                }
            }
        }
        result = sanitize_payload(payload)
        assert result.sanitized == {
            "level1": {"level2": {"level3": {"safe_key": "ok"}}}
        }
        assert result.removals == 1


class TestSanitizePayloadSequences:
    """List and tuple sanitization."""

    def test_list_of_primitives(self) -> None:
        result = sanitize_payload([1, "hello", True, None])
        assert result.sanitized == [1, "hello", True, None]

    def test_list_of_dicts_with_denylisted_keys(self) -> None:
        payload = [
            {"item_id": "a", "actual": "secret"},
            {"item_id": "b", "text": "raw"},
        ]
        result = sanitize_payload(payload)
        assert result.sanitized == [{"item_id": "a"}, {"item_id": "b"}]
        assert result.removals == 2

    def test_tuple_preserved_as_tuple(self) -> None:
        payload = ({"safe": "yes"}, {"actual": "no"})
        result = sanitize_payload(payload)
        assert result.sanitized == ({"safe": "yes"}, {})
        assert result.removals == 1


class TestSanitizePayloadJsonStrings:
    """Stringified JSON is parsed and recursively sanitized."""

    def test_json_object_string_sanitized(self) -> None:
        inner = json.dumps({"event": "inner", "actual": "hidden"})
        payload = {"data": inner}
        result = sanitize_payload(payload)
        # The JSON string is parsed and sanitized
        assert result.sanitized == {"data": {"event": "inner"}}
        assert result.removals == 1

    def test_json_array_string_sanitized(self) -> None:
        inner = json.dumps([{"key": "val", "raw_text": "secret"}])
        payload = {"items": inner}
        result = sanitize_payload(payload)
        assert result.sanitized == {"items": [{"key": "val"}]}
        assert result.removals == 1

    def test_non_json_string_passes_through(self) -> None:
        payload = {"label": "just a plain string"}
        result = sanitize_payload(payload)
        assert result.sanitized == {"label": "just a plain string"}
        assert result.removals == 0

    def test_json_primitive_string_not_parsed(self) -> None:
        """A JSON-encoded primitive like '"hello"' is not recursed into."""
        payload = {"val": '"hello"'}
        result = sanitize_payload(payload)
        assert result.sanitized == {"val": '"hello"'}


class TestSanitizePayloadObjects:
    """Objects with __dict__ are treated as mappings."""

    def test_dataclass_like_object(self) -> None:
        class FakeObj:
            def __init__(self) -> None:
                self.safe_field = "ok"
                self.actual = "sensitive"
                self._private = "ignored"

        result = sanitize_payload(FakeObj())
        assert result.sanitized == {"safe_field": "ok"}
        assert result.removals == 1


class TestSanitizePayloadFailClosed:
    """Unsupported types trigger SanitizationError (fail-closed)."""

    def test_set_raises_sanitization_error(self) -> None:
        with pytest.raises(SanitizationError) as exc_info:
            sanitize_payload({"data": {1, 2, 3}})
        assert "unsupported_type:set" in str(exc_info.value)

    def test_bytes_raises_sanitization_error(self) -> None:
        with pytest.raises(SanitizationError) as exc_info:
            sanitize_payload({"binary": b"hello"})
        assert "unsupported_type:bytes" in str(exc_info.value)

    def test_complex_raises_sanitization_error(self) -> None:
        with pytest.raises(SanitizationError):
            sanitize_payload({"num": complex(1, 2)})


class TestSanitizeException:
    """Exception sanitization preserves only safe metadata."""

    def test_basic_exception(self) -> None:
        exc = ValueError("user typed sensitive info")
        result = sanitize_exception(exc)
        assert result == {"error_type": "ValueError"}
        # Message is NOT included
        assert "sensitive" not in str(result)

    def test_exception_with_code_attribute(self) -> None:
        class CodedError(Exception):
            def __init__(self) -> None:
                super().__init__("secret message")
                self.code = "invalid_field"

        result = sanitize_exception(CodedError())
        assert result["error_type"] == "CodedError"
        assert result["error_code"] == "invalid_field"
        assert "secret" not in str(result)

    def test_exception_with_context_ids(self) -> None:
        exc = RuntimeError("bad stuff")
        result = sanitize_exception(
            exc,
            context_ids={
                "session_id": "sess_123",
                "request_id": "req_456",
                "item_id": "benefit_1",
                "dangerous_field": "should_not_appear",
            },
        )
        assert result["session_id"] == "sess_123"
        assert result["request_id"] == "req_456"
        assert result["item_id"] == "benefit_1"
        assert "dangerous_field" not in result

    def test_exception_message_never_included(self) -> None:
        """Exception message may echo user input — never include it."""
        user_text = "我先生陳大明上週過世了"
        exc = ValueError(user_text)
        result = sanitize_exception(exc)
        assert user_text not in str(result)
        assert user_text not in json.dumps(result, ensure_ascii=False)


class TestSanitizeAuditEvent:
    """Audit event sanitization."""

    def test_only_allowed_keys_preserved(self) -> None:
        event = {
            "event": "eligibility_evaluated",
            "item_id": "benefit_1",
            "rule_id": "rule_001",
            "rule_version": "v3",
            "eligibility_status": "eligible",
            "timestamp": "2024-01-01T00:00:00Z",
            "session_id": "sess_123",
            "actual": "sensitive_actual_value",
            "text": "raw user text",
            "user_attributes": {"age": 65},
        }
        result = sanitize_audit_event(event)
        assert "actual" not in result
        assert "text" not in result
        assert "user_attributes" not in result
        assert result["item_id"] == "benefit_1"
        assert result["event"] == "eligibility_evaluated"

    def test_empty_audit_event(self) -> None:
        assert sanitize_audit_event({}) == {}

    def test_all_allowed_audit_keys(self) -> None:
        event = {
            "event": "status_changed",
            "item_id": "x",
            "rule_id": "r1",
            "rule_version": "1",
            "eligibility_status": "eligible",
            "status": "verified",
            "timestamp": "t",
            "session_id": "s",
            "request_id": "r",
            "actor_id": "a",
            "old_status": "candidate",
            "new_status": "verified",
        }
        result = sanitize_audit_event(event)
        assert result == event  # All keys are allowed


class TestDenylistCompleteness:
    """Verify the denylist covers expected sensitive field names."""

    def test_actual_variants_denylisted(self) -> None:
        assert "actual" in DENYLISTED_KEYS
        assert "actual_value" in DENYLISTED_KEYS

    def test_raw_text_variants_denylisted(self) -> None:
        assert "raw_text" in DENYLISTED_KEYS
        assert "text" in DENYLISTED_KEYS
        assert "raw_input" in DENYLISTED_KEYS

    def test_user_input_variants_denylisted(self) -> None:
        assert "user_input" in DENYLISTED_KEYS
        assert "message" in DENYLISTED_KEYS
        assert "prompt" in DENYLISTED_KEYS
        assert "response" in DENYLISTED_KEYS
        assert "question" in DENYLISTED_KEYS
        assert "answer" in DENYLISTED_KEYS
