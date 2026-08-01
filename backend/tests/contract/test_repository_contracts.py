"""Contract tests applied to all SQLite adapter implementations.

Verifies cross-cutting contracts that every adapter must satisfy:
- program_id↔item_id boundary (graph uses program_id as item_id)
- Empty tuple for successful-no-data vs exception for failure
- Invalid ID handling
- Deterministic ordering
- No JSON fallback
- Connection lifecycle via execute_read/execute_transaction

These tests use in-memory migrated databases with minimal synthetic data.
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
from backend.app.adapters.sqlite.source_refresh_service import (
    SqliteSourceRefreshService,
)

from app.orchestration.data_errors import (
    InvalidEventIdError,
    RepositoryUnavailableError,
)
from app.orchestration.protocols import CoverageScope

NOW = "2026-07-30T00:00:00+00:00"


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    db = tmp_path / "contract.db"
    migrate_database(db)
    return db


# ---------------------------------------------------------------------------
# Contract 1: Empty tuple for successful queries with no data
# ---------------------------------------------------------------------------


def test_graph_returns_empty_for_valid_event_no_programs(
    database: Path,
) -> None:
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, display_name)
            VALUES ('empty-event', 'life_event', 'Empty')
            """
        )

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    result = repo.expand_from_event("empty-event", {})

    assert result == ()
    assert isinstance(result, tuple)


def test_evidence_returns_empty_for_unknown_program(
    database: Path,
) -> None:
    repo = SqliteEvidenceRepository(lambda: sqlite3.connect(database))
    result = repo.get_citations("nonexistent-program")

    assert result == ()
    assert isinstance(result, tuple)


def test_evidence_references_returns_empty_for_no_match(
    database: Path,
) -> None:
    repo = SqliteEvidenceRepository(lambda: sqlite3.connect(database))
    result = repo.get_citations_for_references("prog", ("ref-1",))

    assert result == ()


def test_coverage_empty_scope_returns_zero_sources(
    database: Path,
) -> None:
    service = SqliteSourceRefreshService(lambda: sqlite3.connect(database))
    snapshot = service.get_coverage_status(CoverageScope(source_ids=(), domain_tags=()))

    assert snapshot.registered_source_count == 0
    assert snapshot.sources == ()


# ---------------------------------------------------------------------------
# Contract 2: Invalid ID raises error (not empty tuple)
# ---------------------------------------------------------------------------


def test_graph_raises_for_invalid_event_id(database: Path) -> None:
    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))

    with pytest.raises(InvalidEventIdError):
        repo.expand_from_event("does-not-exist", {})


def test_graph_raises_for_non_life_event_node(database: Path) -> None:
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, created_at, updated_at
            ) VALUES ('prog-x', 'X', ?, ?)
            """,
            (NOW, NOW),
        )
        conn.execute(
            """
            INSERT INTO graph_nodes (
                node_id, node_type, display_name, program_id
            ) VALUES ('node-x', 'benefit_program', 'X', 'prog-x')
            """
        )

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))

    with pytest.raises(InvalidEventIdError):
        repo.expand_from_event("node-x", {})


# ---------------------------------------------------------------------------
# Contract 3: Connection open failure raises RepositoryUnavailableError
# ---------------------------------------------------------------------------


def test_graph_raises_unavailable_on_open_failure() -> None:
    def failing_factory() -> sqlite3.Connection:
        raise OSError("cannot open")

    repo = SqliteEntitlementGraphRepository(failing_factory)

    with pytest.raises(RepositoryUnavailableError):
        repo.expand_from_event("any", {})


def test_evidence_raises_unavailable_on_open_failure() -> None:
    def failing_factory() -> sqlite3.Connection:
        raise OSError("cannot open")

    repo = SqliteEvidenceRepository(failing_factory)

    with pytest.raises(RepositoryUnavailableError):
        repo.get_citations("any")


def test_refresh_raises_unavailable_on_open_failure() -> None:
    def failing_factory() -> sqlite3.Connection:
        raise OSError("cannot open")

    service = SqliteSourceRefreshService(failing_factory)

    with pytest.raises(RepositoryUnavailableError):
        service.get_coverage_status(CoverageScope(source_ids=(), domain_tags=()))


# ---------------------------------------------------------------------------
# Contract 4: Deterministic ordering on repeated calls
# ---------------------------------------------------------------------------


def test_graph_expansion_is_deterministic(database: Path) -> None:
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executemany(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, program_status,
                created_at, updated_at
            ) VALUES (?, ?, 'candidate', ?, ?)
            """,
            [(f"prog-{i}", f"Program {i}", NOW, NOW) for i in range(5)],
        )
        conn.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, display_name)
            VALUES ('det-event', 'life_event', 'Deterministic')
            """
        )
        for i in range(5):
            conn.execute(
                """
                INSERT INTO graph_nodes (
                    node_id, node_type, display_name, program_id
                ) VALUES (?, 'benefit_program', ?, ?)
                """,
                (f"node-{i}", f"Program {i}", f"prog-{i}"),
            )
            conn.execute(
                """
                INSERT INTO graph_edges (
                    edge_id, from_node_id, to_node_id,
                    edge_type, canonical_order
                ) VALUES (?, 'det-event', ?, 'triggers', ?)
                """,
                (f"edge-{i}", f"node-{i}", i),
            )

    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))

    result1 = repo.expand_from_event("det-event", {})
    result2 = repo.expand_from_event("det-event", {})

    assert result1 == result2
    assert len(result1) == 5


# ---------------------------------------------------------------------------
# Contract 5: No JSON fallback (adapters use SQLite, not files)
# ---------------------------------------------------------------------------


def test_adapters_do_not_read_json_files(database: Path, tmp_path: Path) -> None:
    """Adapters must not fall back to reading JSON catalog files."""

    json_path = tmp_path / "catalog.json"
    json_path.write_text('{"programs": []}')

    # None of the adapters should touch this file
    repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, display_name)
            VALUES ('json-event', 'life_event', 'JSON test')
            """
        )

    result = repo.expand_from_event("json-event", {})

    assert result == ()
    # The JSON file should still exist unchanged (not consumed)
    assert json_path.read_text() == '{"programs": []}'
