from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from backend.app.services.benefit_catalog import (
    get_catalog_summary,
    get_registered_source_statuses,
    load_source_seeds,
)
from scripts.init_benefit_catalog import initialize_database


class BenefitCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "government_oid.db"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_source_seed(self, publisher_oid: str | None = None) -> Path:
        seed_path = Path(self.temporary_directory.name) / "sources.json"
        payload = {
            "sources": [
                {
                    "source_id": "test_source",
                    "name": "測試政府來源",
                    "source_type": "benefit_index",
                    "jurisdiction_code": "TW",
                    "organization_name": "測試機關",
                    "publisher_oid": publisher_oid,
                    "base_url": "https://example.gov.tw/",
                    "entry_url": "https://example.gov.tw/benefits",
                    "canonical_host": "example.gov.tw",
                    "official_status": "verified_official",
                    "access_method": "manual_seed",
                    "connection_status": "pending",
                    "enabled": True,
                    "reviewed_at": "2026-07-26",
                    "review_note": "Unit test source",
                }
            ]
        }
        seed_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return seed_path

    def test_missing_publisher_oid_is_deferred_until_oid_import(self) -> None:
        """Source seeds can load before the separate government OID dataset."""
        seed_path = self.write_source_seed("2.16.886.101.missing")

        initialize_database(self.database_path, source_seed_path=seed_path)

        with closing(sqlite3.connect(self.database_path)) as connection:
            publisher_oid = connection.execute(
                "SELECT publisher_oid FROM source_registry WHERE source_id = ?",
                ("test_source",),
            ).fetchone()

        self.assertEqual(publisher_oid, (None,))

    def test_initialization_is_idempotent_and_reports_sources(self) -> None:
        seed_path = self.write_source_seed()

        first_inserted, _, first_summary = initialize_database(
            self.database_path,
            source_seed_path=seed_path,
        )
        second_inserted, _, second_summary = initialize_database(
            self.database_path,
            source_seed_path=seed_path,
        )

        self.assertEqual(first_inserted, 1)
        self.assertEqual(second_inserted, 0)
        self.assertEqual(first_summary.source_count, 1)
        self.assertEqual(second_summary.source_count, 1)
        self.assertEqual(second_summary.source_status_counts["pending"], 1)

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            tables = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }
            catalog_version = connection.execute(
                """
                SELECT value
                FROM schema_metadata
                WHERE key = 'benefit_catalog_schema_version'
                """
            ).fetchone()

        self.assertTrue(
            {
                "source_registry",
                "source_sync_runs",
                "source_documents",
                "document_discoveries",
                "benefit_programs",
                "program_sources",
                "program_organization_roles",
            }.issubset(tables)
        )
        self.assertEqual(catalog_version, ("1",))

    def test_completed_oid_import_marks_only_oid_source_active(self) -> None:
        seed_path = Path(self.temporary_directory.name) / "sources.json"
        source_payload = {
            "sources": [
                {
                    "source_id": "government_oid_dataset",
                    "name": "政府 OID",
                    "source_type": "reference_dataset",
                    "jurisdiction_code": "TW",
                    "organization_name": "數位發展部",
                    "publisher_oid": None,
                    "base_url": "https://data.gov.tw/",
                    "entry_url": "https://data.gov.tw/dataset/7081",
                    "canonical_host": "data.gov.tw",
                    "official_status": "verified_official",
                    "access_method": "download_file",
                    "connection_status": "pending",
                    "enabled": True,
                    "reviewed_at": "2026-07-26",
                    "review_note": "",
                },
                {
                    "source_id": "planned_source",
                    "name": "規劃中的來源",
                    "source_type": "benefit_index",
                    "jurisdiction_code": "TW",
                    "organization_name": "測試機關",
                    "publisher_oid": None,
                    "base_url": "https://planned.gov.tw/",
                    "entry_url": "https://planned.gov.tw/benefits",
                    "canonical_host": "planned.gov.tw",
                    "official_status": "verified_official",
                    "access_method": "manual_seed",
                    "connection_status": "pending",
                    "enabled": True,
                    "reviewed_at": "2026-07-26",
                    "review_note": "",
                },
            ]
        }
        seed_path.write_text(
            json.dumps(source_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        initialize_database(
            self.database_path,
            source_seed_path=seed_path,
        )

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                """
                INSERT INTO sync_runs (
                    run_id,
                    source_url,
                    source_checksum,
                    started_at,
                    completed_at,
                    status
                )
                VALUES (
                    'oid-sync-1',
                    'https://example.gov.tw/oid.csv',
                    'checksum',
                    '2026-07-26T00:00:00+00:00',
                    '2026-07-26T00:01:00+00:00',
                    'completed'
                )
                """
            )

        _, oid_activated, summary = initialize_database(
            self.database_path,
            source_seed_path=seed_path,
        )

        self.assertTrue(oid_activated)
        self.assertEqual(summary.source_status_counts["active"], 1)
        self.assertEqual(summary.source_status_counts["pending"], 1)

    def test_program_requires_reviewed_classification_when_verified(
        self,
    ) -> None:
        initialize_database(self.database_path, source_seed_path=None)

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO benefit_programs (
                        program_id,
                        canonical_name,
                        program_status,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'program-1',
                        '尚未分類的方案',
                        'verified',
                        '2026-07-26T00:00:00+00:00',
                        '2026-07-26T00:00:00+00:00'
                    )
                    """
                )

    def test_verified_evidence_and_oid_role_require_supporting_data(
        self,
    ) -> None:
        seed_path = self.write_source_seed()
        initialize_database(
            self.database_path,
            source_seed_path=seed_path,
        )

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            now = "2026-07-26T00:00:00+00:00"
            connection.execute(
                """
                INSERT INTO source_documents (
                    document_id,
                    canonical_url,
                    title,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    'document-1',
                    'https://example.gov.tw/benefits/funeral',
                    '喪葬補助',
                    ?,
                    ?,
                    ?,
                    ?
                )
                """,
                (now, now, now, now),
            )
            connection.execute(
                """
                INSERT INTO document_discoveries (
                    document_id,
                    source_id,
                    discovery_method,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (
                    'document-1',
                    'test_source',
                    'manual_seed',
                    ?,
                    ?
                )
                """,
                (now, now),
            )
            connection.execute(
                """
                INSERT INTO benefit_programs (
                    program_id,
                    canonical_name,
                    support_purpose,
                    program_basis,
                    delivery_form,
                    program_status,
                    last_verified_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    'program-1',
                    '喪葬補助',
                    'funeral_cost',
                    'social_assistance',
                    'cash_once',
                    'verified',
                    ?,
                    ?,
                    ?
                )
                """,
                (now, now, now),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO program_sources (
                        program_id,
                        document_id,
                        evidence_role,
                        review_status,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'program-1',
                        'document-1',
                        'application',
                        'verified',
                        ?,
                        ?
                    )
                    """,
                    (now, now),
                )

            connection.execute(
                """
                INSERT INTO program_sources (
                    program_id,
                    document_id,
                    evidence_role,
                    source_excerpt,
                    review_status,
                    reviewed_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    'program-1',
                    'document-1',
                    'application',
                    '符合規定者得提出申請。',
                    'verified',
                    ?,
                    ?,
                    ?
                )
                """,
                (now, now, now),
            )
            connection.execute(
                """
                INSERT INTO government_organizations (
                    oid,
                    org_name,
                    source_url,
                    source_record_hash,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (
                    '2.16.886.101.1',
                    '測試政府機關',
                    'https://example.gov.tw/oid.csv',
                    'hash',
                    ?,
                    ?
                )
                """,
                (now, now),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO program_organization_roles (
                        role_id,
                        program_id,
                        organization_role,
                        oid,
                        review_status,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'role-1',
                        'program-1',
                        'program_owner',
                        '2.16.886.101.1',
                        'verified',
                        ?,
                        ?
                    )
                    """,
                    (now, now),
                )

            connection.execute(
                """
                INSERT INTO program_organization_roles (
                    role_id,
                    program_id,
                    organization_role,
                    oid,
                    evidence_document_id,
                    review_status,
                    created_at,
                    updated_at
                )
                VALUES (
                    'role-1',
                    'program-1',
                    'program_owner',
                    '2.16.886.101.1',
                    'document-1',
                    'verified',
                    ?,
                    ?
                )
                """,
                (now, now),
            )
            connection.commit()
            summary = get_catalog_summary(connection)
            source_statuses = get_registered_source_statuses(connection)

        self.assertEqual(summary.document_count, 1)
        self.assertEqual(summary.verified_program_count, 1)
        self.assertEqual(summary.pending_evidence_count, 0)
        self.assertEqual(len(source_statuses), 1)
        self.assertEqual(source_statuses[0].document_count, 1)
        self.assertEqual(source_statuses[0].verified_program_count, 1)

    def test_seed_loader_rejects_unknown_access_method(self) -> None:
        seed_path = self.write_source_seed()
        payload = json.loads(seed_path.read_text(encoding="utf-8"))
        payload["sources"][0]["access_method"] = "guess"
        seed_path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Unsupported access_method"):
            load_source_seeds(seed_path)


if __name__ == "__main__":
    unittest.main()
