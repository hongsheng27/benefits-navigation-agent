"""PostgreSQL adapter for SourceRefreshService.

Same semantics as SqliteSourceRefreshService — reads coverage state and
enqueues refresh jobs with same-day dedup.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.adapters.postgresql.connection import execute_read, execute_transaction
from app.orchestration.data_contracts import CoverageMetadata
from app.orchestration.protocols import (
    CoverageScope,
    CoverageSnapshot,
    RefreshReceipt,
    RefreshRequest,
)

DEFAULT_APPLICATION_TIMEZONE = "Asia/Taipei"


class PgSourceRefreshService:
    """Coverage status reads and atomic refresh job enqueue via PostgreSQL."""

    def __init__(
        self,
        pool: ConnectionPool,
        *,
        application_timezone: str = DEFAULT_APPLICATION_TIMEZONE,
    ) -> None:
        self._pool = pool
        self._timezone = ZoneInfo(application_timezone)
        self._application_timezone = application_timezone

    @property
    def application_timezone(self) -> str:
        return self._application_timezone

    def local_calendar_date(self, moment: datetime) -> str:
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        return moment.astimezone(self._timezone).date().isoformat()

    def get_coverage_status(self, scope: CoverageScope) -> CoverageSnapshot:
        return execute_read(
            self._pool,
            lambda conn: self._read_coverage(conn, scope),
        )

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        return execute_transaction(
            self._pool,
            lambda conn: self._enqueue_refresh(conn, request),
        )

    def _read_coverage(
        self, conn: psycopg.Connection, scope: CoverageScope
    ) -> CoverageSnapshot:
        observed_at = datetime.now(self._timezone)

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

        with conn.cursor(row_factory=dict_row) as cur:
            if scope.source_ids and scope.domain_tags:
                cur.execute(
                    """
                    SELECT scs.source_id, scs.crawl_status,
                           scs.last_successful_crawl_at,
                           scs.indexed_document_count,
                           scs.last_gap_category
                    FROM source_coverage_state scs
                    WHERE scs.source_id = ANY(%s)
                      AND EXISTS (
                          SELECT 1 FROM source_domain_tags sdt
                          WHERE sdt.source_id = scs.source_id
                            AND sdt.domain_tag = ANY(%s)
                      )
                    ORDER BY scs.source_id
                    """,
                    (list(scope.source_ids), list(scope.domain_tags)),
                )
            elif scope.source_ids:
                cur.execute(
                    """
                    SELECT scs.source_id, scs.crawl_status,
                           scs.last_successful_crawl_at,
                           scs.indexed_document_count,
                           scs.last_gap_category
                    FROM source_coverage_state scs
                    WHERE scs.source_id = ANY(%s)
                    ORDER BY scs.source_id
                    """,
                    (list(scope.source_ids),),
                )
            else:
                cur.execute(
                    """
                    SELECT scs.source_id, scs.crawl_status,
                           scs.last_successful_crawl_at,
                           scs.indexed_document_count,
                           scs.last_gap_category
                    FROM source_coverage_state scs
                    WHERE EXISTS (
                        SELECT 1 FROM source_domain_tags sdt
                        WHERE sdt.source_id = scs.source_id
                          AND sdt.domain_tag = ANY(%s)
                    )
                    ORDER BY scs.source_id
                    """,
                    (list(scope.domain_tags),),
                )

            rows = cur.fetchall()

            sources: list[CoverageMetadata] = []
            gap_categories: set[str] = set()
            crawled_count = 0
            pending_count = 0
            error_count = 0
            total_docs = 0

            for row in rows:
                source_id = row["source_id"]
                crawl_status = row["crawl_status"]
                doc_count = row["indexed_document_count"]
                gap_cat = row["last_gap_category"]

                # Load domain tags
                cur.execute(
                    """
                    SELECT domain_tag FROM source_domain_tags
                    WHERE source_id = %s ORDER BY domain_tag
                    """,
                    (source_id,),
                )
                domain_tags = tuple(r["domain_tag"] for r in cur.fetchall())

                sources.append(
                    CoverageMetadata(
                        source_id=source_id,
                        crawl_status=crawl_status,
                        last_crawled_at=row["last_successful_crawl_at"],
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
        conn: psycopg.Connection,
        request: RefreshRequest,
    ) -> RefreshReceipt:
        job_id = str(uuid.uuid4())
        local_date = self.local_calendar_date(request.requested_at)
        requested_at_iso = request.requested_at.isoformat()

        accepted_count = 0
        deduplicated_count = 0
        existing_job_ids: list[str] = []

        with conn.cursor(row_factory=dict_row) as cur:
            for source_id in request.source_ids:
                dedup_key = f"{source_id}|{request.event_id}|{local_date}"

                # Use INSERT ... ON CONFLICT for atomic dedup
                cur.execute(
                    """
                    INSERT INTO refresh_jobs (
                        job_id, source_id, event_id,
                        local_calendar_date, dedup_key, requested_at
                    ) VALUES (%s, %s, %s, %s::DATE, %s, %s::TIMESTAMPTZ)
                    ON CONFLICT (source_id, event_id, local_calendar_date)
                    DO NOTHING
                    """,
                    (job_id, source_id, request.event_id,
                     local_date, dedup_key, requested_at_iso),
                )

                if cur.rowcount > 0:
                    accepted_count += 1
                    continue

                deduplicated_count += 1
                cur.execute(
                    """
                    SELECT job_id FROM refresh_jobs
                    WHERE source_id = %s AND event_id = %s
                      AND local_calendar_date = %s::DATE
                    """,
                    (source_id, request.event_id, local_date),
                )
                row = cur.fetchone()
                if row is not None:
                    existing_job_ids.append(row["job_id"])

        accepted = accepted_count > 0
        deduplicated = deduplicated_count > 0 and not accepted

        if not accepted and existing_job_ids:
            job_id = sorted(existing_job_ids)[0]

        return RefreshReceipt(
            job_id=job_id,
            accepted=accepted,
            deduplicated=deduplicated,
        )
