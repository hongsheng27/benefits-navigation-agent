"""Owner-aware API response mapper.

Produces API-safe response shapes from workflow state, applying:

- Privacy: requesting user sees `actual` values;
  non-requesting users do not (Req 9.1, 9.2).
- Relevance score omission: NEVER exposes relevance_score
  or derived values (Req 8.7, 8.8).
- Additive compatibility: maintains legacy `decisiveConditions`
  AND new `structuredReasons`.
- Program status: includes `programStatus` on each item view
  (Req 7.3–7.6).
- Optional dates: includes `effective_at`, `retrieved_at` on
  citations when present (Req 10.3, 10.4).
- Publisher name alias: `publisherName` camelCase convention.

Requirements: 3.10–3.15, 7.3–7.6, 8.7, 8.8, 9.1, 9.2, 10.2–10.4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.coverage_tracker import assert_no_completeness_claims
from app.orchestration import data_contracts as dc
from app.orchestration import state
from app.orchestration.protocols import CoverageSnapshot
from app.schemas.session import (
    CitationView,
    CoverageSourceView,
    CoverageView,
    DecisiveConditionView,
    ItemView,
    StructuredReasonView,
)

if TYPE_CHECKING:
    pass


def _map_citation_to_view(
    citation: state.Citation,
    domain_citation: dc.Citation | None = None,
) -> CitationView:
    """Map state.Citation to CitationView, optionally enriching with domain dates.

    If a matching domain_citation is available, its effective_at and retrieved_at
    are included. Otherwise those fields remain None.
    """
    effective_at: str | None = None
    retrieved_at: str | None = None

    if domain_citation is not None:
        if domain_citation.effective_at is not None:
            effective_at = domain_citation.effective_at.isoformat()
        if domain_citation.retrieved_at is not None:
            retrieved_at = domain_citation.retrieved_at.isoformat()

    return CitationView(
        document_id=citation.document_id,
        title=citation.title,
        publisher_name=citation.publisher_name,
        published_at=citation.published_at,
        url=citation.url,
        excerpt=citation.excerpt,
        effective_at=effective_at,
        retrieved_at=retrieved_at,
    )


def _map_structured_reason_to_view(
    reason: dc.StructuredReason,
    *,
    is_requesting_user: bool,
) -> StructuredReasonView:
    """Map a StructuredReason to API view, respecting privacy.

    For requesting users: `actual` is included as string.
    For non-requesting users: `actual` is removed (set to None).
    """
    actual: str | None = None
    if is_requesting_user and reason.actual is not None:
        actual = str(reason.actual)

    return StructuredReasonView(
        condition_id=reason.condition_id,
        field_id=reason.field_id,
        operator=reason.operator,
        expected=str(reason.expected),
        actual=actual,
        label=reason.label,
        source_reference=reason.source_reference,
    )


def _map_decisive_condition_view(
    condition: state.DecisiveCondition,
    *,
    is_requesting_user: bool,
) -> DecisiveConditionView:
    """Map DecisiveCondition to view, respecting privacy for `actual`.

    For requesting users: `actual` is included.
    For non-requesting users: `actual` is replaced with empty string.
    """
    actual = condition.actual if is_requesting_user else ""
    return DecisiveConditionView(
        field_id=condition.field_id,
        expected=condition.expected,
        actual=actual,
    )


def map_item_to_api_view(
    item: state.CandidateItem,
    *,
    is_requesting_user: bool,
    domain_reasons: tuple[dc.StructuredReason, ...] = (),
    domain_citations: tuple[dc.Citation, ...] = (),
) -> ItemView:
    """Map a workflow CandidateItem to an API ItemView.

    This mapper:
    - NEVER includes relevance_score (it doesn't exist on state.CandidateItem).
    - Includes program_status for frontend display.
    - Maps decisive_conditions with privacy-aware actual handling.
    - Maps structured_reasons with privacy-aware actual handling.
    - Maps citations with optional dates from domain citations.
    - Preserves amount quartet.

    Args:
        item: The workflow-side candidate item.
        is_requesting_user: True if the response recipient is
            the requesting user.
        domain_reasons: Optional StructuredReason instances for
            richer structured_reasons.
        domain_citations: Optional domain Citations for enriched
            date fields.

    Returns:
        An API-safe ItemView.
    """
    # Legacy decisive conditions with privacy
    decisive_conditions = tuple(
        _map_decisive_condition_view(c, is_requesting_user=is_requesting_user)
        for c in item.decisive_conditions
    )

    # New structured reasons with privacy
    structured_reasons = tuple(
        _map_structured_reason_to_view(r, is_requesting_user=is_requesting_user)
        for r in domain_reasons
    )

    # Citations: match domain citations by document_id for enriched dates
    domain_citation_map: dict[str, dc.Citation] = {
        c.document_id: c for c in domain_citations
    }
    citations = tuple(
        _map_citation_to_view(
            c,
            domain_citation=domain_citation_map.get(c.document_id),
        )
        for c in item.citations
    )

    return ItemView(
        item_id=item.item_id,
        kind=item.kind,
        status=item.status,
        program_status=item.program_status,
        missing_field_ids=item.missing_field_ids,
        decisive_conditions=decisive_conditions,
        structured_reasons=structured_reasons,
        citations=citations,
        amount_min=item.amount_min,
        amount_max=item.amount_max,
        amount_period=item.amount_period,
        amount_currency=item.amount_currency,
        explanation=item.explanation,
    )


def map_to_api_response(
    items: tuple[state.CandidateItem, ...],
    *,
    is_requesting_user: bool,
    domain_reasons_by_item: dict[str, tuple[dc.StructuredReason, ...]] | None = None,
    domain_citations_by_item: dict[str, tuple[dc.Citation, ...]] | None = None,
) -> tuple[ItemView, ...]:
    """Map a collection of workflow items to API-safe ItemViews.

    This is the top-level entry point for the response mapper.
    Relevance score is structurally absent from both input and output.

    Args:
        items: Workflow candidate items from SessionState.
        is_requesting_user: True if recipient is the requesting user.
        domain_reasons_by_item: Optional dict of item_id → StructuredReason tuples.
        domain_citations_by_item: Optional dict of item_id → domain Citation tuples.

    Returns:
        Tuple of ItemView instances safe for API serialization.
    """
    reasons_map = domain_reasons_by_item or {}
    citations_map = domain_citations_by_item or {}

    return tuple(
        map_item_to_api_view(
            item,
            is_requesting_user=is_requesting_user,
            domain_reasons=reasons_map.get(item.item_id, ()),
            domain_citations=citations_map.get(item.item_id, ()),
        )
        for item in items
    )


# ---------------------------------------------------------------------------
# Coverage mapping (Req 12.1–12.13)
# ---------------------------------------------------------------------------


def _map_coverage_source_to_view(source: dc.CoverageMetadata) -> CoverageSourceView:
    """Map one source's measurable progress to its API view.

    `last_crawled_at` is the last *successful* crawl and is carried through
    unchanged even when the source is currently in error. Clearing it would
    turn "worked yesterday, broken today" into "never worked" (Req 12.12).
    """
    last_crawled_at: str | None = None
    if source.last_crawled_at is not None:
        last_crawled_at = source.last_crawled_at.isoformat()

    return CoverageSourceView(
        source_id=source.source_id,
        crawl_status=source.crawl_status,
        last_crawled_at=last_crawled_at,
        indexed_document_count=source.indexed_document_count,
        domain_tags=tuple(source.domain_tags),
    )


def map_coverage_to_api_view(snapshot: CoverageSnapshot) -> CoverageView:
    """Map a CoverageSnapshot to an API-safe CoverageView.

    This mapper states observable progress only:

    - Every count comes straight from the snapshot, which already enforces
      `registered == crawled + pending + error` and
      `indexed_total == sum(per-source indexed)` (Req 12.1–12.3).
    - Only sources inside the requested scope appear, because the snapshot
      itself rejects out-of-scope entries (Req 12.10).
    - `gap_categories` is preserved rather than summarised away (Req 12.6).
    - No completeness ratio, coverage percentage, or "all indexed" flag is
      produced, because there is no denominator for any of them (Req 12.7,
      12.8).
    """
    return CoverageView(
        observed_at=snapshot.observed_at.isoformat(),
        scope_source_ids=tuple(snapshot.scope.source_ids),
        scope_domain_tags=tuple(snapshot.scope.domain_tags),
        registered_source_count=snapshot.registered_source_count,
        crawled_source_count=snapshot.crawled_source_count,
        pending_crawl_source_count=snapshot.pending_crawl_source_count,
        error_source_count=snapshot.error_source_count,
        indexed_document_count=snapshot.indexed_document_count,
        gap_categories=tuple(snapshot.gap_categories),
        sources=tuple(_map_coverage_source_to_view(s) for s in snapshot.sources),
    )


def coverage_summary_text(snapshot: CoverageSnapshot) -> str:
    """A one-line, claim-free summary of a coverage snapshot.

    The text is checked against the forbidden-claim vocabulary before it is
    returned, so a future edit that reintroduces "完整" or "all indexed" fails
    here rather than in front of a user (Req 12.6–12.8).
    """
    parts = [
        f"觀測時間 {snapshot.observed_at.isoformat()}",
        f"登記來源 {snapshot.registered_source_count}",
        f"已抓取 {snapshot.crawled_source_count}",
        f"待抓取 {snapshot.pending_crawl_source_count}",
        f"錯誤 {snapshot.error_source_count}",
        f"已索引文件 {snapshot.indexed_document_count}",
    ]
    if snapshot.gap_categories:
        parts.append("已知缺口 " + "、".join(snapshot.gap_categories))
    text = "；".join(parts)
    assert_no_completeness_claims(text)
    return text
