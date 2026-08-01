"""PostgreSQL connection pool and lifecycle helpers.

Mirrors the guarantees of the SQLite connection module:
1. Every operation gets a connection from the pool and returns it after use.
2. Read operations use a transaction in REPEATABLE READ for snapshot consistency.
3. Write operations commit on success, rollback on failure.
4. Errors are mapped to storage-neutral exceptions (no SQL/rows in messages).
5. Pool is created once at application startup and closed at shutdown.

Uses psycopg 3 with psycopg_pool for connection pooling.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

import psycopg
from psycopg_pool import ConnectionPool

from app.orchestration.data_errors import (
    RepositoryQueryError,
    RepositoryUnavailableError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PostgresConfig:
    """Connection parameters for RDS PostgreSQL."""

    host: str
    port: int = 5432
    database: str = "benefits_navigation"
    username: str = "benefits_admin"
    password: str = ""
    sslmode: str = "require"
    min_pool_size: int = 2
    max_pool_size: int = 10

    @property
    def conninfo(self) -> str:
        """Build a libpq connection string."""
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.username} password={self.password} "
            f"sslmode={self.sslmode}"
        )


def create_pool(config: PostgresConfig) -> ConnectionPool:
    """Create and open a connection pool.

    The pool is opened eagerly so startup fails fast if RDS is unreachable.
    """
    try:
        pool = ConnectionPool(
            conninfo=config.conninfo,
            min_size=config.min_pool_size,
            max_size=config.max_pool_size,
            open=True,
        )
        return pool
    except Exception as exc:
        raise RepositoryUnavailableError("postgresql_pool_create_failed") from exc


def close_pool(pool: ConnectionPool) -> None:
    """Close the connection pool gracefully."""
    try:
        pool.close()
    except Exception:
        pass  # Best-effort close


def execute_read(
    pool: ConnectionPool,
    operation: Callable[[psycopg.Connection], T],
) -> T:
    """Execute a read-only operation with a pooled connection.

    Uses a transaction block for snapshot consistency.
    Connection is returned to the pool after use.
    """
    try:
        with pool.connection() as conn:
            conn.autocommit = False
            try:
                result = operation(conn)
                conn.rollback()  # Read-only, no commit needed
                return result
            except Exception:
                conn.rollback()
                raise
    except RepositoryUnavailableError:
        raise
    except RepositoryQueryError:
        raise
    except psycopg.OperationalError as exc:
        raise RepositoryUnavailableError("postgresql_connection_failed") from exc
    except Exception as exc:
        raise RepositoryQueryError("read_operation_failed") from exc


def execute_transaction(
    pool: ConnectionPool,
    operation: Callable[[psycopg.Connection], T],
) -> T:
    """Execute a write operation within a transaction.

    Commits on success, rolls back on failure.
    Connection is returned to the pool after use.
    """
    try:
        with pool.connection() as conn:
            conn.autocommit = False
            try:
                result = operation(conn)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
    except RepositoryUnavailableError:
        raise
    except RepositoryQueryError:
        raise
    except psycopg.OperationalError as exc:
        raise RepositoryUnavailableError("postgresql_connection_failed") from exc
    except Exception as exc:
        raise RepositoryQueryError("transaction_failed") from exc
