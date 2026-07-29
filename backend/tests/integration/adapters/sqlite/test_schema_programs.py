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
from scripts.init_benefit_catalog import initialize_database

NOW = "2026-07-30T00:00:00+00:00"


def _object_names(connection: sqlite3.Connection, object_type: str) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ?",
            (object_type,),
        )
    }


def _create_supported_legacy_database(path: Path) -> None:
    initialize_database(path, source_seed_path=None)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE legacy_records (
                record_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO legacy_records VALUES ('legacy-1', 'preserve exactly')"
        )
        connection.execute(
            """
            INSERT INTO source_documents (
                document_id, canonical_url, title, first_seen_at, last_seen_at,
                created_at, updated_at
            )
            VALUES ('document-1', 'https://example.gov.tw/program', 'Synthetic',
                    ?, ?, ?, ?)
            """,
            (NOW, NOW, NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, summary, jurisdiction_code,
                program_status, status_note, created_at, updated_at
            )
            VALUES (
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
            )
            VALUES (
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
            )
            VALUES (
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
            )
            VALUES (
                'legacy-program', 'legacy_field', 'text', 'legacy-value',
                '', 'pending', ?, ?
            )
            """,
            (NOW, NOW),
        )


def test_fresh_schema_has_required_program_review_and_field_objects(
    tmp_path: Path,
) -> None:
    database = tmp_path / "fresh.db"

    result = migrate_database(database)

    assert result.current_version == 2
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        assert {
            "benefit_programs",
            "program_status_history",
            "review_approvals",
            "field_registry",
            "field_allowed_values",
        }.issubset(_object_names(connection, "table"))
        assert {
            "idx_benefit_programs_status_program",
            "idx_program_status_history_program_reviewed",
            "uq_review_approvals_approved_artifact_version",
            "idx_review_approvals_artifact",
            "idx_field_registry_active_field",
            "idx_field_allowed_values_order",
        }.issubset(_object_names(connection, "index"))
        assert "trg_program_status_history_protected_actor" in _object_names(
            connection, "trigger"
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_program_status_amount_and_revision_constraints(tmp_path: Path) -> None:
    database = tmp_path / "constraints.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO catalog_revisions (
                revision_id, committed_at, actor_ref, description_code
            ) VALUES ('revision-1', ?, 'reviewer:test', 'synthetic')
            """,
            (NOW,),
        )
        connection.execute(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, program_status,
                amount_min, amount_max, amount_period, amount_currency,
                current_revision_id, created_at, updated_at
            ) VALUES (
                'program-valid', 'Synthetic', 'candidate',
                100, 200, 'once', 'TWD', 'revision-1', ?, ?
            )
            """,
            (NOW, NOW),
        )

        invalid_statements = (
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, program_status, created_at, updated_at
            ) VALUES ('bad-status', 'Synthetic', 'status_unknown', ?, ?)
            """,
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, amount_min, created_at, updated_at
            ) VALUES ('partial-amount', 'Synthetic', 100, ?, ?)
            """,
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, amount_min, amount_max,
                amount_period, amount_currency, created_at, updated_at
            ) VALUES ('reversed-amount', 'Synthetic', 200, 100, 'once', 'TWD', ?, ?)
            """,
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, current_revision_id,
                created_at, updated_at
            ) VALUES ('missing-revision', 'Synthetic', 'absent', ?, ?)
            """,
        )
        for statement in invalid_statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement, (NOW, NOW))


def test_review_and_field_registry_constraints(tmp_path: Path) -> None:
    database = tmp_path / "review-fields.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, created_at, updated_at
            ) VALUES ('program-1', 'Synthetic', ?, ?)
            """,
            (NOW, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO program_status_history (
                    history_id, program_id, from_status, to_status, actor_type,
                    reviewer_ref, reviewed_at, approved_version
                ) VALUES (
                    'history-invalid', 'program-1', 'candidate', 'verified',
                    'migration', 'migration:test', ?, 'v1'
                )
                """,
                (NOW,),
            )
        connection.execute(
            """
            INSERT INTO program_status_history (
                history_id, program_id, from_status, to_status, actor_type,
                reviewer_ref, reviewed_at, approved_version
            ) VALUES (
                'history-valid', 'program-1', 'candidate', 'under_review',
                'human_reviewer', 'reviewer:test', ?, 'v1'
            )
            """,
            (NOW,),
        )

        approval = (
            "approval-1",
            "program",
            "program-1",
            "v1",
            "reviewer:test",
            NOW,
            "approved",
        )
        connection.execute(
            "INSERT INTO review_approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
            approval,
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO review_approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("approval-2", *approval[1:]),
            )

        connection.execute(
            """
            INSERT INTO field_registry (
                field_id, data_type, prompt_label, why_needed,
                pii_classification, active
            ) VALUES ('field-1', 'enum', 'Synthetic prompt', 'Synthetic reason',
                      'eligibility_sensitive', 1)
            """
        )
        connection.execute(
            "INSERT INTO field_allowed_values VALUES ('field-1', 'a', 0)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO field_allowed_values VALUES ('field-1', 'b', 0)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO field_allowed_values VALUES ('missing', 'a', 0)"
            )


def test_known_legacy_upgrade_preserves_references_and_audits_status_mapping(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy.db"
    _create_supported_legacy_database(database)

    result = migrate_database(database)

    assert result.previous_version == 0
    assert result.current_version == 2
    assert result.applied_migration_ids == ("0001_metadata", "0002_programs_fields")
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        program = connection.execute(
            """
            SELECT program_id, canonical_name, summary, jurisdiction_code,
                   program_status, status_note, amount_min, current_revision_id
            FROM benefit_programs
            """
        ).fetchone()
        history = connection.execute(
            """
            SELECT program_id, from_status, to_status, actor_type,
                   reviewer_ref, approved_version
            FROM program_status_history
            """
        ).fetchall()
        source_program = connection.execute(
            "SELECT program_id FROM program_sources"
        ).fetchone()
        role_program = connection.execute(
            "SELECT program_id FROM program_organization_roles"
        ).fetchone()
        rule_program = connection.execute(
            "SELECT program_id FROM program_rule_fields"
        ).fetchone()
        metadata = dict(connection.execute("SELECT key, value FROM schema_metadata"))
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert program == (
        "legacy-program",
        "Synthetic legacy program",
        "legacy summary",
        "TW",
        "under_review",
        "legacy note",
        None,
        None,
    )
    assert history == [
        (
            "legacy-program",
            "status_unknown",
            "under_review",
            "migration",
            "migration:0002_programs_fields",
            "0002",
        )
    ]
    assert source_program == ("legacy-program",)
    assert role_program == ("legacy-program",)
    assert rule_program == ("legacy-program",)
    assert metadata[SCHEMA_VERSION_KEY] == "2"
    assert foreign_key_errors == []


def test_review_metadata_and_transition_shapes_are_required(tmp_path: Path) -> None:
    database = tmp_path / "review-metadata.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, created_at, updated_at
            ) VALUES ('program-1', 'Synthetic', ?, ?)
            """,
            (NOW, NOW),
        )
        invalid_history_rows = (
            (
                "history-invalid-transition",
                "program-1",
                "candidate",
                "stale",
                "human_reviewer",
                "reviewer:test",
                NOW,
                "v1",
            ),
            (
                "history-missing-reviewer",
                "program-1",
                "candidate",
                "under_review",
                "human_reviewer",
                "",
                NOW,
                "v1",
            ),
        )
        for row in invalid_history_rows:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO program_status_history
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO review_approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    "approval-invalid",
                    "program",
                    "program-1",
                    "",
                    "reviewer:test",
                    NOW,
                    "approved",
                ),
            )


def test_malformed_preexisting_target_table_fails_closed_and_rolls_back_0002(
    tmp_path: Path,
) -> None:
    database = tmp_path / "malformed-target.db"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executescript(
            """
            CREATE TABLE field_registry (
                field_id TEXT PRIMARY KEY,
                data_type TEXT NOT NULL,
                prompt_label TEXT NOT NULL,
                why_needed TEXT NOT NULL,
                pii_classification TEXT NOT NULL,
                active INTEGER NOT NULL
            );
            INSERT INTO field_registry VALUES (
                'legacy-field', 'not-constrained', '', '', 'unknown', 7
            );
            """
        )

    with pytest.raises(MigrationError) as captured:
        migrate_database(database)

    assert captured.value.code == "migration_target_invalid"
    assert str(captured.value) == "migration_target_invalid"
    with closing(sqlite3.connect(database)) as connection:
        tables = _object_names(connection, "table")
        applied = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
        malformed_row = connection.execute("SELECT * FROM field_registry").fetchone()
    assert "benefit_programs" not in tables
    assert "program_status_history" not in tables
    assert applied == [("0001_metadata",)]
    assert version == ("1",)
    assert malformed_row == ("legacy-field", "not-constrained", "", "", "unknown", 7)
