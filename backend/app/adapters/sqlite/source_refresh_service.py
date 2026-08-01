"""SQLite adapter for SourceRefreshService.

Reads source_coverage_state, source_domain_tags for coverage status.
Writes to refresh_jobs with atomic dedup for on-demand refresh.

## Same-day dedup is measured in the Application Timezone

The dedup key is `source_id + event_id + local calendar date` (Req 11.2-11.7).
"Local" means the Application Timezone, not UTC and not the caller's timezone:
`requested_at` arrives as an aware datetime from anywhere, and two requests
that a Taiwanese operator would call "the same day" must collapse to one job.
Formatting `requested_at` directly would put the boundary at 08:00 local time.

## Concurrency safety comes from the schema, not from a read-then-write

`refresh_jobs` has `UNIQUE (source_id, event_id, local_calendar_date)`. A single
`INSERT ... ON CONFLICT DO NOTHING` is therefore atomic: with N concurrent
writers exactly one insert reports `rowcount > 0` and the rest report 0. There
is no window between "check whether it exists" and "insert it", so no sleep or
retry loop is needed to make the outcome deterministic.

Losers still need the *winner's* job id, so a conflicting insert is followed by
a lookup on the same unique key inside the same transaction.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from app.adapters.sqlite.connection import execute_read, execute_transaction
from app.adapters.sqlite.mapping import parse_optional_datetime
from app.orchestration.data_contracts import CoverageMetadata
from app.orchestration.protocols import (
    CoverageScope,
    CoverageSnapshot,
    RefreshReceipt,
    RefreshRequest,
)

DEFAULT_APPLICATION_TIMEZONE = "Asia/Taipei"


def local_calendar_date(moment: datetime, timezone_name: str) -> str:
    """Return the `YYYY-MM-DD` calendar date of `moment` in the given timezone.

    Naive datetimes are rejected rather than assumed to be UTC: guessing the
    offset is exactly how a request lands on the wrong side of the day boundary.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("requested_at must be timezone-aware")
    return moment.astimezone(ZoneInfo(timezone_name)).date().isoformat()


