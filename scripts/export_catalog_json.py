#!/usr/bin/env python3
"""CLI wrapper for the deterministic JSON catalog exporter.

Usage:
    python scripts/export_catalog_json.py --db data/local/catalog.db --output data/snapshots/catalog.json

This script is for tests and releases only. It is NOT part of the application
runtime and must never be imported by app code.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.testing.catalog_exporter import export_catalog  # noqa: E402


def _read_tables(db_path: str) -> dict[str, list[dict[str, Any]]]:
    """Read all user tables from a SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'schema_%' "
            "ORDER BY name"
        )
        tables: dict[str, list[dict[str, Any]]] = {}
        for (table_name,) in cursor.fetchall():
            rows = conn.execute(f"SELECT * FROM [{table_name}]").fetchall()  # noqa: S608
            tables[table_name] = [dict(row) for row in rows]
        return tables
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export SQLite catalog to deterministic JSON snapshot"
    )
    parser.add_argument(
        "--db", required=True, help="Path to SQLite database file"
    )
    parser.add_argument(
        "--output", required=True, help="Output JSON file path"
    )
    parser.add_argument(
        "--schema-version",
        default="1.0.0",
        help="Schema version string (default: 1.0.0)",
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"ERROR: Database not found: {args.db}", file=sys.stderr)
        return 1

    data = _read_tables(args.db)
    result = export_catalog(
        data=data,
        output_path=args.output,
        schema_version=args.schema_version,
        exported_at=datetime.now(UTC),
    )

    if result.success:
        total = sum((result.metadata.row_counts or {}).values())
        print(f"OK: exported {total} rows to {result.output_path}")
        return 0
    else:
        print(
            f"ERROR: {result.error_type}: {result.error_message}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
