"""Test convenience module: re-exports immutable no-SQL fakes and builders.

Test authors import from here rather than reaching into app.testing.fakes
directly, keeping test imports stable if the internal path changes.

Usage:
    from tests.fakes import (
        FakeEntitlementGraphRepository,
        FakeEligibilityService,
        FakeEvidenceRepository,
        FakeSourceRefreshService,
        make_candidate_item,
        make_all_fakes_overrides,
    )
"""

from __future__ import annotations

from app.application.composition import ApplicationOverrides
from app.orchestration.data_contracts import CandidateItem, GraphRelation
from app.testing.fakes import (
    FakeEligibilityService,
    FakeEntitlementGraphRepository,
    FakeEvidenceRepository,
    FakeSourceRefreshService,
)

__all__ = [
    "FakeEntitlementGraphRepository",
    "FakeEligibilityService",
    "FakeEvidenceRepository",
    "FakeSourceRefreshService",
    "make_candidate_item",
    "make_all_fakes_overrides",
]


def make_candidate_item(
    item_id: str = "test_item",
    display_name: str = "Test Item",
    program_status: str = "candidate",
    relevance_score: int | float | None = None,
    missing_field_ids: tuple[str, ...] = (),
    prerequisites: tuple[GraphRelation, ...] = (),
    produces: tuple[GraphRelation, ...] = (),
) -> CandidateItem:
    """Build a CandidateItem with sensible defaults for testing."""
    return CandidateItem(
        item_id=item_id,
        display_name=display_name,
        program_status=program_status,
        relevance_score=relevance_score,
        missing_field_ids=missing_field_ids,
        prerequisites=prerequisites,
        produces=produces,
    )


def make_all_fakes_overrides(
    *,
    graph: FakeEntitlementGraphRepository | None = None,
    eligibility: FakeEligibilityService | None = None,
    evidence: FakeEvidenceRepository | None = None,
    refresh: FakeSourceRefreshService | None = None,
) -> ApplicationOverrides:
    """Build ApplicationOverrides with all four fakes populated.

    If a specific fake is not provided, a default empty instance is used.
    Guarantees that all four ports are non-None so build_dependencies()
    will NOT open any SQLite connection.
    """
    return ApplicationOverrides(
        graph_repository=graph or FakeEntitlementGraphRepository(),
        eligibility_service=eligibility or FakeEligibilityService(),
        evidence_repository=evidence or FakeEvidenceRepository(),
        source_refresh_service=refresh or FakeSourceRefreshService(),
    )
