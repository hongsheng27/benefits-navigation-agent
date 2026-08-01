"""Domain→Workflow mapper: data_contracts → state CandidateItem.

Maps the boundary contract shapes (from the data/evidence layer) into the
workflow state shapes used by the state machine and session API.

Key invariants:
- `relevance_score` is NEVER included in output (Req 8.7, 8.8).
- `program_status` is preserved on the workflow CandidateItem (Req 7.3–7.6).
- `StructuredReason` → `DecisiveCondition` (legacy format) (Req 3.10–3.12).
- `data_contracts.Citation` → `state.Citation` with optional dates mapped.
- Amount quartet mapped as all-or-none (Req 3.13–3.15).
- `EligibilityDecision.status` → `state.ItemStatus`.

Requirements: 3.10–3.15, 7.3–7.6, 8.7, 8.8, 10.2–10.4.
"""

from __future__ import annotations

from app.orchestration import data_contracts as dc
from app.orchestration import state


def _map_eligibility_status(status: dc.EligibilityStatus) -> state.ItemStatus:
    """Map EligibilityStatus literal to workflow ItemStatus enum."""
    return state.ItemStatus(status)


def _map_structured_reason_to_decisive_condition(
    reason: dc.StructuredReason,
) -> state.DecisiveCondition:
    """Map a StructuredReason to the legacy DecisiveCondition format.

    StructuredReason.expected/actual are FrozenValue (recursive tuples, etc.).
    DecisiveCondition.expected/actual are AttributeValue (bool | int | str).
    We convert by taking the string representation for complex values.
    """
    expected = _frozen_value_to_attribute_value(reason.expected)
    actual = _frozen_value_to_attribute_value(reason.actual)
    return state.DecisiveCondition(
        field_id=reason.field_id,
        expected=expected,
        actual=actual,
    )


def _frozen_value_to_attribute_value(
    value: dc.FrozenValue,
) -> state.AttributeValue:
    """Convert a FrozenValue to AttributeValue (bool | int | str).

    Simple scalars pass through; complex types (tuples of pairs, None)
    are stringified for display in the legacy format.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    # For None, float, or complex tuple structures, stringify.
    return str(value)


def _map_citation(citation: dc.Citation) -> state.Citation:
    """Map data_contracts.Citation → state.Citation.

    The data_contracts version has datetime objects for dates;
    state.Citation stores published_at as str | None.
    effective_at and retrieved_at from data_contracts are mapped to the
    extended CitationView in the API layer, not stored in state.Citation.
    """
    published_at_str: str | None = None
    if citation.published_at is not None:
        published_at_str = citation.published_at.isoformat()

    return state.Citation(
        document_id=citation.document_id,
        title=citation.title,
        publisher_name=citation.publisher,
        published_at=published_at_str,
        url=citation.url,
        excerpt=citation.excerpt,
    )


def _map_amount_period(period: dc.AmountPeriod | None) -> state.AmountPeriod | None:
    """Map data_contracts AmountPeriod literal to state.AmountPeriod enum."""
    if period is None:
        return None
    return state.AmountPeriod(period)


def map_domain_to_workflow(
    candidate: dc.CandidateItem,
    decision: dc.EligibilityDecision | None = None,
) -> state.CandidateItem:
    """Map data_contracts.CandidateItem + optional EligibilityDecision.

    Maps to state.CandidateItem.

    This is the primary adapter between the data layer world and the workflow world.

    - `candidate.item_id` maps directly to `state.CandidateItem.item_id`.
    - `candidate.program_status` is preserved on the output.
    - `candidate.relevance_score` is NEVER included in output.
    - If `decision` is provided, its status, reasons, amounts, and missing_field_ids
      are mapped onto the workflow item.

    Args:
        candidate: The data layer candidate item.
        decision: Optional eligibility decision for this item.

    Returns:
        A workflow-side CandidateItem suitable for SessionState.items.
    """
    # Determine item kind — the data layer doesn't carry ItemKind,
    # so we default to BENEFIT (the caller/graph can override).
    kind = state.ItemKind.BENEFIT

    if decision is None:
        # No decision yet → pending item with program_status preserved
        return state.CandidateItem(
            item_id=candidate.item_id,
            kind=kind,
            status=state.ItemStatus.PENDING,
            program_status=candidate.program_status,
            missing_field_ids=candidate.missing_field_ids,
        )

    # Map decision fields
    status = _map_eligibility_status(decision.status)
    decisive_conditions = tuple(
        _map_structured_reason_to_decisive_condition(r) for r in decision.reasons
    )
    missing_field_ids = decision.missing_field_ids

    # Map citations from the data layer candidate (not from decision)
    # Decision doesn't carry citations; they come from the evidence layer
    # and are attached separately. For now, leave citations empty
    # (they are populated by the evidence retrieval step).
    citations: tuple[state.Citation, ...] = ()

    # Amount quartet from decision
    amount_min = decision.amount_min
    amount_max = decision.amount_max
    amount_period = _map_amount_period(decision.amount_period)
    amount_currency = decision.amount_currency

    return state.CandidateItem(
        item_id=candidate.item_id,
        kind=kind,
        status=status,
        program_status=candidate.program_status,
        missing_field_ids=missing_field_ids,
        decisive_conditions=decisive_conditions,
        citations=citations,
        amount_min=amount_min,
        amount_max=amount_max,
        amount_period=amount_period,
        amount_currency=amount_currency,
    )


def map_domain_citations_to_workflow(
    citations: tuple[dc.Citation, ...],
) -> tuple[state.Citation, ...]:
    """Map a sequence of data_contracts.Citation to state.Citation tuple.

    This is used when attaching evidence to a workflow CandidateItem
    after the evidence retrieval step.
    """
    return tuple(_map_citation(c) for c in citations)
