"""Integration tests for SqliteEntitlementGraphRepository."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.graph_repository import (
    SqliteEntitlementGraphRepository,
)
from backend.app.adapters.sqlite.migrations import migrate_database

from app.orchestration.data_errors import InvalidEventIdError

NOW = "2026-07-30T00:00:00+00:00"


def _setup_database(tmp_path: Path) -> Path:
    database = tmp_path / "graph.db"
    migrate_database(database)
    return database


def _insert_graph_fixture(connection: sqlite3.Connection) -> None:
    """Insert a minimal life_event → benefit_program graph."""
    connection.execute("PRAGMA foreign_keys = ON")
    # Programs
    connection.executemany(
        """
        INSERT INTO benefit_programs (
            program_id, canonical_name, program_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("prog-a", "Program A", "verified", NOW, NOW),
            ("prog-b", "Program B", "candidate", NOW, NOW),
            ("prog-rejected", "Rejected Program", "rejected", NOW, NOW),
        ],
    )
    # Graph nodes
    connection.executemany(
        """
        INSERT INTO graph_nodes (node_id, node_type, display_name, program_id)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("event-1", "life_event", "Spouse Death", None),
            ("node-prog-a", "benefit_program", "Program A", "prog-a"),
            ("node-prog-b", "benefit_program", "Program B", "prog-b"),
            (
                "node-prog-rejected",
                "benefit_program",
                "Rejected",
                "prog-rejected",
            ),
        ],
    )
    # Edges from event to programs
    connection.executemany(
        """
        INSERT INTO graph_edges (
            edge_id, from_node_id, to_node_id, edge_type, canonical_order
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("e1", "event-1", "node-prog-a", "triggers", 0),
            ("e2", "event-1", "node-prog-b", "triggers", 1),
            ("e3", "event-1", "node-prog-rejected", "triggers", 2),
        ],
    )
    # Field registry for conditions
    connection.execute(
        """
        INSERT INTO field_registry (
            field_id, data_type, prompt_label, why_needed,
            pii_classification, active
        ) VALUES ('age', 'integer', 'Age?', 'Needed', 'none', 1)
        """
    )
    # Edge condition on e1: age >= 18
    connection.execute(
        """
        INSERT INTO graph_edge_conditions (
            edge_id, condition_id, field_id, operator,
            expected_value_type, expected_value_json, condition_order
        ) VALUES ('e1', 'cond-age', 'age', '>=', 'integer', '18', 0)
        """
    )


def test_expand_event_returns_visible_programs(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_graph_fixture(conn)

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    items = repo.expand_from_event("event-1", {"age": 25})

    item_ids = [item.item_id for item in items]
    assert "prog-a" in item_ids
    assert "prog-b" in item_ids
    # rejected program excluded
    assert "prog-rejected" not in item_ids


def test_expand_event_condition_missing_field_preserves_path(
    tmp_path: Path,
) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_graph_fixture(conn)

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    # Don't provide 'age' → path preserved, age in missing_field_ids
    items = repo.expand_from_event("event-1", {})

    prog_a = next((i for i in items if i.item_id == "prog-a"), None)
    assert prog_a is not None
    assert "age" in prog_a.missing_field_ids


def test_expand_event_condition_fails_excludes_path(
    tmp_path: Path,
) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_graph_fixture(conn)

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    # age=10 fails condition age >= 18
    items = repo.expand_from_event("event-1", {"age": 10})

    item_ids = [item.item_id for item in items]
    # prog-a excluded (condition failed), prog-b still visible (no condition)
    assert "prog-a" not in item_ids
    assert "prog-b" in item_ids


def test_expand_invalid_event_raises_error(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_graph_fixture(conn)

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))

    with pytest.raises(InvalidEventIdError):
        repo.expand_from_event("nonexistent-event", {})


def test_expand_non_life_event_raises_error(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        _insert_graph_fixture(conn)

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))

    # node-prog-a is benefit_program, not life_event
    with pytest.raises(InvalidEventIdError):
        repo.expand_from_event("node-prog-a", {})


def test_expand_valid_event_no_programs_returns_empty(
    tmp_path: Path,
) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, display_name)
            VALUES ('lonely-event', 'life_event', 'Lonely Event')
            """
        )

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    items = repo.expand_from_event("lonely-event", {})

    assert items == ()
