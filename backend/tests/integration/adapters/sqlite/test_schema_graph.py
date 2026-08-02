from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.migrations import (
    SCHEMA_VERSION_KEY,
    MigrationError,
    migrate_database,
)

NOW = "2026-07-30T00:00:00+00:00"


def _object_names(connection: sqlite3.Connection, object_type: str) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ?",
            (object_type,),
        )
    }


def _insert_graph_prerequisites(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO catalog_revisions (
            revision_id, committed_at, actor_ref, description_code
        ) VALUES ('revision-1', ?, 'reviewer:test', 'synthetic')
        """,
        (NOW,),
    )
    connection.executemany(
        """
        INSERT INTO benefit_programs (
            program_id, canonical_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?)
        """,
        (
            ("program-a", "Synthetic A", NOW, NOW),
            ("program-b", "Synthetic B", NOW, NOW),
        ),
    )
    connection.execute(
        """
        INSERT INTO field_registry (
            field_id, data_type, prompt_label, why_needed,
            pii_classification, active
        ) VALUES (
            'field-1', 'integer', 'Synthetic prompt', 'Synthetic reason',
            'eligibility_sensitive', 1
        )
        """
    )
    connection.executemany(
        """
        INSERT INTO graph_nodes (node_id, node_type, display_name, program_id)
        VALUES (?, ?, ?, ?)
        """,
        (
            ("event-1", "life_event", "Synthetic event", None),
            ("program-node-a", "benefit_program", "Synthetic A", "program-a"),
            ("program-node-b", "benefit_program", "Synthetic B", "program-b"),
            ("document-a", "document_requirement", "Synthetic document A", None),
            ("document-b", "document_requirement", "Synthetic document B", None),
            ("agency-1", "agency", "Synthetic agency", None),
        ),
    )


def test_fresh_schema_has_required_graph_objects(tmp_path: Path) -> None:
    database = tmp_path / "fresh-graph.db"

    result = migrate_database(database)

    assert result.current_version == 8
    assert result.applied_migration_ids == (
        "0001_metadata",
        "0002_programs_fields",
        "0003_graph",
        "0004_rules_evidence",
        "0005_refresh_compatibility",
        "0006_preserve_legacy_rules",
        "0007_mvp_catalog_scaffold",
        "0008_case2_database_seed",
    )
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        assert {
            "graph_nodes",
            "graph_edges",
            "graph_edge_conditions",
            "graph_versions",
        }.issubset(_object_names(connection, "table"))
        assert {
            "uq_graph_nodes_program_id",
            "idx_graph_edges_from_type_order",
            "idx_graph_edges_to_type",
            "idx_graph_edge_conditions_order",
            "uq_graph_versions_current",
        }.issubset(_object_names(connection, "index"))
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_graph_node_edge_and_reference_constraints(tmp_path: Path) -> None:
    database = tmp_path / "graph-constraints.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_graph_prerequisites(connection)
        connection.execute(
            """
            INSERT INTO graph_edges (
                edge_id, from_node_id, to_node_id, edge_type, canonical_order
            ) VALUES (
                'edge-valid', 'event-1', 'program-node-a', 'triggers', 0
            )
            """
        )

        invalid_node_rows = (
            ("bad-type", "unknown", "Synthetic", None),
            ("missing-program", "benefit_program", "Synthetic", None),
            ("wrong-node-program", "agency", "Synthetic", "program-a"),
            ("absent-program", "benefit_program", "Synthetic", "absent"),
            ("duplicate-program", "benefit_program", "Synthetic", "program-a"),
        )
        for row in invalid_node_rows:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO graph_nodes (
                        node_id, node_type, display_name, program_id
                    ) VALUES (?, ?, ?, ?)
                    """,
                    row,
                )

        invalid_edge_rows = (
            ("bad-edge-type", "event-1", "program-node-b", "unknown", 0),
            ("missing-from", "absent", "program-node-b", "triggers", 0),
            ("missing-to", "event-1", "absent", "triggers", 0),
            ("negative-order", "event-1", "program-node-b", "triggers", -1),
            ("duplicate-relation", "event-1", "program-node-a", "triggers", 1),
        )
        for row in invalid_edge_rows:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO graph_edges VALUES (?, ?, ?, ?, ?)",
                    row,
                )


