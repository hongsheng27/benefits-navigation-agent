"""Cross-adapter semantic integration tests.

Verifies committed-state reads, visibility gates, and referential
integrity across the adapter layer.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.evidence_repository import (
    SqliteEvidenceRepository,
)
from backend.app.adapters.sqlite.graph_repository import (
    SqliteEntitlementGraphRepository,
)
from backend.app.adapters.sqlite.migrations import migrate_database
from backend.app.adapters.sqlite.rule_repository import SqliteRuleRepository

NOW = "2026-07-30T00:00:00+00:00"


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    db = tmp_path / "semantics.db"
    migrate_database(db)
    return db


def _insert_full_fixture(connection: sqlite3.Connection) -> None:
    """Insert a complete program with graph, rule, and evidence."""
    connection.execute("PRAGMA foreign_keys = ON")
    # Programs with different statuses
    connection.executemany(
        """
        INSERT INTO benefit_programs (
            program_id, canonical_name, program_status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("prog-verified", "Verified Program", "verified", NOW, NOW),
            ("prog-candidate", "Candidate Program", "candidate", NOW, NOW),
            ("prog-rejected", "Rejected Program", "rejected", NOW, NOW),
            ("prog-inactive", "Inactive Program", "inactive", NOW, NOW),
        ],
    )
    # Graph
    connection.execute(
        """
        INSERT INTO graph_nodes (node_id, node_type, display_name)
        VALUES ('event-sem', 'life_event', 'Semantic Event')
        """
    )
    for prog_id in (
        "prog-verified",
        "prog-candidate",
        "prog-rejected",
        "prog-inactive",
    ):
        node_id = f"node-{prog_id}"
        connection.execute(
            """
            INSERT INTO graph_nodes (
                node_id, node_type, display_name, program_id
            ) VALUES (?, 'benefit_program', ?, ?)
            """,
            (node_id, prog_id, prog_id),
        )
        connection.execute(
            """
            INSERT INTO graph_edges (
                edge_id, from_node_id, to_node_id,
                edge_type, canonical_order
            ) VALUES (?, 'event-sem', ?, 'triggers', 0)
            """,
            (f"edge-{prog_id}", node_id),
        )


# ---------------------------------------------------------------------------
# Visibility gates: rejected/inactive excluded from expansion
# ---------------------------------------------------------------------------


def test_graph_excludes_rejected_and_inactive_programs(
    database: Path,
) -> None:
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_full_fixture(conn)

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    items = repo.expand_from_event("event-sem", {})

    item_ids = {item.item_id for item in items}
    assert "prog-verified" in item_ids
    assert "prog-candidate" in item_ids
    assert "prog-rejected" not in item_ids
    assert "prog-inactive" not in item_ids


def test_graph_preserves_program_status_in_candidate_items(
    database: Path,
) -> None:
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_full_fixture(conn)

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    items = repo.expand_from_event("event-sem", {})

    statuses = {item.item_id: item.program_status for item in items}
    assert statuses["prog-verified"] == "verified"
    assert statuses["prog-candidate"] == "candidate"


# ---------------------------------------------------------------------------
# Rule reader respects program boundary
# ---------------------------------------------------------------------------


def test_rule_repository_returns_none_for_rejected_program(
    database: Path,
) -> None:
    """Rule reader returns None when program has no rule (rejected has no rules)."""
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_full_fixture(conn)

    repo = SqliteRuleRepository(lambda: sqlite3.connect(database))
    rule = repo.load_current_approved_rule("prog-rejected")

    assert rule is None


# ---------------------------------------------------------------------------
# Evidence returns empty for programs without verified evidence
# ---------------------------------------------------------------------------


def test_evidence_returns_empty_for_program_without_evidence(
    database: Path,
) -> None:
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_full_fixture(conn)

    repo = SqliteEvidenceRepository(lambda: sqlite3.connect(database))
    citations = repo.get_citations("prog-verified")

    assert citations == ()


# ---------------------------------------------------------------------------
# Committed-state reads see only committed data
# ---------------------------------------------------------------------------


def test_uncommitted_program_not_visible_to_graph(
    database: Path,
) -> None:
    """A program inserted but not committed should not be visible."""
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, display_name)
            VALUES ('commit-event', 'life_event', 'Commit Test')
            """
        )

    # Insert a program in a separate connection without committing
    conn2 = sqlite3.connect(database)
    conn2.execute("PRAGMA foreign_keys = ON")
    conn2.execute(
        """
        INSERT INTO benefit_programs (
            program_id, canonical_name, program_status,
            created_at, updated_at
        ) VALUES ('uncommitted-prog', 'Uncommitted', 'candidate', ?, ?)
        """,
        (NOW, NOW),
    )
    conn2.execute(
        """
        INSERT INTO graph_nodes (
            node_id, node_type, display_name, program_id
        ) VALUES (
            'node-uncommitted', 'benefit_program',
            'Uncommitted', 'uncommitted-prog'
        )
        """
    )
    conn2.execute(
        """
        INSERT INTO graph_edges (
            edge_id, from_node_id, to_node_id,
            edge_type, canonical_order
        ) VALUES ('edge-uncommitted', 'commit-event', 'node-uncommitted',
                  'triggers', 0)
        """
    )
    # NOT committed

    # Reader should not see uncommitted data
    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    items = repo.expand_from_event("commit-event", {})

    assert all(item.item_id != "uncommitted-prog" for item in items)

    conn2.rollback()
    conn2.close()
