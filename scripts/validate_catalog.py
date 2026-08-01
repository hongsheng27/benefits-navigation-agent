#!/usr/bin/env python3
"""Catalog validation CLI (Req 15.5-15.12).

Usage:
    python scripts/validate_catalog.py --db data/local/catalog.db
    python scripts/validate_catalog.py --json data/snapshots/catalog.json

Exit codes:
    0 — validation passed, output shows count
    1 — validation failed, output shows safe IDs/version/code

Does NOT start a server, watcher, or live crawler.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.validation.catalog import ValidationFinding, validate_catalog  # noqa: E402


def _read_sqlite_tables(db_path: str) -> dict[str, list[dict[str, Any]]]:
    """Read all user tables from SQLite."""
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


def _read_json(json_path: str) -> dict[str, list[dict[str, Any]]]:
    """Read catalog from exported JSON."""
    content = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return content.get("tables", {})


def _format_finding(f: ValidationFinding) -> str:
    parts = [f"[{f.severity.upper()}]", f.code]
    if f.item_id:
        parts.append(f"item={f.item_id}")
    if f.message:
        parts.append(f"— {f.message}")
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate catalog integrity")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--db", help="Path to SQLite database")
    group.add_argument("--json", help="Path to exported JSON catalog")
    args = parser.parse_args()

    if args.db:
        if not Path(args.db).exists():
            print(f"ERROR: database not found: {args.db}", file=sys.stderr)
            return 1
        data = _read_sqlite_tables(args.db)
    else:
        if not Path(args.json).exists():
            print(f"ERROR: JSON file not found: {args.json}", file=sys.stderr)
            return 1
        data = _read_json(args.json)

    result = validate_catalog(data)

    if result.is_valid:
        print(
            f"OK: validated {result.rows_checked} rows "
            f"across {result.tables_checked} tables"
        )
        if result.warning_count > 0:
            print(f"  ({result.warning_count} warnings)")
            for f in result.findings:
                if f.severity == "warning":
                    print(f"  {_format_finding(f)}")
        return 0
    else:
        print(
            f"FAILED: {result.error_count} errors, "
            f"{result.warning_count} warnings",
            file=sys.stderr,
        )
        for f in result.findings:
            print(f"  {_format_finding(f)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
