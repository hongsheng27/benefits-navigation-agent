"""SQLite connection lifecycle helpers.

Every adapter operation must go through one of these helpers to guarantee:

1. `contextlib.closing` ensures close() on all paths (Req 13.1, 13.11).
2. PRAGMA foreign_keys = ON on every connection (design section 14).
3. Read: operation → close → return (Req 13.4).
4. Transaction: operation → commit → close → return (Req 13.2).
5. Failure: rollback (best-effort) → close → sanitized error (Req 13.3, 13.6).
6. Close failure: discard result, return sanitized error (Req 13.7).
7. Errors never contain SQL, rows, or user values (Req 13.8).

Callers must materialize/map all rows inside the operation callable.
Do not return lazy cursors or iterators that depend on the connection.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from typing import TypeVar

from app.orchestration.data_errors import (
    DataLayerError,
    RepositoryQueryError,
    RepositoryUnavailableError,
)

T = TypeVar("T")


def _enable_foreign_keys(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")


def execute_read(
    connection_factory: Callable[[], sqlite3.Connection],
    operation: Callable[[sqlite3.Connection], T],
) -> T:
    """Execute a read-only operation with guaranteed connection closure.

    Lifecycle: open → foreign_keys → operation → close → return result.
    The operation must materialize all rows before returning.
    """
    try:
        connection = connection_factory()
    except Exception as exc:
        raise RepositoryUnavailableError("connection_open_failed") from exc

    result: T
    try:
        with closing(connection) as conn:
            _enable_foreign_keys(conn)
            result = operation(conn)
    except RepositoryUnavailableError:
        raise
    except RepositoryQueryError:
        raise
    except DataLayerError:
        raise
    except Exception as exc:
        raise RepositoryQueryError("read_operation_failed") from exc

    # If we reach here, close succeeded (closing guarantees close() call).
    # However, if closing itself raised during __exit__, we won't reach here —
    # that case is handled by catching the exception above.
    return result


def execute_transaction(
    connection_factory: Callable[[], sqlite3.Connection],
    operation: Callable[[sqlite3.Connection], T],
) -> T:
    """Execute a write operation within a transaction with guaranteed closure.

    Lifecycle: open → foreign_keys → operation → commit → close → return result.
    On failure: rollback (best-effort) → close → sanitized error.
    """
    try:
        connection = connection_factory()
    except Exception as exc:
        raise RepositoryUnavailableError("connection_open_failed") from exc

    result: T
    committed = False
    try:
        with closing(connection) as conn:
            _enable_foreign_keys(conn)
            try:
                result = operation(conn)
                conn.commit()
                committed = True
            except BaseException:
                try:
                    conn.rollback()
                except Exception:
                    pass  # Req 13.6: rollback failure → still close
                raise
    except RepositoryUnavailableError:
        raise
    except RepositoryQueryError:
        raise
    except DataLayerError:
        raise
    except Exception as exc:
        if committed:
            # Close failed after successful commit — discard result (Req 13.7)
            raise RepositoryUnavailableError("connection_close_failed") from exc
        raise RepositoryQueryError("transaction_failed") from exc

    return result
