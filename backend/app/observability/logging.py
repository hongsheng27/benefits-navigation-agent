"""Structured application logging.

Every log record is emitted as a single JSON object so that CloudWatch can
query on fields instead of matching substrings.

This module exists to enforce
[ADR-0007](../../../docs/decisions/0007-limit-data-retention-and-egress.md):
user-supplied text is never written to logs. Enforcement is structural rather
than advisory — `log_event` accepts only the field names in `ALLOWED_FIELDS`
and raises on anything else, so an accidental `text=...` fails immediately
instead of reaching CloudWatch.

Two traps this module is specifically shaped to avoid:

1. Exception *messages* often echo their input. A Pydantic `ValidationError`
   quotes the offending value, so `str(exc)` can leak the very text we
   discarded. Callers therefore never pass an error message; the formatter
   records the exception *type* only.
2. Tracebacks rendered with `traceback.format_exception` include that same
   message. This module uses `traceback.format_tb`, which yields the stack
   frames without it.

The allowlist below is a starting point owned by the project lead. Fields hold
identifiers, names, counts, and outcomes — never values a user typed.
"""

import json
import logging
import sys
import traceback
from typing import Any

LOGGER_NAME = "jiezhu"

# --- Field allowlist -------------------------------------------------------
#
# Grouped for review. Adding a field is a privacy decision, not a convenience:
# ask whether its value could contain anything a user typed.

_CORRELATION_FIELDS = frozenset(
    {
        "session_id",  # random, carries no personal data (ADR-0005)
        "request_id",
    }
)

_WORKFLOW_FIELDS = frozenset(
    {
        "state",
        "next_state",
        "transition",
        "guard",
    }
)

_AGENT_FIELDS = frozenset(
    {
        "tool",
        "tool_allowed",
        "agent_iterations",
        "model_id",
    }
)

_ENTITLEMENT_FIELDS = frozenset(
    {
        "candidate_count",  # candidate benefits produced by the entitlement graph
    }
)

_RULE_FIELDS = frozenset(
    {
        "rule_id",
        "rule_version",
        "benefit_id",
        "eligibility_status",
        "eligible_count",
    }
)

_RETRIEVAL_FIELDS = frozenset(
    {
        "document_id",
        "source_count",
    }
)

# Names of fields only. The values a user supplied for them are never logged.
_FIELD_NAME_FIELDS = frozenset(
    {
        "missing_field_names",
        "extracted_field_names",
        "life_event",  # a de-identified category such as `spouse_death`
    }
)

_OUTCOME_FIELDS = frozenset(
    {
        "outcome",
        "status_code",
        "duration_ms",
        "error_type",  # exception class name, never the message
    }
)

ALLOWED_FIELDS: frozenset[str] = (
    _CORRELATION_FIELDS
    | _WORKFLOW_FIELDS
    | _AGENT_FIELDS
    | _ENTITLEMENT_FIELDS
    | _RULE_FIELDS
    | _RETRIEVAL_FIELDS
    | _FIELD_NAME_FIELDS
    | _OUTCOME_FIELDS
)


class DisallowedLogFieldError(ValueError):
    """Raised when a caller passes a field outside `ALLOWED_FIELDS`.

    This is a programming error, not a runtime condition: call sites are
    written by developers, so failing loudly during development is preferable
    to silently dropping the field and discovering the gap in production.
    """


class JsonFormatter(logging.Formatter):
    """Render a log record as one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }

        payload.update(getattr(record, "fields", {}))

        if record.exc_info:
            exc_type, _, exc_tb = record.exc_info
            payload["error_type"] = exc_type.__name__ if exc_type else "Unknown"
            # format_tb yields stack frames only. format_exception would append
            # the exception message, which may quote user input.
            payload["stack"] = [frame.strip() for frame in traceback.format_tb(exc_tb)]

        # ensure_ascii=False keeps Chinese state and benefit names readable.
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    """Install the JSON formatter on the root logger.

    Third-party loggers such as uvicorn are formatted too, so output stays
    machine-readable. Their message text is not allowlist-checked, which is
    acceptable only because no user-supplied text is ever passed to them.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    """Emit one structured event.

    Args:
        event: A stable snake_case name such as `state_transitioned`. Keep it
            constant so queries can group on it; put what varies in fields.
        level: Standard `logging` level.
        exc_info: Attach the current exception's type and stack frames.
        **fields: Structured fields, each of which must be in `ALLOWED_FIELDS`.

    Raises:
        DisallowedLogFieldError: If any field is not on the allowlist.
    """
    rejected = sorted(set(fields) - ALLOWED_FIELDS)
    if rejected:
        raise DisallowedLogFieldError(
            f"Log fields not on the allowlist: {', '.join(rejected)}. "
            "Log identifiers, names, counts, and outcomes rather than values a "
            "user supplied. See ADR-0007 before extending ALLOWED_FIELDS."
        )

    logging.getLogger(LOGGER_NAME).log(
        level,
        event,
        exc_info=exc_info,
        extra={"event": event, "fields": fields},
    )
