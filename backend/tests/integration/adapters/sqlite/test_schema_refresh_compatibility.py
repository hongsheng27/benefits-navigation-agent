from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.migrations import (
    SCHEMA_VERSION_KEY,
    MigrationError,
    load_migrations,
    migrate_database,
)

NOW = "2026-07-30T00:00:00+00:00"
HASH_A = "a" * 64
HASH_B = "b" * 64


def _object_names(connection: sqlite3.Connection, object_type: str) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ?",
            (object_type,),
        )
    }


def _insert_source(connection: sqlite3.Connection, source_id: str) -> None:
    connection.execute(
        """
        INSERT INTO source_registry (
            source_id, name, source_type, base_url, entry_url,
            canonical_host, official_status, access_method,
            connection_status, created_at, updated_at
        ) VALUES (
            ?, 'Synthetic source', 'agency_site',
            'https://example.gov.tw', 'https://example.gov.tw/entry',
            'example.gov.tw', 'verified_official', 'manual_seed',
            'active', ?, ?
        )
        """,
        (source_id, NOW, NOW),
    )


def _insert_program_rule(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO benefit_programs (
            program_id, canonical_name, created_at, updated_at
        ) VALUES ('program-1', 'Synthetic program', ?, ?)
        """,
        (NOW, NOW),
    )
    connection.execute("INSERT INTO rule_definitions VALUES ('rule-1', 'program-1')")
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


def _insert_generation(
    connection: sqlite3.Connection,
    *,
    generation_id: str,
    canonical_hash: str,
    field_value: str,
    rule_version_id: str = "rule-version-1",
    status: str = "validated",
) -> None:
    connection.execute(
        """
        INSERT INTO compat_projection_generations (
            generation_id, rule_version_id, program_id,
            converter_version, canonical_hash, status,
            row_count, created_at, validated_at
        ) VALUES (?, ?, 'program-1', 'converter-v1', ?, 'building', 1, ?, NULL)
        """,
        (generation_id, rule_version_id, canonical_hash, NOW),
    )
    connection.execute(
        """
        INSERT INTO compat_projection_rows (
            generation_id, ordinal, program_id, field_name,
            field_type, field_value, source_excerpt,
            review_status, created_at, updated_at
        ) VALUES (?, 0, 'program-1', 'reserved.rule', 'json', ?, '', 'verified', ?, ?)
        """,
        (generation_id, field_value, NOW, NOW),
    )
    if status == "validated":
        connection.execute(
            """
            UPDATE compat_projection_generations
            SET status = 'validated', validated_at = ?
            WHERE generation_id = ?
            """,
            (NOW, generation_id),
        )


def test_refresh_compatibility_schema_is_version_six(tmp_path: Path) -> None:
    database = tmp_path / "refresh-compatibility.db"

    result = migrate_database(database)

    assert result.current_version == 7
    assert result.applied_migration_ids == (
        "0001_metadata",
        "0002_programs_fields",
        "0003_graph",
        "0004_rules_evidence",
        "0005_refresh_compatibility",
        "0006_preserve_legacy_rules",
        "0007_mvp_catalog_scaffold",
    )
    with closing(sqlite3.connect(database)) as connection:
        tables = _object_names(connection, "table")
        views = _object_names(connection, "view")
        triggers = _object_names(connection, "trigger")
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert {
        "source_crawl_attempts",
        "source_coverage_state",
        "coverage_snapshots",
        "coverage_snapshot_sources",
        "refresh_jobs",
        "compat_projection_generations",
        "compat_projection_rows",
        "compat_projection_active",
    }.issubset(tables)
    assert "program_rule_fields" in views
    assert {
        "trg_compat_projection_active_validated_insert",
        "trg_compat_projection_active_validated_update",
        "trg_compat_projection_generations_program_insert",
        "trg_compat_projection_generations_program_update",
        "trg_rule_definitions_projection_owner_update",
        "trg_rule_versions_projection_owner_update",
        "trg_compat_projection_rows_immutable_insert",
        "trg_compat_projection_rows_immutable_update",
        "trg_compat_projection_rows_immutable_delete",
        "trg_compat_projection_generations_immutable_update",
        "trg_compat_projection_generations_immutable_delete",
        "trg_program_rule_fields_read_only_insert",
        "trg_program_rule_fields_read_only_update",
        "trg_program_rule_fields_read_only_delete",
    }.issubset(triggers)
    assert version == ("7",)
    assert foreign_key_errors == []


def test_refresh_jobs_support_batch_identity_and_atomic_dedup(
    tmp_path: Path,
) -> None:
    database = tmp_path / "refresh-jobs.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_source(connection, "source-1")
        _insert_source(connection, "source-2")
        rows = (
            (
                "job-batch-1",
                "source-1",
                "event-1",
                "2026-07-30",
                "source-1|event-1|2026-07-30",
                NOW,
            ),
            (
                "job-batch-1",
                "source-2",
                "event-1",
                "2026-07-30",
                "source-2|event-1|2026-07-30",
                NOW,
            ),
        )
        connection.executemany(
            """
            INSERT INTO refresh_jobs (
                job_id, source_id, event_id, local_calendar_date,
                dedup_key, requested_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        assert connection.execute(
            "SELECT job_id, source_id FROM refresh_jobs ORDER BY source_id"
        ).fetchall() == [
            ("job-batch-1", "source-1"),
            ("job-batch-1", "source-2"),
        ]

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO refresh_jobs (
                    job_id, source_id, event_id, local_calendar_date,
                    dedup_key, requested_at
                ) VALUES (
                    'job-batch-2', 'source-1', 'event-1', '2026-07-30',
                    'different-key', ?
                )
                """,
                (NOW,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO refresh_jobs (
                    job_id, source_id, event_id, local_calendar_date,
                    dedup_key, requested_at
                ) VALUES (
                    'job-invalid', 'source-1', 'event-2', 'not-a-date',
                    'source-1|event-2|not-a-date', ?
                )
                """,
                (NOW,),
            )


def test_coverage_state_and_snapshot_constraints_preserve_honest_gaps(
    tmp_path: Path,
) -> None:
    database = tmp_path / "coverage.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_source(connection, "source-1")
        connection.execute(
            """
            INSERT INTO source_coverage_state (
                source_id, crawl_status, last_successful_crawl_at,
                indexed_document_count, last_gap_category, updated_at
            ) VALUES (
                'source-1', 'error', ?, 7, 'robots_policy', ?
            )
            """,
            (NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO coverage_snapshots (
                snapshot_id, observed_at, scope_source_ids_json,
                scope_domain_tags_json, scope_hash
            ) VALUES (
                'snapshot-1', ?, '["source-1"]', '["synthetic"]', ?
            )
            """,
            (NOW, HASH_A),
        )
        connection.execute(
            """
            INSERT INTO coverage_snapshot_sources (
                snapshot_id, source_id, crawl_status,
                last_successful_crawl_at, indexed_document_count,
                domain_tags_json, gap_category
            ) VALUES (
                'snapshot-1', 'source-1', 'error', ?, 7,
                '["synthetic"]', 'robots_policy'
            )
            """,
            (NOW,),
        )
        assert connection.execute(
            """
            SELECT observed_at, crawl_status, indexed_document_count,
                   gap_category
            FROM coverage_snapshots
            JOIN coverage_snapshot_sources USING (snapshot_id)
            """
        ).fetchone() == (NOW, "error", 7, "robots_policy")

        invalid_statements = (
            """
            INSERT INTO source_coverage_state (
                source_id, crawl_status, indexed_document_count, updated_at
            ) VALUES ('missing-source', 'pending_crawl', 0, 'x')
            """,
            """
            INSERT INTO coverage_snapshots (
                snapshot_id, observed_at, scope_source_ids_json,
                scope_domain_tags_json, scope_hash
            ) VALUES (
                'bad-json', 'x', '{}', '[]',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
            )
            """,
        )
        for statement in invalid_statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)


def test_active_projection_switch_is_complete_and_view_is_read_only(
    tmp_path: Path,
) -> None:
    database = tmp_path / "active-projection.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_program_rule(connection)
        _insert_generation(
            connection,
            generation_id="generation-1",
            canonical_hash=HASH_A,
            field_value='{"version":1}',
        )
        connection.execute(
            """
            INSERT INTO compat_projection_active (
                program_id, rule_version_id, generation_id, activated_at
            ) VALUES ('program-1', 'rule-version-1', 'generation-1', ?)
            """,
            (NOW,),
        )
        assert connection.execute(
            """
            SELECT field_name, field_value
            FROM program_rule_fields
            WHERE program_id = 'program-1'
            """
        ).fetchall() == [("reserved.rule", '{"version":1}')]

        _insert_generation(
            connection,
            generation_id="generation-2",
            canonical_hash=HASH_B,
            field_value='{"version":2}',
            status="building",
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE compat_projection_active
                SET generation_id = 'generation-2'
                WHERE rule_version_id = 'rule-version-1'
                """
            )
        assert connection.execute(
            "SELECT field_value FROM program_rule_fields"
        ).fetchall() == [('{"version":1}',)]

        for statement in (
            (
                "INSERT INTO program_rule_fields VALUES "
                "('p','f','text','v','','pending','x','x')"
            ),
            "UPDATE program_rule_fields SET field_value = 'changed'",
            "DELETE FROM program_rule_fields",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)


def test_malformed_0005_target_rolls_back_new_schema(tmp_path: Path) -> None:
    database = tmp_path / "malformed-refresh.db"
    first_four = load_migrations()[:4]
    migrate_database(database, migrations=first_four)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE refresh_jobs (job_id TEXT PRIMARY KEY)")

    with pytest.raises(MigrationError) as captured:
        migrate_database(database, migrations=load_migrations()[:5])

    assert captured.value.code == "migration_failed"
    with closing(sqlite3.connect(database)) as connection:
        tables = _object_names(connection, "table")
        applied = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
        malformed_columns = tuple(
            row[1] for row in connection.execute("PRAGMA table_info(refresh_jobs)")
        )

    assert "source_crawl_attempts" not in tables
    assert "compat_projection_generations" not in tables
    assert malformed_columns == ("job_id",)
    assert applied == [
        ("0001_metadata",),
        ("0002_programs_fields",),
        ("0003_graph",),
        ("0004_rules_evidence",),
    ]
    assert version == ("4",)


def test_validated_projection_rows_and_metadata_are_immutable(
    tmp_path: Path,
) -> None:
    database = tmp_path / "immutable-projection.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_program_rule(connection)
        _insert_generation(
            connection,
            generation_id="generation-1",
            canonical_hash=HASH_A,
            field_value='{"version":1}',
        )
        connection.execute(
            """
            INSERT INTO compat_projection_active (
                program_id, rule_version_id, generation_id, activated_at
            ) VALUES ('program-1', 'rule-version-1', 'generation-1', ?)
            """,
            (NOW,),
        )

        immutable_statements = (
            """
            INSERT INTO compat_projection_rows (
                generation_id, ordinal, program_id, field_name,
                field_type, created_at, updated_at
            ) VALUES (
                'generation-1', 1, 'program-1', 'extra', 'text', 'x', 'x'
            )
            """,
            """
            UPDATE compat_projection_rows
            SET field_value = 'changed'
            WHERE generation_id = 'generation-1'
            """,
            """
            DELETE FROM compat_projection_rows
            WHERE generation_id = 'generation-1'
            """,
            """
            UPDATE compat_projection_generations
            SET row_count = 2
            WHERE generation_id = 'generation-1'
            """,
            """
            DELETE FROM compat_projection_generations
            WHERE generation_id = 'generation-1'
            """,
        )
        for statement in immutable_statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)

        assert connection.execute(
            "SELECT field_value FROM program_rule_fields"
        ).fetchall() == [('{"version":1}',)]
        assert connection.execute(
            """
            SELECT status, row_count
            FROM compat_projection_generations
            WHERE generation_id = 'generation-1'
            """
        ).fetchone() == ("validated", 1)


def test_active_projection_switches_across_rule_versions_per_program(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cross-version-switch.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_program_rule(connection)
        connection.execute(
            """
            INSERT INTO rule_versions (
                rule_version_id, rule_id, version, dsl_version,
                approval_status, is_current, created_at
            ) VALUES (
                'rule-version-2', 'rule-1', '2', 'dsl-v1',
                'candidate', 0, ?
            )
            """,
            (NOW,),
        )
        _insert_generation(
            connection,
            generation_id="generation-1",
            canonical_hash=HASH_A,
            field_value='{"version":1}',
        )
        _insert_generation(
            connection,
            generation_id="generation-2",
            canonical_hash=HASH_B,
            field_value='{"version":2}',
            rule_version_id="rule-version-2",
        )
        connection.execute(
            """
            INSERT INTO compat_projection_active (
                program_id, rule_version_id, generation_id, activated_at
            ) VALUES ('program-1', 'rule-version-1', 'generation-1', ?)
            """,
            (NOW,),
        )
        connection.execute(
            """
            UPDATE compat_projection_active
            SET rule_version_id = 'rule-version-2',
                generation_id = 'generation-2',
                activated_at = ?
            WHERE program_id = 'program-1'
            """,
            (NOW,),
        )

        assert connection.execute(
            """
            SELECT program_id, rule_version_id, generation_id
            FROM compat_projection_active
            """
        ).fetchall() == [("program-1", "rule-version-2", "generation-2")]
        assert connection.execute(
            "SELECT field_value FROM program_rule_fields"
        ).fetchall() == [('{"version":2}',)]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO compat_projection_active (
                    program_id, rule_version_id, generation_id, activated_at
                ) VALUES (
                    'program-1', 'rule-version-1', 'generation-1', ?
                )
                """,
                (NOW,),
            )


@pytest.mark.parametrize(
    "trigger_name",
    (
        "trg_compat_projection_rows_immutable_update",
        "trg_program_status_history_protected_actor",
    ),
)
def test_rerun_rejects_tampered_applied_target(
    tmp_path: Path,
    trigger_name: str,
) -> None:
    database = tmp_path / f"tampered-{trigger_name}.db"
    migrate_database(database)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(f'DROP TRIGGER "{trigger_name}"')

    with pytest.raises(MigrationError) as captured:
        migrate_database(database)

    assert captured.value.code == "migration_target_invalid"


def test_projection_generation_rejects_cross_program_rule_version(
    tmp_path: Path,
) -> None:
    database = tmp_path / "cross-program-generation.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_program_rule(connection)
        connection.executemany(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                ("program-2", "Synthetic program 2", NOW, NOW),
                ("program-3", "Synthetic program 3", NOW, NOW),
            ),
        )
        connection.execute(
            "INSERT INTO rule_definitions VALUES ('rule-2', 'program-2')"
        )
        connection.execute(
            """
            INSERT INTO rule_versions (
                rule_version_id, rule_id, version, dsl_version,
                approval_status, is_current, created_at
            ) VALUES (
                'rule-version-2', 'rule-2', '1', 'dsl-v1',
                'candidate', 0, ?
            )
            """,
            (NOW,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO compat_projection_generations (
                    generation_id, rule_version_id, program_id,
                    converter_version, canonical_hash, created_at
                ) VALUES (
                    'cross-program-generation', 'rule-version-1', 'program-2',
                    'converter-v1', ?, ?
                )
                """,
                (HASH_A, NOW),
            )

        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM compat_projection_generations
            WHERE generation_id = 'cross-program-generation'
            """
        ).fetchone() == (0,)
        connection.execute(
            """
            INSERT INTO compat_projection_generations (
                generation_id, rule_version_id, program_id,
                converter_version, canonical_hash, created_at
            ) VALUES (
                'valid-generation', 'rule-version-1', 'program-1',
                'converter-v1', ?, ?
            )
            """,
            (HASH_A, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE compat_projection_generations
                SET program_id = 'program-2'
                WHERE generation_id = 'valid-generation'
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE rule_definitions
                SET program_id = 'program-3'
                WHERE rule_id = 'rule-1'
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE rule_versions
                SET rule_id = 'rule-2'
                WHERE rule_version_id = 'rule-version-1'
                """
            )


def test_rerun_rejects_semantically_weakened_ownership_trigger(
    tmp_path: Path,
) -> None:
    database = tmp_path / "weakened-ownership-trigger.db"
    migrate_database(database)
    trigger_name = "trg_compat_projection_generations_program_insert"
    with closing(sqlite3.connect(database)) as connection, connection:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger_name,),
        ).fetchone()
        assert row is not None
        trigger_sql = str(row[0])
        weakened_sql = trigger_sql.replace(
            "rule_definition.program_id = NEW.program_id",
            "(rule_definition.program_id = NEW.program_id OR 1 = 1)",
            1,
        )
        assert weakened_sql != trigger_sql
        connection.execute(f'DROP TRIGGER "{trigger_name}"')
        connection.execute(weakened_sql)

    with pytest.raises(MigrationError) as captured:
        migrate_database(database)

    assert captured.value.code == "migration_target_invalid"
