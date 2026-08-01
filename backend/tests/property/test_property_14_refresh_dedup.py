"""Property 14: Concurrent same-day refresh dedup.

**Validates: Requirements 11.2-11.7**

For any N >= 1 requests carrying the same dedup key (source_id + event_id +
Application Timezone calendar date), issued in any interleaving:

1. Exactly one refresh job row exists afterwards.
2. Exactly one receipt reports `deduplicated=False`.
3. The remaining N-1 receipts report `deduplicated=True`.
4. Every receipt names the same job id.

The property is checked twice over the same generated inputs: once sequentially
and once with real threads released by a barrier. The sequential run pins the
semantics; the threaded run proves the semantics survive contention.
"""

from __future__ import annotations

import sqlite3
import tempfile
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.adapters.sqlite.migrations import migrate_database
from app.adapters.sqlite.source_refresh_service import (
    SqliteSourceRefreshService,
    local_calendar_date,
)
from app.orchestration.protocols import RefreshReceipt, RefreshRequest

TAIPEI = "Asia/Taipei"
NOW = "2026-07-30T00:00:00+00:00"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_source_ids = st.sampled_from(["synth-src-a", "synth-src-b", "synth-src-c"])
_event_ids = st.sampled_from(["spouse_death", "parent_death", "child_birth"])
_request_counts = st.integers(min_value=1, max_value=6)

# Offsets used to express the *same instant* from different clocks. Same-day
# dedup must not depend on which offset the caller happened to send.
_offsets = st.sampled_from([0, 8, -5, 9, 13, -11])

