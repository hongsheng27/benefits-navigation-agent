"""Property 12: Recursive sanitizer 與 fail-closed observability.

**Validates: Requirements 9.3–9.8, 9.12, 9.13**

Feature: data-layer-rule-engine, Property 12: successful observability emissions
contain no generated raw-text or actual-value markers, while sanitizer failure
never serializes or emits the original payload and emits only the fixed failure
indicator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.observability.pipeline import (
    _SANITIZATION_FAILED_INDICATOR,
    ObservabilityPipeline,
)
from app.privacy.sanitizer import DENYLISTED_KEYS

_SAFE_TEXT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    min_size=1,
    max_size=24,
)
_FAILURE_KINDS: tuple[Literal["bytes", "complex", "set"], ...] = (
    "bytes",
    "complex",
    "set",
)


@dataclass
class _SyntheticPayloadModel:
    """Model-like object used to exercise recursive ``__dict__`` traversal."""

    details: object
    actual: str
    safe_id: str


def _sensitive_value(
    shape: str,
    *,
    raw_marker: str,
    actual_marker: str,
    safe_text: str,
) -> object:
    """Build a supported nested value that always contains both markers."""
    sensitive_mapping = {
        "safe_id": safe_text,
        "raw_text": raw_marker,
        "actual": actual_marker,
    }

    if shape == "mapping":
        return {"outer": {"inner": sensitive_mapping}}
    if shape == "list":
        return [safe_text, {"nested": sensitive_mapping}]
    if shape == "tuple":
        return (safe_text, {"nested": [sensitive_mapping]})
    if shape == "model":
        return _SyntheticPayloadModel(
            details={"nested": sensitive_mapping},
            actual=actual_marker,
            safe_id=safe_text,
        )
    if shape == "json_object":
        return json.dumps({"nested": sensitive_mapping}, sort_keys=True)
    if shape == "json_array":
        return json.dumps([safe_text, sensitive_mapping], sort_keys=True)
    if shape == "plain_strings":
        return {
            "raw_text": raw_marker,
            "actual": actual_marker,
            "safe_label": safe_text,
        }
    raise AssertionError(f"unhandled generated shape: {shape}")


def _unsupported_value(
    kind: Literal["bytes", "complex", "set"], marker: str
) -> object:
    """Create an unsupported value that forces sanitizer uncertainty."""
    if kind == "bytes":
        return marker.encode()
    if kind == "complex":
        return complex(1, 2)
    return {marker}


def _assert_no_sensitive_keys(value: object) -> None:
    """Independent recursive oracle for the serialized JSON output."""
    if isinstance(value, dict):
        assert DENYLISTED_KEYS.isdisjoint(value)
        for nested_value in value.values():
            _assert_no_sensitive_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _assert_no_sensitive_keys(nested_value)


@given(
    nonce=st.integers(min_value=0, max_value=1_000_000_000),
    safe_text=_SAFE_TEXT,
    shape=st.sampled_from(
        (
            "mapping",
            "list",
            "tuple",
            "model",
            "json_object",
            "json_array",
            "plain_strings",
        )
    ),
    failure_kind=st.sampled_from(_FAILURE_KINDS),
)
@settings(max_examples=150, deadline=None)
def test_property_12_recursive_sanitizer_and_fail_closed_observability(
    nonce: int,
    safe_text: str,
    shape: str,
    failure_kind: Literal["bytes", "complex", "set"],
) -> None:
    """All successful paths redact markers; uncertain paths drop the payload."""
    raw_marker = f"P12_RAW_USER_TEXT_{nonce}"
    actual_marker = f"P12_ACTUAL_VALUE_{nonce}"
    markers = (raw_marker, actual_marker)

    serialized_payloads: list[dict[str, Any]] = []
    successful_emissions: list[str] = []

    def tracking_serializer(payload: dict[str, Any]) -> str:
        serialized_payloads.append(payload)
        return json.dumps(payload, sort_keys=True)

    success_pipeline = ObservabilityPipeline(
        serializer=tracking_serializer,
        emitter=successful_emissions.append,
    )
    success_pipeline.emit_event(
        {
            "event": "synthetic_property_12",
            "payload": _sensitive_value(
                shape,
                raw_marker=raw_marker,
                actual_marker=actual_marker,
                safe_text=safe_text,
            ),
        }
    )

    assert success_pipeline.serialize_count == 1
    assert len(serialized_payloads) == 1
    assert len(successful_emissions) == 1
    successful_output = successful_emissions[0]
    assert all(marker not in successful_output for marker in markers)
    _assert_no_sensitive_keys(json.loads(successful_output))

    exception_emissions: list[str] = []
    exception_pipeline = ObservabilityPipeline(emitter=exception_emissions.append)
    exception_pipeline.emit_exception(
        ValueError(f"{raw_marker}:{actual_marker}"),
        context_ids={"request_id": f"synthetic_request_{nonce}"},
    )
    assert len(exception_emissions) == 1
    assert all(marker not in exception_emissions[0] for marker in markers)
    assert json.loads(exception_emissions[0]) == {
        "error_type": "ValueError",
        "event": "exception_recorded",
        "request_id": f"synthetic_request_{nonce}",
    }

    audit_emissions: list[str] = []
    audit_pipeline = ObservabilityPipeline(emitter=audit_emissions.append)
    audit_pipeline.emit_audit(
        {
            "event": "eligibility_evaluated",
            "item_id": f"synthetic_item_{nonce}",
            "rule_version": "synthetic_v1",
            "status": "needs_human_review",
            "actual": actual_marker,
            "raw_text": raw_marker,
            "unapproved_context": {"actual": actual_marker},
        }
    )
    assert len(audit_emissions) == 1
    assert all(marker not in audit_emissions[0] for marker in markers)
    assert json.loads(audit_emissions[0]) == {
        "event": "eligibility_evaluated",
        "item_id": f"synthetic_item_{nonce}",
        "rule_version": "synthetic_v1",
        "status": "needs_human_review",
    }

    failure_serializer_calls: list[dict[str, Any]] = []
    failure_emissions: list[str] = []

    def forbidden_original_serializer(payload: dict[str, Any]) -> str:
        failure_serializer_calls.append(payload)
        return json.dumps({"event": "original_payload_was_serialized"})

    failure_pipeline = ObservabilityPipeline(
        serializer=forbidden_original_serializer,
        emitter=failure_emissions.append,
    )
    failure_pipeline.emit_event(
        {
            "event": "synthetic_property_12_failure",
            "raw_text": raw_marker,
            "actual": actual_marker,
            "unsupported": _unsupported_value(failure_kind, raw_marker),
        }
    )

    assert failure_serializer_calls == []
    assert failure_pipeline.serialize_count == 0
    assert failure_pipeline.sanitization_failures == 1
    assert failure_emissions == [_SANITIZATION_FAILED_INDICATOR]
    assert all(marker not in failure_emissions[0] for marker in markers)
