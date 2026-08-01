"""Property 19: JSON deterministic atomic export and runtime isolation.

**Validates: Requirements 1.3, 1.9, 14.1-14.11**

1. Any insertion order produces identical bytes (determinism).
2. Any export failure leaves no partial file.
3. Any runtime request has zero JSON exporter calls (isolation).
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.testing.catalog_exporter import export_catalog

T0 = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

_field_names = st.sampled_from(
    ["id", "name", "status", "value", "created_at", "type", "score"]
)
_field_values = st.one_of(
    st.none(),
    st.integers(min_value=-1000, max_value=1000),
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=1, max_size=15
    ),
    st.booleans(),
)

_table_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=3, max_size=12
)


@st.composite
def _row(draw: st.DrawFn) -> dict:
    keys = draw(st.lists(_field_names, min_size=1, max_size=5, unique=True))
    return {k: draw(_field_values) for k in keys}


@st.composite
def _table_data(draw: st.DrawFn) -> dict[str, list[dict]]:
    table_count = draw(st.integers(min_value=0, max_value=4))
    tables: dict[str, list[dict]] = {}
    for _ in range(table_count):
        name = draw(_table_names)
        rows = draw(st.lists(_row(), min_size=0, max_size=8))
        tables[name] = rows
    return tables


# ---------------------------------------------------------------------------
# Property 19.1 — Deterministic: any insertion order → same bytes
# ---------------------------------------------------------------------------


@given(data=_table_data())
@settings(max_examples=200, deadline=5000)
def test_shuffled_insertion_order_produces_identical_bytes(
    data: dict[str, list[dict]], tmp_path_factory
) -> None:
    """Rows and tables in different insertion orders yield identical output."""
    base = tmp_path_factory.mktemp("prop19")
    out1 = base / "a.json"
    out2 = base / "b.json"

    # Shuffle the data for the second export
    shuffled: dict[str, list[dict]] = {}
    table_names = list(data.keys())
    random.shuffle(table_names)
    for name in table_names:
        rows = list(data[name])
        random.shuffle(rows)
        shuffled[name] = rows

    r1 = export_catalog(data=data, output_path=out1, exported_at=T0)
    r2 = export_catalog(data=shuffled, output_path=out2, exported_at=T0)

    assert r1.success
    assert r2.success
    assert out1.read_bytes() == out2.read_bytes()


# ---------------------------------------------------------------------------
# Property 19.2 — Atomicity: any failure → no partial file
# ---------------------------------------------------------------------------


@given(data=_table_data())
@settings(max_examples=100, deadline=5000)
def test_serialization_failure_leaves_no_partial(
    data: dict[str, list[dict]], tmp_path_factory
) -> None:
    """If serialization fails, no output file is created or modified."""
    base = tmp_path_factory.mktemp("prop19fail")
    output = base / "catalog.json"

    # Write a valid file first
    export_catalog(data=data, output_path=output, exported_at=T0)
    original = output.read_bytes()

    # Now inject an unserializable value
    class Bad:
        pass

    bad_data = dict(data)
    bad_data["_bad"] = [{"x": Bad()}]  # type: ignore[dict-item]
    result = export_catalog(data=bad_data, output_path=output, exported_at=T0)

    assert not result.success
    # Original file is preserved exactly
    assert output.read_bytes() == original


# ---------------------------------------------------------------------------
# Property 19.3 — Runtime isolation: exporter not imported by app
# ---------------------------------------------------------------------------


def test_runtime_modules_do_not_import_exporter() -> None:
    """No app runtime module imports the exporter."""
    import ast

    app_dir = Path(__file__).resolve().parents[2] / "app"
    # Check all .py files under app/ except app/testing/
    violations: list[str] = []
    for py_file in app_dir.rglob("*.py"):
        if "testing" in py_file.parts:
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "catalog_exporter" in alias.name:
                        violations.append(f"{py_file}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if "catalog_exporter" in node.module:
                    violations.append(
                        f"{py_file}: from {node.module} import ..."
                    )

    assert violations == [], f"Runtime imports exporter: {violations}"


def test_exported_json_is_valid_json(tmp_path_factory) -> None:
    """Every successful export produces valid parseable JSON."""
    base = tmp_path_factory.mktemp("prop19json")
    output = base / "test.json"
    data = {"programs": [{"id": "p1", "name": "Test"}]}

    result = export_catalog(data=data, output_path=output, exported_at=T0)
    assert result.success

    content = json.loads(output.read_text())
    assert "_metadata" in content
    assert "tables" in content
