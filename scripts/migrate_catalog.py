"""Safely apply or dry-run ordered catalog migrations."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.adapters.sqlite.migrations import (  # noqa: E402
    Migration,
    MigrationError,
    MigrationResult,
    migrate_database,
)


class CatalogMigrationCliError(RuntimeError):
    """A CLI safety failure represented by a stable public code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CatalogMigrationExecution:
    """Safe result of a dry-run or explicitly applied migration."""

    mode: str
    migration_result: MigrationResult
    backup_path: Path | None
    working_database_path: Path


def _validate_source(source: Path) -> None:
    if not source.is_file():
        raise CatalogMigrationCliError("source_database_unavailable")


def _copy_database(source: Path, destination: Path) -> None:
    if destination.exists():
        raise CatalogMigrationCliError("backup_path_exists")
    if not destination.parent.is_dir():
        raise CatalogMigrationCliError("backup_directory_unavailable")
    try:
        with (
            closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as source_db,
            closing(sqlite3.connect(destination)) as destination_db,
        ):
            source_db.backup(destination_db)
    except (OSError, sqlite3.Error) as exc:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise CatalogMigrationCliError("database_backup_failed") from exc


def _restore_database(backup: Path, destination: Path) -> None:
    try:
        with (
            closing(sqlite3.connect(f"file:{backup}?mode=ro", uri=True)) as backup_db,
            closing(sqlite3.connect(destination)) as destination_db,
        ):
            backup_db.backup(destination_db)
    except (OSError, sqlite3.Error) as exc:
        raise CatalogMigrationCliError("database_restore_failed") from exc


def execute_catalog_migration(
    source: Path,
    *,
    apply: bool,
    backup_path: Path | None = None,
    migrations: tuple[Migration, ...] | None = None,
) -> CatalogMigrationExecution:
    """Dry-run on a temporary copy, or apply only after making a backup."""

    _validate_source(source)
    source = source.resolve()

    if not apply:
        if backup_path is not None:
            raise CatalogMigrationCliError("backup_not_allowed_for_dry_run")
        with tempfile.TemporaryDirectory(
            prefix="catalog-migration-dry-run-"
        ) as directory:
            temporary_copy = Path(directory) / source.name
            _copy_database(source, temporary_copy)
            result = migrate_database(temporary_copy, migrations=migrations)
            return CatalogMigrationExecution(
                mode="dry-run",
                migration_result=result,
                backup_path=None,
                working_database_path=temporary_copy,
            )

    if backup_path is None:
        raise CatalogMigrationCliError("backup_required_for_apply")
    backup_path = backup_path.resolve()
    if backup_path == source:
        raise CatalogMigrationCliError("backup_path_invalid")

    _copy_database(source, backup_path)
    try:
        result = migrate_database(source, migrations=migrations)
    except BaseException:
        _restore_database(backup_path, source)
        raise
    return CatalogMigrationExecution(
        mode="apply",
        migration_result=result,
        backup_path=backup_path,
        working_database_path=source,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run catalog migrations on a temporary copy by default. "
            "Applying requires --apply and --backup."
        )
    )
    parser.add_argument("--database", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Migrate a temporary copy only (default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply to the source database after creating a backup.",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        help="Required non-existing backup path when --apply is used.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        execution = execute_catalog_migration(
            args.database,
            apply=args.apply,
            backup_path=args.backup,
        )
    except (CatalogMigrationCliError, MigrationError) as exc:
        parser.exit(1, f"Catalog migration failed: {exc}\n")

    result = execution.migration_result
    print(f"Mode: {execution.mode}")
    print(f"Previous schema version: {result.previous_version}")
    print(f"Current schema version: {result.current_version}")
    print(f"Applied migrations: {len(result.applied_migration_ids)}")
    if execution.backup_path is not None:
        print(f"Backup: {execution.backup_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
