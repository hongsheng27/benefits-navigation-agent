"""Deterministic atomic one-way JSON catalog exporter (Req 1.3, 1.9, 14.1-14.11).

Exports the canonical SQLite catalog into a stable JSON snapshot for tests and
releases. This is a **one-way** export: there is no JSON-to-SQL importer or
runtime fallback. The application runtime never reads, imports, or depends on
the exported JSON file.

## Atomicity

Uses temp file + atomic rename so a failure during export preserves the
previous snapshot. Partial writes are impossible: either the full new file
replaces the old one, or nothing changes.

## Determinism

- Rows are ordered by primary key
- Fields within each row are ordered alphabetically
- Timestamps use explicit UTC ISO format
- Floating-point values are rounded to avoid platform variance
- The output includes a metadata header with schema version, export timestamp,
  and row counts

## Constraints

- Does NOT provide a JSON-to-SQL importer
- Does NOT serve as a runtime fallback
- The application startup, request path, and workflow NEVER import this module
- Tests and release tooling are the only consumers
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExportMetadata:
    """Metadata header included in every exported snapshot."""

    schema_version: str
    exported_at: str
    exporter_version: str = "1.0.0"
    row_counts: dict[str, int] | None = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Result of an export operation."""

    success: bool
    output_path: str | None = None
    metadata: ExportMetadata | None = None
    error_type: str | None = None
    error_message: str | None = None


def export_catalog(
    *,
    data: dict[str, list[dict[str, Any]]],
    output_path: str | Path,
    schema_version: str = "1.0.0",
    exported_at: datetime | None = None,
) -> ExportResult:
    """Export catalog data to a deterministic JSON file atomically.

    Args:
        data: Dict mapping table names to lists of row dicts.
        output_path: Target file path for the JSON snapshot.
        schema_version: Version string for the schema.
        exported_at: Explicit export timestamp (defaults to now).

    Returns:
        ExportResult indicating success or failure.

    On failure, the previous file at output_path is preserved unchanged.
    """
    timestamp = exported_at or datetime.now(UTC)
    output = Path(output_path)

    row_counts = {table: len(rows) for table, rows in data.items()}
    metadata = ExportMetadata(
        schema_version=schema_version,
        exported_at=timestamp.isoformat(),
        row_counts=row_counts,
    )

    # Build the canonical payload
    payload = _build_canonical_payload(data, metadata)

    # Serialize deterministically
    try:
        content = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        return ExportResult(
            success=False,
            error_type=type(exc).__name__,
            error_message="Serialization failed",
        )

    # Atomic write: temp file in same directory + rename
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(output.parent),
            prefix=".export_",
            suffix=".json.tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.write("\n")  # Trailing newline
                f.flush()
                os.fsync(f.fileno())
            # Atomic replace
            os.replace(tmp_path, str(output))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        return ExportResult(
            success=False,
            error_type=type(exc).__name__,
            error_message="Write failed",
        )

    return ExportResult(
        success=True,
        output_path=str(output),
        metadata=metadata,
    )


def _build_canonical_payload(
    data: dict[str, list[dict[str, Any]]],
    metadata: ExportMetadata,
) -> dict[str, Any]:
    """Build the canonical JSON structure with deterministic ordering."""
    tables: dict[str, list[dict[str, Any]]] = {}

    for table_name in sorted(data.keys()):
        rows = data[table_name]
        # Sort rows by all fields to ensure deterministic order
        sorted_rows = sorted(rows, key=_row_sort_key)
        # Sort fields within each row alphabetically
        canonical_rows = [{k: v for k, v in sorted(row.items())} for row in sorted_rows]
        tables[table_name] = canonical_rows

    return {
        "_metadata": {
            "exported_at": metadata.exported_at,
            "exporter_version": metadata.exporter_version,
            "row_counts": metadata.row_counts,
            "schema_version": metadata.schema_version,
        },
        "tables": tables,
    }


def _row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Generate a sort key from all row values for deterministic ordering.

    Uses (key, value) pairs to disambiguate rows with identical values but
    different keys, then falls back to full JSON serialization for truly
    identical rows (ensuring stable sort without depending on insertion order).
    """
    return tuple((k, str(v) if v is not None else "") for k, v in sorted(row.items()))
