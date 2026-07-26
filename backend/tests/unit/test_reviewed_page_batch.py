from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.fetch_reviewed_benefit_pages import load_reviewed_items


class ReviewedPageBatchTests(unittest.TestCase):
    def _write_manifest(
        self,
        directory: str,
        *,
        fetch_url: str,
        review_decision: str = "approved_for_fetch",
    ) -> Path:
        manifest_path = Path(directory) / "batch.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "items": [
                        {
                            "candidate_id": "candidate_1",
                            "label": "Candidate",
                            "source_id": "my_egov",
                            "candidate_url": fetch_url,
                            "fetch_url": fetch_url,
                            "review_decision": review_decision,
                            "fetch_action": "fetch",
                            "review_note": "Reviewed for a test.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return manifest_path

    def test_loads_only_approved_government_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = self._write_manifest(
                directory,
                fetch_url="https://service.gov.tw/benefit",
            )
            items = load_reviewed_items(manifest_path)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].candidate_id, "candidate_1")

    def test_rejects_approved_non_government_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = self._write_manifest(
                directory,
                fetch_url="https://example.com/benefit",
            )
            with self.assertRaisesRegex(
                ValueError,
                "HTTPS Taiwan government URL",
            ):
                load_reviewed_items(manifest_path)

    def test_rejects_manifest_without_approved_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = self._write_manifest(
                directory,
                fetch_url="https://service.gov.tw/benefit",
                review_decision="rejected",
            )
            with self.assertRaisesRegex(
                ValueError,
                "no approved_for_fetch items",
            ):
                load_reviewed_items(manifest_path)


if __name__ == "__main__":
    unittest.main()
