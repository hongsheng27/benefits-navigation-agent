from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import backend.app.adapters.sqlite.migrations as migrations_module
import pytest
from backend.app.adapters.sqlite.migrations import (
    SCHEMA_VERSION_KEY,
    Migration,
    MigrationError,
    load_migrations,
    migrate_database,
    run_migrations,
)
from scripts.init_benefit_catalog import initialize_database
from scripts.migrate_catalog import CatalogMigrationCliError, execute_catalog_migration

NOW = "2026-07-30T00:00:00+00:00"


def create_supported_legacy_database(path: Path) -> None:
    initialize_database(path, source_seed_path=None)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE legacy_records (
                record_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            INSERT INTO legacy_records (record_id, payload)
            VALUES ('legacy-1', 'preserve exactly');
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', 'legacy-oid-v1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """
        )
        connection.execute(
            """
            INSERT INTO source_documents (
                document_id, canonical_url, title, first_seen_at, last_seen_at,
                created_at, updated_at
            ) VALUES (
                'document-1', 'https://example.gov.tw/program', 'Synthetic',
                ?, ?, ?, ?
            )
            """,
            (NOW, NOW, NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, summary, jurisdiction_code,
                program_status, status_note, created_at, updated_at
            ) VALUES (
                'legacy-program', 'Synthetic legacy program', 'legacy summary',
                'TW', 'status_unknown', 'legacy note', ?, ?
            )
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO program_sources (
                program_id, document_id, evidence_role, source_excerpt,
                review_status, created_at, updated_at
            ) VALUES (
                'legacy-program', 'document-1', 'overview', 'synthetic excerpt',
                'pending', ?, ?
            )
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO program_organization_roles (
                role_id, program_id, organization_role, organization_name,
                review_status, created_at, updated_at
            ) VALUES (
                'role-1', 'legacy-program', 'administrator',
                'Synthetic organization', 'pending', ?, ?
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
                'legacy-program', 'legacy-field', 'text', 'legacy-value',
                '', 'pending', ?, ?
            )
            """,
            (NOW, NOW),
        )


