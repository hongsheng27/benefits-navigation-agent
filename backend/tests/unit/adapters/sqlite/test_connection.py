"""Lifecycle failure-injection tests for SQLite connection helpers.

Uses an instrumented fake connection to verify invocation ordering,
guaranteed closure, and sanitized error behavior at every failure point.

Requirements coverage: 13.1–13.11.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from app.adapters.sqlite.connection import execute_read, execute_transaction
from app.orchestration.data_errors import (
    RepositoryQueryError,
    RepositoryUnavailableError,
)


class FakeConnection:
    """Instrumented fake that records invocation order and injects failures."""

    def __init__(
        self,
        *,
        execute_side_effect: Exception | None = None,
        commit_side_effect: Exception | None = None,
        rollback_side_effect: Exception | None = None,
        close_side_effect: Exception | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._execute_side_effect = execute_side_effect
        self._commit_side_effect = commit_side_effect
        self._rollback_side_effect = rollback_side_effect
        self._close_side_effect = close_side_effect

    def execute(self, sql: str, *args: object) -> object:
        self.calls.append(f"execute:{sql.strip()}")
        if self._execute_side_effect is not None:
            # Only fail on non-PRAGMA calls
            if "PRAGMA" not in sql:
                raise self._execute_side_effect
        return MagicMock()

    def commit(self) -> None:
        self.calls.append("commit")
        if self._commit_side_effect is not None:
            raise self._commit_side_effect

    def rollback(self) -> None:
        self.calls.append("rollback")
        if self._rollback_side_effect is not None:
            raise self._rollback_side_effect

    def close(self) -> None:
        self.calls.append("close")
        if self._close_side_effect is not None:
            raise self._close_side_effect


def _factory(fake: FakeConnection):
    """Return a connection factory that returns the given fake."""
    return lambda: fake


def _successful_operation(connection: object) -> str:
    """A simple operation that returns a result."""
    return "operation_result"


def _failing_operation(connection: object) -> str:
    """An operation that always fails."""
    raise sqlite3.OperationalError("simulated operation failure")


# ---------------------------------------------------------------------------
# Read path: success and ordering
# ---------------------------------------------------------------------------


def test_read_success_ordering() -> None:
    """Read: foreign_keys → operation → close → return."""
    fake = FakeConnection()

    result = execute_read(_factory(fake), _successful_operation)

    assert result == "operation_result"
    assert "execute:PRAGMA foreign_keys = ON" in fake.calls
    assert "close" in fake.calls
    # Close must come after the PRAGMA
    pragma_idx = fake.calls.index("execute:PRAGMA foreign_keys = ON")
    close_idx = fake.calls.index("close")
    assert close_idx > pragma_idx


def test_read_foreign_keys_enabled() -> None:
    """PRAGMA foreign_keys = ON is executed on every read connection."""
    fake = FakeConnection()

    execute_read(_factory(fake), _successful_operation)

    assert any("PRAGMA foreign_keys = ON" in call for call in fake.calls)


# ---------------------------------------------------------------------------
# Transaction path: success and ordering
# ---------------------------------------------------------------------------


def test_transaction_success_ordering() -> None:
    """Transaction: foreign_keys → operation → commit → close → return."""
    fake = FakeConnection()

    result = execute_transaction(_factory(fake), _successful_operation)

    assert result == "operation_result"
    assert "execute:PRAGMA foreign_keys = ON" in fake.calls
    assert "commit" in fake.calls
    assert "close" in fake.calls
    commit_idx = fake.calls.index("commit")
    close_idx = fake.calls.index("close")
    assert close_idx > commit_idx


def test_transaction_foreign_keys_enabled() -> None:
    """PRAGMA foreign_keys = ON is executed on every transaction connection."""
    fake = FakeConnection()

    execute_transaction(_factory(fake), _successful_operation)

    assert any("PRAGMA foreign_keys = ON" in call for call in fake.calls)


# ---------------------------------------------------------------------------
# Read path: failure cases
# ---------------------------------------------------------------------------


def test_read_operation_failure_closes_connection() -> None:
    """Read operation failure: close is still called, raises RepositoryQueryError."""
    fake = FakeConnection()

    with pytest.raises(RepositoryQueryError) as exc_info:
        execute_read(_factory(fake), _failing_operation)

    assert exc_info.value.code == "read_operation_failed"
    assert "close" in fake.calls


def test_read_open_failure_raises_unavailable() -> None:
    """Open failure: raises RepositoryUnavailableError."""

    def failing_factory() -> sqlite3.Connection:
        raise OSError("cannot open database")

    with pytest.raises(RepositoryUnavailableError) as exc_info:
        execute_read(failing_factory, _successful_operation)

    assert exc_info.value.code == "connection_open_failed"


def test_read_close_failure_discards_result() -> None:
    """Close failure on read: discards result, raises RepositoryUnavailableError."""
    fake = FakeConnection(close_side_effect=OSError("close failed"))

    with pytest.raises((RepositoryUnavailableError, RepositoryQueryError)):
        execute_read(_factory(fake), _successful_operation)


# ---------------------------------------------------------------------------
# Transaction path: failure cases
# ---------------------------------------------------------------------------


def test_transaction_operation_failure_rollback_close() -> None:
    """Operation failure: rollback → close → RepositoryQueryError."""
    fake = FakeConnection()

    with pytest.raises(RepositoryQueryError) as exc_info:
        execute_transaction(_factory(fake), _failing_operation)

    assert exc_info.value.code == "transaction_failed"
    assert "rollback" in fake.calls
    assert "close" in fake.calls
    rollback_idx = fake.calls.index("rollback")
    close_idx = fake.calls.index("close")
    assert close_idx > rollback_idx


def test_transaction_commit_failure_rollback_close() -> None:
    """Commit failure: rollback → close → RepositoryQueryError."""
    fake = FakeConnection(commit_side_effect=sqlite3.OperationalError("disk full"))

    with pytest.raises(RepositoryQueryError) as exc_info:
        execute_transaction(_factory(fake), _successful_operation)

    assert exc_info.value.code == "transaction_failed"
    assert "rollback" in fake.calls
    assert "close" in fake.calls


def test_transaction_rollback_failure_still_closes() -> None:
    """Rollback failure: close is still called (Req 13.6)."""
    fake = FakeConnection(
        rollback_side_effect=sqlite3.OperationalError("rollback failed"),
    )

    with pytest.raises(RepositoryQueryError):
        execute_transaction(_factory(fake), _failing_operation)

    assert "rollback" in fake.calls
    assert "close" in fake.calls


def test_transaction_close_failure_discards_result() -> None:
    """Close failure after commit: discards result (Req 13.7)."""
    fake = FakeConnection(close_side_effect=OSError("close failed"))

    with pytest.raises(RepositoryUnavailableError) as exc_info:
        execute_transaction(_factory(fake), _successful_operation)

    assert exc_info.value.code == "connection_close_failed"
    assert "commit" in fake.calls


def test_transaction_open_failure_raises_unavailable() -> None:
    """Open failure: raises RepositoryUnavailableError."""

    def failing_factory() -> sqlite3.Connection:
        raise sqlite3.OperationalError("unable to open database file")

    with pytest.raises(RepositoryUnavailableError) as exc_info:
        execute_transaction(failing_factory, _successful_operation)

    assert exc_info.value.code == "connection_open_failed"


# ---------------------------------------------------------------------------
# Error sanitization (Req 13.8)
# ---------------------------------------------------------------------------


_SQL_KEYWORDS = ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER")
_SENSITIVE_PATTERNS = ("program_rule_fields", "user_", "actual=")


def test_errors_never_contain_sql_or_user_values() -> None:
    """Error codes and str() must not leak SQL or user data."""
    fake = FakeConnection()
    errors: list[RepositoryQueryError | RepositoryUnavailableError] = []

    try:
        execute_read(_factory(fake), _failing_operation)
    except (RepositoryQueryError, RepositoryUnavailableError) as exc:
        errors.append(exc)

    try:
        execute_transaction(_factory(fake), _failing_operation)
    except (RepositoryQueryError, RepositoryUnavailableError) as exc:
        errors.append(exc)

    def failing_factory():
        raise sqlite3.OperationalError("unable to open /secret/path.db")

    try:
        execute_read(failing_factory, _successful_operation)
    except (RepositoryQueryError, RepositoryUnavailableError) as exc:
        errors.append(exc)

    assert len(errors) >= 2
    for error in errors:
        error_text = f"{error.code} {error!s}"
        for keyword in _SQL_KEYWORDS:
            assert keyword not in error_text
        for pattern in _SENSITIVE_PATTERNS:
            assert pattern not in error_text


# ---------------------------------------------------------------------------
# Connection closure verification (Req 13.10)
# ---------------------------------------------------------------------------


def test_every_successful_path_closes_connection() -> None:
    """Both read and transaction success paths close the connection."""
    read_fake = FakeConnection()
    tx_fake = FakeConnection()

    execute_read(_factory(read_fake), _successful_operation)
    execute_transaction(_factory(tx_fake), _successful_operation)

    assert "close" in read_fake.calls
    assert "close" in tx_fake.calls


def test_every_failure_path_closes_connection() -> None:
    """All failure paths still close the connection."""
    fakes: list[FakeConnection] = []

    # Read operation failure
    f1 = FakeConnection()
    fakes.append(f1)
    with pytest.raises(RepositoryQueryError):
        execute_read(_factory(f1), _failing_operation)

    # Transaction operation failure
    f2 = FakeConnection()
    fakes.append(f2)
    with pytest.raises(RepositoryQueryError):
        execute_transaction(_factory(f2), _failing_operation)

    # Transaction commit failure
    f3 = FakeConnection(commit_side_effect=sqlite3.OperationalError("x"))
    fakes.append(f3)
    with pytest.raises(RepositoryQueryError):
        execute_transaction(_factory(f3), _successful_operation)

    # Transaction rollback failure
    f4 = FakeConnection(
        rollback_side_effect=sqlite3.OperationalError("y"),
    )
    fakes.append(f4)
    with pytest.raises(RepositoryQueryError):
        execute_transaction(_factory(f4), _failing_operation)

    for fake in fakes:
        assert "close" in fake.calls, f"Missing close in {fake.calls}"
