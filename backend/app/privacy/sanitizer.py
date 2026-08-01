"""Recursive Privacy Sanitizer.

Recursively processes mappings, models, sequences, JSON strings, and plain
strings to remove `actual` values, raw user text, and denylisted keys from
any payload before it reaches observability outputs.

Requirements: 9.3–9.8, 9.12.

Design principles:
- Denylisted keys are removed at any nesting depth.
- JSON strings embedded in values are parsed and recursively sanitized.
- Exception payloads are reduced to safe type, code, and context IDs.
- If sanitization cannot be confirmed complete (unsupported types), the
  sanitizer raises SanitizationError rather than letting data through.
- No DB access, no network, no side effects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class SanitizationError(Exception):
    """Raised when sanitizer cannot confirm complete sanitization.

    The observability pipeline must treat this as a hard failure and
    suppress the original payload entirely.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"sanitization_failed: {reason}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Keys whose values must be removed from any mapping at any depth.
# These correspond to fields that could contain user-supplied data or
# actual eligibility values per ADR-0007 and Req 9.3–9.8.
DENYLISTED_KEYS: frozenset[str] = frozenset(
    {
        "actual",
        "actual_value",
        "raw_text",
        "text",
        "message",
        "prompt",
        "response",
        "question",
        "answer",
        "user_input",
        "raw_input",
        "description",
        "note",
        "reason",  # free-form reason text (not condition_id-based reasons)
    }
)

# Keys that are safe to keep in exception records (Req 9.7).
SAFE_EXCEPTION_KEYS: frozenset[str] = frozenset(
    {
        "error_type",
        "error_code",
        "code",
        "session_id",
        "request_id",
        "item_id",
        "rule_id",
        "rule_version",
        "timestamp",
    }
)

# Marker value used to replace removed content, making removal visible
# in sanitized output without leaking the original value.
REDACTED_MARKER = "[REDACTED]"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SanitizationResult:
    """Result of a successful sanitization pass.

    Attributes:
        sanitized: The sanitized payload, safe for serialization and emission.
        removals: Count of values that were redacted or removed.
    """

    sanitized: Any
    removals: int


def sanitize_payload(payload: Any) -> SanitizationResult:
    """Recursively sanitize a payload for observability output.

    Processes:
    - dict/Mapping: removes denylisted keys, recurses into remaining values.
    - list/tuple/sequence: recurses into each element.
    - str: attempts JSON parse and recurses if valid JSON object/array;
      plain strings pass through unchanged (they are field values, not
      structured data that could hide denylisted content).
    - int/float/bool/None: pass through unchanged.
    - Objects with __dict__: treated as mappings of their attributes.
    - Unsupported types: raise SanitizationError (fail-closed).

    Args:
        payload: Any value to sanitize.

    Returns:
        SanitizationResult with the sanitized payload and removal count.

    Raises:
        SanitizationError: If the payload contains unsupported types that
            cannot be confirmed sanitized.
    """
    removals = [0]  # mutable counter for nested calls
    result = _sanitize_recursive(payload, removals)
    return SanitizationResult(sanitized=result, removals=removals[0])


def sanitize_exception(
    exc: BaseException,
    *,
    context_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Sanitize an exception into a safe observability record.

    Only preserves:
    - error_type: the exception class name
    - error_code: if the exception has a `code` attribute
    - Context IDs (session_id, request_id, item_id, etc.)

    Never includes:
    - Exception message (may echo user input)
    - Exception args (may contain raw values)
    - Traceback content with local variables

    Args:
        exc: The exception to sanitize.
        context_ids: Optional dict of safe context identifiers.

    Returns:
        A dict containing only safe exception metadata.
    """
    result: dict[str, Any] = {
        "error_type": type(exc).__name__,
    }

    # Extract code if available (e.g., DataLayerError subclasses)
    if hasattr(exc, "code"):
        code = exc.code
        if isinstance(code, str):
            result["error_code"] = code

    # Add safe context IDs
    if context_ids:
        for key, value in context_ids.items():
            if key in SAFE_EXCEPTION_KEYS and isinstance(value, str):
                result[key] = value

    return result


def sanitize_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    """Sanitize an audit event to only keep allowed fields (Req 9.8).

    Preserves: item_id, rule_id, rule_version, eligibility_status,
    timestamp, session_id, request_id, actor pseudonymous ID.

    Removes everything else, especially actual values and user text.
    """
    AUDIT_ALLOWED_KEYS: frozenset[str] = frozenset(
        {
            "event",
            "item_id",
            "rule_id",
            "rule_version",
            "eligibility_status",
            "status",
            "timestamp",
            "session_id",
            "request_id",
            "actor_id",
            "old_status",
            "new_status",
        }
    )
    return {k: v for k, v in event.items() if k in AUDIT_ALLOWED_KEYS}


# ---------------------------------------------------------------------------
# Internal recursive implementation
# ---------------------------------------------------------------------------


def _sanitize_recursive(value: Any, removals: list[int]) -> Any:
    """Recursively sanitize a value, counting removals."""
    # None, bool, int, float — safe primitives
    if value is None or isinstance(value, (bool, int, float)):
        return value

    # String: check if it's embedded JSON
    if isinstance(value, str):
        return _sanitize_string(value, removals)

    # Dict/Mapping
    if isinstance(value, dict):
        return _sanitize_dict(value, removals)

    # List
    if isinstance(value, list):
        return [_sanitize_recursive(item, removals) for item in value]

    # Tuple
    if isinstance(value, tuple):
        return tuple(_sanitize_recursive(item, removals) for item in value)

    # Frozenset (e.g., from frozen dataclass fields)
    if isinstance(value, frozenset):
        return frozenset(_sanitize_recursive(item, removals) for item in value)

    # Objects with __dict__ (dataclasses, Pydantic models, etc.)
    if hasattr(value, "__dict__"):
        obj_dict = {}
        for attr_name, attr_value in vars(value).items():
            if attr_name.startswith("_"):
                continue  # Skip private/internal attributes
            if attr_name in DENYLISTED_KEYS:
                removals[0] += 1
                continue
            obj_dict[attr_name] = _sanitize_recursive(attr_value, removals)
        return obj_dict

    # Unsupported type — fail closed
    raise SanitizationError(f"unsupported_type:{type(value).__name__}")


def _sanitize_dict(d: dict[str, Any], removals: list[int]) -> dict[str, Any]:
    """Sanitize a dictionary, removing denylisted keys and recursing."""
    result: dict[str, Any] = {}
    for key, val in d.items():
        if key in DENYLISTED_KEYS:
            removals[0] += 1
            continue
        result[key] = _sanitize_recursive(val, removals)
    return result


def _sanitize_string(s: str, removals: list[int]) -> Any:
    """Attempt to parse string as JSON and sanitize recursively.

    If the string is valid JSON (object or array), it's parsed, sanitized,
    and returned as the parsed (not re-stringified) structure so the caller
    can see its contents. If it's a plain string, return as-is.
    """
    # Only attempt JSON parse if it looks like JSON
    stripped = s.strip()
    if not stripped or (stripped[0] not in ("{", "[")):
        return s

    try:
        parsed = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return s

    # Only recurse into objects and arrays
    if isinstance(parsed, (dict, list)):
        return _sanitize_recursive(parsed, removals)

    return s
