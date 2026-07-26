from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from scripts.import_government_oid import (
    DEFAULT_SOURCE_URL,
    OFFICIAL_QUALITY_SNAPSHOT_URL,
    download_csv,
    import_into_sqlite,
    parse_official_csv,
)


def csv_bytes(*rows: str) -> bytes:
    header = "OrgName,OID,TEL,Address,DN,OrgCode"
    return ("\n".join((header, *rows)) + "\n").encode("utf-8")


def checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class FakeHttpResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.headers = {"Last-Modified": "Sat, 25 Jul 2026 00:00:00 GMT"}

    def __enter__(self) -> FakeHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class GovernmentOidImportTests(unittest.TestCase):
    @patch("scripts.import_government_oid.urlopen")
    def test_downloader_uses_official_quality_snapshot_fallback(
        self,
        mocked_urlopen: object,
    ) -> None:
        payload = csv_bytes(
            "有效機關,2.16.886.101.1,02-1111,臺北市,ou=valid,A00000001"
        )
        mocked_urlopen.side_effect = [
            OSError("primary source unavailable"),
            FakeHttpResponse(payload),
        ]

        downloaded, modified_at, retrieval_url = download_csv(
            DEFAULT_SOURCE_URL,
            timeout_seconds=1,
        )

        self.assertEqual(downloaded, payload)
        self.assertEqual(modified_at, "Sat, 25 Jul 2026 00:00:00 GMT")
        self.assertEqual(retrieval_url, OFFICIAL_QUALITY_SNAPSHOT_URL)
        self.assertEqual(mocked_urlopen.call_count, 2)

    def test_refresh_preserves_tags_and_deactivates_missing_oids(self) -> None:
        first_payload = csv_bytes(
            "第一機關,2.16.886.101.1,02-1111,臺北市,ou=first,A00000001",
            "第二機關,2.16.886.101.2,02-2222,臺中市,ou=second,A00000002",
        )
        second_payload = csv_bytes(
            "第一機關（新名稱）,2.16.886.101.1,02-1111,臺北市,ou=first,A00000001",
            "第三機關,2.16.886.101.3,02-3333,高雄市,ou=third,A00000003",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "government_oid.db"
            first_result = parse_official_csv(first_payload)
            first_summary = import_into_sqlite(
                first_result,
                database_path,
                source_url="https://example.gov/oid.csv",
                source_checksum=checksum(first_payload),
            )
            self.assertEqual(first_summary.inserted_count, 2)
            self.assertEqual(first_summary.active_count, 2)

            with closing(sqlite3.connect(database_path)) as connection, connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    """
                    INSERT INTO tags (
                        tag_id,
                        name,
                        category,
                        description,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'social_welfare',
                        '社會福利',
                        'service',
                        '',
                        '2026-07-25T00:00:00+00:00',
                        '2026-07-25T00:00:00+00:00'
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO organization_tags (
                        oid,
                        tag_id,
                        source,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        '2.16.886.101.1',
                        'social_welfare',
                        'manual',
                        '2026-07-25T00:00:00+00:00',
                        '2026-07-25T00:00:00+00:00'
                    )
                    """
                )

            second_result = parse_official_csv(second_payload)
            second_summary = import_into_sqlite(
                second_result,
                database_path,
                source_url="https://example.gov/oid.csv",
                source_checksum=checksum(second_payload),
            )

            self.assertEqual(second_summary.inserted_count, 1)
            self.assertEqual(second_summary.updated_count, 1)
            self.assertEqual(second_summary.deactivated_count, 1)
            self.assertEqual(second_summary.active_count, 2)
            self.assertEqual(second_summary.database_total_count, 3)

            with closing(sqlite3.connect(database_path)) as connection, connection:
                first_organization = connection.execute(
                    """
                    SELECT org_name, active
                    FROM government_organizations
                    WHERE oid = '2.16.886.101.1'
                    """
                ).fetchone()
                second_organization = connection.execute(
                    """
                    SELECT active
                    FROM government_organizations
                    WHERE oid = '2.16.886.101.2'
                    """
                ).fetchone()
                preserved_tag_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM organization_tags
                    WHERE oid = '2.16.886.101.1'
                      AND tag_id = 'social_welfare'
                    """
                ).fetchone()[0]
                completed_sync_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM sync_runs
                    WHERE status = 'completed'
                    """
                ).fetchone()[0]

            self.assertEqual(first_organization, ("第一機關（新名稱）", 1))
            self.assertEqual(second_organization, (0,))
            self.assertEqual(preserved_tag_count, 1)
            self.assertEqual(completed_sync_count, 2)

    def test_parser_reports_invalid_and_identical_duplicate_rows(self) -> None:
        payload = csv_bytes(
            "有效機關,2.16.886.101.1,02-1111,臺北市,ou=valid,A00000001",
            "有效機關,2.16.886.101.1,02-1111,臺北市,ou=valid,A00000001",
            "缺少OID,,02-2222,臺中市,ou=invalid,A00000002",
        )

        result = parse_official_csv(payload)

        self.assertEqual(result.source_record_count, 3)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.invalid_count, 1)
        self.assertEqual(result.duplicate_count, 1)

    def test_parser_rejects_conflicting_duplicate_oids(self) -> None:
        payload = csv_bytes(
            "第一個名稱,2.16.886.101.1,02-1111,臺北市,ou=first,A00000001",
            "不同名稱,2.16.886.101.1,02-1111,臺北市,ou=first,A00000001",
        )

        with self.assertRaisesRegex(ValueError, "Conflicting rows"):
            parse_official_csv(payload)


if __name__ == "__main__":
    unittest.main()
