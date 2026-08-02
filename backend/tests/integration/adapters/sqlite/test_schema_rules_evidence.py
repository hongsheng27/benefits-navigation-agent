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

NOW = "2026-07-30T00:00:00+00:00"


def _object_names(connection: sqlite3.Connection, object_type: str) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ?",
            (object_type,),
        )
    }


def _insert_program_and_field(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO benefit_programs (
            program_id, canonical_name, created_at, updated_at
        ) VALUES ('program-1', 'Synthetic program', ?, ?)
        """,
        (NOW, NOW),
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


def _insert_source(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    official_status: str = "verified_official",
) -> None:
    connection.execute(
        """
        INSERT INTO source_registry (
            source_id, name, source_type, jurisdiction_code,
            organization_name, base_url, entry_url, canonical_host,
            official_status, access_method, connection_status, enabled,
            reviewed_at, review_note, created_at, updated_at
        ) VALUES (
            ?, 'Synthetic source', 'agency_site', 'TW',
            'Synthetic publisher', 'https://example.gov.tw',
            'https://example.gov.tw/entry', 'example.gov.tw',
            ?, 'manual_seed', 'active', 1, ?, '', ?, ?
        )
        """,
        (source_id, official_status, NOW, NOW, NOW),
    )


def _insert_document(
    connection: sqlite3.Connection,
    *,
    document_id: str = "document-1",
    review_status: str = "verified",
) -> None:
    connection.execute(
        """
        INSERT INTO source_documents (
            document_id, canonical_url, title, publisher_name,
            first_seen_at, last_seen_at, retrieved_at, review_status,
            created_at, updated_at, effective_at
        ) VALUES (
            ?, ?, 'Synthetic document', 'Synthetic publisher',
            ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            document_id,
            f"https://example.gov.tw/{document_id}",
            NOW,
            NOW,
            NOW,
            review_status,
            NOW,
            NOW,
            NOW,
        ),
    )


def _link_document_source(
    connection: sqlite3.Connection,
    *,
    document_id: str = "document-1",
    source_id: str = "source-1",
) -> None:
    connection.execute(
        """
        INSERT INTO document_discoveries (
            document_id, source_id, discovery_url, discovery_method,
            first_seen_at, last_seen_at
        ) VALUES (?, ?, 'https://example.gov.tw/entry', 'manual_seed', ?, ?)
        """,
        (document_id, source_id, NOW, NOW),
    )


def _insert_rule_draft(connection: sqlite3.Connection) -> None:
    connection.execute("INSERT INTO rule_definitions VALUES ('rule-1', 'program-1')")
    connection.execute(
        """
        INSERT INTO rule_versions (
            rule_version_id, rule_id, version, dsl_version,
            approval_status, is_current, created_at
        ) VALUES ('rule-version-1', 'rule-1', '1', 'dsl-v1', 'candidate', 0, ?)
        """,
        (NOW,),
    )
    connection.execute(
        """
        INSERT INTO rule_nodes (
            node_id, rule_version_id, parent_node_id, node_type, child_order
        ) VALUES ('root-1', 'rule-version-1', NULL, 'all_of', 0)
        """
    )
    connection.execute(
        """
        INSERT INTO rule_nodes (
            node_id, rule_version_id, parent_node_id, node_type, child_order
        ) VALUES (
            'condition-node-1', 'rule-version-1', 'root-1', 'condition', 0
        )
        """
    )
    connection.execute(
        """
        INSERT INTO rule_conditions (
            condition_id, node_id, field_id, operator,
            expected_value_type, expected_value_json, label, source_reference
        ) VALUES (
            'condition-1', 'condition-node-1', 'field-1', 'opaque_operator',
            'integer', '2', 'Synthetic condition', 'source-ref-1'
        )
        """
    )
    connection.execute(
        "INSERT INTO rule_required_fields VALUES ('rule-version-1', 'field-1', 0)"
    )
    connection.execute(
        "INSERT INTO rule_version_source_refs VALUES ('rule-version-1', 'source-ref-1')"
    )


