"""Initialize the local SQLite benefit source and program catalog."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.benefit_catalog import (  # noqa: E402, I001
    CATALOG_SCHEMA_VERSION,
    CatalogSummary,
    get_catalog_summary,
    get_registered_source_statuses,
    initialize_catalog_schema,
    load_source_seeds,
    mark_oid_source_active_when_imported,
    seed_source_registry,
)
from scripts.import_government_oid import (  # noqa: E402
    DEFAULT_DATABASE_PATH,
    initialize_schema as initialize_oid_schema,
)

DEFAULT_SOURCE_SEED_PATH = (
    REPO_ROOT / "data" / "source_registry" / "initial_sources.v0.1.json"
)


def initialize_database(
    database_path: Path,
    *,
    source_seed_path: Path | None = DEFAULT_SOURCE_SEED_PATH,
) -> tuple[int, bool, CatalogSummary]:
    """Create catalog tables, add missing seeds, and report current counts."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        initialize_oid_schema(connection)
        initialize_catalog_schema(connection)
        inserted_source_count = 0
        if source_seed_path is not None:
            source_seeds = load_source_seeds(source_seed_path)
            inserted_source_count = seed_source_registry(
                connection,
                source_seeds,
            )
        oid_source_activated = mark_oid_source_active_when_imported(connection)
        summary = get_catalog_summary(connection)
    finally:
        connection.close()
    return inserted_source_count, oid_source_activated, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize the local SQLite benefit catalog."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite database path (default: {DEFAULT_DATABASE_PATH})",
    )
    parser.add_argument(
        "--source-seed",
        type=Path,
        default=DEFAULT_SOURCE_SEED_PATH,
        help=(
            "Reviewable source seed JSON "
            f"(default: {DEFAULT_SOURCE_SEED_PATH})"
        ),
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Create the schema without inserting initial source records.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    source_seed_path = None if args.no_seed else args.source_seed

    try:
        inserted_count, oid_activated, summary = initialize_database(
            args.database,
            source_seed_path=source_seed_path,
        )
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, f"Catalog initialization failed: {exc}\n")

    print(f"Database: {args.database}")
    print(f"Benefit catalog schema version: {CATALOG_SCHEMA_VERSION}")
    print(f"New source records inserted: {inserted_count}")
    print(f"OID source newly marked active: {oid_activated}")
    print(f"Registered sources: {summary.source_count}")
    for status, count in summary.source_status_counts.items():
        print(f"  {status}: {count}")
    print(f"Benefit source sync runs: {summary.source_sync_run_count}")
    print(f"Source documents: {summary.document_count}")
    print(f"Candidate programs: {summary.candidate_program_count}")
    print(f"Verified programs: {summary.verified_program_count}")
    print(f"Pending evidence links: {summary.pending_evidence_count}")
    connection = sqlite3.connect(args.database)
    try:
        source_statuses = get_registered_source_statuses(connection)
    finally:
        connection.close()
    print("Source coverage:")
    for source in source_statuses:
        print(
            "  "
            f"{source.name} [{source.connection_status}] "
            f"method={source.access_method} "
            f"documents={source.document_count} "
            f"candidates={source.candidate_program_count} "
            f"verified={source.verified_program_count}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
