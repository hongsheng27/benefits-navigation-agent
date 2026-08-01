"""Architecture test: orchestration layer has NO SQLite / SQL leakage.

Uses AST parsing to prove that the workflow and state-machine modules:
- Do NOT import sqlite3 or app.adapters.sqlite.*
- Do NOT contain actual SQL statements in string literals
- Do NOT reference SQLite table names in executable code

Docstrings, comments, and documentation mentions are intentionally excluded —
the test targets real storage boundary violations (actual SQL code, sqlite3
usage), not documentation that mentions table names for context.

Requirements traced: 1.3, 2.5–2.10, 14.5, 14.6.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths under test
# ---------------------------------------------------------------------------

_ORCHESTRATION_DIR = (
    Path(__file__).resolve().parents[2] / "app" / "orchestration"
)

_MODULES_TO_SCAN: list[str] = [
    "state_machine.py",
    "state.py",
    "protocols.py",
    "determination.py",
    "rule_adapter.py",
    "source_refresh.py",
    "missing_fields.py",
    "field_registry.py",
    "session_store.py",
]

# ---------------------------------------------------------------------------
# Banned patterns
# ---------------------------------------------------------------------------

_BANNED_IMPORTS = frozenset(
    {
        "sqlite3",
    }
)

_BANNED_FROM_PREFIXES = (
    "app.adapters.sqlite",
)

_SQL_KEYWORDS = frozenset(
    {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE TABLE",
        "DROP TABLE",
        "ALTER TABLE",
        "PRAGMA",
    }
)

_SQLITE_TABLE_NAMES = frozenset(
    {
        "benefit_programs",
        "program_status_history",
        "review_approvals",
        "field_registry",
        "field_allowed_values",
        "graph_nodes",
        "graph_edges",
        "edge_conditions",
        "rule_definitions",
        "rule_versions",
        "rule_tree",
        "rule_conditions",
        "source_registry",
        "source_documents",
        "approved_excerpts",
        "attachments",
        "crawl_attempts",
        "coverage_state",
        "coverage_snapshots",
        "refresh_jobs",
        "compatibility_generations",
        "compatibility_rows",
        "schema_metadata",
        "schema_migrations",
        "catalog_revisions",
        "program_rule_fields",
    }
)

_SQLITE_REFERENCES = frozenset(
    {
        "sqlite3.connect",
        "sqlite3.Connection",
        "sqlite3.Row",
        "sqlite3.Cursor",
    }
)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _read_source(module_name: str) -> str:
    """Read a module's source from the orchestration directory."""
    path = _ORCHESTRATION_DIR / module_name
    if not path.exists():
        pytest.skip(f"{module_name} does not exist yet")
    return path.read_text(encoding="utf-8")


def _get_all_imports(tree: ast.AST) -> list[str]:
    """Extract all import module names from an AST."""
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _is_docstring_node(node: ast.AST, tree: ast.AST) -> bool:
    """Check if a Constant node is a docstring (first statement in body)."""
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(parent, "body", [])
            if body and isinstance(body[0], ast.Expr):
                expr_value = body[0].value
                if isinstance(expr_value, ast.Constant) and expr_value is node:
                    return True
    return False


