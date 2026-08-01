"""Immutable no-SQL fakes for structured testing.

These fakes satisfy the four orchestration protocols without importing any
database module, constructing any connection object, or accepting a DB path.
They accept ONLY frozen in-memory data (tuples, frozen dataclasses) at
construction time and expose no mutation methods.

Distinction from `protocols.py` fixture implementations:
- Fixture implementations (e.g. FixtureEntitlementGraphRepository) are
  offline fixtures for development with hardcoded MVP scenario data.
- These fakes are for structured testing: they accept arbitrary immutable
  data supplied by the test author, enabling scenario composition.

Requirements traced: 2.6, 2.8, 2.9.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.orchestration.data_contracts import (
    CandidateItem,
    Citation,
    CoverageMetadata,
    EligibilityDecision,
    FieldRegistryEntry,
    GraphRelation,
)
from app.orchestration.protocols import (
    CoverageScope,
    CoverageSnapshot,
    RefreshReceipt,
    RefreshRequest,
)


# ---------------------------------------------------------------------------
# Fake 1: EntitlementGraphRepository
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeEntitlementGraphRepository:
    """Immutable no-SQL fake for EntitlementGraphRepository.

    Accepts frozen tuples of CandidateItem keyed by event_id. All data must
    be provided at construction time; no mutation after init.
    """

    items_by_event: Mapping[str, tuple[CandidateItem, ...]] = ()  # type: ignore[assignment]
    items_by_system: Mapping[str, tuple[CandidateItem, ...]] = ()  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Normalize to dict for lookup, but keep frozen semantics
        if not isinstance(self.items_by_event, Mapping):
            object.__setattr__(self, "items_by_event", {})
        if not isinstance(self.items_by_system, Mapping):
            object.__setattr__(self, "items_by_system", {})

    def expand_from_event(
        self,
        event_id: str,
        user_attributes: Mapping,
    ) -> tuple[CandidateItem, ...]:
        """Return pre-configured items for the event, or empty tuple."""
        return self.items_by_event.get(event_id, ())

    def get_prerequisites(self, item_id: str) -> tuple[GraphRelation, ...]:
        """Return prerequisites from matched item, or empty tuple."""
        item = self._find(item_id)
        return item.prerequisites if item is not None else ()

    def get_produces(self, item_id: str) -> tuple[GraphRelation, ...]:
        """Return produces from matched item, or empty tuple."""
        item = self._find(item_id)
        return item.produces if item is not None else ()

    def get_programs_by_system(self, system_id: str) -> tuple[CandidateItem, ...]:
        """Return items for system, or empty tuple."""
        return self.items_by_system.get(system_id, ())

    def _find(self, item_id: str) -> CandidateItem | None:
        for items in self.items_by_event.values():
            for item in items:
                if item.item_id == item_id:
                    return item
        for items in self.items_by_system.values():
            for item in items:
                if item.item_id == item_id:
                    return item
        return None


# ---------------------------------------------------------------------------
# Fake 2: EligibilityService
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeEligibilityService:
    """Immutable no-SQL fake for EligibilityService.

    Accepts a frozen mapping of item_id -> EligibilityDecision and
    item_id -> tuple[FieldRegistryEntry, ...]. Items not in the mapping
    return needs_human_review (honest default).
    """

    decisions: Mapping[str, EligibilityDecision] = ()  # type: ignore[assignment]
    required_fields: Mapping[str, tuple[FieldRegistryEntry, ...]] = ()  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not isinstance(self.decisions, Mapping):
            object.__setattr__(self, "decisions", {})
        if not isinstance(self.required_fields, Mapping):
            object.__setattr__(self, "required_fields", {})

    def get_required_fields(self, item_id: str) -> tuple[FieldRegistryEntry, ...]:
        """Return required fields for item, or empty tuple."""
        return self.required_fields.get(item_id, ())

    def evaluate(
        self,
        item_id: str,
        user_attributes: Mapping,
    ) -> EligibilityDecision:
        """Return pre-configured decision, or needs_human_review."""
        decision = self.decisions.get(item_id)
        if decision is not None:
            return decision
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
        self,
        item_ids: Sequence[str],
        user_attributes: Mapping,
    ) -> tuple[EligibilityDecision, ...]:
        """Evaluate each item in order."""
        return tuple(self.evaluate(iid, user_attributes) for iid in item_ids)


# ---------------------------------------------------------------------------
# Fake 3: EvidenceRepository
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeEvidenceRepository:
    """Immutable no-SQL fake for EvidenceRepository.

    Accepts frozen mappings of citations. Empty by default (honest: no
    fabricated evidence).
    """

    citations: Mapping[str, tuple[Citation, ...]] = ()  # type: ignore[assignment]
    citations_by_reference: Mapping[tuple[str, str], tuple[Citation, ...]] = ()  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not isinstance(self.citations, Mapping):
            object.__setattr__(self, "citations", {})
        if not isinstance(self.citations_by_reference, Mapping):
            object.__setattr__(self, "citations_by_reference", {})

    def get_citations(self, item_id: str) -> tuple[Citation, ...]:
        """Return citations for item, or empty tuple."""
        return self.citations.get(item_id, ())

    def get_citations_for_references(
        self,
        item_id: str,
        source_references: Sequence[str],
    ) -> tuple[Citation, ...]:
        """Return citations matching source references, deduplicated."""
        results: list[Citation] = []
        seen: set[str] = set()
        for ref in source_references:
            for citation in self.citations_by_reference.get((item_id, ref), ()):
                if citation.document_id not in seen:
                    seen.add(citation.document_id)
                    results.append(citation)
        return tuple(results)


# ---------------------------------------------------------------------------
# Fake 4: SourceRefreshService
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeSourceRefreshService:
    """Immutable no-SQL fake for SourceRefreshService.

    Returns a deterministic empty coverage snapshot and never-accepted
    refresh receipts. No queue, no state mutation, no I/O.
    """

    sources: tuple[CoverageMetadata, ...] = ()

    def get_coverage_status(self, scope: CoverageScope) -> CoverageSnapshot:
        """Return a deterministic snapshot from pre-loaded sources."""
        now = datetime.now(UTC)
        # Filter sources by scope
        matched: list[CoverageMetadata] = []
        scoped_ids = frozenset(scope.source_ids)
        scoped_tags = frozenset(scope.domain_tags)

        for source in self.sources:
            if scoped_ids and source.source_id not in scoped_ids:
                continue
            if scoped_tags and not (scoped_tags & frozenset(source.domain_tags)):
                continue
            # Override observed_at to match snapshot time
            matched.append(
                CoverageMetadata(
                    source_id=source.source_id,
                    crawl_status=source.crawl_status,
                    last_crawled_at=source.last_crawled_at,
                    indexed_document_count=source.indexed_document_count,
                    domain_tags=source.domain_tags,
                    observed_at=now,
                )
            )

        sources_tuple = tuple(sorted(matched, key=lambda s: s.source_id))
        return CoverageSnapshot(
            scope=scope,
            observed_at=now,
            registered_source_count=len(sources_tuple),
            crawled_source_count=sum(
                1 for s in sources_tuple if s.crawl_status == "crawled"
            ),
            pending_crawl_source_count=sum(
                1 for s in sources_tuple if s.crawl_status == "pending_crawl"
            ),
            error_source_count=sum(
                1 for s in sources_tuple if s.crawl_status == "error"
            ),
            indexed_document_count=sum(
                s.indexed_document_count for s in sources_tuple
            ),
            sources=sources_tuple,
            gap_categories=(),
        )

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        """Always return not-accepted receipt. No side effects."""
        day = request.requested_at.date().isoformat()
        return RefreshReceipt(
            job_id=f"fake_refresh_{request.event_id}_{day}",
            accepted=False,
            deduplicated=False,
        )
