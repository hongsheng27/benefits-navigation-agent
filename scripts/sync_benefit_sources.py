"""Fetch the reviewed entry pages for the first-round benefit sources."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.source_connector import sync_registered_source
from scripts.import_government_oid import DEFAULT_DATABASE_PATH
from scripts.init_benefit_catalog import initialize_database

DEFAULT_SOURCE_IDS = ("my_egov", "taipei_funeral_services")
DEFAULT_RAW_DIRECTORY = REPO_ROOT / "data" / "local" / "source_documents"


def sync_sources(
    database_path: Path,
    source_ids: tuple[str, ...],
    raw_directory: Path,
    *,
    timeout_seconds: int = 30,
) -> list[object]:
    initialize_database(database_path)
    summaries: list[object] = []
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for source_id in source_ids:
            summaries.append(
                sync_registered_source(
                    connection,
                    source_id,
                    raw_directory,
                    timeout_seconds=timeout_seconds,
                )
            )
    return summaries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch only the reviewed entry page for each selected source. "
            "This command does not crawl child links or call an AI model."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite database path (default: {DEFAULT_DATABASE_PATH})",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=DEFAULT_SOURCE_IDS,
        help=(
            "Source to fetch; repeat for multiple sources. "
            "Defaults to both first-round sources."
        ),
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
    source_ids = tuple(args.source or DEFAULT_SOURCE_IDS)

    try:
        summaries = sync_sources(
            args.database,
            source_ids,
            args.raw_directory,
            timeout_seconds=args.timeout,
        )
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, f"Source sync failed: {exc}\n")

    print(f"Database: {args.database}")
    for summary in summaries:
        change_label = "changed" if summary.changed else "unchanged"
        print(
            f"{summary.source_id}: active, {change_label}, "
            f"title={summary.title!r}"
        )
        print(f"  URL: {summary.canonical_url}")
        print(f"  Raw HTML: {summary.storage_ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
