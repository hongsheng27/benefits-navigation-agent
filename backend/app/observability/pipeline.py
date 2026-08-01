"""Fail-closed observability pipeline: sanitize -> validate -> serialize -> emit.

Implements Requirements 9.3–9.8, 9.12, 9.13, 13.8.

All logs, traces, metrics, exceptions, and audit events flow through this
single pipeline. The pipeline guarantees:

1. Every payload is sanitized by the PrivacySanitizer BEFORE serialization.
2. If sanitization fails (SanitizationError), the original payload is NEVER
   serialized or emitted. Only a fixed `sanitization_failed` indicator is
   emitted instead.
3. If serialization fails after successful sanitization, only a
   `serialization_failed` indicator is emitted.
4. The pipeline is the single entry point for all observability output.

No DB access, no network beyond the configured emitter.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.privacy.sanitizer import (
    SanitizationError,
    SanitizationResult,
    sanitize_audit_event,
    sanitize_exception,
    sanitize_payload,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# An emitter receives a serialized string and outputs it (e.g., to stdout, file, etc.)
Emitter = Callable[[str], None]

# A serializer converts a sanitized dict to a string
Serializer = Callable[[dict[str, Any]], str]


# ---------------------------------------------------------------------------
# Default implementations
# ---------------------------------------------------------------------------


def default_serializer(payload: dict[str, Any]) -> str:
    """JSON serializer with ensure_ascii=False for Chinese text in identifiers."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def default_emitter(serialized: str) -> None:
    """Default emitter: print to stdout (production would use structured logging)."""
    print(serialized, flush=True)  # noqa: T201


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

# Fixed indicators for failure modes — contain NO original payload content.
_SANITIZATION_FAILED_INDICATOR = '{"event":"sanitization_failed","safe":true}'
_SERIALIZATION_FAILED_INDICATOR = '{"event":"serialization_failed","safe":true}'


@dataclass
class ObservabilityPipeline:
    """Fail-closed observability pipeline.

    Usage:
        pipeline = ObservabilityPipeline()
        pipeline.emit_event({"event": "state_transitioned", "session_id": "abc"})
        pipeline.emit_exception(exc, context_ids={"session_id": "abc"})
        pipeline.emit_audit({"event": "eligibility_evaluated", "item_id": "x"})

    On sanitization failure:
        The original payload is NEVER serialized or emitted. Only the fixed
        sanitization_failed indicator reaches the emitter.

    For testing:
        Pass custom serializer and emitter to capture/inspect outputs.
    """

    serializer: Serializer = field(default=default_serializer)
    emitter: Emitter = field(default=default_emitter)

    # Counters for testing/verification
    _sanitize_count: int = field(default=0, init=False, repr=False)
    _serialize_count: int = field(default=0, init=False, repr=False)
    _emit_count: int = field(default=0, init=False, repr=False)
    _sanitization_failures: int = field(default=0, init=False, repr=False)

    @property
    def sanitize_count(self) -> int:
        """Number of payloads that entered sanitization."""
        return self._sanitize_count

    @property
    def serialize_count(self) -> int:
        """Number of payloads that were serialized (post-sanitization)."""
        return self._serialize_count

    @property
    def emit_count(self) -> int:
        """Number of payloads that were emitted."""
        return self._emit_count

    @property
    def sanitization_failures(self) -> int:
        """Number of sanitization failures (fail-closed activations)."""
        return self._sanitization_failures

    def emit_event(self, payload: dict[str, Any]) -> None:
        """Sanitize and emit a general observability event.

        Flow: sanitize -> serialize -> emit.
        On failure at any stage, fail closed.
        """
        self._process(payload)

    def emit_exception(
        self,
        exc: BaseException,
        *,
        context_ids: dict[str, str] | None = None,
    ) -> None:
        """Sanitize an exception and emit safe metadata only.

        The exception message is NEVER included (may echo user input).
        Only error_type, error_code, and context IDs are preserved.
        """
        safe_record = sanitize_exception(exc, context_ids=context_ids)
        safe_record["event"] = "exception_recorded"
        # This record is already sanitized by sanitize_exception,
        # but we still run it through the full pipeline for consistency.
        self._process(safe_record)

    def emit_audit(self, event: dict[str, Any]) -> None:
        """Sanitize and emit an audit event.

        Audit events are pre-filtered to allowed keys (Req 9.8),
        then run through the full pipeline.
        """
        safe_audit = sanitize_audit_event(event)
        safe_audit.setdefault("event", "audit_recorded")
        self._process(safe_audit)

    def _process(self, payload: dict[str, Any]) -> None:
        """Core pipeline: sanitize -> serialize -> emit with fail-closed semantics."""
        # Step 1: Sanitize
        self._sanitize_count += 1
        try:
            result: SanitizationResult = sanitize_payload(payload)
        except SanitizationError:
            # FAIL CLOSED: Do NOT serialize or emit the original payload.
            self._sanitization_failures += 1
            self.emitter(_SANITIZATION_FAILED_INDICATOR)
            self._emit_count += 1
            return

        sanitized = result.sanitized

        # Ensure sanitized output is a dict for serialization
        if not isinstance(sanitized, dict):
            # Sanitized result is not a dict — treat as serialization failure
            self._sanitization_failures += 1
            self.emitter(_SANITIZATION_FAILED_INDICATOR)
            self._emit_count += 1
            return

        # Step 2: Serialize
        try:
            serialized = self.serializer(sanitized)
            self._serialize_count += 1
        except (TypeError, ValueError, OverflowError):
            # Serialization failed — emit safe indicator only
            self.emitter(_SERIALIZATION_FAILED_INDICATOR)
            self._emit_count += 1
            return

        # Step 3: Emit
        self.emitter(serialized)
        self._emit_count += 1
