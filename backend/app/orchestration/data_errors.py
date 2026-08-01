"""Storage-neutral error hierarchy for repository operations.

These errors carry only a safe string code. They must never include SQL statements,
table/column names, row contents, user values, or internal implementation details.

Adapters raise these in place of sqlite3.Error or other storage-specific exceptions.
The workflow layer catches them to distinguish "no data" (empty tuple) from "query
or storage failure" (exception).
"""

from __future__ import annotations


class DataLayerError(RuntimeError):
    """Base for all storage-neutral data layer errors.

    Subclasses indicate the failure category. The `code` attribute is safe to log,
    return in API error responses, and include in metrics — it contains no user data.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __str__(self) -> str:
        return self.code


class RepositoryUnavailableError(DataLayerError):
    """The underlying storage cannot be opened or is not reachable."""


class RepositoryQueryError(DataLayerError):
    """A query against the storage failed after it was opened."""


class RepositoryMappingError(DataLayerError):
    """A row was read but could not be mapped to the domain contract."""


class InvalidEventIdError(DataLayerError):
    """The provided event ID does not exist or is not a life-event node."""