def create_orphan_rule_fields_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE schema_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO schema_metadata (key, value)
            VALUES ('schema_version', 'legacy-oid-v1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            CREATE TABLE legacy_records (
                record_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            INSERT INTO legacy_records VALUES ('legacy-1', 'preserve exactly');
            CREATE TABLE program_rule_fields (
                program_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                field_value TEXT NOT NULL,
                review_status TEXT NOT NULL,
                PRIMARY KEY (program_id, field_name)
            );
            INSERT INTO program_rule_fields
            VALUES ('legacy-program', 'legacy-field', 'legacy-value', 'verified');
            """
        )


def table_names(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def test_version_migration_preserves_known_legacy_schema_and_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy.db"
    create_supported_legacy_database(database)

    result = migrate_database(database)

    assert result.previous_version == 0
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
    assert {
        "schema_metadata",
        "schema_migrations",
        "catalog_revisions",
        "legacy_records",
        "benefit_programs",
        "program_sources",
        "program_organization_roles",
        "legacy_program_rule_fields_v1",
    }.issubset(table_names(database))
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        metadata = dict(connection.execute("SELECT key, value FROM schema_metadata"))
        legacy_rows = connection.execute("SELECT * FROM legacy_records").fetchall()
        program = connection.execute(
            "SELECT program_id, program_status FROM benefit_programs "
            "WHERE program_id = 'legacy-program'"
        ).fetchone()
        rule_rows = connection.execute(
            "SELECT * FROM program_rule_fields WHERE program_id = 'legacy-program'"
        ).fetchall()
        migration_rows = connection.execute(
            "SELECT migration_id, checksum FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    migrations = load_migrations()
    assert metadata["schema_version"] == "legacy-oid-v1"
    assert metadata[SCHEMA_VERSION_KEY] == "8"
    assert legacy_rows == [("legacy-1", "preserve exactly")]
    assert program == ("legacy-program", "under_review")
    assert rule_rows == [
        (
            "legacy-program",
            "legacy-field",
            "text",
            "legacy-value",
            "",
            "pending",
            NOW,
            NOW,
        )
    ]
    assert migration_rows == [
        ("0001_metadata", migrations[0].checksum),
        ("0002_programs_fields", migrations[1].checksum),
        ("0003_graph", migrations[2].checksum),
        ("0004_rules_evidence", migrations[3].checksum),
        ("0005_refresh_compatibility", migrations[4].checksum),
        ("0006_preserve_legacy_rules", migrations[5].checksum),
        ("0007_mvp_catalog_scaffold", migrations[6].checksum),
        ("0008_case2_database_seed", migrations[7].checksum),
    ]
    assert foreign_key_errors == []


def test_orphan_rule_fields_shape_fails_closed_without_recording_0002(
    tmp_path: Path,
) -> None:
    database = tmp_path / "unsupported.db"
    create_orphan_rule_fields_database(database)

    with pytest.raises(MigrationError) as captured:
        migrate_database(database)

    assert captured.value.code == "legacy_schema_unsupported"
    assert str(captured.value) == "legacy_schema_unsupported"
    with closing(sqlite3.connect(database)) as connection:
        applied = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
        orphan_rows = connection.execute("SELECT * FROM program_rule_fields").fetchall()
    assert applied == [("0001_metadata",)]
    assert version == ("1",)
    assert orphan_rows == [
        ("legacy-program", "legacy-field", "legacy-value", "verified")
    ]


def test_version_guard_rejects_newer_schema_with_safe_error(tmp_path: Path) -> None:
    database = tmp_path / "newer.db"
    migrate_database(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE schema_metadata SET value = '999' WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        )

    with pytest.raises(MigrationError) as captured:
        migrate_database(database)

    assert captured.value.code == "schema_version_unsupported"
    assert str(captured.value) == "schema_version_unsupported"


def test_checksum_guard_rejects_modified_applied_migration(tmp_path: Path) -> None:
    database = tmp_path / "checksum.db"
    migrate_database(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE migration_id = ?",
            ("0" * 64, "0002_programs_fields"),
        )

    with pytest.raises(MigrationError) as captured:
        migrate_database(database)

    assert captured.value.code == "migration_checksum_mismatch"
    assert "CREATE TABLE" not in str(captured.value)


def test_version_guard_rejects_unknown_recorded_migration(tmp_path: Path) -> None:
    database = tmp_path / "unknown.db"
    migrate_database(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            """
            INSERT INTO schema_migrations (
                migration_id, checksum, applied_at, application_version
            ) VALUES ('9999_unknown', ?, '2026-01-01T00:00:00+00:00', 'test')
            """,
            ("0" * 64,),
        )

    with pytest.raises(MigrationError) as captured:
        migrate_database(database)

    assert captured.value.code == "unknown_migration"


def test_migration_enables_foreign_keys_on_supplied_connection() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        run_migrations(connection)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_failed_generic_migration_rolls_back_only_its_partial_changes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "rollback.db"
    first = load_migrations()[0]
    second = Migration.from_sql(
        "0002_failing",
        2,
        """
        CREATE TABLE partial_change (value TEXT NOT NULL);
        INSERT INTO missing_table (value) VALUES ('must rollback');
        """,
    )

    with pytest.raises(MigrationError) as captured:
        migrate_database(database, migrations=(first, second))

    assert captured.value.code == "migration_failed"
    assert "catalog_revisions" in table_names(database)
    assert "partial_change" not in table_names(database)
    with closing(sqlite3.connect(database)) as connection:
        applied = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
    assert applied == [("0001_metadata",)]
    assert version == ("1",)


def test_failed_0002_rebuild_restores_exact_legacy_schema_and_data(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-rollback.db"
    create_supported_legacy_database(database)
    first = load_migrations()[0]
    failing_second = Migration.from_sql(
        "0002_programs_fields",
        2,
        "INSERT INTO missing_table (value) VALUES ('fail after legacy rename');",
    )

    with pytest.raises(MigrationError) as captured:
        migrate_database(database, migrations=(first, failing_second))

    assert captured.value.code == "migration_failed"
    with closing(sqlite3.connect(database)) as connection:
        columns = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(benefit_programs)")
        )
        program = connection.execute(
            "SELECT program_id, program_status FROM benefit_programs"
        ).fetchone()
        source_program = connection.execute(
            "SELECT program_id FROM program_sources"
        ).fetchone()
        applied = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
    assert "amount_min" not in columns
    assert program == ("legacy-program", "status_unknown")
    assert source_program == ("legacy-program",)
    assert applied == [("0001_metadata",)]


def test_dry_run_uses_disposable_copy_and_never_changes_source(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    create_supported_legacy_database(source)

    execution = execute_catalog_migration(source, apply=False)

    assert execution.mode == "dry-run"
    assert execution.migration_result.current_version == 8
    assert execution.working_database_path != source
    assert not execution.working_database_path.exists()
    assert "schema_migrations" not in table_names(source)
    with closing(sqlite3.connect(source)) as connection:
        assert connection.execute("SELECT * FROM legacy_records").fetchall() == [
            ("legacy-1", "preserve exactly")
        ]
        assert connection.execute(
            "SELECT program_status FROM benefit_programs"
        ).fetchone() == ("status_unknown",)


def test_apply_requires_backup_and_preserves_pre_migration_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "source.before-migration.db"
    create_supported_legacy_database(source)

    with pytest.raises(CatalogMigrationCliError) as captured:
        execute_catalog_migration(source, apply=True)
    assert captured.value.code == "backup_required_for_apply"

    execution = execute_catalog_migration(source, apply=True, backup_path=backup)

    assert execution.mode == "apply"
    assert execution.migration_result.current_version == 8
    assert execution.backup_path == backup
    assert "schema_migrations" in table_names(source)
    assert "schema_migrations" not in table_names(backup)
    with closing(sqlite3.connect(source)) as connection:
        assert connection.execute(
            "SELECT program_status FROM benefit_programs "
            "WHERE program_id = 'legacy-program'"
        ).fetchone() == ("under_review",)
    with closing(sqlite3.connect(backup)) as connection:
        assert connection.execute(
            "SELECT program_status FROM benefit_programs "
            "WHERE program_id = 'legacy-program'"
        ).fetchone() == ("status_unknown",)
        assert connection.execute("SELECT * FROM program_rule_fields").fetchall() == [
            (
                "legacy-program",
                "legacy-field",
                "text",
                "legacy-value",
                "",
                "pending",
                NOW,
                NOW,
            )
        ]


def test_failed_apply_restores_source_from_backup(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "source.rollback.db"
    create_supported_legacy_database(source)
    first = load_migrations()[0]
    failing_second = Migration.from_sql(
        "0002_programs_fields",
        2,
        "INSERT INTO missing_table (value) VALUES ('fail safely');",
    )

    with pytest.raises(MigrationError):
        execute_catalog_migration(
            source,
            apply=True,
            backup_path=backup,
            migrations=(first, failing_second),
        )

    assert backup.exists()
    assert "catalog_revisions" not in table_names(source)
    assert "schema_migrations" not in table_names(source)
    with closing(sqlite3.connect(source)) as connection:
        assert connection.execute("SELECT * FROM legacy_records").fetchall() == [
            ("legacy-1", "preserve exactly")
        ]
        assert connection.execute(
            "SELECT program_status FROM benefit_programs"
        ).fetchone() == ("status_unknown",)


def test_legacy_converter_version_is_bound_to_migration_checksum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = "CREATE TABLE synthetic_checksum_target (value TEXT);"
    original = Migration.from_sql("0006_preserve_legacy_rules", 6, sql)

    monkeypatch.setattr(
        migrations_module,
        "CONVERTER_VERSION",
        "legacy-rule-inventory-v2-test",
    )
    changed = Migration.from_sql("0006_preserve_legacy_rules", 6, sql)

    assert changed.checksum != original.checksum
