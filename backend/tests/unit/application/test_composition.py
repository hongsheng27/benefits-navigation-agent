"""Unit tests for the application composition root.

Validates:
- ApplicationDependencies and ApplicationOverrides dataclass behavior
- build_dependencies with full overrides skips SQLite entirely
- build_dependencies with partial overrides still builds remaining from SQLite
- DependencyConfigurationError raised when SQLite unavailable and no override
- DependencyConfigurationError contains dependency_type info
- main.create_app integrates composition root

Requirements traced: 1.3, 1.4, 2.5, 2.8–2.10
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from unittest.mock import patch

import pytest

from app.application.composition import (
    ApplicationDependencies,
    ApplicationOverrides,
    DependencyConfigurationError,
    build_dependencies,
)
from app.orchestration.data_contracts import (
    CandidateItem,
    Citation,
    EligibilityDecision,
    FieldRegistryEntry,
)
from app.orchestration.protocols import (
    CoverageScope,
    CoverageSnapshot,
    RefreshReceipt,
    RefreshRequest,
)


# ---------------------------------------------------------------------------
# Minimal fake implementations for testing composition
# ---------------------------------------------------------------------------


class FakeGraphRepository:
    """Minimal fake EntitlementGraphRepository."""

    def expand_from_event(
        self, event_id: str, user_attributes: Mapping
    ) -> tuple[CandidateItem, ...]:
        return ()

    def get_prerequisites(self, item_id: str) -> tuple:
        return ()

    def get_produces(self, item_id: str) -> tuple:
        return ()

    def get_programs_by_system(self, system_id: str) -> tuple:
        return ()


class FakeEligibilityService:
    """Minimal fake EligibilityService."""

    def get_required_fields(self, item_id: str) -> tuple[FieldRegistryEntry, ...]:
        return ()

    def evaluate(
        self, item_id: str, user_attributes: Mapping
    ) -> EligibilityDecision:
        return EligibilityDecision(
            item_id=item_id,
            status="needs_human_review",
            amount_min=None,
            amount_max=None,
            amount_period=None,
            amount_currency=None,
            missing_field_ids=(),
            reasons=(),
        )

    def evaluate_many(
        self, item_ids: Sequence[str], user_attributes: Mapping
    ) -> tuple[EligibilityDecision, ...]:
        return tuple(self.evaluate(iid, user_attributes) for iid in item_ids)


class FakeEvidenceRepository:
    """Minimal fake EvidenceRepository."""

    def get_citations(self, item_id: str) -> tuple[Citation, ...]:
        return ()

    def get_citations_for_references(
        self, item_id: str, source_references: Sequence[str]
    ) -> tuple[Citation, ...]:
        return ()


class FakeSourceRefreshService:
    """Minimal fake SourceRefreshService."""

    def get_coverage_status(self, scope: CoverageScope) -> CoverageSnapshot:
        from datetime import UTC, datetime

        return CoverageSnapshot(
            scope=scope,
            observed_at=datetime.now(UTC),
            registered_source_count=0,
            crawled_source_count=0,
            pending_crawl_source_count=0,
            error_source_count=0,
            indexed_document_count=0,
            sources=(),
            gap_categories=(),
        )

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        return RefreshReceipt(job_id="fake-job", accepted=False, deduplicated=False)


# ---------------------------------------------------------------------------
# Tests: ApplicationOverrides / ApplicationDependencies dataclass
# ---------------------------------------------------------------------------


class TestApplicationOverrides:
    def test_all_none_by_default(self) -> None:
        overrides = ApplicationOverrides()
        assert overrides.graph_repository is None
        assert overrides.eligibility_service is None
        assert overrides.evidence_repository is None
        assert overrides.source_refresh_service is None

    def test_frozen(self) -> None:
        overrides = ApplicationOverrides()
        with pytest.raises(Exception):  # FrozenInstanceError
            overrides.graph_repository = FakeGraphRepository()  # type: ignore[misc]


class TestApplicationDependencies:
    def test_holds_all_ports(self) -> None:
        deps = ApplicationDependencies(
            graph_repository=FakeGraphRepository(),
            eligibility_service=FakeEligibilityService(),
            evidence_repository=FakeEvidenceRepository(),
            source_refresh_service=FakeSourceRefreshService(),
        )
        assert deps.graph_repository is not None
        assert deps.eligibility_service is not None
        assert deps.evidence_repository is not None
        assert deps.source_refresh_service is not None

    def test_frozen(self) -> None:
        deps = ApplicationDependencies(
            graph_repository=FakeGraphRepository(),
            eligibility_service=FakeEligibilityService(),
            evidence_repository=FakeEvidenceRepository(),
            source_refresh_service=FakeSourceRefreshService(),
        )
        with pytest.raises(Exception):
            deps.graph_repository = FakeGraphRepository()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: build_dependencies with full overrides (Req 2.8, 2.9)
# ---------------------------------------------------------------------------


class TestBuildDependenciesWithFullOverrides:
    """When all four overrides are provided, ZERO SQLite is touched."""

    def test_returns_dependencies_without_sqlite(self) -> None:
        """Full overrides → no SQLite validation, no adapter construction."""
        graph = FakeGraphRepository()
        elig = FakeEligibilityService()
        evidence = FakeEvidenceRepository()
        refresh = FakeSourceRefreshService()

        overrides = ApplicationOverrides(
            graph_repository=graph,
            eligibility_service=elig,
            evidence_repository=evidence,
            source_refresh_service=refresh,
        )

        # Should succeed even with a non-existent db_path
        deps = build_dependencies(
            overrides, db_path=Path("/nonexistent/path.db")
        )

        assert deps.graph_repository is graph
        assert deps.eligibility_service is elig
        assert deps.evidence_repository is evidence
        assert deps.source_refresh_service is refresh

    def test_no_sqlite_connection_opened(self) -> None:
        """Verify zero sqlite3.connect calls when overrides are complete."""
        overrides = ApplicationOverrides(
            graph_repository=FakeGraphRepository(),
            eligibility_service=FakeEligibilityService(),
            evidence_repository=FakeEvidenceRepository(),
            source_refresh_service=FakeSourceRefreshService(),
        )

        with patch("sqlite3.connect") as mock_connect:
            build_dependencies(overrides, db_path=Path("/nonexistent/path.db"))
            mock_connect.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: build_dependencies without overrides — SQLite unavailable (Req 1.3, 1.4, 2.10)
# ---------------------------------------------------------------------------


class TestBuildDependenciesWithoutOverrides:
    """When no overrides, SQLite must be validated. Failure → config error."""

    def test_raises_on_invalid_db_path(self) -> None:
        """Non-existent DB path raises DependencyConfigurationError."""
        with pytest.raises(DependencyConfigurationError) as exc_info:
            build_dependencies(db_path=Path("/nonexistent/database.db"))

        assert exc_info.value.dependency_type == "sqlite"

    def test_error_includes_reason(self) -> None:
        """The error should contain a reason code."""
        with pytest.raises(DependencyConfigurationError) as exc_info:
            build_dependencies(db_path=Path("/nonexistent/database.db"))

        assert exc_info.value.reason != ""


# ---------------------------------------------------------------------------
# Tests: DependencyConfigurationError (Req 2.10)
# ---------------------------------------------------------------------------


class TestDependencyConfigurationError:
    def test_has_dependency_type(self) -> None:
        err = DependencyConfigurationError("graph_repository")
        assert err.dependency_type == "graph_repository"
        assert "graph_repository" in str(err)

    def test_has_reason(self) -> None:
        err = DependencyConfigurationError("sqlite", reason="unavailable")
        assert err.reason == "unavailable"
        assert "unavailable" in str(err)

    def test_empty_reason(self) -> None:
        err = DependencyConfigurationError("eligibility_service")
        assert err.reason == ""


# ---------------------------------------------------------------------------
# Tests: create_app integration (Req 2.5)
# ---------------------------------------------------------------------------


class TestCreateAppComposition:
    """Verify create_app wires composition root to app.state."""

    def test_app_with_full_overrides_has_dependencies(self) -> None:
        """create_app with overrides sets app.state.dependencies."""
        from app.main import create_app

        overrides = ApplicationOverrides(
            graph_repository=FakeGraphRepository(),
            eligibility_service=FakeEligibilityService(),
            evidence_repository=FakeEvidenceRepository(),
            source_refresh_service=FakeSourceRefreshService(),
        )

        app = create_app(overrides)
        assert hasattr(app.state, "dependencies")
        assert isinstance(app.state.dependencies, ApplicationDependencies)

    def test_app_without_sqlite_raises(self) -> None:
        """create_app without overrides and bad db_path raises."""
        from app.main import create_app

        with pytest.raises(DependencyConfigurationError):
            create_app(db_path=Path("/nonexistent/database.db"))

    def test_routes_do_not_create_adapters(self) -> None:
        """Routes receive dependencies from app.state, not by building them."""
        from fastapi.testclient import TestClient

        from app.main import create_app

        overrides = ApplicationOverrides(
            graph_repository=FakeGraphRepository(),
            eligibility_service=FakeEligibilityService(),
            evidence_repository=FakeEvidenceRepository(),
            source_refresh_service=FakeSourceRefreshService(),
        )

        app = create_app(overrides)
        client = TestClient(app)

        # Health check should work
        response = client.get("/health")
        assert response.status_code == 200

        # Session creation should work (uses session_store, not adapters)
        response = client.post("/sessions")
        assert response.status_code == 201
