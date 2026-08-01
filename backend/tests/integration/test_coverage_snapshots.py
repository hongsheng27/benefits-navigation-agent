"""Integration tests for coverage snapshots (Requirements 12.1-12.13).

Covers:
- Aggregate arithmetic: registered == crawled + pending + error, and
  indexed_total == sum of per-source counts
- One shared observed_at across every source in a snapshot
- Scope containment: out-of-scope sources never enter a snapshot
- Gap category preservation for error sources
- Failure history: an error keeps the last successful crawl time and the
  documents already indexed
- The API view states observable progress only, with no completeness claims
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.migrations import migrate_database
from backend.app.adapters.sqlite.source_refresh_service import (
    SqliteSourceRefreshService,
)
from backend.app.api.response_mapper import (
    coverage_summary_text,
    map_coverage_to_api_view,
)
from backend.app.application.coverage_tracker import (
    GAP_CATEGORIES,
    build_snapshot,
    collect_gap_categories,
    find_completeness_claims,
    merge_failure_history,
    select_scoped_records,
)
from backend.app.orchestration.protocols import CoverageScope, LocalSourceRecord

NOW = "2026-07-30T00:00:00+00:00"
OBSERVED_AT = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
LAST_SUCCESS = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)


def _records() -> tuple[LocalSourceRecord, ...]:
    return (
        LocalSourceRecord(
            source_id="synth-src-a",
            crawl_status="crawled",
            domain_tags=("funeral",),
            check_frequency_days=7,
            last_crawled_at=LAST_SUCCESS,
            indexed_document_count=5,
        ),
        LocalSourceRecord(
            source_id="synth-src-b",
            crawl_status="pending_crawl",
            domain_tags=("funeral", "pension"),
            check_frequency_days=7,
        ),
        LocalSourceRecord(
            source_id="synth-src-c",
            crawl_status="error",
            domain_tags=("housing",),
            check_frequency_days=7,
            last_crawled_at=LAST_SUCCESS,
            indexed_document_count=2,
            gap_category="robots_policy",
        ),
        LocalSourceRecord(
            source_id="synth-src-d",
            crawl_status="error",
            domain_tags=("housing",),
            check_frequency_days=7,
            gap_category="login_required",
        ),
    )


# ---------------------------------------------------------------------------
# Req 12.1-12.5 — arithmetic and shared observation time
# ---------------------------------------------------------------------------


def test_status_counts_sum_to_registered_count() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral", "housing"))
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    assert snapshot.registered_source_count == 4
    assert (
        snapshot.crawled_source_count
        + snapshot.pending_crawl_source_count
        + snapshot.error_source_count
        == snapshot.registered_source_count
    )
    assert snapshot.crawled_source_count == 1
    assert snapshot.pending_crawl_source_count == 1
    assert snapshot.error_source_count == 2


def test_indexed_total_equals_sum_of_per_source_counts() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral", "housing"))
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    assert snapshot.indexed_document_count == 7
    assert snapshot.indexed_document_count == sum(
        source.indexed_document_count for source in snapshot.sources
    )


def test_all_sources_share_the_snapshot_observed_at() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral", "housing"))
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    assert snapshot.observed_at == OBSERVED_AT
    assert {source.observed_at for source in snapshot.sources} == {OBSERVED_AT}


def test_naive_observed_at_is_rejected() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral",))
    with pytest.raises(ValueError, match="timezone-aware"):
        build_snapshot(_records(), scope, datetime(2026, 7, 30, 12, 0))


def test_all_counts_are_non_negative() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral", "housing"))
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    counts = (
        snapshot.registered_source_count,
        snapshot.crawled_source_count,
        snapshot.pending_crawl_source_count,
        snapshot.error_source_count,
        snapshot.indexed_document_count,
    )
    assert all(count >= 0 for count in counts)
    assert all(source.indexed_document_count >= 0 for source in snapshot.sources)


# ---------------------------------------------------------------------------
# Req 12.9-12.11 — scope containment
# ---------------------------------------------------------------------------


def test_out_of_scope_sources_are_excluded() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral",))
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    assert {source.source_id for source in snapshot.sources} == {
        "synth-src-a",
        "synth-src-b",
    }
    assert snapshot.registered_source_count == 2
    assert snapshot.indexed_document_count == 5


def test_source_ids_and_domain_tags_intersect() -> None:
    scope = CoverageScope(
        source_ids=("synth-src-a", "synth-src-c"), domain_tags=("funeral",)
    )
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    # src-c matches the id filter but not the tag filter, so it is excluded.
    assert {source.source_id for source in snapshot.sources} == {"synth-src-a"}


def test_empty_scope_yields_an_empty_snapshot() -> None:
    """An unspecified scope means "nothing", never "everything"."""
    scope = CoverageScope(source_ids=(), domain_tags=())
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    assert select_scoped_records(_records(), scope) == ()
    assert snapshot.sources == ()
    assert snapshot.registered_source_count == 0
    assert snapshot.indexed_document_count == 0
    assert snapshot.gap_categories == ()


def test_duplicate_source_ids_are_rejected() -> None:
    duplicated = (_records()[0], _records()[0])
    scope = CoverageScope(source_ids=("synth-src-a",), domain_tags=())
    with pytest.raises(ValueError, match="unique source_ids"):
        build_snapshot(duplicated, scope, OBSERVED_AT)


# ---------------------------------------------------------------------------
# Req 12.6-12.8, 12.12, 12.13 — gaps and failure history
# ---------------------------------------------------------------------------


def test_gap_categories_are_preserved_and_sorted() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("housing",))
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    assert snapshot.gap_categories == ("login_required", "robots_policy")
    assert set(snapshot.gap_categories) <= GAP_CATEGORIES


def test_pending_sources_do_not_produce_gap_categories() -> None:
    """ "Not crawled yet" is a queue position, not a gap."""
    scope = CoverageScope(source_ids=("synth-src-b",), domain_tags=())
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    assert snapshot.pending_crawl_source_count == 1
    assert snapshot.gap_categories == ()


def test_unknown_gap_category_is_rejected_not_dropped() -> None:
    """Silently dropping an unknown category would erase a real gap."""
    record = LocalSourceRecord(
        source_id="synth-src-x",
        crawl_status="error",
        domain_tags=("housing",),
        check_frequency_days=7,
        gap_category="mystery",
    )
    with pytest.raises(ValueError, match="unsupported gap_category"):
        collect_gap_categories((record,))


def test_error_source_preserves_last_successful_crawl_time() -> None:
    """An error keeps the last success visible instead of looking untouched."""
    scope = CoverageScope(source_ids=("synth-src-c",), domain_tags=())
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    source = snapshot.sources[0]
    assert source.crawl_status == "error"
    assert source.last_crawled_at == LAST_SUCCESS
    assert source.indexed_document_count == 2


def test_merge_failure_history_restores_prior_success() -> None:
    previous = _records()[0]  # crawled, 5 documents, last success recorded
    current = LocalSourceRecord(
        source_id="synth-src-a",
        crawl_status="error",
        domain_tags=("funeral",),
        check_frequency_days=7,
        gap_category="connection_error",
    )

    merged = merge_failure_history(previous, current)

    assert merged.crawl_status == "error"
    assert merged.gap_category == "connection_error"
    assert merged.last_crawled_at == LAST_SUCCESS
    assert merged.indexed_document_count == 5


def test_merge_failure_history_leaves_successful_records_alone() -> None:
    previous = _records()[0]
    current = _records()[1]
    assert merge_failure_history(previous, current) is current


# ---------------------------------------------------------------------------
# Req 12.6-12.8 — honest response mapping
# ---------------------------------------------------------------------------


def test_api_view_reports_only_observable_numbers() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral", "housing"))
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    view = map_coverage_to_api_view(snapshot)

    assert view.registered_source_count == 4
    assert (
        view.crawled_source_count
        + view.pending_crawl_source_count
        + view.error_source_count
        == view.registered_source_count
    )
    assert view.indexed_document_count == 7
    assert view.gap_categories == ("login_required", "robots_policy")
    assert len(view.sources) == 4
    assert view.observed_at == OBSERVED_AT.isoformat()


def test_api_view_has_no_completeness_fields() -> None:
    """No ratio, percentage or "all indexed" flag exists to be misread."""
    scope = CoverageScope(source_ids=(), domain_tags=("funeral",))
    view = map_coverage_to_api_view(build_snapshot(_records(), scope, OBSERVED_AT))

    payload = view.model_dump(by_alias=True)
    banned_keys = {
        "complete",
        "completeness",
        "completenessRatio",
        "coverageRatio",
        "coveragePercentage",
        "allIndexed",
        "isComplete",
        "guaranteed",
    }
    assert banned_keys.isdisjoint(payload.keys())


def test_serialized_view_contains_no_completeness_claims() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral", "housing"))
    view = map_coverage_to_api_view(build_snapshot(_records(), scope, OBSERVED_AT))

    serialized = json.dumps(view.model_dump(by_alias=True), ensure_ascii=False)

    assert find_completeness_claims(serialized) == ()


def test_summary_text_is_claim_free() -> None:
    scope = CoverageScope(source_ids=(), domain_tags=("funeral", "housing"))
    snapshot = build_snapshot(_records(), scope, OBSERVED_AT)

    text = coverage_summary_text(snapshot)

    assert find_completeness_claims(text) == ()
    assert "4" in text and "7" in text
    assert "robots_policy" in text


def test_claim_detector_catches_known_phrasings() -> None:
    assert find_completeness_claims("已完整索引所有福利") != ()
    assert find_completeness_claims("All benefits indexed") != ()
    assert find_completeness_claims("we guarantee zero omissions") != ()
    assert find_completeness_claims("觀測時間 2026-07-30；登記來源 4") == ()


# ---------------------------------------------------------------------------
# SQLite path — the same invariants hold against the real adapter
# ---------------------------------------------------------------------------


def _sqlite_fixture(tmp_path: Path) -> Path:
    database = tmp_path / "coverage.db"
    migrate_database(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executemany(
            """
            INSERT INTO source_registry (
                source_id, name, source_type, base_url, entry_url,
                canonical_host, official_status, access_method,
                connection_status, created_at, updated_at
            ) VALUES (
                ?, ?, 'agency_site',
                'https://synthetic.invalid', 'https://synthetic.invalid/e',
                'synthetic.invalid', 'pending_review', 'manual_seed',
                'pending', ?, ?
            )
            """,
            [
                ("synth-src-a", "A", NOW, NOW),
                ("synth-src-b", "B", NOW, NOW),
                ("synth-src-c", "C", NOW, NOW),
            ],
        )
        connection.executemany(
            """
            INSERT INTO source_coverage_state (
                source_id, crawl_status, last_successful_crawl_at,
                indexed_document_count, last_gap_category, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("synth-src-a", "crawled", NOW, 5, None, NOW),
                ("synth-src-b", "pending_crawl", None, 0, None, NOW),
                ("synth-src-c", "error", NOW, 2, "robots_policy", NOW),
            ],
        )
        connection.executemany(
            "INSERT INTO source_domain_tags (source_id, domain_tag) VALUES (?, ?)",
            [
                ("synth-src-a", "funeral"),
                ("synth-src-b", "funeral"),
                ("synth-src-c", "funeral"),
            ],
        )
    return database


