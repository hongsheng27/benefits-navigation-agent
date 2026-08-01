"""Integration tests for SqliteEvidenceRepository."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from backend.app.adapters.sqlite.evidence_repository import (
    SqliteEvidenceRepository,
)
from backend.app.adapters.sqlite.migrations import migrate_database

NOW = "2026-07-30T00:00:00+00:00"


def _setup_database(tmp_path: Path) -> Path:
    database = tmp_path / "evidence.db"
    migrate_database(database)
    return database


def _insert_evidence_fixture(connection: sqlite3.Connection) -> None:
    """Insert verified evidence with verified source documents."""
    connection.execute("PRAGMA foreign_keys = ON")
    # Source registry + documents
    connection.execute(
        """
        INSERT INTO source_registry (
            source_id, name, source_type, base_url, entry_url,
            canonical_host, official_status, access_method,
            connection_status, created_at, updated_at
        ) VALUES (
            'src-1', 'Test Source', 'agency_site',
            'https://example.gov.tw', 'https://example.gov.tw/e',
            'example.gov.tw', 'verified_official', 'manual_seed',
            'active', ?, ?
        )
        """,
        (NOW, NOW),
    )
    connection.execute(
        """
        INSERT INTO source_documents (
            document_id, canonical_url, title, publisher_name,
            first_seen_at, last_seen_at, review_status,
            created_at, updated_at, effective_at
        ) VALUES (
            'doc-1',
            'https://example.gov.tw/rule',
            'Test Document',
            'Test Publisher',
            ?, ?, 'verified', ?, ?,
            ?
        )
        """,
        (NOW, NOW, NOW, NOW, NOW),
    )
    # Link document to verified source
    connection.execute(
        """
        INSERT INTO document_discoveries (
            document_id, source_id, discovery_method,
            first_seen_at, last_seen_at
        ) VALUES ('doc-1', 'src-1', 'manual_seed', ?, ?)
        """,
        (NOW, NOW),
    )
    # Program
    connection.execute(
        """
        INSERT INTO benefit_programs (
            program_id, canonical_name, created_at, updated_at
        ) VALUES ('prog-1', 'Program 1', ?, ?)
        """,
        (NOW, NOW),
    )
    # Evidence excerpt (verified)
    connection.execute(
        """
        INSERT INTO evidence_excerpts (
            evidence_id, document_id, excerpt,
            review_status, reviewer_ref, reviewed_at,
            created_at, updated_at
        ) VALUES (
            'ev-1', 'doc-1', 'Section 5 states...',
            'verified', 'reviewer-1', ?,
            ?, ?
        )
        """,
        (NOW, NOW, NOW),
    )
    # Program-evidence link (verified)
    connection.execute(
        """
        INSERT INTO program_evidence_links (
            program_id, evidence_id, evidence_role,
            review_status, reviewer_ref, reviewed_at
        ) VALUES (
            'prog-1', 'ev-1', 'eligibility',
            'verified', 'reviewer-1', ?
        )
        """,
        (NOW,),
    )
    # Rule + source reference evidence
    connection.execute("INSERT INTO rule_definitions VALUES ('rule-1', 'prog-1')")
    # Need a root node for the approved rule version
    connection.execute(
        """
        INSERT INTO field_registry (
            field_id, data_type, prompt_label, why_needed,
            pii_classification, active
        ) VALUES ('f1', 'text', 'Q?', 'Needed', 'none', 1)
        """
    )
    connection.execute(
        """
        INSERT INTO rule_versions (
            rule_version_id, rule_id, version, dsl_version,
            approval_status, is_current, root_node_id, created_at,
            approved_by, approved_at
        ) VALUES (
            'rv-1', 'rule-1', '1', 'dsl-v1',
            'approved', 1, 'rn-1', ?, 'reviewer-1', ?
        )
        """,
        (NOW, NOW),
    )
    connection.execute(
        """
        INSERT INTO rule_nodes (
            node_id, rule_version_id, parent_node_id,
            node_type, child_order
        ) VALUES ('rn-1', 'rv-1', NULL, 'all_of', 0)
        """
    )
    connection.execute(
        """
        INSERT INTO rule_version_source_refs
        VALUES ('rv-1', 'doc-1#section_5')
        """
    )
    connection.execute(
        """
        INSERT INTO source_reference_evidence
        VALUES ('rv-1', 'doc-1#section_5', 'ev-1')
        """
    )
    # Unverified evidence (should not appear)
    connection.execute(
        """
        INSERT INTO evidence_excerpts (
            evidence_id, document_id, excerpt,
            review_status, created_at, updated_at
        ) VALUES (
            'ev-unverified', 'doc-1', 'Unverified excerpt',
            'candidate', ?, ?
        )
        """,
        (NOW, NOW),
    )
    connection.execute(
        """
        INSERT INTO program_evidence_links (
            program_id, evidence_id, evidence_role, review_status
        ) VALUES ('prog-1', 'ev-unverified', 'overview', 'candidate')
        """
    )


def test_get_citations_returns_only_verified(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_evidence_fixture(conn)

    repo = SqliteEvidenceRepository(lambda: sqlite3.connect(database))
    citations = repo.get_citations("prog-1")

    assert len(citations) == 1
    assert citations[0].document_id == "doc-1"
    assert citations[0].title == "Test Document"
    assert citations[0].publisher == "Test Publisher"
    assert citations[0].excerpt == "Section 5 states..."
    assert citations[0].url == "https://example.gov.tw/rule"


def test_get_citations_empty_for_unknown_program(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_evidence_fixture(conn)

    repo = SqliteEvidenceRepository(lambda: sqlite3.connect(database))
    citations = repo.get_citations("nonexistent-program")

    assert citations == ()


def test_get_citations_for_references_exact_match(
    tmp_path: Path,
) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_evidence_fixture(conn)

    repo = SqliteEvidenceRepository(lambda: sqlite3.connect(database))
    citations = repo.get_citations_for_references("prog-1", ("doc-1#section_5",))

    assert len(citations) == 1
    assert citations[0].document_id == "doc-1"


def test_get_citations_for_references_no_match(
    tmp_path: Path,
) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_evidence_fixture(conn)

    repo = SqliteEvidenceRepository(lambda: sqlite3.connect(database))
    citations = repo.get_citations_for_references("prog-1", ("nonexistent-ref",))

    assert citations == ()


def test_get_citations_for_references_empty_list(
    tmp_path: Path,
) -> None:
    database = _setup_database(tmp_path)

    repo = SqliteEvidenceRepository(lambda: sqlite3.connect(database))
    citations = repo.get_citations_for_references("prog-1", ())

    assert citations == ()
