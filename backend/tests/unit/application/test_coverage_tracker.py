"""Unit tests for the coverage tracker (Requirements 12.1-12.13)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.coverage_tracker import (
    FORBIDDEN_CLAIM_TERMS,
    GAP_CATEGORIES,
    assert_no_completeness_claims,
    build_snapshot,
    collect_gap_categories,
    describe_coverage,
    find_completeness_claims,
    merge_failure_history,
    select_scoped_records,
)
from app.orchestration.protocols import CoverageScope, LocalSourceRecord

OBSERVED_AT = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
LAST_SUCCESS = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)


def _record(
    source_id: str,
    crawl_status: str = "crawled",
    *,
    tags: tuple[str, ...] = ("funeral",),
    indexed: int = 0,
    last_crawled_at: datetime | None = None,
    gap_category: str | None = None,
) -> LocalSourceRecord:
    return LocalSourceRecord(
        source_id=source_id,
        crawl_status=crawl_status,  # type: ignore[arg-type]
        domain_tags=tags,
        check_frequency_days=7,
        last_crawled_at=last_crawled_at,
        indexed_document_count=indexed,
        gap_category=gap_category,
    )


# ---------------------------------------------------------------------------
# Scope selection
# ---------------------------------------------------------------------------


def test_scope_selection_is_sorted_and_deterministic() -> None:
    records = (
        _record("src-c"),
        _record("src-a"),
        _record("src-b"),
    )
    scope = CoverageScope(source_ids=(), domain_tags=("funeral",))

    selected = select_scoped_records(records, scope)

    assert [record.source_id for record in selected] == ["src-a", "src-b", "src-c"]


def test_empty_scope_selects_nothing() -> None:
    records = (_record("src-a"),)
    assert select_scoped_records(records, CoverageScope((), ())) == ()


def test_scope_dimensions_intersect() -> None:
    records = (
        _record("src-a", tags=("funeral",)),
        _record("src-b", tags=("housing",)),
    )
    scope = CoverageScope(source_ids=("src-a", "src-b"), domain_tags=("housing",))

    selected = select_scoped_records(records, scope)

    assert [record.source_id for record in selected] == ["src-b"]


# ---------------------------------------------------------------------------
# Snapshot construction
# ---------------------------------------------------------------------------


def test_snapshot_counts_match_the_records() -> None:
    records = (
        _record("src-a", "crawled", indexed=4, last_crawled_at=LAST_SUCCESS),
        _record("src-b", "pending_crawl"),
        _record("src-c", "error", gap_category="broken_link", indexed=1),
    )
    scope = CoverageScope(source_ids=(), domain_tags=("funeral",))

    snapshot = build_snapshot(records, scope, OBSERVED_AT)

    assert snapshot.registered_source_count == 3
    assert snapshot.crawled_source_count == 1
    assert snapshot.pending_crawl_source_count == 1
    assert snapshot.error_source_count == 1
    assert snapshot.indexed_document_count == 5
    assert snapshot.gap_categories == ("broken_link",)


def test_snapshot_applies_one_observed_at_to_every_source() -> None:
    records = (_record("src-a"), _record("src-b"))
    scope = CoverageScope(source_ids=(), domain_tags=("funeral",))

    snapshot = build_snapshot(records, scope, OBSERVED_AT)

    assert {source.observed_at for source in snapshot.sources} == {OBSERVED_AT}


def test_snapshot_rejects_naive_observed_at() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral",))
    with pytest.raises(ValueError, match="timezone-aware"):
        build_snapshot((_record("src-a"),), scope, datetime(2026, 7, 30, 12, 0))


def test_snapshot_rejects_duplicate_source_ids() -> None:
    scope = CoverageScope(source_ids=("src-a",), domain_tags=())
    with pytest.raises(ValueError, match="unique source_ids"):
        build_snapshot((_record("src-a"), _record("src-a")), scope, OBSERVED_AT)


# ---------------------------------------------------------------------------
# Gap categories
# ---------------------------------------------------------------------------


def test_gap_categories_only_come_from_error_sources() -> None:
    records = (
        _record("src-a", "crawled", last_crawled_at=LAST_SUCCESS),
        _record("src-b", "pending_crawl"),
        _record("src-c", "error", gap_category="login_required"),
    )
    assert collect_gap_categories(records) == ("login_required",)


def test_gap_categories_are_deduplicated_and_sorted() -> None:
    records = (
        _record("src-a", "error", gap_category="robots_policy"),
        _record("src-b", "error", gap_category="login_required"),
        _record("src-c", "error", gap_category="robots_policy"),
    )
    assert collect_gap_categories(records) == ("login_required", "robots_policy")


def test_all_known_gap_categories_are_accepted() -> None:
    records = tuple(
        _record(f"src-{index}", "error", gap_category=category)
        for index, category in enumerate(sorted(GAP_CATEGORIES))
    )
    assert collect_gap_categories(records) == tuple(sorted(GAP_CATEGORIES))


def test_unknown_gap_category_raises() -> None:
    record = _record("src-a", "error", gap_category="made_up")
    with pytest.raises(ValueError, match="unsupported gap_category"):
        collect_gap_categories((record,))


# ---------------------------------------------------------------------------
# Failure history
# ---------------------------------------------------------------------------


def test_failure_history_carries_forward_success_data() -> None:
    previous = _record("src-a", "crawled", indexed=9, last_crawled_at=LAST_SUCCESS)
    current = _record("src-a", "error", gap_category="connection_error")

    merged = merge_failure_history(previous, current)

    assert merged.last_crawled_at == LAST_SUCCESS
    assert merged.indexed_document_count == 9


def test_failure_history_does_not_overwrite_present_values() -> None:
    newer = datetime(2026, 7, 20, tzinfo=UTC)
    previous = _record("src-a", "crawled", indexed=9, last_crawled_at=LAST_SUCCESS)
    current = _record(
        "src-a",
        "error",
        gap_category="connection_error",
        indexed=3,
        last_crawled_at=newer,
    )

    merged = merge_failure_history(previous, current)

    assert merged.last_crawled_at == newer
    assert merged.indexed_document_count == 3


def test_failure_history_without_a_previous_record_is_a_passthrough() -> None:
    current = _record("src-a", "error", gap_category="connection_error")
    assert merge_failure_history(None, current) is current


# ---------------------------------------------------------------------------
# Honest claims
# ---------------------------------------------------------------------------


def test_every_forbidden_term_is_detected() -> None:
    for term in FORBIDDEN_CLAIM_TERMS:
        assert find_completeness_claims(f"prefix {term} suffix") != (), term


def test_claim_detection_is_case_insensitive() -> None:
    assert find_completeness_claims("ALL INDEXED") == ("all indexed",)
    assert find_completeness_claims("Complete") == ("complete",)


def test_neutral_progress_text_passes() -> None:
    text = "registered=3 crawled=1 pending_crawl=1 error=1"
    assert find_completeness_claims(text) == ()
    assert_no_completeness_claims(text)


def test_assert_no_completeness_claims_raises_on_a_claim() -> None:
    with pytest.raises(ValueError, match="completeness claims"):
        assert_no_completeness_claims("所有福利均已索引")


def test_describe_coverage_states_numbers_only() -> None:
    records = (
        _record("src-a", "crawled", indexed=4, last_crawled_at=LAST_SUCCESS),
        _record("src-b", "error", gap_category="javascript_only"),
    )
    scope = CoverageScope(source_ids=(), domain_tags=("funeral",))
    snapshot = build_snapshot(records, scope, OBSERVED_AT)

    description = describe_coverage(snapshot)

    assert "registered=2" in description
    assert "indexed_documents=4" in description
    assert "gap_categories=javascript_only" in description
    assert find_completeness_claims(description) == ()