def test_sqlite_snapshot_satisfies_the_same_invariants(tmp_path: Path) -> None:
    database = _sqlite_fixture(tmp_path)
    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))

    snapshot = service.get_coverage_status(
        CoverageScope(source_ids=(), domain_tags=("funeral",))
    )

    assert snapshot.registered_source_count == 3
    assert (
        snapshot.crawled_source_count
        + snapshot.pending_crawl_source_count
        + snapshot.error_source_count
        == 3
    )
    assert snapshot.indexed_document_count == 7
    assert {source.observed_at for source in snapshot.sources} == {snapshot.observed_at}
    assert snapshot.gap_categories == ("robots_policy",)


def test_sqlite_error_source_keeps_failure_history(tmp_path: Path) -> None:
    database = _sqlite_fixture(tmp_path)
    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))

    snapshot = service.get_coverage_status(
        CoverageScope(source_ids=("synth-src-c",), domain_tags=())
    )

    source = snapshot.sources[0]
    assert source.crawl_status == "error"
    assert source.last_crawled_at is not None
    assert source.indexed_document_count == 2


def test_sqlite_snapshot_serializes_without_claims(tmp_path: Path) -> None:
    database = _sqlite_fixture(tmp_path)
    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))

    snapshot = service.get_coverage_status(
        CoverageScope(source_ids=(), domain_tags=("funeral",))
    )
    view = map_coverage_to_api_view(snapshot)
    serialized = json.dumps(view.model_dump(by_alias=True), ensure_ascii=False)

    assert find_completeness_claims(serialized) == ()
