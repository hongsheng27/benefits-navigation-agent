from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from backend.app.services.source_connector import (
    sync_registered_source,
    sync_reviewed_source_page,
)
from scripts.init_benefit_catalog import initialize_database


class FakeHtmlResponse:
    def __init__(self, body: bytes, url: str) -> None:
        self.body = body
        self.url = url
        self.status = 200
        self.headers = {"Content-Type": "text/html; charset=utf-8"}

    def __enter__(self) -> FakeHtmlResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]

    def geturl(self) -> str:
        return self.url


class SourceConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temporary_directory.name)
        self.database_path = temporary_path / "government_oid.db"
        self.raw_directory = temporary_path / "raw"
        initialize_database(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @patch("backend.app.services.source_connector.urlopen")
    def test_sync_stores_one_document_and_is_idempotent(
        self,
        mocked_urlopen: object,
    ) -> None:
        first_body = (
            b"<html><head><title>Official Benefit Page</title></head>"
            b"<body><input type='hidden' value='dynamic-1'>content"
            b"<p>Browse count: placeholder</p>"
            b"<p>\xe7\x80\x8f\xe8\xa6\xbd\xe4\xba\xba\xe6\xac\xa1\xef\xbc\x9a"
            b"100 \xe4\xba\xba</p></body></html>"
        )
        second_body = (
            b"<html><head><title>Official Benefit Page</title></head>"
            b"<body><input type='hidden' value='dynamic-2'>content"
            b"<p>Browse count: placeholder</p>"
            b"<p>\xe7\x80\x8f\xe8\xa6\xbd\xe4\xba\xba\xe6\xac\xa1\xef\xbc\x9a"
            b"101 \xe4\xba\xba</p></body></html>"
        )
        final_url = "https://www.gov.tw/News_Content_26_666371"
        mocked_urlopen.side_effect = [
            FakeHtmlResponse(first_body, final_url),
            FakeHtmlResponse(second_body, final_url),
        ]

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            first_summary = sync_registered_source(
                connection,
                "my_egov",
                self.raw_directory,
            )
            second_summary = sync_registered_source(
                connection,
                "my_egov",
                self.raw_directory,
            )
            source_status = connection.execute(
                """
                SELECT connection_status
                FROM source_registry
                WHERE source_id = 'my_egov'
                """
            ).fetchone()
            document_count = connection.execute(
                "SELECT COUNT(*) FROM source_documents"
            ).fetchone()[0]
            run_counts = connection.execute(
                """
                SELECT
                    SUM(changed_document_count),
                    SUM(unchanged_document_count)
                FROM source_sync_runs
                WHERE source_id = 'my_egov'
                  AND status = 'completed'
                """
            ).fetchone()

        self.assertTrue(first_summary.changed)
        self.assertFalse(second_summary.changed)
        self.assertEqual(source_status, ("active",))
        self.assertEqual(document_count, 1)
        self.assertEqual(run_counts, (1, 1))
        self.assertTrue(Path(first_summary.storage_ref).is_file())

    @patch("backend.app.services.source_connector.urlopen")
    def test_failed_fetch_records_failure_without_document(
        self,
        mocked_urlopen: object,
    ) -> None:
        mocked_urlopen.side_effect = OSError("network unavailable")

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            with self.assertRaisesRegex(OSError, "network unavailable"):
                sync_registered_source(
                    connection,
                    "taipei_funeral_services",
                    self.raw_directory,
                )
            source_status = connection.execute(
                """
                SELECT connection_status
                FROM source_registry
                WHERE source_id = 'taipei_funeral_services'
                """
            ).fetchone()
            failed_runs = connection.execute(
                """
                SELECT COUNT(*)
                FROM source_sync_runs
                WHERE source_id = 'taipei_funeral_services'
                  AND status = 'failed'
                """
            ).fetchone()[0]
            document_count = connection.execute(
                "SELECT COUNT(*) FROM source_documents"
            ).fetchone()[0]

        self.assertEqual(source_status, ("failed",))
        self.assertEqual(failed_runs, 1)
        self.assertEqual(document_count, 0)

    @patch("backend.app.services.source_connector.urlopen")
    def test_reviewed_child_page_preserves_source_health(
        self,
        mocked_urlopen: object,
    ) -> None:
        child_url = "https://cab.tycg.gov.tw/News_Content.aspx?n=1&s=2"
        mocked_urlopen.return_value = FakeHtmlResponse(
            b"<html><head><title>Benefit Child</title></head>"
            b"<body>approved content</body></html>",
            child_url,
        )

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            summary = sync_reviewed_source_page(
                connection,
                "my_egov",
                child_url,
                self.raw_directory,
            )
            source_status = connection.execute(
                """
                SELECT connection_status
                FROM source_registry
                WHERE source_id = 'my_egov'
                """
            ).fetchone()
            discovery = connection.execute(
                """
                SELECT discovery_method
                FROM document_discoveries
                WHERE document_id = ?
                  AND source_id = 'my_egov'
                """,
                (summary.document_id,),
            ).fetchone()
            publisher = connection.execute(
                """
                SELECT publisher_name, jurisdiction_code
                FROM source_documents
                WHERE document_id = ?
                """,
                (summary.document_id,),
            ).fetchone()

        self.assertEqual(source_status, ("pending",))
        self.assertEqual(discovery, ("reviewed_candidate",))
        self.assertEqual(publisher, ("", ""))

    @patch("backend.app.services.source_connector.urlopen")
    def test_reviewed_child_page_rejects_non_government_url(
        self,
        mocked_urlopen: object,
    ) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            with self.assertRaisesRegex(
                ValueError,
                "HTTPS Taiwan government URL",
            ):
                sync_reviewed_source_page(
                    connection,
                    "my_egov",
                    "https://example.com/benefit",
                    self.raw_directory,
                )

        mocked_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
