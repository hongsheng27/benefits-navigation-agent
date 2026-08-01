"""Integration tests for SqliteSourceRefreshService."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from backend.app.adapters.sqlite.migrations import migrate_database
from backend.app.adapters.sqlite.source_refresh_service import (
    SqliteSourceRefreshService,
)
from backend.app.orchestration.protocols import (
    CoverageScope,
    RefreshRequest,
)

NOW = "2026-07-30T00:00:00+00:00"
NOW_DT = datetime(2026, 7, 30, 0, 0, tzinfo=UTC)


def _setup_database(tmp_path: Path) -> Path:
    database = tmp_path / "refresh.db"
    migrate_database(database)
    return database


def _insert_coverage_fixture(connection: sqlite3.Connection) -> None:
    """Insert sources with coverage state and domain tags."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executemany(
        """
        INSERT INTO source_registry (
            source_id, name, source_type, base_url, entry_url,
            canonical_host, official_status, access_method,
            connection_status, created_at, updated_at
        ) VALUES (
            ?, ?, 'agency_site',
            'https://example.gov.tw', 'https://example.gov.tw/e',
            'example.gov.tw', 'verified_official', 'manual_seed',
            'active', ?, ?
        )
        """,
        [
            ("src-a", "Source A", NOW, NOW),
            ("src-b", "Source B", NOW, NOW),
            ("src-c", "Source C", NOW, NOW),
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
            ("src-a", "crawled", NOW, 5, None, NOW),
            ("src-b", "pending_crawl", None, 0, None, NOW),
            ("src-c", "error", None, 0, "robots_policy", NOW),
        ],
    )
    connection.executemany(
        """
        INSERT INTO source_domain_tags (source_id, domain_tag)
        VALUES (?, ?)
        """,
        [
            ("src-a", "funeral"),
            ("src-b", "funeral"),
            ("src-c", "housing"),
        ],
    )


def test_coverage_status_by_domain_tag(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_coverage_fixture(conn)

    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))
    snapshot = service.get_coverage_status(
        CoverageScope(source_ids=(), domain_tags=("funeral",))
    )

    assert snapshot.registered_source_count == 2
    assert snapshot.crawled_source_count == 1
    assert snapshot.pending_crawl_source_count == 1
    assert snapshot.error_source_count == 0
    assert snapshot.indexed_document_count == 5
    assert len(snapshot.sources) == 2
    source_ids = [s.source_id for s in snapshot.sources]
    assert "src-a" in source_ids
    assert "src-b" in source_ids


def test_coverage_status_by_source_ids(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_coverage_fixture(conn)

    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))
    snapshot = service.get_coverage_status(
        CoverageScope(source_ids=("src-c",), domain_tags=())
    )

    assert snapshot.registered_source_count == 1
    assert snapshot.error_source_count == 1
    assert snapshot.gap_categories == ("robots_policy",)


def test_coverage_status_empty_scope(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_coverage_fixture(conn)

    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))
    snapshot = service.get_coverage_status(CoverageScope(source_ids=(), domain_tags=()))

    assert snapshot.registered_source_count == 0
    assert snapshot.sources == ()


def test_refresh_enqueue_accepted(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_coverage_fixture(conn)

    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))
    receipt = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("src-a",),
            requested_at=NOW_DT,
        )
    )

    assert receipt.accepted is True
    assert receipt.deduplicated is False
    assert receipt.job_id  # non-empty


def test_refresh_dedup_same_day(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_coverage_fixture(conn)

    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))
    # First request
    service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("src-a",),
            requested_at=NOW_DT,
        )
    )
    # Second request same day
    receipt2 = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("src-a",),
            requested_at=NOW_DT,
        )
    )

    assert receipt2.accepted is False
    assert receipt2.deduplicated is True
