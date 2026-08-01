"""Application composition root — the ONLY place that builds adapters.

This module constructs all protocol implementations and injects them into the
application. Routes must never create adapters themselves.

Design:
- `ApplicationDependencies`: frozen dataclass holding all protocol ports.
- `ApplicationOverrides`: optional frozen dataclass for test injection.
- `build_dependencies()`: validates SQLite, builds real adapters.
  When overrides supply all four ports, ZERO SQLite connections are opened.
- If any required dependency is missing, `DependencyConfigurationError` is
  raised before the app can accept requests.

Requirements traced: 1.3, 1.4, 2.5, 2.8–2.10.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.adapters.sqlite.connection import execute_read
from app.adapters.sqlite.evidence_repository import SqliteEvidenceRepository
from app.adapters.sqlite.graph_repository import SqliteEntitlementGraphRepository
from app.adapters.sqlite.migrations import (
    MIN_SUPPORTED_VERSION,
    MigrationError,
    load_migrations,
    run_migrations,
)
from app.adapters.sqlite.rule_repository import SqliteRuleRepository
from app.adapters.sqlite.source_refresh_service import SqliteSourceRefreshService
from app.application.eligibility_service import DeterministicEligibilityService
from app.orchestration.data_errors import RepositoryUnavailableError
from app.orchestration.protocols import (
    EligibilityService,
    EntitlementGraphRepository,
    EvidenceRepository,
    SourceRefreshService,
)


# ---------------------------------------------------------------------------
# Typed error for missing or misconfigured dependencies
# ---------------------------------------------------------------------------


class DependencyConfigurationError(RuntimeError):
    """Raised when a required dependency cannot be built during startup.

    The `dependency_type` attribute names which port is missing, without
    leaking user data or internal paths.
    """

    def __init__(self, dependency_type: str, reason: str = "") -> None:
        self.dependency_type = dependency_type
        self.reason = reason
        msg = f"dependency_configuration_error:{dependency_type}"
        if reason:
            msg += f":{reason}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Dependency containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ApplicationOverrides:
    """Optional overrides for test injection.

    When ALL four ports are provided, the composition root will NOT open any
    SQLite connection or build any SQLite adapter.
    """

    graph_repository: EntitlementGraphRepository | None = None
    eligibility_service: EligibilityService | None = None
    evidence_repository: EvidenceRepository | None = None
    source_refresh_service: SourceRefreshService | None = None


@dataclass(frozen=True, slots=True)
class ApplicationDependencies:
    """Holds all protocol implementations needed by the application.

    Passed to app.state so routes and the state machine can access services
    without constructing adapters themselves.
    """

    graph_repository: EntitlementGraphRepository
    eligibility_service: EligibilityService
    evidence_repository: EvidenceRepository
    source_refresh_service: SourceRefreshService


# ---------------------------------------------------------------------------
# SQLite validation helpers
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "local" / "government_oid.db"


def _make_connection_factory(db_path: Path) -> Callable[[], sqlite3.Connection]:
    """Return a factory that creates a new SQLite connection each call."""

    def factory() -> sqlite3.Connection:
        return sqlite3.connect(db_path)

    return factory


def _validate_sqlite(db_path: Path) -> None:
    """Verify SQLite is accessible and schema version is supported.

    Raises DependencyConfigurationError on failure (Req 1.3, 1.4).
    """
    try:
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            migrations = load_migrations()
            run_migrations(conn, migrations=migrations)
    except MigrationError as exc:
        raise DependencyConfigurationError(
            "sqlite", reason=exc.code
        ) from exc
    except (OSError, sqlite3.Error) as exc:
        raise DependencyConfigurationError(
            "sqlite", reason="unavailable"
        ) from exc


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def build_dependencies(
    overrides: ApplicationOverrides | None = None,
    *,
    db_path: Path | None = None,
) -> ApplicationDependencies:
    """Build all application dependencies.

    When `overrides` supplies all four ports, no SQLite is touched (Req 2.9).
    Otherwise, validates SQLite and builds real adapters (Req 2.5).

    If any required port ends up None, raises DependencyConfigurationError
    before the app can accept requests (Req 2.10).
    """
    # Check if all overrides are supplied — skip SQLite entirely
    if overrides is not None and _all_overrides_present(overrides):
        return ApplicationDependencies(
            graph_repository=overrides.graph_repository,  # type: ignore[arg-type]
            eligibility_service=overrides.eligibility_service,  # type: ignore[arg-type]
            evidence_repository=overrides.evidence_repository,  # type: ignore[arg-type]
            source_refresh_service=overrides.source_refresh_service,  # type: ignore[arg-type]
        )

    # Default SQLite path
    resolved_db_path = db_path if db_path is not None else _DEFAULT_DB_PATH

    # Validate SQLite availability and schema (Req 1.3, 1.4)
    _validate_sqlite(resolved_db_path)

    # Build real adapters
    connection_factory = _make_connection_factory(resolved_db_path)

    graph_repository: EntitlementGraphRepository
    eligibility_service: EligibilityService
    evidence_repository: EvidenceRepository
    source_refresh_service: SourceRefreshService

    # Use override if provided, otherwise build from SQLite
    if overrides is not None and overrides.graph_repository is not None:
        graph_repository = overrides.graph_repository
    else:
        graph_repository = SqliteEntitlementGraphRepository(connection_factory)

    if overrides is not None and overrides.evidence_repository is not None:
        evidence_repository = overrides.evidence_repository
    else:
        evidence_repository = SqliteEvidenceRepository(connection_factory)

    if overrides is not None and overrides.source_refresh_service is not None:
        source_refresh_service = overrides.source_refresh_service
    else:
        source_refresh_service = SqliteSourceRefreshService(connection_factory)

    if overrides is not None and overrides.eligibility_service is not None:
        eligibility_service = overrides.eligibility_service
    else:
        # Build eligibility service from SQLite rule repo + evidence repo
        rule_repository = SqliteRuleRepository(connection_factory)
        eligibility_service = DeterministicEligibilityService(
            rule_repository=rule_repository,
            evidence_repository=evidence_repository,
        )

    # Final validation: all dependencies must be present
    _validate_all_present(
        graph_repository=graph_repository,
        eligibility_service=eligibility_service,
        evidence_repository=evidence_repository,
        source_refresh_service=source_refresh_service,
    )

    return ApplicationDependencies(
        graph_repository=graph_repository,
        eligibility_service=eligibility_service,
        evidence_repository=evidence_repository,
        source_refresh_service=source_refresh_service,
    )


def _all_overrides_present(overrides: ApplicationOverrides) -> bool:
    """Return True if every override slot is filled."""
    return (
        overrides.graph_repository is not None
        and overrides.eligibility_service is not None
        and overrides.evidence_repository is not None
        and overrides.source_refresh_service is not None
    )


def _validate_all_present(
    *,
    graph_repository: EntitlementGraphRepository | None,
    eligibility_service: EligibilityService | None,
    evidence_repository: EvidenceRepository | None,
    source_refresh_service: SourceRefreshService | None,
) -> None:
    """Raise if any required dependency is missing (Req 2.10)."""
    if graph_repository is None:
        raise DependencyConfigurationError("graph_repository")
    if eligibility_service is None:
        raise DependencyConfigurationError("eligibility_service")
    if evidence_repository is None:
        raise DependencyConfigurationError("evidence_repository")
    if source_refresh_service is None:
        raise DependencyConfigurationError("source_refresh_service")