def _get_non_docstring_string_literals(tree: ast.AST) -> list[str]:
    """Extract string constants that are NOT docstrings."""
    strings: list[str] = []
    # Collect all docstring nodes first
    docstring_nodes: set[int] = set()
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(parent, "body", [])
            if body and isinstance(body[0], ast.Expr):
                expr_value = body[0].value
                if isinstance(expr_value, ast.Constant) and isinstance(expr_value.value, str):
                    docstring_nodes.add(id(expr_value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstring_nodes:
                strings.append(node.value)
    return strings


def _get_all_attribute_chains(tree: ast.AST) -> list[str]:
    """Extract dotted attribute accesses like sqlite3.connect."""
    chains: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            parts: list[str] = []
            current: ast.expr = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                chains.append(".".join(reversed(parts)))
    return chains


def _looks_like_sql(s: str, keyword: str) -> bool:
    """Return True if the string looks like an actual SQL statement.

    A real SQL statement typically has the keyword followed by table/column
    names or other SQL syntax. A single keyword appearing in prose (e.g.,
    "update=..." or "delete the old file") is not SQL.
    """
    upper = s.upper().strip()
    idx = upper.find(keyword)
    if idx == -1:
        return False
    # Word-boundary check
    before_ok = idx == 0 or not upper[idx - 1].isalpha()
    after_idx = idx + len(keyword)
    after_ok = after_idx >= len(upper) or not upper[after_idx].isalpha()
    if not (before_ok and after_ok):
        return False

    # The string must look like a multi-token SQL statement, not just prose
    # containing the keyword. Check for SQL-like patterns after the keyword:
    # - SELECT ... FROM
    # - INSERT INTO
    # - UPDATE ... SET
    # - DELETE FROM
    # - CREATE TABLE ...
    # - PRAGMA ...
    _SQL_PATTERNS = [
        r"\bSELECT\b.*\bFROM\b",
        r"\bINSERT\b.*\bINTO\b",
        r"\bUPDATE\b.*\bSET\b",
        r"\bDELETE\b.*\bFROM\b",
        r"\bCREATE\s+TABLE\b",
        r"\bDROP\s+TABLE\b",
        r"\bALTER\s+TABLE\b",
        r"\bPRAGMA\b\s+\w+",
    ]
    for pattern in _SQL_PATTERNS:
        if re.search(pattern, upper):
            return True
    return False


# ---------------------------------------------------------------------------
# Test: no sqlite3 or app.adapters.sqlite imports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _MODULES_TO_SCAN)
def test_no_sqlite_imports(module_name: str) -> None:
    """Orchestration modules must not import sqlite3 or adapter modules."""
    source = _read_source(module_name)
    tree = ast.parse(source)
    imports = _get_all_imports(tree)

    for imp in imports:
        assert imp not in _BANNED_IMPORTS, (
            f"{module_name} imports banned module: {imp}"
        )
        for prefix in _BANNED_FROM_PREFIXES:
            assert not imp.startswith(prefix), (
                f"{module_name} imports from banned prefix: {imp}"
            )


# ---------------------------------------------------------------------------
# Test: no sqlite3.connect / sqlite3.Connection references
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _MODULES_TO_SCAN)
def test_no_sqlite3_attribute_references(module_name: str) -> None:
    """Orchestration modules must not reference sqlite3.connect etc."""
    source = _read_source(module_name)
    tree = ast.parse(source)
    chains = _get_all_attribute_chains(tree)

    for chain in chains:
        assert chain not in _SQLITE_REFERENCES, (
            f"{module_name} references banned attribute: {chain}"
        )


# ---------------------------------------------------------------------------
# Test: no actual SQL statements in non-docstring string literals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _MODULES_TO_SCAN)
def test_no_sql_keywords_in_strings(module_name: str) -> None:
    """Orchestration modules must not contain actual SQL in string literals.

    Only flags strings that look like real SQL statements (e.g., SELECT...FROM,
    INSERT INTO, UPDATE...SET). Single keywords appearing in documentation or
    method names (e.g., model_copy(update=...)) are not violations.
    Docstrings are excluded entirely.
    """
    source = _read_source(module_name)
    tree = ast.parse(source)
    strings = _get_non_docstring_string_literals(tree)

    for s in strings:
        for keyword in _SQL_KEYWORDS:
            if _looks_like_sql(s, keyword):
                pytest.fail(
                    f"{module_name} contains SQL statement with '{keyword}' "
                    f"in string literal: {s!r:.80}"
                )


# ---------------------------------------------------------------------------
# Test: no SQLite table names in executable code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _MODULES_TO_SCAN)
def test_no_sqlite_table_names(module_name: str) -> None:
    """Orchestration modules must not reference SQLite table names in code.

    Allows table name mentions in:
    - Import statements (module names may coincide with table names)
    - Comments (lines starting with #)
    - Docstrings (triple-quoted strings at module/class/function level)
    - Type annotations and string annotations referencing module paths

    Flags table name references in:
    - Non-docstring string literals (especially SQL-like ones)
    - Executable code identifiers
    """
    source = _read_source(module_name)
    tree = ast.parse(source)

    # Check non-docstring string literals for table name references that
    # look like actual SQL or storage-layer usage.
    non_doc_strings = _get_non_docstring_string_literals(tree)

    for table in _SQLITE_TABLE_NAMES:
        pattern = rf"\b{re.escape(table)}\b"

        # Check non-docstring strings for table references
        for s in non_doc_strings:
            if re.search(pattern, s, re.IGNORECASE):
                # Only flag if the string looks like SQL or a direct table ref
                # (not a module path like "app.orchestration.field_registry")
                if _string_is_table_reference(s, table):
                    pytest.fail(
                        f"{module_name} references table '{table}' "
                        f"in string literal: {s!r:.80}"
                    )

        # Check source lines for non-string, non-import, non-comment usage
        source_lower = source.lower()
        if table in source_lower:
            lines_with_table = [
                (i, line)
                for i, line in enumerate(source.splitlines())
                if re.search(pattern, line, re.IGNORECASE)
            ]
            for lineno, line in lines_with_table:
                stripped = line.strip()
                # Allow: import lines
                if stripped.startswith(("from ", "import ")):
                    continue
                # Allow: comments
                if stripped.startswith("#"):
                    continue
                # Allow: lines inside docstrings (detected by being within
                # triple-quoted blocks). Use a heuristic: if the line is part
                # of a multi-line string constant, skip it.
                if _line_is_in_docstring(lineno, source, tree):
                    continue
                # Allow: inline comments at end of line (the table name is
                # in the comment portion)
                code_part, _, comment_part = line.partition("#")
                if not re.search(pattern, code_part, re.IGNORECASE):
                    continue
                # Allow: the table name is part of a Python identifier path
                # (e.g., field_registry.FieldRegistry or source_documents.document_id
                # referenced as a domain concept attribute)
                if re.search(
                    rf"\b{re.escape(table)}\.\w+", code_part, re.IGNORECASE
                ):
                    # Could be a module attribute access — only flag if it also
                    # looks like SQL
                    if not _looks_like_sql(code_part, table.upper()):
                        continue
                pytest.fail(
                    f"{module_name} references table name '{table}' "
                    f"in non-import line: {stripped!r:.120}"
                )


def _string_is_table_reference(s: str, table: str) -> bool:
    """Determine if a string containing a table name is an actual table ref.

    Returns False for:
    - Module path references like "app.orchestration.field_registry"
    - Prose/documentation text that just mentions the name for context
    Returns True for:
    - SQL-like statements
    - Bare table names used as identifiers in query-like context
    """
    # If it looks like a module path (dotted Python path), not a table ref
    if re.search(rf"app\.\w+\.{re.escape(table)}", s):
        return False
    # If the string looks like SQL, it's a real violation
    upper = s.upper()
    for kw in _SQL_KEYWORDS:
        if _looks_like_sql(s, kw):
            return True
    # If the string is short and just the table name, flag it
    if s.strip().lower() == table:
        return True
    # Otherwise, it's likely prose/documentation — not a violation
    return False


def _line_is_in_docstring(lineno: int, source: str, tree: ast.AST) -> bool:
    """Check if a source line number (0-indexed) falls within a docstring."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr):
                expr_value = body[0].value
                if isinstance(expr_value, ast.Constant) and isinstance(expr_value.value, str):
                    # lineno is 1-indexed in AST
                    start = expr_value.lineno - 1  # convert to 0-indexed
                    end = expr_value.end_lineno - 1 if expr_value.end_lineno else start
                    if start <= lineno <= end:
                        return True
    return False
