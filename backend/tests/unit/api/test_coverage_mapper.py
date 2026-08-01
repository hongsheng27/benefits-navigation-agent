"""Unit tests for the coverage response mapper (Requirements 12.1-12.13)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.api.response_mapper import coverage_summary_text, map_coverage_to_api_view
from app.application.coverage_tracker import build_snapshot, find_completeness_claims
from app.orchestration.protocols import CoverageScope, LocalSourceRecord

OBSERVED_AT = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
LAST_SUCCESS = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
SCOPE = CoverageScope(source_ids=(), domain_tags=("funeral",))


def _snapshot() -> object:
    records = (
        LocalSourceRecord(
            source_id="src-a",
            crawl_status="crawled",
            domain_tags=("funeral",),
            check_frequency_days=7,
            last_crawled_at=LAST_SUCCESS,
            indexed_document_count=4,
        ),
        LocalSourceRecord(
            source_id="src-b",
            crawl_status="pending_crawl",
            domain_tags=("funeral",),
            check_frequency_days=7,
        ),
        LocalSourceRecord(
            source_id="src-c",
            crawl_status="error",
            domain_tags=("funeral",),
            check_frequency_days=7,
            last_crawled_at=LAST_SUCCESS,
            indexed_document_count=2,
            gap_category="scanned_attachment",
        ),
    )
    return build_snapshot(records, SCOPE, OBSERVED_AT)


def test_counts_are_carried_through_unchanged() -> None:
    view = map_coverage_to_api_view(_snapshot())  # type: ignore[arg-type]

    assert view.registered_source_count == 3
    assert view.crawled_source_count == 1
    assert view.pending_crawl_source_count == 1
    assert view.error_source_count == 1
    assert view.indexed_document_count == 6


def test_scope_is_echoed_so_the_reader_knows_what_was_measured() -> None:
    view = map_coverage_to_api_view(_snapshot())  # type: ignore[arg-type]

    assert view.scope_domain_tags == ("funeral",)
    assert view.scope_source_ids == ()


def test_gap_categories_survive_serialization() -> None:
    view = map_coverage_to_api_view(_snapshot())  # type: ignore[arg-type]

    assert view.gap_categories == ("scanned_attachment",)
    payload = view.model_dump(by_alias=True)
    assert payload["gapCategories"] == ("scanned_attachment",)


def test_error_source_keeps_its_last_successful_crawl_time() -> None:
    view = map_coverage_to_api_view(_snapshot())  # type: ignore[arg-type]

    by_id = {source.source_id: source for source in view.sources}
    assert by_id["src-c"].crawl_status == "error"
    assert by_id["src-c"].last_crawled_at == LAST_SUCCESS.isoformat()
    assert by_id["src-c"].indexed_document_count == 2


def test_never_crawled_source_reports_a_null_timestamp() -> None:
    view = map_coverage_to_api_view(_snapshot())  # type: ignore[arg-type]

    by_id = {source.source_id: source for source in view.sources}
    assert by_id["src-b"].last_crawled_at is None
    assert by_id["src-b"].indexed_document_count == 0


def test_field_names_are_camel_case_on_the_wire() -> None:
    view = map_coverage_to_api_view(_snapshot())  # type: ignore[arg-type]
    payload = view.model_dump(by_alias=True)

    assert "registeredSourceCount" in payload
    assert "indexedDocumentCount" in payload
    assert "observedAt" in payload
    assert "registered_source_count" not in payload


def test_view_forbids_extra_fields() -> None:
    """A future caller cannot slip a completeness flag into the response."""
    view = map_coverage_to_api_view(_snapshot())  # type: ignore[arg-type]
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError
        type(view)(**view.model_dump(), is_complete=True)


def test_serialized_payload_has_no_completeness_claims() -> None:
    view = map_coverage_to_api_view(_snapshot())  # type: ignore[arg-type]
    serialized = json.dumps(view.model_dump(by_alias=True), ensure_ascii=False)

    assert find_completeness_claims(serialized) == ()


def test_summary_text_states_progress_without_claims() -> None:
    text = coverage_summary_text(_snapshot())  # type: ignore[arg-type]

    assert find_completeness_claims(text) == ()
    assert "登記來源 3" in text
    assert "已知缺口 scanned_attachment" in text