def test_fresh_schema_has_required_rule_evidence_objects(tmp_path: Path) -> None:
    database = tmp_path / "fresh-rules-evidence.db"

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
            "source_registry",
            "source_documents",
            "document_discoveries",
            "source_domain_tags",
            "rule_definitions",
            "rule_versions",
            "rule_nodes",
            "rule_conditions",
            "rule_required_fields",
            "rule_version_source_refs",
            "approved_amounts",
            "evidence_excerpts",
            "program_evidence_links",
            "source_reference_evidence",
            "document_attachments",
        }.issubset(_object_names(connection, "table"))
        assert {
            "uq_rule_versions_current_approved",
            "uq_rule_nodes_root_per_version",
            "idx_rule_nodes_parent_order",
            "idx_rule_required_fields_order",
            "idx_evidence_excerpts_document_status",
            "idx_document_attachments_document_status",
        }.issubset(_object_names(connection, "index"))
        assert {
            "trg_evidence_excerpts_verified_source_insert",
            "trg_evidence_excerpts_verified_source_update",
            "trg_program_evidence_links_verified_insert",
            "trg_program_evidence_links_verified_update",
        }.issubset(_object_names(connection, "trigger"))
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_rule_versions_tree_and_current_approval_constraints(tmp_path: Path) -> None:
    database = tmp_path / "rule-tree.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_program_and_field(connection)
        _insert_rule_draft(connection)
        connection.execute(
            """
            UPDATE rule_versions
            SET root_node_id = 'root-1', approval_status = 'approved',
                is_current = 1, approved_by = 'reviewer:test', approved_at = ?
            WHERE rule_version_id = 'rule-version-1'
            """,
            (NOW,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO rule_definitions VALUES ('rule-duplicate', 'program-1')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO rule_versions (
                    rule_version_id, rule_id, version, dsl_version,
                    approval_status, is_current, root_node_id, created_at
                ) VALUES (
                    'bad-approved', 'rule-1', '2', 'dsl-v1',
                    'approved', 1, NULL, ?
                )
                """,
                (NOW,),
            )

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
        connection.execute(
            """
            INSERT INTO rule_nodes
            VALUES ('root-2', 'rule-version-2', NULL, 'any_of', 0)
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE rule_versions
                SET root_node_id = 'root-2', approval_status = 'approved',
                    is_current = 1, approved_by = 'reviewer:test', approved_at = ?
                WHERE rule_version_id = 'rule-version-2'
                """,
                (NOW,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO rule_nodes
                VALUES ('second-root', 'rule-version-2', NULL, 'all_of', 1)
                """
            )


def test_rule_conditions_amounts_and_references_are_typed(tmp_path: Path) -> None:
    database = tmp_path / "rule-values.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_program_and_field(connection)
        _insert_rule_draft(connection)
        connection.executemany(
            """
            INSERT INTO rule_nodes (
                node_id, rule_version_id, parent_node_id, node_type, child_order
            ) VALUES (?, 'rule-version-1', 'root-1', 'condition', ?)
            """,
            (
                ("condition-node-bad-json", 1),
                ("condition-node-wrong-type", 2),
                ("condition-node-missing-field", 3),
            ),
        )
        invalid_conditions = (
            (
                "condition-bad-json",
                "condition-node-bad-json",
                "field-1",
                "operator",
                "integer",
                "{",
                "Synthetic",
                "source-ref-1",
            ),
            (
                "condition-wrong-type",
                "condition-node-wrong-type",
                "field-1",
                "operator",
                "integer",
                '"2"',
                "Synthetic",
                "source-ref-1",
            ),
            (
                "condition-missing-field",
                "condition-node-missing-field",
                "absent",
                "operator",
                "integer",
                "2",
                "Synthetic",
                "source-ref-1",
            ),
        )
        for row in invalid_conditions:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO rule_conditions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO approved_amounts
                VALUES (
                    'rule-version-1', 300, 200, 'once', 'TWD', 'source-ref-1'
                )
                """
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO approved_amounts
                VALUES (
                    'rule-version-1', 100, 200, 'once', 'TWD', 'absent-ref'
                )
                """
            )
        connection.execute(
            """
            INSERT INTO approved_amounts
            VALUES ('rule-version-1', 100, 200, 'once', 'TWD', 'source-ref-1')
            """
        )


