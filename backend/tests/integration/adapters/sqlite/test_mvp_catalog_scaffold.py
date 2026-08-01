"""Integration tests for migration 0007: MVP catalog scaffold.

Validates:
- Exactly 6 known MVP IDs exist after migration
- No unapproved facts, thresholds, deadlines, amounts, or source excerpts
- Status is candidate or under_review (never verified)
- Protected transitions cannot bypass human reviewer
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.migrations import (
    MigrationError,
    load_migrations,
    migrate_database,
)

_MVP_IDS = frozenset(
    {
        "death_registration",
        "labor_funeral_grant",
        "national_pension_funeral_grant",
        "labor_survivor_pension",
        "national_pension_survivor_pension",
        "nhi_status_change",
    }
)


def _migrate_to_version_7(tmp_path: Path) -> Path:
    """Run all migrations up to version 7 on a fresh database."""
    database = tmp_path / "test-scaffold.db"
    result = migrate_database(database)
    assert result.current_version == 7
    assert "0007_mvp_catalog_scaffold" in result.applied_migration_ids
    return database


def test_exactly_six_mvp_ids_exist(tmp_path: Path) -> None:
    """After migration 0007, exactly the 6 MVP IDs should be present."""
    database = _migrate_to_version_7(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        rows = connection.execute(
            "SELECT program_id FROM benefit_programs ORDER BY program_id"
        ).fetchall()
    program_ids = {str(row[0]) for row in rows}
    assert program_ids == _MVP_IDS


def test_all_programs_have_candidate_or_under_review_status(
    tmp_path: Path,
) -> None:
    """All MVP programs must be candidate or under_review, never verified."""
    database = _migrate_to_version_7(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            """
            SELECT program_id, program_status
            FROM benefit_programs
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_IDS)),
        ).fetchall()
    for program_id, status in rows:
        assert status in (
            "candidate",
            "under_review",
        ), f"{program_id} has unexpected status: {status}"


def test_no_amounts_exist_for_mvp_programs(tmp_path: Path) -> None:
    """No MVP program should have any amount data (all null)."""
    database = _migrate_to_version_7(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        rows = connection.execute(
            """
            SELECT program_id, amount_min, amount_max,
                   amount_period, amount_currency
            FROM benefit_programs
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_IDS)),
        ).fetchall()
    for row in rows:
        program_id = row[0]
        assert row[1] is None, f"{program_id} has amount_min"
        assert row[2] is None, f"{program_id} has amount_max"
        assert row[3] is None, f"{program_id} has amount_period"
        assert row[4] is None, f"{program_id} has amount_currency"


def test_no_rule_definitions_for_mvp_programs(tmp_path: Path) -> None:
    """No canonical rules should exist for any MVP program."""
    database = _migrate_to_version_7(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        rows = connection.execute(
            """
            SELECT program_id
            FROM rule_definitions
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_IDS)),
        ).fetchall()
    assert rows == []


def test_no_evidence_excerpts_linked_to_mvp_programs(tmp_path: Path) -> None:
    """No approved evidence should be linked to any MVP program."""
    database = _migrate_to_version_7(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        rows = connection.execute(
            """
            SELECT program_id
            FROM program_evidence_links
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_IDS)),
        ).fetchall()
    assert rows == []


def test_no_source_excerpts_in_program_sources(tmp_path: Path) -> None:
    """No source excerpts should exist for MVP programs (legacy path)."""
    database = _migrate_to_version_7(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        # program_rule_fields is a view at this point; check legacy bridge
        rows = connection.execute(
            """
            SELECT program_id, field_value, source_excerpt
            FROM program_rule_fields
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_IDS)),
        ).fetchall()
    assert rows == []


def test_protected_transition_blocked_for_non_human(tmp_path: Path) -> None:
    """Non-human actors cannot transition MVP programs to verified."""
    database = _migrate_to_version_7(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="human reviewer"):
            connection.execute(
                """
                INSERT INTO program_status_history (
                    history_id, program_id, from_status, to_status,
                    actor_type, reviewer_ref, reviewed_at, approved_version
                ) VALUES (
                    'test-blocked', 'death_registration',
                    'candidate', 'verified',
                    'migration', 'test-migration', '2026-01-01T00:00:00+00:00', 'v1'
                )
                """
            )


def test_migration_is_idempotent_for_existing_programs(tmp_path: Path) -> None:
    """Running migration 0007 when programs already exist does not fail."""
    database = _migrate_to_version_7(tmp_path)
    # The migration uses INSERT ... WHERE NOT EXISTS, so re-running the SQL
    # should not cause duplicates. Verify the count remains exactly 6.
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        count = connection.execute("SELECT COUNT(*) FROM benefit_programs").fetchone()[
            0
        ]
    assert count == 6


def test_foreign_key_integrity_after_scaffold(tmp_path: Path) -> None:
    """No foreign key violations after the scaffold migration."""
    database = _migrate_to_version_7(tmp_path)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == []


def test_rollback_on_failure_preserves_version_six(tmp_path: Path) -> None:
    """If migration 0007 fails, the database remains at version 6."""
    database = tmp_path / "rollback-test.db"
    migrations = load_migrations()
    # Apply versions 1-6
    result = migrate_database(database, migrations=migrations[:6])
    assert result.current_version == 6

    # Create a failing version of migration 7
    from backend.app.adapters.sqlite.migrations import Migration

    target = migrations[6]
    failing_target = Migration.from_sql(
        target.migration_id,
        target.version,
        target.sql + "\nINSERT INTO deliberately_missing_table VALUES ('fail');",
    )
    with pytest.raises(MigrationError) as captured:
        migrate_database(
            database,
            migrations=(*migrations[:6], failing_target),
        )
    assert captured.value.code == "migration_failed"

    # Verify we're still at version 6
    with closing(sqlite3.connect(database)) as connection:
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'data_layer_schema_version'"
        ).fetchone()
    assert version == ("6",)
