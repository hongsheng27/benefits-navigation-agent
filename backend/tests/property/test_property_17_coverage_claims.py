"""Property 17: Coverage gaps are reported honestly.

**Validates: Requirements 12.6-12.8**

For any snapshot containing error sources:

1. Every distinct gap category on an error source appears in
   `snapshot.gap_categories` — a gap is never summarised away.
2. No pending-only snapshot invents a gap category.
3. The serialized API response contains none of the forbidden completeness
   claims, in either Chinese or English.
4. The response carries no field that could be read as a completeness ratio,
   coverage percentage, or "everything is indexed" flag.
5. Nothing outside the requested scope appears in the response, so the numbers
   cannot be read as covering more than was measured.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from app.api.response_mapper import coverage_summary_text, map_coverage_to_api_view
from app.application.coverage_tracker import (
    FORBIDDEN_CLAIM_TERMS,
    GAP_CATEGORIES,
    build_snapshot,
    find_completeness_claims,
)
from app.orchestration.protocols import CoverageScope, LocalSourceRecord

TAGS = ("funeral", "pension", "housing", "medical")

_observed_at = st.datetimes(
    min_value=datetime(2026, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(UTC),
)
_crawl_times = st.datetimes(
    min_value=datetime(2025, 1, 1),
    max_value=datetime(2025, 12, 31),
    timezones=st.just(UTC),
)
_source_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=10
).filter(
    lambda s: not any(term in s for term in FORBIDDEN_CLAIM_TERMS)
)

_BANNED_RESPONSE_KEYS = frozenset(
    {
        "complete",
        "completeness",
        "completenessRatio",
        "completeness_ratio",
        "coverageRatio",
        "coverage_ratio",
        "coveragePercentage",
        "coverage_percentage",
        "allIndexed",
        "all_indexed",
        "isComplete",
        "is_complete",
        "guaranteed",
        "zeroOmission",
        "zero_omission",
        "totalBenefits",
        "total_benefits",
    }
)


@st.composite
def _error_record(draw: st.DrawFn, source_id: str) -> LocalSourceRecord:
    return LocalSourceRecord(
        source_id=source_id,
        crawl_status="error",
        domain_tags=("funeral",),
        check_frequency_days=draw(st.integers(min_value=0, max_value=365)),
        last_crawled_at=draw(st.one_of(st.none(), _crawl_times)),
        indexed_document_count=draw(st.integers(min_value=0, max_value=1000)),
        gap_category=draw(st.sampled_from(sorted(GAP_CATEGORIES))),
    )


@st.composite
def _mixed_record(draw: st.DrawFn, source_id: str) -> LocalSourceRecord:
    crawl_status = draw(st.sampled_from(["crawled", "pending_crawl", "error"]))
    tags = tuple(
        sorted(
            draw(st.lists(st.sampled_from(TAGS), min_size=1, max_size=4, unique=True))
        )
    )
    if crawl_status == "pending_crawl":
        return LocalSourceRecord(
            source_id=source_id,
            crawl_status="pending_crawl",
            domain_tags=tags,
            check_frequency_days=draw(st.integers(min_value=0, max_value=365)),
        )
    return LocalSourceRecord(
        source_id=source_id,
        crawl_status=crawl_status,
        domain_tags=tags,
        check_frequency_days=draw(st.integers(min_value=0, max_value=365)),
        last_crawled_at=draw(st.one_of(st.none(), _crawl_times)),
        indexed_document_count=draw(st.integers(min_value=0, max_value=1000)),
        gap_category=(
            draw(st.sampled_from(sorted(GAP_CATEGORIES)))
            if crawl_status == "error"
            else None
        ),
    )


@st.composite
def _error_records(draw: st.DrawFn) -> tuple[LocalSourceRecord, ...]:
    source_ids = draw(st.lists(_source_ids, min_size=1, max_size=6, unique=True))
    return tuple(draw(_error_record(source_id)) for source_id in source_ids)


@st.composite
def _mixed_records(draw: st.DrawFn) -> tuple[LocalSourceRecord, ...]:
    source_ids = draw(st.lists(_source_ids, min_size=0, max_size=8, unique=True))
    return tuple(draw(_mixed_record(source_id)) for source_id in source_ids)


_FUNERAL_SCOPE = CoverageScope(source_ids=(), domain_tags=("funeral",))
_ALL_TAGS_SCOPE = CoverageScope(source_ids=(), domain_tags=TAGS)


# ---------------------------------------------------------------------------
# Property 17.1 — gap categories are preserved
# ---------------------------------------------------------------------------


@given(records=_error_records(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_every_error_gap_category_reaches_the_snapshot(
    records: tuple[LocalSourceRecord, ...],
    observed_at: datetime,
) -> None:
    """No error source loses its gap category on the way into a snapshot."""
    snapshot = build_snapshot(records, _FUNERAL_SCOPE, observed_at)

    expected = {record.gap_category for record in records}
    assert set(snapshot.gap_categories) == expected
    assert snapshot.gap_categories == tuple(sorted(snapshot.gap_categories))
    assert snapshot.error_source_count == len(records)


@given(records=_mixed_records(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_gap_categories_come_from_error_sources_only(
    records: tuple[LocalSourceRecord, ...],
    observed_at: datetime,
) -> None:
    """A snapshot with no error source reports no gaps, and vice versa."""
    snapshot = build_snapshot(records, _ALL_TAGS_SCOPE, observed_at)

    scoped_ids = {source.source_id for source in snapshot.sources}
    expected = {
        record.gap_category
        for record in records
        if record.crawl_status == "error" and record.source_id in scoped_ids
    }
    assert set(snapshot.gap_categories) == expected
    if snapshot.error_source_count == 0:
        assert snapshot.gap_categories == ()


@given(records=_error_records(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_gap_categories_survive_api_serialization(
    records: tuple[LocalSourceRecord, ...],
    observed_at: datetime,
) -> None:
    """Serialization does not drop the reason a source is missing."""
    snapshot = build_snapshot(records, _FUNERAL_SCOPE, observed_at)
    payload = map_coverage_to_api_view(snapshot).model_dump(by_alias=True)

    assert set(payload["gapCategories"]) == set(snapshot.gap_categories)
    assert payload["errorSourceCount"] == snapshot.error_source_count


# ---------------------------------------------------------------------------
# Property 17.2 — no completeness claims in any serialized response
# ---------------------------------------------------------------------------


@given(records=_mixed_records(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_serialized_response_contains_no_forbidden_claims(
    records: tuple[LocalSourceRecord, ...],
    observed_at: datetime,
) -> None:
    """No generated snapshot serialises into a completeness claim."""
    snapshot = build_snapshot(records, _ALL_TAGS_SCOPE, observed_at)
    payload = map_coverage_to_api_view(snapshot).model_dump(by_alias=True)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert find_completeness_claims(serialized) == ()


@given(records=_mixed_records(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_summary_text_contains_no_forbidden_claims(
    records: tuple[LocalSourceRecord, ...],
    observed_at: datetime,
) -> None:
    snapshot = build_snapshot(records, _ALL_TAGS_SCOPE, observed_at)

    assert find_completeness_claims(coverage_summary_text(snapshot)) == ()


@given(records=_mixed_records(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_response_has_no_completeness_shaped_fields(
    records: tuple[LocalSourceRecord, ...],
    observed_at: datetime,
) -> None:
    """There is no field a reader could mistake for a completeness measure."""
    snapshot = build_snapshot(records, _ALL_TAGS_SCOPE, observed_at)
    payload = map_coverage_to_api_view(snapshot).model_dump(by_alias=True)

    assert _BANNED_RESPONSE_KEYS.isdisjoint(payload.keys())
    for source in payload["sources"]:
        assert _BANNED_RESPONSE_KEYS.isdisjoint(source.keys())


@given(text=st.sampled_from(FORBIDDEN_CLAIM_TERMS), filler=st.text(max_size=20))
@settings(max_examples=200, deadline=5000)
def test_the_detector_would_catch_a_reintroduced_claim(text: str, filler: str) -> None:
    """The guard is only useful if it actually fires, so prove that it does."""
    assert find_completeness_claims(f"{filler}{text}{filler}") != ()


# ---------------------------------------------------------------------------
# Property 17.3 — nothing outside the requested scope is reported
# ---------------------------------------------------------------------------


@given(records=_mixed_records(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_response_never_reports_beyond_the_requested_scope(
    records: tuple[LocalSourceRecord, ...],
    observed_at: datetime,
) -> None:
    """Numbers describe the requested scope and nothing wider."""
    snapshot = build_snapshot(records, _FUNERAL_SCOPE, observed_at)
    view = map_coverage_to_api_view(snapshot)

    assert view.scope_domain_tags == ("funeral",)
    for source in view.sources:
        assert "funeral" in source.domain_tags
    assert view.registered_source_count == len(view.sources)
    assert view.indexed_document_count == sum(
        source.indexed_document_count for source in view.sources
    )


@given(observed_at=_observed_at)
@settings(max_examples=100, deadline=5000)
def test_empty_scope_reports_zero_rather_than_everything(
    observed_at: datetime,
) -> None:
    """An unspecified scope reports nothing measured, not everything covered."""
    records = (
        LocalSourceRecord(
            source_id="src-a",
            crawl_status="crawled",
            domain_tags=("funeral",),
            check_frequency_days=7,
            last_crawled_at=observed_at,
            indexed_document_count=42,
        ),
    )
    snapshot = build_snapshot(
        records, CoverageScope(source_ids=(), domain_tags=()), observed_at
    )
    view = map_coverage_to_api_view(snapshot)

    assert view.registered_source_count == 0
    assert view.indexed_document_count == 0
    assert view.sources == ()
    assert view.gap_categories == ()
    serialized = json.dumps(view.model_dump(by_alias=True), ensure_ascii=False)
    assert find_completeness_claims(serialized) == ()
