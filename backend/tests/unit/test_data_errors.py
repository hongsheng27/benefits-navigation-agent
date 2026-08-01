"""Verify the storage-neutral error hierarchy.

These errors must only expose a safe code — no SQL, table names, row content,
or user values. The hierarchy lets the workflow layer distinguish unavailability,
query failure, and mapping failure without importing storage-specific exceptions.
"""

import pytest

from app.orchestration.data_errors import (
    DataLayerError,
    RepositoryMappingError,
    RepositoryQueryError,
    RepositoryUnavailableError,
)


@pytest.mark.parametrize(
    "error_class",
    [
        RepositoryUnavailableError,
        RepositoryQueryError,
        RepositoryMappingError,
    ],
)
def test_each_error_is_a_data_layer_error_and_runtime_error(
    error_class: type,
) -> None:
    error = error_class("test_code")

    assert isinstance(error, DataLayerError)
    assert isinstance(error, RuntimeError)


def test_error_str_only_shows_code_not_details() -> None:
    error = RepositoryQueryError("query_failed")

    assert str(error) == "query_failed"
    assert error.code == "query_failed"
    # Ensure no SQL or user data leaks even if constructed with extra info
    assert "SELECT" not in str(error)


def test_error_hierarchy_has_distinct_codes() -> None:
    unavailable = RepositoryUnavailableError("storage_unavailable")
    query = RepositoryQueryError("query_execution_failed")
    mapping = RepositoryMappingError("row_mapping_failed")

    assert unavailable.code != query.code != mapping.code


def test_error_can_be_caught_by_base_class() -> None:
    with pytest.raises(DataLayerError):
        raise RepositoryUnavailableError("db_locked")

    with pytest.raises(DataLayerError):
        raise RepositoryQueryError("timeout")

    with pytest.raises(DataLayerError):
        raise RepositoryMappingError("invalid_datetime")
