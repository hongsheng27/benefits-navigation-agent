"""Integration tests for same-day refresh dedup (Requirements 11.2-11.7).

Covers:
- The dedup key is the Application Timezone calendar date, not the UTC date
- Two requests either side of the local midnight boundary produce two jobs
- Two requests from different UTC offsets on the same local day collapse to one
- Concurrent writers reach exactly one accepted receipt via a barrier, with no
  sleeps and no dependence on thread scheduling
- Every deduplicated caller learns the winning job id
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from backend.app.adapters.sqlite.migrations import migrate_database
from backend.app.adapters.sqlite.source_refresh_service import (
    SqliteSourceRefreshService,
    local_calendar_date,
)
from backend.app.orchestration.protocols import RefreshRequest

TAIPEI = "Asia/Taipei"
NOW = "2026-07-30T00:00:00+00:00"
SOURCE_IDS = ("synth-src-a", "synth-src-b", "synth-src-c")


def _setup_database(tmp_path: Path) -> Path:
    database = tmp_path / "refresh-dedup.db"
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
            [(source_id, source_id, NOW, NOW) for source_id in SOURCE_IDS],
        )
    return database


def _service(database: Path, timezone_name: str = TAIPEI) -> SqliteSourceRefreshService:
    return SqliteSourceRefreshService(
        lambda: sqlite3.connect(database, timeout=30.0),
        application_timezone=timezone_name,
    )


def _job_rows(database: Path) -> list[tuple[str, str, str]]:
    with closing(sqlite3.connect(database)) as connection:
        return [
            (str(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                """
                SELECT job_id, source_id, local_calendar_date
                FROM refresh_jobs ORDER BY source_id, local_calendar_date
                """
            )
        ]


# ---------------------------------------------------------------------------
# Timezone-aware calendar date
# ---------------------------------------------------------------------------


def test_local_calendar_date_uses_application_timezone() -> None:
    """15:59 UTC is still 30 July in Taipei; 16:01 UTC is already 31 July."""
    before = datetime(2026, 7, 30, 15, 59, tzinfo=UTC)
    after = datetime(2026, 7, 30, 16, 1, tzinfo=UTC)
    assert local_calendar_date(before, TAIPEI) == "2026-07-30"
    assert local_calendar_date(after, TAIPEI) == "2026-07-31"
    # The same two moments are the same UTC day, which is why UTC cannot be
    # used as the dedup calendar.
    assert before.date() == after.date()


def test_local_calendar_date_rejects_naive_datetime() -> None:
    """A naive datetime has no defined calendar date in any timezone."""
    try:
        local_calendar_date(datetime(2026, 7, 30, 12, 0), TAIPEI)
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError for a naive datetime")


def test_same_local_day_across_offsets_deduplicates(tmp_path: Path) -> None:
    """Two callers in different offsets on the same Taipei day get one job."""
    database = _setup_database(tmp_path)
    service = _service(database)

    # 2026-07-30 09:00 Taipei expressed two ways.
    from_utc = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)
    from_plus_nine = datetime(2026, 7, 30, 10, 0, tzinfo=timezone(timedelta(hours=9)))
    assert from_utc == from_plus_nine

    first = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=(SOURCE_IDS[0],),
            requested_at=from_utc,
        )
    )
    second = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=(SOURCE_IDS[0],),
            requested_at=from_plus_nine,
        )
    )

    assert first.accepted is True
    assert first.deduplicated is False
    assert second.accepted is False
    assert second.deduplicated is True
    assert second.job_id == first.job_id
    assert _job_rows(database) == [(first.job_id, SOURCE_IDS[0], "2026-07-30")]


def test_local_midnight_boundary_creates_two_jobs(tmp_path: Path) -> None:
    """23:59 and 00:01 Taipei are different days, so both are accepted."""
    database = _setup_database(tmp_path)
    service = _service(database)

    before_midnight = datetime(2026, 7, 30, 15, 59, tzinfo=UTC)  # 23:59 Taipei
    after_midnight = datetime(2026, 7, 30, 16, 1, tzinfo=UTC)  # 00:01 Taipei

    first = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=(SOURCE_IDS[0],),
            requested_at=before_midnight,
        )
    )
    second = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=(SOURCE_IDS[0],),
            requested_at=after_midnight,
        )
    )

    assert first.accepted is True
    assert second.accepted is True
    assert second.deduplicated is False
    assert second.job_id != first.job_id
    assert _job_rows(database) == [
        (first.job_id, SOURCE_IDS[0], "2026-07-30"),
        (second.job_id, SOURCE_IDS[0], "2026-07-31"),
    ]


def test_utc_timezone_shifts_the_boundary(tmp_path: Path) -> None:
    """With UTC configured, the same two moments collapse into one day.

    This is the failure mode the Application Timezone exists to prevent: it is
    not a formatting preference, it moves which requests count as the same day.
    """
    database = _setup_database(tmp_path)
    service = _service(database, timezone_name="UTC")

    first = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=(SOURCE_IDS[0],),
            requested_at=datetime(2026, 7, 30, 15, 59, tzinfo=UTC),
        )
    )
    second = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=(SOURCE_IDS[0],),
            requested_at=datetime(2026, 7, 30, 16, 1, tzinfo=UTC),
        )
    )

    assert first.accepted is True
    assert second.accepted is False
    assert second.deduplicated is True


# ---------------------------------------------------------------------------
# Dedup scope: key is source + event + local date
# ---------------------------------------------------------------------------


def test_different_event_ids_are_independent(tmp_path: Path) -> None:
    """Dedup is per event, so a second life event still triggers a refresh."""
    database = _setup_database(tmp_path)
    service = _service(database)
    moment = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)

    first = service.request_on_demand_refresh(
        RefreshRequest("spouse_death", (SOURCE_IDS[0],), moment)
    )
    second = service.request_on_demand_refresh(
        RefreshRequest("parent_death", (SOURCE_IDS[0],), moment)
    )

    assert first.accepted is True
    assert second.accepted is True
    assert len(_job_rows(database)) == 2


def test_partially_new_source_set_is_accepted_not_deduplicated(
    tmp_path: Path,
) -> None:
    """A request that adds one unseen source is accepted, not marked dedup.

    `accepted` and `deduplicated` answer different questions: "did anything get
    queued" and "was everything already queued". A request that queues one new
    source is not a duplicate even though the other two were.
    """
    database = _setup_database(tmp_path)
    service = _service(database)
    moment = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)

    service.request_on_demand_refresh(
        RefreshRequest("spouse_death", SOURCE_IDS[:2], moment)
    )
    second = service.request_on_demand_refresh(
        RefreshRequest("spouse_death", SOURCE_IDS, moment)
    )

    assert second.accepted is True
    assert second.deduplicated is False
    assert len(_job_rows(database)) == 3


def test_fully_repeated_source_set_reports_winning_job_id(tmp_path: Path) -> None:
    """A fully duplicate request reports the job id that actually exists."""
    database = _setup_database(tmp_path)
    service = _service(database)
    moment = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)

    first = service.request_on_demand_refresh(
        RefreshRequest("spouse_death", SOURCE_IDS, moment)
    )
    second = service.request_on_demand_refresh(
        RefreshRequest("spouse_death", SOURCE_IDS, moment)
    )

    assert second.accepted is False
    assert second.deduplicated is True
    assert second.job_id == first.job_id
    stored_job_ids = {row[0] for row in _job_rows(database)}
    assert second.job_id in stored_job_ids


# ---------------------------------------------------------------------------
# Concurrency: exactly one winner, decided by the unique index
# ---------------------------------------------------------------------------


def test_concurrent_requests_produce_exactly_one_job(tmp_path: Path) -> None:
    """N threads released by a barrier produce one job and one accepted receipt.

    The barrier removes the need to sleep: every thread is inside
    `request_on_demand_refresh` before any of them can commit, so the outcome
    is decided by the UNIQUE index rather than by who started first.
    """
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")

    thread_count = 8
    barrier = threading.Barrier(thread_count)
    moment = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)
    results: list[tuple[bool, bool, str]] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        # Each thread gets its own connection: sqlite3 connections are not
        # shared across threads, and sharing one would serialise the race away.
        service = _service(database)
        try:
            barrier.wait(timeout=30)
            receipt = service.request_on_demand_refresh(
                RefreshRequest("spouse_death", (SOURCE_IDS[0],), moment)
            )
        except BaseException as error:  # noqa: BLE001 — surfaced via assertion
            with lock:
                errors.append(error)
            return
        with lock:
            results.append((receipt.accepted, receipt.deduplicated, receipt.job_id))

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == [], f"unexpected errors: {errors}"
    assert len(results) == thread_count

    accepted = [row for row in results if row[0]]
    deduplicated = [row for row in results if not row[0]]
    assert len(accepted) == 1, "exactly one writer may win the unique key"
    assert len(deduplicated) == thread_count - 1
    assert all(row[1] is True for row in deduplicated)

    rows = _job_rows(database)
    assert len(rows) == 1
    winning_job_id = rows[0][0]
    assert accepted[0][2] == winning_job_id
    assert {row[2] for row in deduplicated} == {winning_job_id}


def test_concurrent_requests_across_two_days_produce_two_jobs(
    tmp_path: Path,
) -> None:
    """Concurrency does not merge distinct local dates."""
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")

    moments = (
        datetime(2026, 7, 30, 15, 59, tzinfo=UTC),  # 30 July Taipei
        datetime(2026, 7, 30, 16, 1, tzinfo=UTC),  # 31 July Taipei
    )
    thread_count = 8
    barrier = threading.Barrier(thread_count)
    results: list[bool] = []
    lock = threading.Lock()

    def worker(index: int) -> None:
        service = _service(database)
        barrier.wait(timeout=30)
        receipt = service.request_on_demand_refresh(
            RefreshRequest("spouse_death", (SOURCE_IDS[0],), moments[index % 2])
        )
        with lock:
            results.append(receipt.accepted)

    threads = [
        threading.Thread(target=worker, args=(index,)) for index in range(thread_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert sum(results) == 2, "one winner per local calendar date"
    dates = {row[2] for row in _job_rows(database)}
    assert dates == {"2026-07-30", "2026-07-31"}
