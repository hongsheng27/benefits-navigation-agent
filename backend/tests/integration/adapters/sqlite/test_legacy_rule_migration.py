from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import backend.app.adapters.sqlite.migrations as migrations_module
import pytest
from backend.app.adapters.sqlite.legacy_rule_conversion import (
    persist_legacy_rule_conversion,
    prepare_legacy_rule_inventory,
)
from backend.app.adapters.sqlite.migrations import (
    SCHEMA_VERSION_KEY,
    Migration,
    MigrationError,
    load_migrations,
    migrate_database,
)
from scripts.init_benefit_catalog import initialize_database

NOW = "2026-07-30T00:00:00+00:00"


def _create_legacy_database(path: Path) -> None:
    initialize_database(path, source_seed_path=None)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
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
        connection.executemany(
            """
            INSERT INTO program_rule_fields (
                program_id, field_name, field_type, field_value,
                source_excerpt, review_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "legacy-program",
                    "legacy-a",
                    "text",
                    "synthetic-a",
                    "",
                    "pending",
                    NOW,
                    NOW,
                ),
                (
                    "legacy-program",
                    "legacy-b",
                    "integer",
                    "2",
                    "Synthetic unapproved excerpt",
                    "rejected",
                    NOW,
                    NOW,
                ),
            ),
        )


def _object_type(connection: sqlite3.Connection, name: str) -> str | None:
    row = connection.execute(
        "SELECT type FROM sqlite_master WHERE name = ?",
        (name,),
    ).fetchone()
    return None if row is None else str(row[0])


def _legacy_rows(connection: sqlite3.Connection, table_name: str) -> list[tuple]:
    return connection.execute(
        f"""
        SELECT
            program_id, field_name, field_type, field_value,
            source_excerpt, review_status, created_at, updated_at
        FROM {table_name}
        ORDER BY program_id, field_name
        """
    ).fetchall()


def test_legacy_rows_are_frozen_in_version_five(tmp_path: Path) -> None:
    database = tmp_path / "legacy-v5.db"
    _create_legacy_database(database)
    first_five = load_migrations()[:5]

    result = migrate_database(database, migrations=first_five)

    assert result.current_version == 5
    with closing(sqlite3.connect(database)) as connection:
        assert _object_type(connection, "program_rule_fields") == "table"
        assert [row[1] for row in _legacy_rows(connection, "program_rule_fields")] == [
            "legacy-a",
            "legacy-b",
        ]
        for statement in (
            """
            INSERT INTO program_rule_fields VALUES (
                'legacy-program', 'new', 'text', '', '', 'pending', 'x', 'x'
            )
            """,
            "UPDATE program_rule_fields SET field_value = 'changed'",
            "DELETE FROM program_rule_fields",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)


def test_0006_preserves_rows_and_creates_under_review_manifest(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-v6.db"
    _create_legacy_database(database)
    migrations = load_migrations()
    migrate_database(database, migrations=migrations[:5])
    with closing(sqlite3.connect(database)) as connection:
        inventory = prepare_legacy_rule_inventory(connection)
        before_rows = _legacy_rows(connection, "program_rule_fields")
    assert inventory is not None

    result = migrate_database(database)

    assert result.current_version == 7
    with closing(sqlite3.connect(database)) as connection:
        assert _object_type(connection, "program_rule_fields") == "view"
        assert _object_type(connection, "legacy_program_rule_fields_v1") == "table"
        preserved_rows = _legacy_rows(
            connection,
            "legacy_program_rule_fields_v1",
        )
        bridge_rows = _legacy_rows(connection, "program_rule_fields")
        inventory_row = connection.execute(
            """
            SELECT
                source_schema_sha256, source_rows_sha256,
                row_count, converter_version
            FROM legacy_rule_migration_inventory
            """
        ).fetchone()
        draft = connection.execute(
            """
            SELECT
                program_id, conversion_status, reason_code,
                source_row_count, source_rows_sha256
            FROM legacy_rule_conversion_drafts
            """
        ).fetchone()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert preserved_rows == before_rows
    assert bridge_rows == before_rows
    assert inventory_row == (
        inventory.source_schema_sha256,
        inventory.source_rows_sha256,
        2,
        "legacy-rule-inventory-v1",
    )
    assert draft == (
        "legacy-program",
        "under_review",
        "manual_mapping_required",
        2,
        inventory.drafts[0].source_rows_sha256,
    )
    assert foreign_key_errors == []


def test_converter_manifest_is_rerunnable_without_duplicate_rows(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-rerun.db"
    _create_legacy_database(database)
    migrations = load_migrations()
    migrate_database(database, migrations=migrations[:5])
    with closing(sqlite3.connect(database)) as connection:
        inventory = prepare_legacy_rule_inventory(connection)
    assert inventory is not None
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        persist_legacy_rule_conversion(
            connection,
            inventory,
            captured_at="2026-07-31T00:00:00+00:00",
        )
        inventory_count = connection.execute(
            "SELECT COUNT(*) FROM legacy_rule_migration_inventory"
        ).fetchone()
        draft_count = connection.execute(
            "SELECT COUNT(*) FROM legacy_rule_conversion_drafts"
        ).fetchone()

    assert inventory_count == (1,)
    assert draft_count == (1,)


def test_active_canonical_generation_replaces_only_matching_legacy_program(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-bridge-switch.db"
    _create_legacy_database(database)
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO rule_definitions VALUES ('rule-1', 'legacy-program')"
        )
        connection.execute(
            """
            INSERT INTO rule_versions (
                rule_version_id, rule_id, version, dsl_version,
                approval_status, is_current, created_at
            ) VALUES (
                'rule-version-1', 'rule-1', '1', 'dsl-v1',
                'candidate', 0, ?
            )
            """,
            (NOW,),
        )
        connection.execute(
            """
            INSERT INTO compat_projection_generations (
                generation_id, rule_version_id, program_id,
                converter_version, canonical_hash, status,
                row_count, created_at, validated_at
            ) VALUES (
                'generation-1', 'rule-version-1', 'legacy-program',
                'converter-v1', ?, 'building', 1, ?, NULL
            )
            """,
            ("a" * 64, NOW),
        )
        connection.execute(
            """
            INSERT INTO compat_projection_rows (
                generation_id, ordinal, program_id, field_name,
                field_type, field_value, source_excerpt,
                review_status, created_at, updated_at
            ) VALUES (
                'generation-1', 0, 'legacy-program', 'reserved.rule',
                'json', '{"canonical":true}', '', 'verified', ?, ?
            )
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            UPDATE compat_projection_generations
            SET status = 'validated', validated_at = ?
            WHERE generation_id = 'generation-1'
            """,
            (NOW,),
        )
        connection.execute(
            """
            INSERT INTO compat_projection_active (
                program_id, rule_version_id, generation_id, activated_at
            ) VALUES (
                'legacy-program', 'rule-version-1', 'generation-1', ?
            )
            """,
            (NOW,),
        )
        visible_rows = connection.execute(
            """
            SELECT field_name, field_value
            FROM program_rule_fields
            WHERE program_id = 'legacy-program'
            ORDER BY field_name
            """
        ).fetchall()
        preserved_rows = _legacy_rows(
            connection,
            "legacy_program_rule_fields_v1",
        )

    assert visible_rows == [("reserved.rule", '{"canonical":true}')]
    assert [row[1] for row in preserved_rows] == ["legacy-a", "legacy-b"]


def test_failed_0006_with_uncorrelated_bridge_restores_version_five(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-v6-rollback.db"
    _create_legacy_database(database)
    migrations = load_migrations()
    migrate_database(database, migrations=migrations[:5])
    with closing(sqlite3.connect(database)) as connection:
        before_rows = _legacy_rows(connection, "program_rule_fields")

    malformed_sql = migrations[5].sql.replace(
        "WHERE generation.program_id = legacy.program_id",
        "WHERE generation.program_id = legacy.program_id OR 1 = 1",
        1,
    )
    failing_0006 = Migration.from_sql(
        "0006_preserve_legacy_rules",
        6,
        malformed_sql,
    )
    with pytest.raises(MigrationError) as captured:
        migrate_database(
            database,
            migrations=(*migrations[:5], failing_0006),
        )

    assert captured.value.code == "migration_target_invalid"
    with closing(sqlite3.connect(database)) as connection:
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
        applied = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        after_rows = _legacy_rows(connection, "program_rule_fields")
        assert _object_type(connection, "program_rule_fields") == "table"
        assert _object_type(connection, "legacy_program_rule_fields_v1") is None
        assert _object_type(connection, "legacy_rule_migration_inventory") is None

    assert version == ("5",)
    assert applied == [
        ("0001_metadata",),
        ("0002_programs_fields",),
        ("0003_graph",),
        ("0004_rules_evidence",),
        ("0005_refresh_compatibility",),
    ]
    assert after_rows == before_rows


def test_0006_captures_inventory_after_acquiring_immediate_write_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "legacy-inventory-lock.db"
    _create_legacy_database(database)
    migrations = load_migrations()
    migrate_database(database, migrations=migrations[:5])
    original_prepare = migrations_module.prepare_legacy_rule_inventory
    observed_transaction = False

    def guarded_prepare(
        connection: sqlite3.Connection,
    ) -> migrations_module.LegacyRuleInventory | None:
        nonlocal observed_transaction
        observed_transaction = connection.in_transaction
        with closing(sqlite3.connect(database, timeout=0)) as competitor:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                competitor.execute(
                    "UPDATE schema_metadata SET value = value WHERE key = ?",
                    (SCHEMA_VERSION_KEY,),
                )
        return original_prepare(connection)

    monkeypatch.setattr(
        migrations_module,
        "prepare_legacy_rule_inventory",
        guarded_prepare,
    )

    result = migrate_database(database)

    assert result.current_version == 7
    assert observed_transaction is True
