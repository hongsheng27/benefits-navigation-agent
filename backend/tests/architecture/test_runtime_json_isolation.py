"""Architecture test: runtime import graph does NOT include JSON exporter.

Proves that:
- Application startup (via create_app with fakes) does NOT import any
  catalog_exporter or export_catalog module
- The composition root and main module do NOT have static imports to the
  optional JSON exporter

The JSON exporter is a test/release-only utility. It must never become a
runtime dependency that would pull in heavy I/O or schema assumptions at
startup.

Requirements traced: 14.5, 14.6, 14.10.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_APP_DIR = Path(__file__).resolve().parents[2] / "app"
_MAIN_MODULE = _APP_DIR / "main.py"
_COMPOSITION_MODULE = _APP_DIR / "application" / "composition.py"

# Modules that should NEVER be imported at runtime
_EXPORTER_MARKERS = ("catalog_exporter", "export_catalog")


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _get_all_imports(source_path: Path) -> list[str]:
    """Parse a Python file and return all imported module names."""
    if not source_path.exists():
        pytest.skip(f"{source_path.name} does not exist yet")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


# ---------------------------------------------------------------------------
# Test: AST-level — main.py does not statically import exporter
# ---------------------------------------------------------------------------


def test_main_no_static_exporter_import() -> None:
    """app/main.py must not statically import any exporter module."""
    imports = _get_all_imports(_MAIN_MODULE)
    violators = [
        imp for imp in imports if any(m in imp for m in _EXPORTER_MARKERS)
    ]
    assert not violators, (
        f"app/main.py statically imports exporter modules: {violators}"
    )


def test_composition_no_static_exporter_import() -> None:
    """app/application/composition.py must not statically import exporter."""
    imports = _get_all_imports(_COMPOSITION_MODULE)
    violators = [
        imp for imp in imports if any(m in imp for m in _EXPORTER_MARKERS)
    ]
    assert not violators, (
        f"composition.py statically imports exporter modules: {violators}"
    )


# ---------------------------------------------------------------------------
# Test: runtime — importing create_app with fakes does NOT load exporter
# ---------------------------------------------------------------------------


def test_runtime_does_not_import_json_exporter() -> None:
    """Runtime startup with all fakes does not import the JSON exporter."""
    # Record modules loaded before we trigger the app factory
    modules_before = set(sys.modules.keys())

    from app.main import create_app
    from tests.fakes import make_all_fakes_overrides

    overrides = make_all_fakes_overrides()
    _app = create_app(overrides)

    # Check no exporter module was loaded
    loaded = set(sys.modules.keys()) - modules_before
    exporter_modules = [
        m
        for m in loaded
        if any(marker in m for marker in _EXPORTER_MARKERS)
    ]
    assert not exporter_modules, (
        f"JSON exporter loaded at runtime: {exporter_modules}"
    )
