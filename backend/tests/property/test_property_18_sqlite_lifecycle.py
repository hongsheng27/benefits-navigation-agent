"""Property 18: SQLite lifecycle trace and closure.

**Validates: Requirements 1.8, 1.9, 13.1-13.11**

For any operation/commit/rollback/close failure matrix:
1. Connection is always closed (success or failure).
2. Lifecycle trace follows the expected invocation order.
3. Errors are sanitized (no SQL, rows, or user values leaked).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.adapters.sqlite.connection import execute_read, execute_transaction

# ---------------------------------------------------------------------------
# Instrumented fake connection for property testing
# ---------------------------------------------------------------------------


@dataclass
class FakeConnection:
    """Records lifecycle events and optionally fails at specified points."""

    trace: list[str] = field(default_factory=list)
    fail_on_execute: bool = False
    fail_on_commit: bool = False
    fail_on_rollback: bool = False
    fail_on_close: bool = False
    _closed: bool = False

    def execute(self, sql: str, params: Any = None) -> FakeConnection:
        self.trace.append("execute")
        if self.fail_on_execute:
            raise RuntimeError("execute failed")
        return self

    def fetchall(self) -> list[tuple]:
        return [("row1",)]

    def commit(self) -> None:
        self.trace.append("commit")
        if self.fail_on_commit:
            raise RuntimeError("commit failed")

    def rollback(self) -> None:
        self.trace.append("rollback")
        if self.fail_on_rollback:
            raise RuntimeError("rollback failed")

    def close(self) -> None:
        self.trace.append("close")
        self._closed = True
        if self.fail_on_close:
            raise RuntimeError("close failed")

    def cursor(self) -> FakeConnection:
        return self

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# Failure point strategies
_failure_matrix = st.fixed_dictionaries(
    {
        "fail_on_execute": st.booleans(),
        "fail_on_commit": st.booleans(),
        "fail_on_rollback": st.booleans(),
        "fail_on_close": st.booleans(),
    }
)


def _make_factory(conn: FakeConnection):
    """Create a connection_factory that returns our instrumented fake."""

    def factory() -> Any:
        conn.trace.append("open")
        return conn

    return factory


# ---------------------------------------------------------------------------
# Property 18.1 — Connection is always closed
# ---------------------------------------------------------------------------


@given(failures=_failure_matrix)
@settings(max_examples=200, deadline=5000)
def test_transaction_always_closes_connection(failures: dict[str, bool]) -> None:
    """Regardless of which operations fail, close is always attempted."""
    conn = FakeConnection(**failures)
    factory = _make_factory(conn)

    try:
        execute_transaction(factory, lambda c: c.execute("INSERT INTO t VALUES (1)"))
    except Exception:
        pass

    assert "close" in conn.trace


@given(failures=_failure_matrix)
@settings(max_examples=200, deadline=5000)
def test_read_always_closes_connection(failures: dict[str, bool]) -> None:
    """Read operations also always close the connection."""
    conn = FakeConnection(**failures)
    factory = _make_factory(conn)

    try:
        execute_read(factory, lambda c: c.execute("SELECT 1").fetchall())
    except Exception:
        pass

    assert "close" in conn.trace


# ---------------------------------------------------------------------------
# Property 18.2 — Lifecycle trace ordering
# ---------------------------------------------------------------------------


@given(
    fail_execute=st.booleans(),
    fail_commit=st.booleans(),
)
@settings(max_examples=200, deadline=5000)
def test_transaction_trace_ordering(fail_execute: bool, fail_commit: bool) -> None:
    """Transaction trace follows: open → execute → commit/rollback → close."""
    conn = FakeConnection(
        fail_on_execute=fail_execute,
        fail_on_commit=fail_commit,
    )
    factory = _make_factory(conn)

    try:
        execute_transaction(factory, lambda c: c.execute("INSERT INTO t VALUES (1)"))
    except Exception:
        pass

    # Open is always first
    if conn.trace:
        assert conn.trace[0] == "open"

    # Close is always last
    if "close" in conn.trace:
        assert conn.trace[-1] == "close"

    # If execute succeeded and commit failed, rollback should appear
    if not fail_execute and fail_commit:
        assert "rollback" in conn.trace


@given(fail_execute=st.booleans())
@settings(max_examples=200, deadline=5000)
def test_read_trace_ordering(fail_execute: bool) -> None:
    """Read trace follows: open → execute → close."""
    conn = FakeConnection(fail_on_execute=fail_execute)
    factory = _make_factory(conn)

    try:
        execute_read(factory, lambda c: c.execute("SELECT 1").fetchall())
    except Exception:
        pass

    if conn.trace:
        assert conn.trace[0] == "open"
    if "close" in conn.trace:
        assert conn.trace[-1] == "close"


# ---------------------------------------------------------------------------
# Property 18.3 — Errors are sanitized
# ---------------------------------------------------------------------------


@given(failures=_failure_matrix)
@settings(max_examples=200, deadline=5000)
def test_errors_do_not_leak_sql_or_values(failures: dict[str, bool]) -> None:
    """Exceptions from lifecycle helpers don't contain raw SQL or user values."""
    conn = FakeConnection(**failures)
    factory = _make_factory(conn)

    try:
        execute_transaction(
            factory, lambda c: c.execute("SELECT password FROM secrets WHERE id=1")
        )
    except Exception as exc:
        error_text = str(exc)
        # Sanitized errors should not contain raw SQL
        assert "SELECT password" not in error_text
        assert "secrets" not in error_text
        assert "WHERE id" not in error_text


@given(failures=_failure_matrix)
@settings(max_examples=200, deadline=5000)
def test_read_errors_do_not_leak(failures: dict[str, bool]) -> None:
    """Read errors also don't leak SQL content."""
    conn = FakeConnection(**failures)
    factory = _make_factory(conn)

    try:
        execute_read(factory, lambda c: c.execute("SELECT ssn FROM users").fetchall())
    except Exception as exc:
        error_text = str(exc)
        assert "SELECT ssn" not in error_text
        assert "users" not in error_text
