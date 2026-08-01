"""Property 16: Coverage snapshot invariants.

**Validates: Requirements 12.1-12.5, 12.9-12.13**

For any legal set of source records and any scope:

1. `registered == crawled + pending + error`
2. `indexed_total == sum(per-source indexed)`
3. Every count is non-negative
4. Every source carries the snapshot's `observed_at`
5. Every source is inside the requested scope
6. An error source keeps the last successful crawl time and the documents it
   had already indexed (failure history preservation)

The expected aggregates are recomputed from the generated records, not read
back from the snapshot, so the assertions do not restate the implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.application.coverage_tracker import (
    GAP_CATEGORIES,
    build_snapshot,
    merge_failure_history,
    select_scoped_records,
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
)


@st.composite
def _record(draw: st.DrawFn, source_id: str) -> LocalSourceRecord:
    """Generate a legal LocalSourceRecord.

    The dataclass enforces its own invariants (non-negative counts, aware
    datetimes, a gap category on every error), so anything this returns is a
    state the system is allowed to be in.
    """
    crawl_status = draw(st.sampled_from(["crawled", "pending_crawl", "error"]))
    tags = tuple(
        sorted(
            draw(st.lists(st.sampled_from(TAGS), min_size=1, max_size=4, unique=True))
        )
    )
    frequency = draw(st.integers(min_value=0, max_value=365))

    if crawl_status == "pending_crawl":
        # The contract for a never-crawled source: no timestamp, no documents.
        return LocalSourceRecord(
            source_id=source_id,
            crawl_status="pending_crawl",
            domain_tags=tags,
            check_frequency_days=frequency,
        )

    return LocalSourceRecord(
        source_id=source_id,
        crawl_status=crawl_status,
        domain_tags=tags,
        check_frequency_days=frequency,
        last_crawled_at=draw(st.one_of(st.none(), _crawl_times)),
        indexed_document_count=draw(st.integers(min_value=0, max_value=10_000)),
        gap_category=(
            draw(st.sampled_from(sorted(GAP_CATEGORIES)))
            if crawl_status == "error"
            else None
        ),
    )


@st.composite
def _records(draw: st.DrawFn) -> tuple[LocalSourceRecord, ...]:
    source_ids = draw(st.lists(_source_ids, min_size=0, max_size=8, unique=True))
    return tuple(draw(_record(source_id)) for source_id in source_ids)


@st.composite
def _scope(draw: st.DrawFn, records: tuple[LocalSourceRecord, ...]) -> CoverageScope:
    """Generate a scope, sometimes by id, sometimes by tag, sometimes both."""
    known_ids = [record.source_id for record in records]
    mode = draw(st.sampled_from(["ids", "tags", "both", "empty"]))
    if mode == "empty":
        return CoverageScope(source_ids=(), domain_tags=())
    ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    if mode in ("ids", "both") and known_ids:
        ids = tuple(
            draw(
                st.lists(
                    st.sampled_from(known_ids),
                    min_size=1,
                    max_size=len(known_ids),
                    unique=True,
                )
            )
        )
    if mode in ("tags", "both"):
        tags = tuple(
            draw(st.lists(st.sampled_from(TAGS), min_size=1, max_size=4, unique=True))
        )
    if not ids and not tags:
        tags = (draw(st.sampled_from(TAGS)),)
    return CoverageScope(source_ids=ids, domain_tags=tags)


# ---------------------------------------------------------------------------
# Property 16.1 — status counts sum to the registered count
# ---------------------------------------------------------------------------


@given(data=st.data(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_status_counts_sum_to_registered(
    data: st.DataObject, observed_at: datetime
) -> None:
    records = data.draw(_records())
    scope = data.draw(_scope(records))

    snapshot = build_snapshot(records, scope, observed_at)

    assert snapshot.registered_source_count == (
        snapshot.crawled_source_count
        + snapshot.pending_crawl_source_count
        + snapshot.error_source_count
    )
    assert snapshot.registered_source_count == len(snapshot.sources)


@given(data=st.data(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_counts_match_an_independent_tally(
    data: st.DataObject, observed_at: datetime
) -> None:
    """The aggregates are recomputed from the scoped records, not read back."""
    records = data.draw(_records())
    scope = data.draw(_scope(records))
    expected = select_scoped_records(records, scope)

    snapshot = build_snapshot(records, scope, observed_at)

    assert snapshot.registered_source_count == len(expected)
    assert snapshot.crawled_source_count == sum(
        record.crawl_status == "crawled" for record in expected
    )
    assert snapshot.pending_crawl_source_count == sum(
        record.crawl_status == "pending_crawl" for record in expected
    )
    assert snapshot.error_source_count == sum(
        record.crawl_status == "error" for record in expected
    )


# ---------------------------------------------------------------------------
# Property 16.2 — indexed totals sum
# ---------------------------------------------------------------------------


@given(data=st.data(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_indexed_total_equals_the_per_source_sum(
    data: st.DataObject, observed_at: datetime
) -> None:
    records = data.draw(_records())
    scope = data.draw(_scope(records))
    expected = select_scoped_records(records, scope)

    snapshot = build_snapshot(records, scope, observed_at)

    assert snapshot.indexed_document_count == sum(
        record.indexed_document_count for record in expected
    )
    assert snapshot.indexed_document_count == sum(
        source.indexed_document_count for source in snapshot.sources
    )


# ---------------------------------------------------------------------------
# Property 16.3 — non-negativity
# ---------------------------------------------------------------------------


@given(data=st.data(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_all_counts_are_non_negative(
    data: st.DataObject, observed_at: datetime
) -> None:
    records = data.draw(_records())
    scope = data.draw(_scope(records))

    snapshot = build_snapshot(records, scope, observed_at)

    assert snapshot.registered_source_count >= 0
    assert snapshot.crawled_source_count >= 0
    assert snapshot.pending_crawl_source_count >= 0
    assert snapshot.error_source_count >= 0
    assert snapshot.indexed_document_count >= 0
    assert all(source.indexed_document_count >= 0 for source in snapshot.sources)


# ---------------------------------------------------------------------------
# Property 16.4 — one shared observation time
# ---------------------------------------------------------------------------


@given(data=st.data(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_every_source_shares_the_snapshot_observed_at(
    data: st.DataObject, observed_at: datetime
) -> None:
    records = data.draw(_records())
    scope = data.draw(_scope(records))

    snapshot = build_snapshot(records, scope, observed_at)

    assert snapshot.observed_at == observed_at
    assert all(source.observed_at == observed_at for source in snapshot.sources)
    assert snapshot.observed_at.utcoffset() is not None


@given(data=st.data())
@settings(max_examples=100, deadline=5000)
def test_naive_observed_at_is_always_rejected(data: st.DataObject) -> None:
    records = data.draw(_records())
    scope = data.draw(_scope(records))
    naive = data.draw(
        st.datetimes(
            min_value=datetime(2026, 1, 1),
            max_value=datetime(2026, 12, 31),
        )
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        build_snapshot(records, scope, naive)


# ---------------------------------------------------------------------------
# Property 16.5 — scope containment
# ---------------------------------------------------------------------------


@given(data=st.data(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_every_source_is_inside_the_requested_scope(
    data: st.DataObject, observed_at: datetime
) -> None:
    records = data.draw(_records())
    scope = data.draw(_scope(records))

    snapshot = build_snapshot(records, scope, observed_at)

    scoped_ids = frozenset(scope.source_ids)
    scoped_tags = frozenset(scope.domain_tags)
    for source in snapshot.sources:
        if scoped_ids:
            assert source.source_id in scoped_ids
        if scoped_tags:
            assert scoped_tags & frozenset(source.domain_tags)
    if not scoped_ids and not scoped_tags:
        assert snapshot.sources == ()


@given(data=st.data(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_source_ids_are_unique_within_a_snapshot(
    data: st.DataObject, observed_at: datetime
) -> None:
    records = data.draw(_records())
    scope = data.draw(_scope(records))

    snapshot = build_snapshot(records, scope, observed_at)

    ids = [source.source_id for source in snapshot.sources]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids), "ordering must be deterministic"


# ---------------------------------------------------------------------------
# Property 16.6 — failure history preservation
# ---------------------------------------------------------------------------


@given(data=st.data(), observed_at=_observed_at)
@settings(max_examples=200, deadline=5000)
def test_error_sources_keep_their_last_crawl_time(
    data: st.DataObject, observed_at: datetime
) -> None:
    """Going into error never rewrites the last successful crawl time."""
    records = data.draw(_records())
    scope = data.draw(_scope(records))

    snapshot = build_snapshot(records, scope, observed_at)

    by_id = {record.source_id: record for record in records}
    for source in snapshot.sources:
        original = by_id[source.source_id]
        assert source.last_crawled_at == original.last_crawled_at
        assert source.indexed_document_count == original.indexed_document_count


@given(
    source_id=_source_ids,
    previous_indexed=st.integers(min_value=1, max_value=1000),
    previous_crawled_at=_crawl_times,
    gap_category=st.sampled_from(sorted(GAP_CATEGORIES)),
)
@settings(max_examples=200, deadline=5000)
def test_merging_an_error_over_a_success_keeps_the_history(
    source_id: str,
    previous_indexed: int,
    previous_crawled_at: datetime,
    gap_category: str,
) -> None:
    """A crawl failure does not delete documents that are already indexed."""
    previous = LocalSourceRecord(
        source_id=source_id,
        crawl_status="crawled",
        domain_tags=("funeral",),
        check_frequency_days=7,
        last_crawled_at=previous_crawled_at,
        indexed_document_count=previous_indexed,
    )
    failed = LocalSourceRecord(
        source_id=source_id,
        crawl_status="error",
        domain_tags=("funeral",),
        check_frequency_days=7,
        gap_category=gap_category,
    )

    merged = merge_failure_history(previous, failed)

    assert merged.crawl_status == "error"
    assert merged.gap_category == gap_category
    assert merged.last_crawled_at == previous_crawled_at
    assert merged.indexed_document_count == previous_indexed


@given(
    source_id=_source_ids,
    observed_at=_observed_at,
    gap_category=st.sampled_from(sorted(GAP_CATEGORIES)),
    indexed=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=200, deadline=5000)
def test_repeated_failures_do_not_erode_history(
    source_id: str,
    observed_at: datetime,
    gap_category: str,
    indexed: int,
) -> None:
    """History survives an arbitrary number of consecutive failures."""
    success_at = observed_at - timedelta(days=30)
    current = LocalSourceRecord(
        source_id=source_id,
        crawl_status="crawled",
        domain_tags=("funeral",),
        check_frequency_days=7,
        last_crawled_at=success_at,
        indexed_document_count=indexed,
    )

    for _ in range(5):
        failure = LocalSourceRecord(
            source_id=source_id,
            crawl_status="error",
            domain_tags=("funeral",),
            check_frequency_days=7,
            gap_category=gap_category,
        )
        current = merge_failure_history(current, failure)

    assert current.last_crawled_at == success_at
    assert current.indexed_document_count == indexed

    snapshot = build_snapshot(
        (current,),
        CoverageScope(source_ids=(source_id,), domain_tags=()),
        observed_at,
    )
    assert snapshot.error_source_count == 1
    assert snapshot.sources[0].last_crawled_at == success_at
    assert snapshot.gap_categories == (gap_category,)