class SqliteSourceRefreshService:
    """Coverage status reads and atomic refresh job enqueue."""

    def __init__(
        self,
        connection_factory: Callable[[], sqlite3.Connection],
        *,
        application_timezone: str = DEFAULT_APPLICATION_TIMEZONE,
    ) -> None:
        self._connection_factory = connection_factory
        # Constructed eagerly so an unknown timezone name fails at wiring time
        # rather than on the first refresh request.
        self._timezone = ZoneInfo(application_timezone)
        self._application_timezone = application_timezone

    @property
    def application_timezone(self) -> str:
        """The timezone whose calendar date defines "same day"."""
        return self._application_timezone

    def local_calendar_date(self, moment: datetime) -> str:
        """The `YYYY-MM-DD` date of `moment` in the Application Timezone."""
        return local_calendar_date(moment, self._application_timezone)

    def get_coverage_status(self, scope: CoverageScope) -> CoverageSnapshot:
        """Read current coverage state for the given scope."""
        return execute_read(
            self._connection_factory,
            lambda conn: self._read_coverage(conn, scope),
        )

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        """Atomically enqueue refresh jobs with same-day dedup."""
        return execute_transaction(
            self._connection_factory,
            lambda conn: self._enqueue_refresh(conn, request),
        )

    def _read_coverage(
        self, connection: sqlite3.Connection, scope: CoverageScope
    ) -> CoverageSnapshot:
        # One observed_at for the whole snapshot: CoverageSnapshot rejects
        # sources that disagree, because a snapshot stitched from several
        # moments is not a snapshot (Req 12.4).
        observed_at = datetime.now(self._timezone)

        # Determine which sources are in scope
        if not scope.source_ids and not scope.domain_tags:
            return CoverageSnapshot(
                scope=scope,
                observed_at=observed_at,
                registered_source_count=0,
                crawled_source_count=0,
                pending_crawl_source_count=0,
                error_source_count=0,
                indexed_document_count=0,
                sources=(),
                gap_categories=(),
            )

        # Build query based on scope
        if scope.source_ids and scope.domain_tags:
            # Intersection: sources must match both
            src_placeholders = ",".join("?" for _ in scope.source_ids)
            tag_placeholders = ",".join("?" for _ in scope.domain_tags)
            query = f"""
                SELECT scs.source_id, scs.crawl_status,
                       scs.last_successful_crawl_at,
                       scs.indexed_document_count,
                       scs.last_gap_category
                FROM source_coverage_state scs
                WHERE scs.source_id IN ({src_placeholders})
                  AND EXISTS (
                      SELECT 1 FROM source_domain_tags sdt
                      WHERE sdt.source_id = scs.source_id
                        AND sdt.domain_tag IN ({tag_placeholders})
                  )
                ORDER BY scs.source_id
            """
            params: list[str] = [*scope.source_ids, *scope.domain_tags]
        elif scope.source_ids:
            src_placeholders = ",".join("?" for _ in scope.source_ids)
            query = f"""
                SELECT scs.source_id, scs.crawl_status,
                       scs.last_successful_crawl_at,
                       scs.indexed_document_count,
                       scs.last_gap_category
                FROM source_coverage_state scs
                WHERE scs.source_id IN ({src_placeholders})
                ORDER BY scs.source_id
            """
            params = list(scope.source_ids)
        else:
            tag_placeholders = ",".join("?" for _ in scope.domain_tags)
            query = f"""
                SELECT scs.source_id, scs.crawl_status,
                       scs.last_successful_crawl_at,
                       scs.indexed_document_count,
                       scs.last_gap_category
                FROM source_coverage_state scs
                WHERE EXISTS (
                    SELECT 1 FROM source_domain_tags sdt
                    WHERE sdt.source_id = scs.source_id
                      AND sdt.domain_tag IN ({tag_placeholders})
                )
                ORDER BY scs.source_id
            """
            params = list(scope.domain_tags)

        rows = connection.execute(query, params).fetchall()

        # Load domain tags for each source
        sources: list[CoverageMetadata] = []
        gap_categories: set[str] = set()
        crawled_count = 0
        pending_count = 0
        error_count = 0
        total_docs = 0

        for row in rows:
            source_id = str(row[0])
            crawl_status = str(row[1])
            last_crawled = str(row[2]) if row[2] is not None else None
            doc_count = int(row[3])
            gap_cat = str(row[4]) if row[4] is not None else None

            # Load domain tags for this source
            tag_rows = connection.execute(
                """
                SELECT domain_tag FROM source_domain_tags
                WHERE source_id = ? ORDER BY domain_tag
                """,
                (source_id,),
            ).fetchall()
            domain_tags = tuple(str(r[0]) for r in tag_rows)

            sources.append(
                CoverageMetadata(
                    source_id=source_id,
                    crawl_status=crawl_status,  # type: ignore[arg-type]
                    last_crawled_at=parse_optional_datetime(
                        last_crawled, "last_crawled_at"
                    ),
                    indexed_document_count=doc_count,
                    domain_tags=domain_tags,
                    observed_at=observed_at,
                )
            )

            if crawl_status == "crawled":
                crawled_count += 1
            elif crawl_status == "pending_crawl":
                pending_count += 1
            elif crawl_status == "error":
                error_count += 1
                if gap_cat:
                    gap_categories.add(gap_cat)

            total_docs += doc_count

        return CoverageSnapshot(
            scope=scope,
            observed_at=observed_at,
            registered_source_count=len(sources),
            crawled_source_count=crawled_count,
            pending_crawl_source_count=pending_count,
            error_source_count=error_count,
            indexed_document_count=total_docs,
            sources=tuple(sources),
            gap_categories=tuple(sorted(gap_categories)),
        )

    def _enqueue_refresh(
        self,
        connection: sqlite3.Connection,
        request: RefreshRequest,
    ) -> RefreshReceipt:
        job_id = str(uuid.uuid4())
        local_date = self.local_calendar_date(request.requested_at)
        requested_at_iso = request.requested_at.isoformat()

        accepted_count = 0
        deduplicated_count = 0
        existing_job_ids: list[str] = []

        for source_id in request.source_ids:
            dedup_key = f"{source_id}|{request.event_id}|{local_date}"
            cursor = connection.execute(
                """
                INSERT INTO refresh_jobs (
                    job_id, source_id, event_id,
                    local_calendar_date, dedup_key,
                    requested_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, event_id, local_calendar_date)
                DO NOTHING
                """,
                (
                    job_id,
                    source_id,
                    request.event_id,
                    local_date,
                    dedup_key,
                    requested_at_iso,
                ),
            )
            if cursor.rowcount > 0:
                accepted_count += 1
                continue

            deduplicated_count += 1
            # The conflicting row is the winner for this key. Callers that lost
            # the race still need its job id so every same-day request for the
            # same key reports the same job.
            row = connection.execute(
                """
                SELECT job_id FROM refresh_jobs
                WHERE source_id = ? AND event_id = ? AND local_calendar_date = ?
                """,
                (source_id, request.event_id, local_date),
            ).fetchone()
            if row is not None:
                existing_job_ids.append(str(row[0]))

        accepted = accepted_count > 0
        deduplicated = deduplicated_count > 0 and not accepted

        if not accepted and existing_job_ids:
            # Report the job that actually exists rather than a fresh uuid that
            # was never written. Sorted so the answer does not depend on the
            # order of request.source_ids.
            job_id = sorted(existing_job_ids)[0]

        return RefreshReceipt(
            job_id=job_id,
            accepted=accepted,
            deduplicated=deduplicated,
        )
