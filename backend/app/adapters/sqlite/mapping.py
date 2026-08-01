"""Row-to-contract mapping utilities for SQLite adapters.

All adapters share these helpers to convert raw SQLite text/numeric values
into domain contract fields. Parse failures raise RepositoryMappingError
with a safe code — no SQL, no row content, no user values.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import get_args

from app.orchestration.data_contracts import (
    FieldRegistryEntry,
    FrozenValue,
    ProgramStatus,
    freeze_value,
)
from app.orchestration.data_errors import RepositoryMappingError

_PROGRAM_STATUS_VALUES: frozenset[str] = frozenset(get_args(ProgramStatus))


def parse_aware_datetime(text: str, field_name: str) -> datetime:
    """Parse ISO-8601 text into a timezone-aware datetime.

    Raises RepositoryMappingError if the text cannot be parsed or is naive.
    """
    try:
        dt = datetime.fromisoformat(text)
    except (ValueError, TypeError) as exc:
        raise RepositoryMappingError(f"datetime_parse_failed:{field_name}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise RepositoryMappingError(f"datetime_not_timezone_aware:{field_name}")
    return dt


def parse_optional_datetime(text: str | None, field_name: str) -> datetime | None:
    """Parse optional ISO-8601 text. None input → None output."""
    if text is None:
        return None
    return parse_aware_datetime(text, field_name)


def parse_json_value(json_text: str, value_type: str) -> FrozenValue:
    """Decode a JSON expected_value_json column into a FrozenValue.

    The value_type hint (string, integer, number, boolean, null) is used
    for validation but the actual JSON decode determines the Python type.
    """
    try:
        raw = json.loads(json_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RepositoryMappingError("json_value_decode_failed") from exc
    return freeze_value(raw)


def map_program_status(raw: str) -> ProgramStatus:
    """Validate and return a ProgramStatus literal value."""
    if raw not in _PROGRAM_STATUS_VALUES:
        raise RepositoryMappingError("invalid_program_status")
    return raw  # type: ignore[return-value]


def map_field_registry_entry(
    row: tuple[str, str, str, str, str, str],
    allowed_values: tuple[str, ...] = (),
) -> FieldRegistryEntry:
    """Map a field_registry row + pre-loaded allowed_values to contract."""
    field_id, data_type, prompt_label, why_needed, pii_classification, _active = row
    return FieldRegistryEntry(
        field_id=field_id,
        data_type=data_type,
        allowed_values=allowed_values,
        prompt_label=prompt_label,
        why_needed=why_needed,
        pii_classification=pii_classification,
    )