def test_edge_conditions_enforce_typed_scalar_json_and_references(
    tmp_path: Path,
) -> None:
    database = tmp_path / "graph-conditions.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_graph_prerequisites(connection)
        connection.execute(
            """
            INSERT INTO graph_edges
            VALUES ('edge-1', 'event-1', 'program-node-a', 'triggers', 0)
            """
        )
        valid_conditions = (
            ("string", '"synthetic"'),
            ("integer", "2"),
            ("number", "2.5"),
            ("boolean", "true"),
            ("null", "null"),
        )
        for order, (value_type, value_json) in enumerate(valid_conditions):
            connection.execute(
                """
                INSERT INTO graph_edge_conditions (
                    edge_id, condition_id, field_id, operator,
                    expected_value_type, expected_value_json, condition_order
                ) VALUES ('edge-1', ?, 'field-1', 'opaque_operator', ?, ?, ?)
                """,
                (f"condition-{order}", value_type, value_json, order),
            )

        invalid_condition_rows = (
            ("edge-1", "blank-operator", "field-1", " ", "integer", "2", 5),
            ("edge-1", "bad-json", "field-1", "op", "integer", "{", 5),
            ("edge-1", "wrong-type", "field-1", "op", "integer", '"2"', 5),
            ("edge-1", "object-value", "field-1", "op", "string", "{}", 5),
            ("edge-1", "missing-field", "absent", "op", "integer", "2", 5),
            ("absent", "missing-edge", "field-1", "op", "integer", "2", 5),
            ("edge-1", "negative-order", "field-1", "op", "integer", "2", -1),
        )
        for row in invalid_condition_rows:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO graph_edge_conditions VALUES (?, ?, ?, ?, ?, ?, ?)",
                    row,
                )


def test_graph_versions_reference_revisions_and_allow_one_current(
    tmp_path: Path,
) -> None:
    database = tmp_path / "graph-versions.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_graph_prerequisites(connection)
        connection.execute(
            """
            INSERT INTO graph_versions
            VALUES ('graph-v1', 'revision-1', 'reviewer:test', ?, 1)
            """,
            (NOW,),
        )
        connection.execute(
            """
            INSERT INTO graph_versions
            VALUES ('graph-draft-history', 'revision-1', 'reviewer:test', ?, 0)
            """,
            (NOW,),
        )

        invalid_versions = (
            ("second-current", "revision-1", "reviewer:test", NOW, 1),
            ("missing-revision", "absent", "reviewer:test", NOW, 0),
            ("blank-reviewer", "revision-1", " ", NOW, 0),
            ("bad-current", "revision-1", "reviewer:test", NOW, 2),
        )
        for row in invalid_versions:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO graph_versions VALUES (?, ?, ?, ?, ?)",
                    row,
                )


def test_relations_have_stable_canonical_then_target_order(tmp_path: Path) -> None:
    database = tmp_path / "graph-order.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_graph_prerequisites(connection)
        connection.executemany(
            """
            INSERT INTO graph_edges (
                edge_id, from_node_id, to_node_id, edge_type, canonical_order
            ) VALUES (?, 'program-node-a', ?, 'requires', ?)
            """,
            (
                ("requires-b", "document-b", 1),
                ("requires-agency", "agency-1", 0),
                ("requires-a", "document-a", 1),
            ),
        )
        ordered_targets = connection.execute(
            """
            SELECT to_node_id
            FROM graph_edges
            WHERE from_node_id = 'program-node-a' AND edge_type = 'requires'
            ORDER BY canonical_order, to_node_id
            """
        ).fetchall()

    assert ordered_targets == [("agency-1",), ("document-a",), ("document-b",)]


def test_invalid_graph_batch_rolls_back_all_rows(tmp_path: Path) -> None:
    database = tmp_path / "graph-batch.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            _insert_graph_prerequisites(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                INSERT INTO graph_edges
                VALUES (
                    'batch-valid', 'event-1', 'program-node-a', 'triggers', 0
                );
                INSERT INTO graph_edges
                VALUES (
                    'batch-invalid', 'event-1', 'missing-target', 'triggers', 1
                );
                COMMIT;
                """
            )
        connection.rollback()
        assert (
            connection.execute(
                "SELECT edge_id FROM graph_edges WHERE edge_id LIKE 'batch-%'"
            ).fetchall()
            == []
        )


def test_malformed_preexisting_graph_target_fails_closed_and_rolls_back_0003(
    tmp_path: Path,
) -> None:
    database = tmp_path / "malformed-graph-target.db"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE graph_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                display_name TEXT NOT NULL,
                program_id TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO graph_nodes VALUES ('legacy-node', 'anything', '', NULL)"
        )

    with pytest.raises(MigrationError) as captured:
        migrate_database(database)

    assert captured.value.code == "migration_target_invalid"
    assert str(captured.value) == "migration_target_invalid"
    with closing(sqlite3.connect(database)) as connection:
        tables = _object_names(connection, "table")
        indexes = _object_names(connection, "index")
        applied = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
        malformed_row = connection.execute("SELECT * FROM graph_nodes").fetchone()

    assert "graph_edges" not in tables
    assert "graph_edge_conditions" not in tables
    assert "graph_versions" not in tables
    assert "uq_graph_nodes_program_id" not in indexes
    assert applied == [("0001_metadata",), ("0002_programs_fields",)]
    assert version == ("2",)
    assert malformed_row == ("legacy-node", "anything", "", None)
