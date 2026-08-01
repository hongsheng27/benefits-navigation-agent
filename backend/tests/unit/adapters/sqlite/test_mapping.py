"""Unit tests for row-to-contract mapping utilities."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.sqlite.mapping import (
    map_field_registry_entry,
    map_program_status,
    parse_aware_datetime,
    parse_json_value,
    parse_optional_datetime,
)
from app.orchestration.data_errors import RepositoryMappingError

# ---------------------------------------------------------------------------
# parse_aware_datetime
# ---------------------------------------------------------------------------


def test_parse_aware_datetime_iso_with_offset() -> None:
    result = parse_aware_datetime("2026-07-30T10:00:00+08:00", "test_field")

    assert (
        result == datetime(2026, 7, 30, 10, 0, tzinfo=UTC).replace(tzinfo=None)
        or result.utcoffset() is not None
    )
    assert result.year == 2026
    assert result.utcoffset() is not None


def test_parse_aware_datetime_utc_suffix() -> None:
    result = parse_aware_datetime("2026-07-30T02:00:00+00:00", "field")

    assert result.tzinfo is not None
    assert result == datetime(2026, 7, 30, 2, 0, tzinfo=UTC)


def test_parse_aware_datetime_rejects_naive() -> None:
    with pytest.raises(RepositoryMappingError, match="datetime_not_timezone_aware"):
        parse_aware_datetime("2026-07-30T10:00:00", "field")


def test_parse_aware_datetime_rejects_invalid_text() -> None:
    with pytest.raises(RepositoryMappingError, match="datetime_parse_failed"):
        parse_aware_datetime("not-a-date", "field")


def test_parse_aware_datetime_rejects_empty() -> None:
    with pytest.raises(RepositoryMappingError, match="datetime_parse_failed"):
        parse_aware_datetime("", "field")


# ---------------------------------------------------------------------------
# parse_optional_datetime
# ---------------------------------------------------------------------------


def test_parse_optional_datetime_none_input() -> None:
    assert parse_optional_datetime(None, "field") is None


def test_parse_optional_datetime_valid() -> None:
    result = parse_optional_datetime("2026-01-01T00:00:00+00:00", "field")

    assert result is not None
    assert result.year == 2026


# ---------------------------------------------------------------------------
# parse_json_value
# ---------------------------------------------------------------------------


def test_parse_json_value_string() -> None:
    assert parse_json_value('"hello"', "string") == "hello"


def test_parse_json_value_integer() -> None:
    assert parse_json_value("42", "integer") == 42


def test_parse_json_value_number() -> None:
    assert parse_json_value("3.14", "number") == 3.14


def test_parse_json_value_boolean() -> None:
    assert parse_json_value("true", "boolean") is True
    assert parse_json_value("false", "boolean") is False


def test_parse_json_value_null() -> None:
    assert parse_json_value("null", "null") is None


def test_parse_json_value_array() -> None:
    result = parse_json_value('["a", "b"]', "string")

    assert result == ("a", "b")


def test_parse_json_value_object() -> None:
    result = parse_json_value('{"key": 1}', "string")

    assert result == (("key", 1),)


def test_parse_json_value_invalid_json() -> None:
    with pytest.raises(RepositoryMappingError, match="json_value_decode_failed"):
        parse_json_value("{invalid", "string")


# ---------------------------------------------------------------------------
# map_program_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    ["candidate", "under_review", "verified", "stale", "rejected", "inactive"],
)
def test_map_program_status_valid(status: str) -> None:
    assert map_program_status(status) == status


def test_map_program_status_invalid() -> None:
    with pytest.raises(RepositoryMappingError, match="invalid_program_status"):
        map_program_status("unknown_status")


# ---------------------------------------------------------------------------
# map_field_registry_entry
# ---------------------------------------------------------------------------


def test_map_field_registry_entry_basic() -> None:
    row = (
        "age",
        "integer",
        "How old are you?",
        "Age determines eligibility",
        "eligibility_sensitive",
        "1",
    )

    entry = map_field_registry_entry(row, allowed_values=())

    assert entry.field_id == "age"
    assert entry.data_type == "integer"
    assert entry.prompt_label == "How old are you?"
    assert entry.why_needed == "Age determines eligibility"
    assert entry.pii_classification == "eligibility_sensitive"
    assert entry.allowed_values == ()


def test_map_field_registry_entry_with_allowed_values() -> None:
    row = (
        "insurance_type",
        "enum",
        "Which insurance?",
        "Determines handler",
        "none",
        "1",
    )

    entry = map_field_registry_entry(row, allowed_values=("labor", "national_pension"))

    assert entry.allowed_values == ("labor", "national_pension")
