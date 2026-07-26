"""Fetch only child pages explicitly approved in a reviewed batch manifest."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.link_discovery import (  # noqa: E402
    is_taiwan_government_host,
)
from backend.app.services.source_connector import (  # noqa: E402
    sync_reviewed_source_page,
)
from scripts.import_government_oid import DEFAULT_DATABASE_PATH  # noqa: E402
from scripts.init_benefit_catalog import initialize_database  # noqa: E402
from scripts.sync_benefit_sources import DEFAULT_RAW_DIRECTORY  # noqa: E402

DEFAULT_MANIFEST_PATH = (
    REPO_ROOT
    / "data"
    / "benefit_discovery"
    / "death_benefit_first_batch.v0.1.json"
)
ALLOWED_FETCH_ACTIONS = ("fetch", "reuse_existing")


@dataclass(frozen=True)
class ReviewedPageItem:
    candidate_id: str
    label: str
    source_id: str
    candidate_url: str
    fetch_url: str
    fetch_action: str
    review_note: str


@dataclass(frozen=True)
class BatchItemResult:
    candidate_id: str
    label: str
    action: str
    status: str
    canonical_url: str
    title: str
    changed: bool | None
    error: str | None


def _require_nonempty_string(
    item: dict[str, object],
    key: str,
    candidate_id: str,
) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{candidate_id}: {key} must be a non-empty string."
        )
    return value.strip()


def _validate_government_url(url: str, candidate_id: str) -> None:
    parts = urlsplit(url)
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or not is_taiwan_government_host(parts.hostname)
    ):
        raise ValueError(
            f"{candidate_id}: fetch_url must be an HTTPS Taiwan government "
            f"URL, received {url}"
        )


def load_reviewed_items(manifest_path: Path) -> tuple[ReviewedPageItem, ...]:
    with manifest_path.open(encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict):
        raise ValueError(f"Batch manifest must be an object: {manifest_path}")
    if manifest.get("schema_version") != "1.0":
        raise ValueError(
            f"Unsupported batch schema_version in {manifest_path}."
        )
    raw_items = manifest.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError(f"Batch manifest has no items: {manifest_path}")

    reviewed_items: list[ReviewedPageItem] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError(f"Batch item {index} must be an object.")
        raw_id = raw_item.get("candidate_id")
        candidate_id = (
            raw_id.strip()
            if isinstance(raw_id, str) and raw_id.strip()
            else f"item_{index}"
        )
        if candidate_id in seen_ids:
            raise ValueError(f"Duplicate candidate_id: {candidate_id}")
        seen_ids.add(candidate_id)

        if raw_item.get("review_decision") != "approved_for_fetch":
            continue
        fetch_action = _require_nonempty_string(
            raw_item,
            "fetch_action",
            candidate_id,
        )
        if fetch_action not in ALLOWED_FETCH_ACTIONS:
            raise ValueError(
                f"{candidate_id}: unsupported fetch_action {fetch_action}."
            )
        fetch_url = _require_nonempty_string(
            raw_item,
            "fetch_url",
            candidate_id,
        )
        _validate_government_url(fetch_url, candidate_id)
        reviewed_items.append(
            ReviewedPageItem(
                candidate_id=candidate_id,
                label=_require_nonempty_string(
                    raw_item,
                    "label",
                    candidate_id,
                ),
                source_id=_require_nonempty_string(
                    raw_item,
                    "source_id",
                    candidate_id,
                ),
                candidate_url=_require_nonempty_string(
                    raw_item,
                    "candidate_url",
                    candidate_id,
                ),
                fetch_url=fetch_url,
                fetch_action=fetch_action,
                review_note=_require_nonempty_string(
                    raw_item,
                    "review_note",
                    candidate_id,
                ),
            )
        )

    if not reviewed_items:
        raise ValueError(
            f"Batch manifest has no approved_for_fetch items: {manifest_path}"
        )
    return tuple(reviewed_items)


def _reuse_existing_document(
    connection: sqlite3.Connection,
    item: ReviewedPageItem,
) -> BatchItemResult:
    row = connection.execute(
        """
        SELECT d.canonical_url, d.title
        FROM source_documents AS d
        JOIN document_discoveries AS x
          ON x.document_id = d.document_id
        WHERE d.canonical_url = ?
          AND x.source_id = ?
        """,
        (item.fetch_url, item.source_id),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"{item.candidate_id}: approved existing page is not in the "
            "database; run scripts/sync_benefit_sources.py first."
        )
    return BatchItemResult(
        candidate_id=item.candidate_id,
        label=item.label,
        action=item.fetch_action,
        status="reused",
        canonical_url=str(row[0]),
        title=str(row[1]),
        changed=None,
        error=None,
    )


def fetch_reviewed_batch(
    database_path: Path,
    manifest_path: Path,
    raw_directory: Path,
    *,
    timeout_seconds: int = 30,
) -> list[BatchItemResult]:
    initialize_database(database_path)
    items = load_reviewed_items(manifest_path)
    results: list[BatchItemResult] = []

    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for item in items:
            try:
                if item.fetch_action == "reuse_existing":
                    result = _reuse_existing_document(connection, item)
                else:
                    summary = sync_reviewed_source_page(
                        connection,
                        item.source_id,
                        item.fetch_url,
                        raw_directory,
                        timeout_seconds=timeout_seconds,
                    )
                    result = BatchItemResult(
                        candidate_id=item.candidate_id,
                        label=item.label,
                        action=item.fetch_action,
                        status="fetched",
                        canonical_url=summary.canonical_url,
                        title=summary.title,
                        changed=summary.changed,
                        error=None,
                    )
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
                result = BatchItemResult(
                    candidate_id=item.candidate_id,
                    label=item.label,
                    action=item.fetch_action,
                    status="failed",
                    canonical_url=item.fetch_url,
                    title="",
                    changed=None,
                    error=str(exc),
                )
            results.append(result)

    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch only approved government pages from a reviewed manifest. "
            "This command does not crawl links or call AI."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite database path (default: {DEFAULT_DATABASE_PATH})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help=f"Reviewed batch manifest (default: {DEFAULT_MANIFEST_PATH})",
    )
    parser.add_argument(
        "--raw-directory",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY,
        help=f"Raw HTML directory (default: {DEFAULT_RAW_DIRECTORY})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-page network timeout in seconds (default: 30).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        results = fetch_reviewed_batch(
            args.database,
            args.manifest,
            args.raw_directory,
            timeout_seconds=args.timeout,
        )
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, f"Reviewed-page fetch failed: {exc}\n")

    for result in results:
        changed_label = (
            ""
            if result.changed is None
            else f", {'changed' if result.changed else 'unchanged'}"
        )
        print(
            f"{result.candidate_id}: {result.status}{changed_label}, "
            f"label={result.label!r}"
        )
        print(f"  URL: {result.canonical_url}")
        if result.title:
            print(f"  Title: {result.title}")
        if result.error:
            print(f"  Error: {result.error}")

    failed_count = sum(result.status == "failed" for result in results)
    print(
        f"Summary: total={len(results)}, "
        f"successful={len(results) - failed_count}, failed={failed_count}"
    )
    return int(failed_count > 0)


if __name__ == "__main__":
    sys.exit(main())
