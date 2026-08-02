from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.migrations import (
    SCHEMA_VERSION_KEY,
    Migration,
    MigrationError,
    load_migrations,
    migrate_database,
)
from scripts.init_benefit_catalog import initialize_database
from scripts.migrate_catalog import execute_catalog_migration

NOW = "2026-07-30T00:00:00+00:00"


def _schema_snapshot(path: Path) -> tuple[tuple, tuple, tuple]:
    with closing(sqlite3.connect(path)) as connection:
        objects = tuple(
            connection.execute(
                """
                SELECT type, name, sql
                FROM sqlite_master
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            ).fetchall()
        )
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        metadata = (
            tuple(
                connection.execute(
                    "SELECT key, value FROM schema_metadata ORDER BY key"
                ).fetchall()
            )
            if "schema_metadata" in tables
            else ()
        )
        applied = (
            tuple(
                connection.execute(
                    """
                    SELECT migration_id, checksum
                    FROM schema_migrations
                    ORDER BY migration_id
                    """
                ).fetchall()
            )
            if "schema_migrations" in tables
            else ()
        )
    return objects, metadata, applied


def _create_legacy_database(path: Path) -> None:
    initialize_database(path, source_seed_path=None)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, program_status,
                created_at, updated_at
            ) VALUES (
                'legacy-program', 'Synthetic legacy program',
                'candidate', ?, ?
            )
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO program_rule_fields (
                program_id, field_name, field_type, field_value,
                source_excerpt, review_status, created_at, updated_at
            ) VALUES (
                'legacy-program', 'legacy-field', 'text',
                'synthetic-value', '', 'pending', ?, ?
            )
            """,
            (NOW, NOW),
        )


@pytest.mark.parametrize("migration_index", range(7))
def test_each_migration_failure_restores_previous_committed_schema(
    tmp_path: Path,
    migration_index: int,
) -> None:
    database = tmp_path / f"rollback-{migration_index + 1}.db"
    migrations = load_migrations()
    previous = migrations[:migration_index]
    if previous:
        migrate_database(database, migrations=previous)
    before = _schema_snapshot(database) if database.exists() else ((), (), ())

    target = migrations[migration_index]
    failing_target = Migration.from_sql(
        target.migration_id,
        target.version,
        target.sql
        + """
        CREATE TABLE partial_rollback_marker (marker TEXT PRIMARY KEY);
        INSERT INTO deliberately_missing_table VALUES ('fail');
        """,
    )
    with pytest.raises(MigrationError) as captured:
        migrate_database(
            database,
            migrations=(*previous, failing_target),
        )

    assert captured.value.code == "migration_failed"
    assert _schema_snapshot(database) == before
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_dry_run_migrates_disposable_copy_to_version_six(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-source.db"
    _create_legacy_database(source)
    before = _schema_snapshot(source)

    execution = execute_catalog_migration(source, apply=False)

    assert execution.mode == "dry-run"
    assert execution.migration_result.current_version == 8
    assert execution.migration_result.applied_migration_ids == (
        "0001_metadata",
        "0002_programs_fields",
        "0003_graph",
        "0004_rules_evidence",
        "0005_refresh_compatibility",
        "0006_preserve_legacy_rules",
        "0007_mvp_catalog_scaffold",
        "0008_case2_database_seed",
    )
    assert execution.working_database_path != source
    assert not execution.working_database_path.exists()
    assert _schema_snapshot(source) == before


def test_successful_apply_exposes_only_final_committed_bridge(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-source.db"
    backup = tmp_path / "legacy-source.before-v6.db"
    _create_legacy_database(source)

    execution = execute_catalog_migration(
        source,
        apply=True,
        backup_path=backup,
    )

    assert execution.mode == "apply"
    assert execution.migration_result.current_version == 8
    with closing(sqlite3.connect(source)) as connection:
        object_type = connection.execute(
            "SELECT type FROM sqlite_master WHERE name = 'program_rule_fields'"
        ).fetchone()
        visible = connection.execute(
            """
            SELECT program_id, field_name, field_value
            FROM program_rule_fields
            """
        ).fetchall()
        draft_statuses = connection.execute(
            "SELECT conversion_status FROM legacy_rule_conversion_drafts"
        ).fetchall()
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    with closing(sqlite3.connect(backup)) as connection:
        backup_object_type = connection.execute(
            "SELECT type FROM sqlite_master WHERE name = 'program_rule_fields'"
        ).fetchone()
        backup_has_migrations = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()

    assert object_type == ("view",)
    assert visible == [("legacy-program", "legacy-field", "synthetic-value")]
    assert draft_statuses == [("under_review",)]
    assert version == ("8",)
    assert foreign_key_errors == []
    assert backup_object_type == ("table",)
    assert backup_has_migrations is None
