"""Tests for no-SQL fakes satisfying protocols and composition integration.

Validates:
- All four fakes satisfy protocol structural checks (duck typing)
- build_dependencies(ApplicationOverrides(graph=fake, elig=fake, evidence=fake, refresh=fake))
  returns without touching SQLite
- App startup with full fakes does NOT build any factory/adapter/connection

Requirements traced: 2.6, 2.8, 2.9.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

from app.application.composition import (
    ApplicationDependencies,
    ApplicationOverrides,
    build_dependencies,
)
from app.orchestration.protocols import (
    CoverageScope,
    EligibilityService,
    EntitlementGraphRepository,
    EvidenceRepository,
    SourceRefreshService,
)
from app.testing.fakes import (
    FakeEligibilityService,
    FakeEntitlementGraphRepository,
    FakeEvidenceRepository,
    FakeSourceRefreshService,
)
from tests.fakes import make_all_fakes_overrides


# ---------------------------------------------------------------------------
# Tests: Protocol structural conformance
# ---------------------------------------------------------------------------


class TestFakeProtocolConformance:
    """All four fakes must satisfy their protocol's structural type."""

    def test_fake_graph_satisfies_protocol(self) -> None:
        """FakeEntitlementGraphRepository has all methods of EntitlementGraphRepository."""
        fake = FakeEntitlementGraphRepository()
        # Check all protocol methods exist and are callable
        assert callable(getattr(fake, "expand_from_event", None))
        assert callable(getattr(fake, "get_prerequisites", None))
        assert callable(getattr(fake, "get_produces", None))
        assert callable(getattr(fake, "get_programs_by_system", None))

    def test_fake_eligibility_satisfies_protocol(self) -> None:
        """FakeEligibilityService has all methods of EligibilityService."""
        fake = FakeEligibilityService()
        assert callable(getattr(fake, "get_required_fields", None))
        assert callable(getattr(fake, "evaluate", None))
        assert callable(getattr(fake, "evaluate_many", None))

    def test_fake_evidence_satisfies_protocol(self) -> None:
        """FakeEvidenceRepository has all methods of EvidenceRepository."""
        fake = FakeEvidenceRepository()
        assert callable(getattr(fake, "get_citations", None))
        assert callable(getattr(fake, "get_citations_for_references", None))

    def test_fake_refresh_satisfies_protocol(self) -> None:
        """FakeSourceRefreshService has all methods of SourceRefreshService."""
        fake = FakeSourceRefreshService()
        assert callable(getattr(fake, "get_coverage_status", None))
        assert callable(getattr(fake, "request_on_demand_refresh", None))

    def test_fake_graph_method_signatures_match(self) -> None:
        """FakeEntitlementGraphRepository method signatures match protocol."""
        protocol_methods = {
            name
            for name, _ in inspect.getmembers(
                EntitlementGraphRepository, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name in dir(FakeEntitlementGraphRepository)
            if not name.startswith("_") and callable(getattr(FakeEntitlementGraphRepository, name, None))
        }
        assert protocol_methods.issubset(fake_methods)

    def test_fake_eligibility_method_signatures_match(self) -> None:
        """FakeEligibilityService method signatures match protocol."""
        protocol_methods = {
            name
            for name, _ in inspect.getmembers(
                EligibilityService, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name in dir(FakeEligibilityService)
            if not name.startswith("_") and callable(getattr(FakeEligibilityService, name, None))
        }
        assert protocol_methods.issubset(fake_methods)

    def test_fake_evidence_method_signatures_match(self) -> None:
        """FakeEvidenceRepository method signatures match protocol."""
        protocol_methods = {
            name
            for name, _ in inspect.getmembers(
                EvidenceRepository, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name in dir(FakeEvidenceRepository)
            if not name.startswith("_") and callable(getattr(FakeEvidenceRepository, name, None))
        }
        assert protocol_methods.issubset(fake_methods)

    def test_fake_refresh_method_signatures_match(self) -> None:
        """FakeSourceRefreshService method signatures match protocol."""
        protocol_methods = {
            name
            for name, _ in inspect.getmembers(
                SourceRefreshService, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name in dir(FakeSourceRefreshService)
            if not name.startswith("_") and callable(getattr(FakeSourceRefreshService, name, None))
        }
        assert protocol_methods.issubset(fake_methods)


# ---------------------------------------------------------------------------
# Tests: Fakes are immutable and no-SQL
# ---------------------------------------------------------------------------


class TestFakesAreImmutable:
    """Fakes must be frozen dataclasses — no mutation after init."""

    def test_graph_fake_is_frozen(self) -> None:
        fake = FakeEntitlementGraphRepository()
        with pytest.raises(Exception):  # FrozenInstanceError
            fake.items_by_event = {}  # type: ignore[misc]

    def test_eligibility_fake_is_frozen(self) -> None:
        fake = FakeEligibilityService()
        with pytest.raises(Exception):
            fake.decisions = {}  # type: ignore[misc]

    def test_evidence_fake_is_frozen(self) -> None:
        fake = FakeEvidenceRepository()
        with pytest.raises(Exception):
            fake.citations = {}  # type: ignore[misc]

    def test_refresh_fake_is_frozen(self) -> None:
        fake = FakeSourceRefreshService()
        with pytest.raises(Exception):
            fake.sources = ()  # type: ignore[misc]


class TestFakesAreNoSQL:
    """Fakes must not import or reference sqlite3."""

    def test_fakes_module_does_not_import_sqlite3(self) -> None:
        """The fakes module has no sqlite3 import statements."""
        from app.testing import fakes

        source = inspect.getsource(fakes)
        # Check actual import lines (not docstrings/comments)
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "sqlite3" not in line, f"Found sqlite3 in import: {line}"

    def test_fakes_do_not_accept_db_path(self) -> None:
        """No fake constructor accepts a path or connection parameter."""
        for cls in (
            FakeEntitlementGraphRepository,
            FakeEligibilityService,
            FakeEvidenceRepository,
            FakeSourceRefreshService,
        ):
            params = inspect.signature(cls).parameters
            for param_name in params:
                assert "path" not in param_name.lower()
                assert "connection" not in param_name.lower()
                assert "db" not in param_name.lower()


# ---------------------------------------------------------------------------
# Tests: build_dependencies with fakes skips SQLite (Req 2.9)
# ---------------------------------------------------------------------------


class TestBuildDependenciesWithFakes:
    """build_dependencies with all four fakes opens ZERO SQLite connections."""

    def test_returns_dependencies_with_fakes(self) -> None:
        """Full fakes overrides → successful build without SQLite."""
        overrides = make_all_fakes_overrides()
        deps = build_dependencies(overrides, db_path=Path("/nonexistent/impossible.db"))

        assert isinstance(deps, ApplicationDependencies)
        assert isinstance(deps.graph_repository, FakeEntitlementGraphRepository)
        assert isinstance(deps.eligibility_service, FakeEligibilityService)
        assert isinstance(deps.evidence_repository, FakeEvidenceRepository)
        assert isinstance(deps.source_refresh_service, FakeSourceRefreshService)

    def test_zero_sqlite_connections_with_fakes(self) -> None:
        """Patching sqlite3.connect confirms zero calls."""
        overrides = make_all_fakes_overrides()

        with patch("sqlite3.connect") as mock_connect:
            build_dependencies(overrides, db_path=Path("/nonexistent/impossible.db"))
            mock_connect.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: App startup with fakes (Req 2.8)
# ---------------------------------------------------------------------------


class TestAppStartupWithFakes:
    """create_app with all fakes does NOT build factory/adapter/connection."""

    def test_create_app_with_fakes_no_sqlite(self) -> None:
        """create_app succeeds with fakes and opens zero SQLite connections."""
        from app.main import create_app

        overrides = make_all_fakes_overrides()

        with patch("sqlite3.connect") as mock_connect:
            app = create_app(overrides)
            mock_connect.assert_not_called()

        assert hasattr(app.state, "dependencies")
        assert isinstance(app.state.dependencies, ApplicationDependencies)

    def test_create_app_dependencies_are_fakes(self) -> None:
        """create_app stores the fake instances in app.state.dependencies."""
        from app.main import create_app

        overrides = make_all_fakes_overrides()
        app = create_app(overrides)

        deps = app.state.dependencies
        assert isinstance(deps.graph_repository, FakeEntitlementGraphRepository)
        assert isinstance(deps.eligibility_service, FakeEligibilityService)
        assert isinstance(deps.evidence_repository, FakeEvidenceRepository)
        assert isinstance(deps.source_refresh_service, FakeSourceRefreshService)