_base_instants = st.datetimes(
    min_value=datetime(2026, 1, 1, 0, 0),
    max_value=datetime(2026, 12, 30, 23, 0),
    timezones=st.just(UTC),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_database(directory: Path) -> Path:
    database = directory / "property14.db"
    migrate_database(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
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
    return database


def _service(database: Path) -> SqliteSourceRefreshService:
    return SqliteSourceRefreshService(
        lambda: sqlite3.connect(database, timeout=30.0),
        application_timezone=TAIPEI,
    )


def _job_rows(database: Path) -> list[tuple[str, str, str]]:
    with closing(sqlite3.connect(database)) as connection:
        return [
            (str(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                "SELECT job_id, source_id, local_calendar_date FROM refresh_jobs"
            )
        ]


def _assert_exactly_one_winner(
    receipts: list[RefreshReceipt],
    database: Path,
    expected_date: str,
    source_id: str,
) -> None:
    """The shared post-condition for both the sequential and threaded runs."""
    accepted = [receipt for receipt in receipts if receipt.accepted]
    deduplicated = [receipt for receipt in receipts if not receipt.accepted]

    assert len(accepted) == 1, (
        f"expected exactly one accepted receipt, got {len(accepted)} "
        f"out of {len(receipts)}"
    )
    assert accepted[0].deduplicated is False
    assert all(receipt.deduplicated is True for receipt in deduplicated)
    assert len(deduplicated) == len(receipts) - 1

    rows = _job_rows(database)
    assert len(rows) == 1, f"expected exactly one job row, got {rows}"
    job_id, stored_source_id, stored_date = rows[0]
    assert stored_source_id == source_id
    assert stored_date == expected_date
    assert {receipt.job_id for receipt in receipts} == {job_id}


# ---------------------------------------------------------------------------
# Property 14.1 — sequential requests with the same key
# ---------------------------------------------------------------------------


@given(
    source_id=_source_ids,
    event_id=_event_ids,
    instant=_base_instants,
    count=_request_counts,
    offsets=st.lists(_offsets, min_size=1, max_size=6),
)
@settings(
    max_examples=200,
    deadline=5000,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_sequential_same_key_requests_yield_one_job(
    source_id: str,
    event_id: str,
    instant: datetime,
    count: int,
    offsets: list[int],
) -> None:
    """N sequential requests for the same key create exactly one job."""
    expected_date = local_calendar_date(instant, TAIPEI)

    with tempfile.TemporaryDirectory() as directory:
        database = _make_database(Path(directory))
        service = _service(database)

        receipts: list[RefreshReceipt] = []
        for index in range(count):
            # Same instant, expressed in a rotating set of UTC offsets. The
            # dedup key must not move just because the caller's clock did.
            offset = offsets[index % len(offsets)]
            moment = instant.astimezone(timezone(timedelta(hours=offset)))
            assert moment == instant
            receipts.append(
                service.request_on_demand_refresh(
                    RefreshRequest(
                        event_id=event_id,
                        source_ids=(source_id,),
                        requested_at=moment,
                    )
                )
            )

        _assert_exactly_one_winner(receipts, database, expected_date, source_id)


# ---------------------------------------------------------------------------
# Property 14.2 — concurrent requests with the same key
# ---------------------------------------------------------------------------


@given(
    source_id=_source_ids,
    event_id=_event_ids,
    instant=_base_instants,
    count=st.integers(min_value=2, max_value=5),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_concurrent_same_key_requests_yield_one_job(
    source_id: str,
    event_id: str,
    instant: datetime,
    count: int,
) -> None:
    """N threads released together still create exactly one job.

    A barrier is used rather than a sleep: the assertion is about the unique
    index, not about timing, so the test must not depend on how long a thread
    happens to take.
    """
    expected_date = local_calendar_date(instant, TAIPEI)

    with tempfile.TemporaryDirectory() as directory:
        database = _make_database(Path(directory))
        barrier = threading.Barrier(count)
        receipts: list[RefreshReceipt] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def worker() -> None:
            service = _service(database)
            try:
                barrier.wait(timeout=30)
                receipt = service.request_on_demand_refresh(
                    RefreshRequest(
                        event_id=event_id,
                        source_ids=(source_id,),
                        requested_at=instant,
                    )
                )
            except BaseException as error:  # noqa: BLE001 — reported below
                with lock:
                    errors.append(error)
                return
            with lock:
                receipts.append(receipt)

        threads = [threading.Thread(target=worker) for _ in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert errors == [], f"unexpected errors: {errors}"
        assert len(receipts) == count
        _assert_exactly_one_winner(receipts, database, expected_date, source_id)


# ---------------------------------------------------------------------------
# Property 14.3 — distinct keys never collapse
# ---------------------------------------------------------------------------


@given(
    source_id=_source_ids,
    event_id=_event_ids,
    instant=_base_instants,
    day_offsets=st.lists(
        st.integers(min_value=0, max_value=4), min_size=1, max_size=5, unique=True
    ),
)
@settings(
    max_examples=100,
    deadline=5000,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_distinct_local_dates_each_get_their_own_job(
    source_id: str,
    event_id: str,
    instant: datetime,
    day_offsets: list[int],
) -> None:
    """Dedup collapses a day, never two different days."""
    with tempfile.TemporaryDirectory() as directory:
        database = _make_database(Path(directory))
        service = _service(database)

        expected_dates = set()
        for offset in day_offsets:
            moment = instant + timedelta(days=offset)
            expected_dates.add(local_calendar_date(moment, TAIPEI))
            service.request_on_demand_refresh(
                RefreshRequest(
                    event_id=event_id,
                    source_ids=(source_id,),
                    requested_at=moment,
                )
            )

        stored_dates = {row[2] for row in _job_rows(database)}
        assert stored_dates == expected_dates
        assert len(_job_rows(database)) == len(expected_dates)


@given(
    event_id=_event_ids,
    instant=_base_instants,
    source_ids=st.lists(_source_ids, min_size=1, max_size=3, unique=True),
)
@settings(
    max_examples=100,
    deadline=5000,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_each_source_gets_its_own_job_on_the_same_day(
    event_id: str,
    instant: datetime,
    source_ids: list[str],
) -> None:
    """The key includes the source, so distinct sources are not deduplicated."""
    with tempfile.TemporaryDirectory() as directory:
        database = _make_database(Path(directory))
        service = _service(database)

        first = service.request_on_demand_refresh(
            RefreshRequest(
                event_id=event_id,
                source_ids=tuple(source_ids),
                requested_at=instant,
            )
        )
        repeat = service.request_on_demand_refresh(
            RefreshRequest(
                event_id=event_id,
                source_ids=tuple(source_ids),
                requested_at=instant,
            )
        )

        assert first.accepted is True
        assert first.deduplicated is False
        assert repeat.accepted is False
        assert repeat.deduplicated is True

        rows = _job_rows(database)
        assert len(rows) == len(source_ids)
        assert {row[1] for row in rows} == set(source_ids)


# ---------------------------------------------------------------------------
# Property 14.4 — the calendar date is the Application Timezone's
# ---------------------------------------------------------------------------


@given(instant=_base_instants, offset=_offsets)
@settings(max_examples=200, deadline=5000)
def test_local_calendar_date_is_offset_independent(
    instant: datetime, offset: int
) -> None:
    """The same instant yields the same local date from any caller offset."""
    shifted = instant.astimezone(timezone(timedelta(hours=offset)))
    assert shifted == instant
    assert local_calendar_date(shifted, TAIPEI) == local_calendar_date(instant, TAIPEI)


@given(instant=_base_instants)
@settings(max_examples=200, deadline=5000)
def test_local_calendar_date_matches_taipei_wall_clock(instant: datetime) -> None:
    """Taipei is UTC+8 year round, so the date is the UTC date shifted by 8h."""
    expected = (instant + timedelta(hours=8)).astimezone(UTC).date().isoformat()
    assert local_calendar_date(instant, TAIPEI) == expected