def test_verified_evidence_requires_official_source_and_review_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evidence.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_program_and_field(connection)
        _insert_rule_draft(connection)
        _insert_source(connection, source_id="source-1")
        _insert_source(
            connection,
            source_id="source-2",
            official_status="pending_review",
        )
        _insert_document(connection)
        _link_document_source(connection, source_id="source-1")
        _link_document_source(connection, source_id="source-2")
        connection.execute(
            """
            INSERT INTO evidence_excerpts
            VALUES (
                'evidence-1', 'document-1', 'Synthetic reviewed excerpt',
                'verified', 'reviewer:test', ?, ?, ?
            )
            """,
            (NOW, NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO program_evidence_links
            VALUES (
                'program-1', 'evidence-1', 'eligibility',
                'verified', 'reviewer:test', ?
            )
            """,
            (NOW,),
        )
        connection.execute(
            """
            INSERT INTO source_reference_evidence
            VALUES ('rule-version-1', 'source-ref-1', 'evidence-1')
            """
        )

        _insert_document(
            connection,
            document_id="document-non-official",
        )
        _link_document_source(
            connection,
            document_id="document-non-official",
            source_id="source-2",
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO evidence_excerpts
                VALUES (
                    'evidence-non-official', 'document-non-official',
                    'Synthetic excerpt', 'verified', 'reviewer:test', ?, ?, ?
                )
                """,
                (NOW, NOW, NOW),
            )

        _insert_document(
            connection,
            document_id="document-unreviewed",
            review_status="candidate",
        )
        _link_document_source(connection, document_id="document-unreviewed")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO evidence_excerpts
                VALUES (
                    'evidence-unreviewed', 'document-unreviewed',
                    'Synthetic excerpt', 'verified', 'reviewer:test', ?, ?, ?
                )
                """,
                (NOW, NOW, NOW),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO evidence_excerpts
                VALUES (
                    'evidence-no-reviewer', 'document-1',
                    'Synthetic excerpt', 'verified', NULL, NULL, ?, ?
                )
                """,
                (NOW, NOW),
            )

        connection.execute(
            """
            INSERT INTO evidence_excerpts
            VALUES (
                'evidence-candidate', 'document-1', '',
                'candidate', NULL, NULL, ?, ?
            )
            """,
            (NOW, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO program_evidence_links
                VALUES (
                    'program-1', 'evidence-candidate', 'overview',
                    'verified', 'reviewer:test', ?
                )
                """,
                (NOW,),
            )


def test_attachments_support_local_and_s3_references_with_safe_gates(
    tmp_path: Path,
) -> None:
    database = tmp_path / "attachments.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_source(connection, source_id="source-1")
        _insert_document(connection)
        _link_document_source(connection)
        connection.execute(
            """
            INSERT INTO document_attachments (
                attachment_id, document_id, filename, media_type, source_url,
                storage_backend, storage_ref, content_hash,
                extraction_status, extraction_method, extracted_at,
                review_status, reviewer_ref, reviewed_at, created_at, updated_at
            ) VALUES (
                'attachment-local', 'document-1', 'synthetic.pdf',
                'application/pdf', 'https://example.gov.tw/synthetic.pdf',
                'local', 'attachments/synthetic.pdf', 'sha256:synthetic',
                'extracted', 'fixture-parser', ?,
                'verified', 'reviewer:test', ?, ?, ?
            )
            """,
            (NOW, NOW, NOW, NOW),
        )
        connection.execute(
            """
            INSERT INTO document_attachments (
                attachment_id, document_id, filename, media_type, source_url,
                storage_backend, storage_ref, content_hash,
                extraction_status, review_status, created_at, updated_at
            ) VALUES (
                'attachment-s3', 'document-1', 'future.pdf',
                'application/pdf', 'https://example.gov.tw/future.pdf',
                's3', 'documents/future.pdf', 'sha256:future',
                'pending', 'candidate', ?, ?
            )
            """,
            (NOW, NOW),
        )

        invalid_rows = (
            (
                "partial-storage",
                "document-1",
                "bad.pdf",
                "application/pdf",
                "https://example.gov.tw/bad.pdf",
                "local",
                None,
                None,
                "pending",
                None,
                None,
                "candidate",
                None,
                None,
                NOW,
                NOW,
            ),
            (
                "missing-extraction-metadata",
                "document-1",
                "bad2.pdf",
                "application/pdf",
                "https://example.gov.tw/bad2.pdf",
                "local",
                "bad2.pdf",
                "sha256:bad2",
                "extracted",
                None,
                None,
                "candidate",
                None,
                None,
                NOW,
                NOW,
            ),
            (
                "verified-without-reviewer",
                "document-1",
                "bad3.pdf",
                "application/pdf",
                "https://example.gov.tw/bad3.pdf",
                "s3",
                "bad3.pdf",
                "sha256:bad3",
                "pending",
                None,
                None,
                "verified",
                None,
                None,
                NOW,
                NOW,
            ),
        )
        for row in invalid_rows:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO document_attachments VALUES ("
                    "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )


def test_known_legacy_sources_are_preserved_and_gain_effective_date(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-sources.db"
    initialize_database(database, source_seed_path=None)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_source(connection, source_id="legacy-source")
        connection.execute(
            """
            INSERT INTO source_documents (
                document_id, canonical_url, title, publisher_name,
                first_seen_at, last_seen_at, retrieved_at, review_status,
                created_at, updated_at
            ) VALUES (
                'legacy-document',
                'https://example.gov.tw/legacy-document',
                'Synthetic document', 'Synthetic publisher',
                ?, ?, ?, 'candidate', ?, ?
            )
            """,
            (NOW, NOW, NOW, NOW, NOW),
        )
        _link_document_source(
            connection,
            document_id="legacy-document",
            source_id="legacy-source",
        )

    result = migrate_database(database)

    assert result.current_version == 8
    with closing(sqlite3.connect(database)) as connection:
        document = connection.execute(
            """
            SELECT document_id, title, review_status, effective_at
            FROM source_documents
            WHERE document_id = 'legacy-document'
            """
        ).fetchone()
        discovery = connection.execute(
            """
            SELECT document_id, source_id
            FROM document_discoveries
            WHERE document_id = 'legacy-document'
            """
        ).fetchone()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    assert document == (
        "legacy-document",
        "Synthetic document",
        "candidate",
        None,
    )
    assert discovery == ("legacy-document", "legacy-source")


def test_invalid_rules_evidence_batch_rolls_back_all_rows(tmp_path: Path) -> None:
    database = tmp_path / "rules-evidence-batch.db"
    migrate_database(database)

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            _insert_program_and_field(connection)
            _insert_rule_draft(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                INSERT INTO rule_version_source_refs
                VALUES ('rule-version-1', 'batch-valid');
                INSERT INTO source_reference_evidence
                VALUES ('rule-version-1', 'batch-missing', 'missing-evidence');
                COMMIT;
                """
            )
        connection.rollback()
        assert (
            connection.execute(
                """
            SELECT source_reference
            FROM rule_version_source_refs
            WHERE source_reference = 'batch-valid'
            """
            ).fetchall()
            == []
        )


def test_failed_0004_rolls_back_legacy_effective_date_and_partial_schema(
    tmp_path: Path,
) -> None:
    database = tmp_path / "legacy-rules-evidence-rollback.db"
    initialize_database(database, source_seed_path=None)
    with closing(sqlite3.connect(database)) as connection, connection:
        _insert_source(connection, source_id="legacy-source")
        connection.execute(
            """
            INSERT INTO source_documents (
                document_id, canonical_url, title, publisher_name,
                first_seen_at, last_seen_at, retrieved_at, review_status,
                created_at, updated_at
            ) VALUES (
                'legacy-document', 'https://example.gov.tw/legacy-rollback',
                'Synthetic document', 'Synthetic publisher',
                ?, ?, ?, 'candidate', ?, ?
            )
            """,
            (NOW, NOW, NOW, NOW, NOW),
        )
        _link_document_source(
            connection,
            document_id="legacy-document",
            source_id="legacy-source",
        )

    migrations = load_migrations()
    failing_0004 = Migration.from_sql(
        "0004_rules_evidence",
        4,
        "CREATE TABLE partial_0004 (partial_id TEXT PRIMARY KEY);",
    )
    with pytest.raises(MigrationError) as captured:
        migrate_database(database, migrations=(*migrations[:3], failing_0004))

    assert captured.value.code == "migration_target_invalid"
    with closing(sqlite3.connect(database)) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(source_documents)")
        }
        tables = _object_names(connection, "table")
        applied = connection.execute(
            "SELECT migration_id FROM schema_migrations ORDER BY migration_id"
        ).fetchall()
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = ?",
            (SCHEMA_VERSION_KEY,),
        ).fetchone()
        document = connection.execute(
            """
            SELECT document_id, title, review_status
            FROM source_documents
            WHERE document_id = 'legacy-document'
            """
        ).fetchone()
        discovery = connection.execute(
            """
            SELECT document_id, source_id
            FROM document_discoveries
            WHERE document_id = 'legacy-document'
            """
        ).fetchone()

    assert "effective_at" not in columns
    assert "partial_0004" not in tables
    assert applied == [
        ("0001_metadata",),
        ("0002_programs_fields",),
        ("0003_graph",),
    ]
    assert version == ("3",)
    assert document == ("legacy-document", "Synthetic document", "candidate")
    assert discovery == ("legacy-document", "legacy-source")


def test_malformed_preexisting_target_rolls_back_0004(tmp_path: Path) -> None:
    database = tmp_path / "malformed-rules-evidence.db"
    first_three = load_migrations()[:3]
    migrate_database(database, migrations=first_three)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE rule_definitions (
                rule_id TEXT PRIMARY KEY,
                program_id TEXT
            )
            """
        )
        connection.execute("INSERT INTO rule_definitions VALUES ('legacy-rule', NULL)")

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
        malformed_row = connection.execute("SELECT * FROM rule_definitions").fetchone()

    assert "rule_versions" not in tables
    assert "evidence_excerpts" not in tables
    assert "document_attachments" not in tables
    assert applied == [
        ("0001_metadata",),
        ("0002_programs_fields",),
        ("0003_graph",),
    ]
    assert version == ("3",)
    assert malformed_row == ("legacy-rule", None)
