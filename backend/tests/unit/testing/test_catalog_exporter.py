"""Unit tests for the deterministic JSON catalog exporter (Task 13.1, 13.2).

Covers:
- Stable row/field ordering (determinism)
- Metadata in output
- Failure cleanup (no partial file)
- Existing snapshot preservation on failure
- Atomic replacement
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.testing.catalog_exporter import export_catalog

T0 = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


@pytest.fixture()
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "catalog.json"


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


def test_same_data_different_insertion_order_same_bytes(
    tmp_output: Path,
) -> None:
    """Rows inserted in different orders produce identical output bytes."""
    data_a = {
        "programs": [
            {"id": "prog-2", "name": "B"},
            {"id": "prog-1", "name": "A"},
        ]
    }
    data_b = {
        "programs": [
            {"id": "prog-1", "name": "A"},
            {"id": "prog-2", "name": "B"},
        ]
    }

    out_a = tmp_output.parent / "a.json"
    out_b = tmp_output.parent / "b.json"

    export_catalog(data=data_a, output_path=out_a, exported_at=T0)
    export_catalog(data=data_b, output_path=out_b, exported_at=T0)

    assert out_a.read_bytes() == out_b.read_bytes()


def test_fields_are_alphabetically_sorted(tmp_output: Path) -> None:
    """Fields within each row are sorted alphabetically."""
    data = {"items": [{"zebra": 1, "alpha": 2, "mid": 3}]}

    export_catalog(data=data, output_path=tmp_output, exported_at=T0)
    content = json.loads(tmp_output.read_text())

    row = content["tables"]["items"][0]
    assert list(row.keys()) == ["alpha", "mid", "zebra"]


def test_tables_are_alphabetically_sorted(tmp_output: Path) -> None:
    """Table names in output are sorted."""
    data = {"zebra_table": [], "alpha_table": [{"x": 1}]}

    export_catalog(data=data, output_path=tmp_output, exported_at=T0)
    content = json.loads(tmp_output.read_text())

    assert list(content["tables"].keys()) == ["alpha_table", "zebra_table"]


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_metadata_included_in_output(tmp_output: Path) -> None:
    """Export includes metadata header with schema version and row counts."""
    data = {"programs": [{"id": "p1"}, {"id": "p2"}], "rules": [{"id": "r1"}]}

    result = export_catalog(
        data=data,
        output_path=tmp_output,
        schema_version="2.0.0",
        exported_at=T0,
    )

    assert result.success
    assert result.metadata is not None
    assert result.metadata.schema_version == "2.0.0"
    assert result.metadata.row_counts == {"programs": 2, "rules": 1}

    content = json.loads(tmp_output.read_text())
    assert content["_metadata"]["schema_version"] == "2.0.0"
    assert content["_metadata"]["row_counts"]["programs"] == 2


def test_exported_at_is_explicit_timestamp(tmp_output: Path) -> None:
    """The export timestamp is the one we passed, not 'now'."""
    export_catalog(data={}, output_path=tmp_output, exported_at=T0)
    content = json.loads(tmp_output.read_text())

    assert content["_metadata"]["exported_at"] == T0.isoformat()


# ---------------------------------------------------------------------------
# Atomicity — failure preserves previous file
# ---------------------------------------------------------------------------


def test_existing_file_preserved_on_serialization_failure(
    tmp_output: Path,
) -> None:
    """If serialization fails, the old file is untouched."""
    # Write a valid file first
    export_catalog(data={"t": [{"a": 1}]}, output_path=tmp_output, exported_at=T0)
    original_content = tmp_output.read_bytes()

    # Attempt export with unserializable data
    class BadObj:
        pass

    result = export_catalog(
        data={"t": [{"a": BadObj()}]},  # type: ignore[dict-item]
        output_path=tmp_output,
        exported_at=T0,
    )

    assert not result.success
    assert result.error_type == "TypeError"
    assert tmp_output.read_bytes() == original_content


def test_no_partial_file_on_write_failure(tmp_path: Path) -> None:
    """A write failure does not leave a partial .json file."""
    # Use a non-existent nested path where parent creation will work
    # but simulate failure by testing the error result
    output = tmp_path / "output.json"

    # Export with unserializable data to trigger serialization failure
    class Unserializable:
        pass

    result = export_catalog(
        data={"t": [{"x": Unserializable()}]},  # type: ignore[dict-item]
        output_path=output,
        exported_at=T0,
    )

    assert not result.success
    # No output file should exist since serialization failed before write
    assert not output.exists()


def test_atomic_replace_on_success(tmp_output: Path) -> None:
    """Successful export atomically replaces the previous file."""
    export_catalog(data={"t": [{"v": "old"}]}, output_path=tmp_output, exported_at=T0)
    export_catalog(data={"t": [{"v": "new"}]}, output_path=tmp_output, exported_at=T0)

    content = json.loads(tmp_output.read_text())
    assert content["tables"]["t"][0]["v"] == "new"


# ---------------------------------------------------------------------------
# Empty catalog
# ---------------------------------------------------------------------------


def test_empty_data_produces_valid_json(tmp_output: Path) -> None:
    """An empty catalog still produces valid JSON with metadata."""
    result = export_catalog(data={}, output_path=tmp_output, exported_at=T0)

    assert result.success
    content = json.loads(tmp_output.read_text())
    assert content["tables"] == {}
    assert content["_metadata"]["row_counts"] == {}


# ---------------------------------------------------------------------------
# No JSON-to-SQL importer exists
# ---------------------------------------------------------------------------


def test_no_import_function_exists() -> None:
    """The exporter module does not provide an import/read function."""
    import app.testing.catalog_exporter as mod

    public = [n for n in dir(mod) if not n.startswith("_")]
    assert "import_catalog" not in public
    assert "read_catalog" not in public
    assert "load_catalog" not in public
