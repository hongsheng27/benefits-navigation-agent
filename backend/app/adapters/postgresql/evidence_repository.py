"""PostgreSQL adapter for the Evidence repository.

Same semantics as SqliteEvidenceRepository — reads verified evidence
from verified official sources.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.adapters.postgresql.connection import execute_read
from app.orchestration.data_contracts import Citation


class PgEvidenceRepository:
    """Reads official evidence from PostgreSQL."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_citations(self, item_id: str) -> tuple[Citation, ...]:
        """Get all verified citations linked to a program."""
        return execute_read(
            self._pool,
            lambda conn: self._citations_for_program(conn, item_id),
        )

    def get_citations_for_references(
        self,
        item_id: str,
        source_references: Sequence[str],
    ) -> tuple[Citation, ...]:
        """Get citations for exact source references."""
        if not source_references:
            return ()
        return execute_read(
            self._pool,
            lambda conn: self._citations_by_reference(conn, item_id, source_references),
        )

    def _citations_for_program(
        self, conn: psycopg.Connection, program_id: str
    ) -> tuple[Citation, ...]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT DISTINCT
                    sd.document_id,
                    sd.title,
                    sd.publisher_name,
                    sd.canonical_url,
                    ee.excerpt,
                    sd.published_at,
                    sd.effective_at,
                    sd.retrieved_at
                FROM program_evidence_links pel
                JOIN evidence_excerpts ee
                  ON ee.evidence_id = pel.evidence_id
                JOIN source_documents sd
                  ON sd.document_id = ee.document_id
                WHERE pel.program_id = %s
                  AND pel.review_status = 'verified'
                  AND ee.review_status = 'verified'
                  AND sd.review_status = 'verified'
                ORDER BY sd.document_id, ee.evidence_id
                """,
                (program_id,),
            )
            return self._map_rows(cur.fetchall())

    def _citations_by_reference(
        self,
        conn: psycopg.Connection,
        program_id: str,
        source_references: Sequence[str],
    ) -> tuple[Citation, ...]:
        with conn.cursor(row_factory=dict_row) as cur:
            # Find current approved rule version
            cur.execute(
                """
                SELECT rv.rule_version_id
                FROM rule_definitions rd
                JOIN rule_versions rv ON rv.rule_id = rd.rule_id
                WHERE rd.program_id = %s
                  AND rv.is_current = TRUE
                  AND rv.approval_status = 'approved'
                """,
                (program_id,),
            )
            rule_row = cur.fetchone()
            if rule_row is None:
                return ()

            rule_version_id = rule_row["rule_version_id"]

            cur.execute(
                """
                SELECT DISTINCT
                    sd.document_id,
                    sd.title,
                    sd.publisher_name,
                    sd.canonical_url,
                    ee.excerpt,
                    sd.published_at,
                    sd.effective_at,
                    sd.retrieved_at
                FROM source_reference_evidence sre
                JOIN evidence_excerpts ee
                  ON ee.evidence_id = sre.evidence_id
                JOIN source_documents sd
                  ON sd.document_id = ee.document_id
                WHERE sre.rule_version_id = %s
                  AND sre.source_reference = ANY(%s)
                  AND ee.review_status = 'verified'
                  AND sd.review_status = 'verified'
                ORDER BY sd.document_id, ee.evidence_id
                """,
                (rule_version_id, list(source_references)),
            )
            return self._map_rows(cur.fetchall())

    def _map_rows(self, rows: list[dict]) -> tuple[Citation, ...]:
        citations: list[Citation] = []
        for r in rows:
            citations.append(
                Citation(
                    document_id=r["document_id"],
                    title=r["title"],
                    publisher_name=r["publisher_name"],
                    canonical_url=r["canonical_url"],
                    excerpt=r["excerpt"],
                    published_at=r["published_at"],
                    effective_at=r.get("effective_at"),
                    retrieved_at=r["retrieved_at"],
                )
            )
        return tuple(citations)
