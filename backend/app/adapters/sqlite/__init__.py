"""SQLite persistence adapter."""

from app.adapters.sqlite.connection import execute_read, execute_transaction

__all__ = ["execute_read", "execute_transaction"]
