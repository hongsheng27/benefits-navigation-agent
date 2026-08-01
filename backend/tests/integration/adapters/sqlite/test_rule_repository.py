"""Integration tests for SqliteRuleRepository.

Uses in-memory migrated databases with synthetic rule data.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from backend.app.adapters.sqlite.migrations import migrate_database
from backend.app.adapters.sqlite.rule_repository import SqliteRuleRepository

NOW = "2026-07-30T00:00:00+00:00"


def _setup_database(tmp_path: Path) -> Path:
    """Create a fully migrated database."""
    database = tmp_path / "rules.db"
    migrate_database(database)
    return database


def _insert_program_with_rule(
    connection: sqlite3.Connection,
    *,
    program_id: str = "program-1",
    rule_id: str = "rule-1",
    rule_version_id: str = "rv-1",
    is_current: int = 1,
    approval_status: str = "approved",
) -> None:
    """Insert a minimal program with one rule version."""
    connection.execute(
        """
        INSERT OR IGNORE INTO benefit_programs (
            program_id, canonical_name, created_at, updated_at
        ) VALUES (?, 'Test Program', ?, ?)
        """,
        (program_id, NOW, NOW),
    )
    connection.execute(
        "INSERT OR IGNORE INTO rule_definitions VALUES (?, ?)",
        (rule_id, program_id),
    )
    # Insert field registry entries for required fields
    connection.execute(
        """
        INSERT OR IGNORE INTO field_registry (
            field_id, data_type, prompt_label, why_needed,
            pii_classification, active
        ) VALUES ('age', 'integer', 'Age?', 'Needed', 'none', 1)
        """
    )
    # Insert root node (all_of) with one child condition
    root_node_id = f"node-root-{rule_version_id}"
    condition_node_id = f"node-cond-{rule_version_id}"
    connection.execute(
        """
        INSERT INTO rule_versions (
            rule_version_id, rule_id, version, dsl_version,
            approval_status, is_current, root_node_id, created_at,
            approved_by, approved_at
        ) VALUES (?, ?, '1', 'dsl-v1', ?, ?, ?, ?, ?, ?)
        """,
        (
            rule_version_id,
            rule_id,
            approval_status,
            is_current,
            root_node_id if approval_status == "approved" else None,
            NOW,
            "reviewer-1" if approval_status == "approved" else None,
            NOW if approval_status == "approved" else None,
        ),
    )
    if approval_status == "approved":
        connection.execute(
            """
            INSERT INTO rule_nodes (
                node_id, rule_version_id, parent_node_id, node_type, child_order
            ) VALUES (?, ?, NULL, 'all_of', 0)
            """,
            (root_node_id, rule_version_id),
        )
        connection.execute(
            """
            INSERT INTO rule_nodes (
                node_id, rule_version_id, parent_node_id, node_type, child_order
            ) VALUES (?, ?, ?, 'condition', 0)
            """,
            (condition_node_id, rule_version_id, root_node_id),
        )
        connection.execute(
            """
            INSERT INTO rule_conditions (
                condition_id, node_id, field_id, operator,
                expected_value_type, expected_value_json,
                label, source_reference
            ) VALUES (?, ?, 'age', 'gte', 'integer', '18', 'Age >= 18', 'doc#s1')
            """,
            (f"cond-{rule_version_id}", condition_node_id),
        )
        connection.execute(
            """
            INSERT INTO rule_required_fields
                (rule_version_id, field_id, canonical_order)
            VALUES (?, 'age', 0)
            """,
            (rule_version_id,),
        )
        connection.execute(
            """
            INSERT INTO rule_version_source_refs (rule_version_id, source_reference)
            VALUES (?, 'doc#s1')
            """,
            (rule_version_id,),
        )


def test_load_current_approved_rule_returns_complete_data(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _insert_program_with_rule(conn)
        conn.commit()

    repo = SqliteRuleRepository(lambda: sqlite3.connect(database))
    rule = repo.load_current_approved_rule("program-1")

    assert rule is not None
    assert rule.program_id == "program-1"
    assert rule.rule_id == "rule-1"
    assert rule.rule_version_id == "rv-1"
    assert rule.version == "1"
    assert rule.dsl_version == "dsl-v1"
    assert rule.root.node_type == "all_of"
    assert len(rule.root.children) == 1
    assert rule.root.children[0].node_type == "condition"
    assert rule.root.children[0].condition is not None
    assert rule.root.children[0].condition.field_id == "age"
    assert rule.root.children[0].condition.operator == "gte"
    assert rule.required_fields[0].field_id == "age"
    assert rule.source_references == ("doc#s1",)
    assert rule.amount is None


def test_load_current_approved_rule_returns_none_for_missing_program(
    tmp_path: Path,
) -> None:
    database = _setup_database(tmp_path)

    repo = SqliteRuleRepository(lambda: sqlite3.connect(database))
    rule = repo.load_current_approved_rule("nonexistent-program")

    assert rule is None


def test_load_current_approved_rule_returns_none_for_non_approved(
    tmp_path: Path,
) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _insert_program_with_rule(conn, approval_status="candidate", is_current=0)
        conn.commit()

    repo = SqliteRuleRepository(lambda: sqlite3.connect(database))
    rule = repo.load_current_approved_rule("program-1")

    assert rule is None


def test_load_current_approved_rule_with_amounts(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _insert_program_with_rule(conn)
        conn.execute(
            """
            INSERT INTO approved_amounts (
                rule_version_id, amount_min, amount_max,
                amount_period, amount_currency, source_reference
            ) VALUES ('rv-1', 5000, 10000, 'one_time', 'TWD', 'doc#s1')
            """
        )
        conn.commit()

    repo = SqliteRuleRepository(lambda: sqlite3.connect(database))
    rule = repo.load_current_approved_rule("program-1")

    assert rule is not None
    assert rule.amount is not None
    assert rule.amount.amount_min == 5000
    assert rule.amount.amount_max == 10000
    assert rule.amount.amount_period == "one_time"
    assert rule.amount.amount_currency == "TWD"


def test_load_required_fields_returns_ordered_entries(tmp_path: Path) -> None:
    database = _setup_database(tmp_path)
    with closing(sqlite3.connect(database)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        _insert_program_with_rule(conn)
        conn.execute(
            """
            INSERT INTO field_registry (
                field_id, data_type, prompt_label, why_needed,
                pii_classification, active
            ) VALUES (
                'income', 'number', 'Income?', 'Needed',
                'eligibility_sensitive', 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO rule_required_fields
                (rule_version_id, field_id, canonical_order)
            VALUES ('rv-1', 'income', 1)
            """
        )
        conn.commit()

    repo = SqliteRuleRepository(lambda: sqlite3.connect(database))
    fields = repo.load_required_fields("program-1")

    assert len(fields) == 2
    assert fields[0].field_id == "age"
    assert fields[1].field_id == "income"
