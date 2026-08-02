"""SQLite adapter for the Evidence repository.

Reads evidence_excerpts, source_documents, program_evidence_links,
and source_reference_evidence tables. Only returns verified evidence
from verified official sources.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence

from app.adapters.sqlite.connection import execute_read
from app.adapters.sqlite.mapping import parse_optional_datetime
from app.orchestration.data_contracts import Citation


class SqliteEvidenceRepository:
    """Reads official evidence from SQLite."""

    def __init__(self, connection_factory: Callable[[], sqlite3.Connection]) -> None:
        self._connection_factory = connection_factory

    def get_citations(self, item_id: str) -> tuple[Citation, ...]:
        """Get all verified citations linked to a program (item_id=program_id).

        Only returns evidence_excerpts with review_status='verified'
        from source_documents with review_status='verified'.
        """
        return execute_read(
            self._connection_factory,
            lambda conn: self._citations_for_program(conn, item_id),
        )

    def get_candidate_citations(self, item_id: str) -> tuple[Citation, ...]:
        """Get display-only candidate or reviewed official material.

        This method is intentionally separate from ``get_citations`` so an
        unreviewed excerpt can never satisfy an eligibility evidence gate.
        """
        return execute_read(
            self._connection_factory,
            lambda conn: self._candidate_citations_for_program(conn, item_id),
        )

    def get_citations_for_references(
        self,
        item_id: str,
        source_references: Sequence[str],
    ) -> tuple[Citation, ...]:
        """Get citations for exact source references.

        Uses source_reference_evidence to find evidence linked to
        specific rule version source references.
        """
        if not source_references:
            return ()
        return execute_read(
            self._connection_factory,
            lambda conn: self._citations_by_reference(conn, item_id, source_references),
        )

    def _citations_for_program(
        self, connection: sqlite3.Connection, program_id: str
    ) -> tuple[Citation, ...]:
        rows = connection.execute(
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
            WHERE pel.program_id = ?
              AND pel.review_status = 'verified'
              AND ee.review_status = 'verified'
              AND sd.review_status = 'verified'
            ORDER BY sd.document_id, ee.evidence_id
            """,
            (program_id,),
        ).fetchall()
        return self._map_rows(rows)

    def _candidate_citations_for_program(
        self, connection: sqlite3.Connection, program_id: str
    ) -> tuple[Citation, ...]:
        rows = connection.execute(
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
            WHERE pel.program_id = ?
              AND pel.review_status IN ('candidate', 'under_review', 'verified')
              AND ee.review_status IN ('candidate', 'under_review', 'verified')
              AND sd.review_status IN (
                  'candidate', 'under_review', 'verified', 'stale'
              )
            ORDER BY sd.document_id, ee.evidence_id
            """,
            (program_id,),
        ).fetchall()
        return self._map_rows(rows)

    def _citations_by_reference(
        self,
        connection: sqlite3.Connection,
        program_id: str,
        source_references: Sequence[str],
    ) -> tuple[Citation, ...]:
        # Find the current approved rule version for this program
        rule_version_row = connection.execute(
            """
            SELECT rv.rule_version_id
            FROM rule_definitions rd
            JOIN rule_versions rv ON rv.rule_id = rd.rule_id
            WHERE rd.program_id = ?
              AND rv.is_current = 1
              AND rv.approval_status = 'approved'
            """,
            (program_id,),
        ).fetchone()
        if rule_version_row is None:
            return ()
        rule_version_id = str(rule_version_row[0])

        # Build placeholders for source_references
        placeholders = ",".join("?" for _ in source_references)
        params: list[str] = [rule_version_id, *source_references]

        rows = connection.execute(
            f"""
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
            WHERE sre.rule_version_id = ?
              AND sre.source_reference IN ({placeholders})
              AND ee.review_status = 'verified'
              AND sd.review_status = 'verified'
            ORDER BY sd.document_id, ee.evidence_id
            """,
            params,
        ).fetchall()
        return self._map_rows(rows)

    def _map_rows(self, rows: list[tuple[object, ...]]) -> tuple[Citation, ...]:
        citations: list[Citation] = []
        for row in rows:
            citations.append(
                Citation(
                    document_id=str(row[0]),
                    title=str(row[1]),
                    publisher=str(row[2]),
                    url=str(row[3]),
                    excerpt=str(row[4]),
                    published_at=parse_optional_datetime(
                        str(row[5]) if row[5] else None, "published_at"
                    ),
                    effective_at=parse_optional_datetime(
                        str(row[6]) if row[6] else None, "effective_at"
                    ),
                    retrieved_at=parse_optional_datetime(
                        str(row[7]) if row[7] else None, "retrieved_at"
                    ),
                )
            )
        return tuple(citations)
