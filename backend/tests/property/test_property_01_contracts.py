"""Property 1: Immutable contracts and amount shape.

Validates Requirements 3.1–3.9, 3.13–3.15 using independent reference oracles.
Does not use production code to self-verify — each property defines its own
expected behavior independently.

Each @given test runs at least 100 examples (Hypothesis default).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.orchestration.data_contracts import (
    CandidateItem,
    Citation,
    CoverageMetadata,
    EligibilityDecision,
    FieldRegistryEntry,
    GraphRelation,
    StructuredReason,
    freeze_value,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)

_program_statuses = st.sampled_from(
    ["candidate", "under_review", "verified", "stale", "rejected", "inactive"]
)
_eligibility_statuses = st.sampled_from(
    ["eligible", "ineligible", "needs_information", "needs_human_review"]
)
_amount_periods = st.sampled_from(["one_time", "monthly", "annual"])


def _graph_relations() -> st.SearchStrategy[GraphRelation]:
    return st.builds(
        GraphRelation,
        target_id=st.text(min_size=1, max_size=20),
        display_name=st.text(min_size=1, max_size=30),
        canonical_order=st.integers(min_value=0, max_value=100),
    )


def _candidate_items() -> st.SearchStrategy[CandidateItem]:
    return st.builds(
        CandidateItem,
        item_id=st.text(min_size=1, max_size=20),
        display_name=st.text(min_size=1, max_size=30),
        program_status=_program_statuses,
        relevance_score=st.one_of(
            st.none(),
            st.integers(-100, 100),
            st.floats(-100.0, 100.0, allow_nan=False, allow_infinity=False),
        ),
        missing_field_ids=st.lists(st.text(min_size=1, max_size=10), max_size=5).map(
            tuple
        ),
        prerequisites=st.lists(_graph_relations(), max_size=3).map(tuple),
        produces=st.lists(_graph_relations(), max_size=3).map(tuple),
    )


def _frozen_values() -> st.SearchStrategy[object]:
    """Generate arbitrary JSON-like structures for freeze testing."""
    return st.recursive(
        st.one_of(
            st.none(),
            st.booleans(),
            st.integers(-1000, 1000),
            st.floats(-100.0, 100.0, allow_nan=False, allow_infinity=False),
            st.text(max_size=20),
        ),
        lambda children: st.one_of(
            st.lists(children, max_size=4),
            st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=4),
        ),
        max_leaves=15,
    )


def _structured_reasons() -> st.SearchStrategy[StructuredReason]:
    return st.builds(
        StructuredReason,
        condition_id=st.text(min_size=1, max_size=15),
        field_id=st.text(min_size=1, max_size=15),
        operator=st.sampled_from(["equals", "greater_than", "less_than", "in"]),
        expected=_frozen_values(),
        actual=_frozen_values(),
        label=st.text(min_size=1, max_size=30),
        source_reference=st.text(min_size=1, max_size=30),
    )


def _valid_amount_quartets() -> st.SearchStrategy[
    tuple[int | float | None, int | float | None, str | None, str | None]
]:
    """All-None or all-present with min <= max."""
    all_none = st.just((None, None, None, None))
    all_present = st.tuples(
        st.integers(0, 100000),
        st.integers(0, 100000),
        _amount_periods,
        st.just("TWD"),
    ).filter(lambda t: t[0] <= t[1])
    return st.one_of(all_none, all_present)


def _eligibility_decisions() -> st.SearchStrategy[EligibilityDecision]:
    return _valid_amount_quartets().flatmap(
        lambda amounts: st.builds(
            EligibilityDecision,
            item_id=st.text(min_size=1, max_size=20),
            status=_eligibility_statuses,
            amount_min=st.just(amounts[0]),
            amount_max=st.just(amounts[1]),
            amount_period=st.just(amounts[2]),
            amount_currency=st.just(amounts[3]),
            missing_field_ids=st.lists(
                st.text(min_size=1, max_size=10), max_size=5
            ).map(tuple),
            reasons=st.lists(_structured_reasons(), max_size=2).map(tuple),
        )
    )


def _citations() -> st.SearchStrategy[Citation]:
    return st.builds(
        Citation,
        document_id=st.text(min_size=1, max_size=20),
        title=st.text(min_size=1, max_size=30),
        publisher=st.text(min_size=1, max_size=30),
        published_at=st.one_of(st.none(), st.just(_NOW)),
        effective_at=st.one_of(st.none(), st.just(_NOW)),
        url=st.text(min_size=5, max_size=50),
        excerpt=st.text(min_size=1, max_size=50),
        retrieved_at=st.one_of(st.none(), st.just(_NOW)),
    )


def _field_entries() -> st.SearchStrategy[FieldRegistryEntry]:
    return st.builds(
        FieldRegistryEntry,
        field_id=st.text(min_size=1, max_size=20),
        data_type=st.sampled_from(
            ["text", "integer", "number", "boolean", "date", "enum"]
        ),
        allowed_values=st.lists(st.text(min_size=1, max_size=10), max_size=5).map(
            tuple
        ),
        prompt_label=st.text(min_size=1, max_size=30),
        why_needed=st.text(min_size=1, max_size=50),
        pii_classification=st.sampled_from(
            ["none", "eligibility_sensitive", "direct_identifier"]
        ),
    )


def _coverage_metadata() -> st.SearchStrategy[CoverageMetadata]:
    return st.builds(
        CoverageMetadata,
        source_id=st.text(min_size=1, max_size=20),
        crawl_status=st.sampled_from(["pending_crawl", "crawled", "error"]),
        last_crawled_at=st.one_of(st.none(), st.just(_NOW)),
        indexed_document_count=st.integers(min_value=0, max_value=10000),
        domain_tags=st.lists(st.text(min_size=1, max_size=10), max_size=5).map(tuple),
        observed_at=st.just(_NOW),
    )


# ---------------------------------------------------------------------------
# Property 1.1: All collection fields are never None and are always tuples
# ---------------------------------------------------------------------------


@given(instance=_candidate_items())
@settings(max_examples=200)
def test_candidate_item_collections_are_tuples(instance: CandidateItem) -> None:
    assert isinstance(instance.missing_field_ids, tuple)
    assert isinstance(instance.prerequisites, tuple)
    assert isinstance(instance.produces, tuple)


@given(instance=_eligibility_decisions())
@settings(max_examples=200)
def test_eligibility_decision_collections_are_tuples(
    instance: EligibilityDecision,
) -> None:
    assert isinstance(instance.missing_field_ids, tuple)
    assert isinstance(instance.reasons, tuple)


@given(instance=_field_entries())
@settings(max_examples=100)
def test_field_registry_entry_collections_are_tuples(
    instance: FieldRegistryEntry,
) -> None:
    assert isinstance(instance.allowed_values, tuple)


@given(instance=_coverage_metadata())
@settings(max_examples=100)
def test_coverage_metadata_collections_are_tuples(
    instance: CoverageMetadata,
) -> None:
    assert isinstance(instance.domain_tags, tuple)


# ---------------------------------------------------------------------------
# Property 1.2: Frozen contracts reject field reassignment
# ---------------------------------------------------------------------------


@given(instance=_candidate_items())
@settings(max_examples=100)
def test_candidate_item_is_frozen(instance: CandidateItem) -> None:
    for field in dataclasses.fields(instance):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field.name, "mutated")


@given(instance=_eligibility_decisions())
@settings(max_examples=100)
def test_eligibility_decision_is_frozen(instance: EligibilityDecision) -> None:
    for field in dataclasses.fields(instance):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field.name, "mutated")


@given(instance=_citations())
@settings(max_examples=100)
def test_citation_is_frozen(instance: Citation) -> None:
    for field in dataclasses.fields(instance):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field.name, "mutated")


@given(instance=_structured_reasons())
@settings(max_examples=100)
def test_structured_reason_is_frozen(instance: StructuredReason) -> None:
    for field in dataclasses.fields(instance):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, field.name, "mutated")


# ---------------------------------------------------------------------------
# Property 1.3: Amount quartet is all-or-none with min <= max
# ---------------------------------------------------------------------------


@given(amounts=_valid_amount_quartets())
@settings(max_examples=200)
def test_valid_amount_quartet_constructs_successfully(
    amounts: tuple[int | float | None, int | float | None, str | None, str | None],
) -> None:
    """Valid quartets (all None or all present with min<=max) always succeed."""
    decision = EligibilityDecision(
        item_id="test",
        status="eligible",
        amount_min=amounts[0],
        amount_max=amounts[1],
        amount_period=amounts[2],
        amount_currency=amounts[3],
        missing_field_ids=(),
        reasons=(),
    )
    if amounts[0] is None:
        assert decision.amount_min is None
        assert decision.amount_max is None
        assert decision.amount_period is None
        assert decision.amount_currency is None
    else:
        assert decision.amount_min <= decision.amount_max  # type: ignore[operator]


@given(
    amount_min=st.integers(0, 100000),
    amount_max=st.integers(0, 100000),
    period=_amount_periods,
)
@settings(max_examples=100)
def test_invalid_amount_quartet_min_greater_than_max_fails(
    amount_min: int,
    amount_max: int,
    period: str,
) -> None:
    """When min > max, construction must fail."""
    if amount_min <= amount_max:
        return  # skip valid cases
    with pytest.raises(ValueError, match="amount_min must be <= amount_max"):
        EligibilityDecision(
            item_id="test",
            status="eligible",
            amount_min=amount_min,
            amount_max=amount_max,
            amount_period=period,
            amount_currency="TWD",
            missing_field_ids=(),
            reasons=(),
        )


@given(
    amount_min=st.one_of(st.none(), st.integers(0, 100)),
    amount_max=st.one_of(st.none(), st.integers(0, 100)),
    amount_period=st.one_of(st.none(), _amount_periods),
    amount_currency=st.one_of(st.none(), st.just("TWD")),
)
@settings(max_examples=200)
def test_partial_amount_quartet_always_fails(
    amount_min: int | None,
    amount_max: int | None,
    amount_period: str | None,
    amount_currency: str | None,
) -> None:
    """Partial quartets (some None, some not) must always raise ValueError."""
    fields = (amount_min, amount_max, amount_period, amount_currency)
    present = [f is not None for f in fields]
    if all(present) or not any(present):
        return  # skip valid all-or-none cases

    with pytest.raises(ValueError, match="amount quartet must be all-or-none"):
        EligibilityDecision(
            item_id="test",
            status="eligible",
            amount_min=amount_min,
            amount_max=amount_max,
            amount_period=amount_period,
            amount_currency=amount_currency,
            missing_field_ids=(),
            reasons=(),
        )


# ---------------------------------------------------------------------------
# Property 1.4: FrozenValue recursive freeze round-trip
# ---------------------------------------------------------------------------


def _is_frozen_value(value: object) -> bool:
    """Independent oracle: check a value is valid FrozenValue without using freeze."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, tuple):
        return all(_is_frozen_value(item) for item in value)
    return False


@given(value=_frozen_values())
@settings(max_examples=200)
def test_freeze_value_always_produces_valid_frozen_value(value: object) -> None:
    """Any JSON-like structure freezes into a valid FrozenValue."""
    frozen = freeze_value(value)

    assert _is_frozen_value(frozen)


@given(value=_frozen_values())
@settings(max_examples=100)
def test_freeze_value_is_idempotent(value: object) -> None:
    """Freezing an already-frozen value produces the same result."""
    frozen_once = freeze_value(value)
    frozen_twice = freeze_value(frozen_once)

    assert frozen_once == frozen_twice


@given(
    expected=_frozen_values(),
    actual=_frozen_values(),
)
@settings(max_examples=100)
def test_structured_reason_expected_actual_are_always_frozen(
    expected: object,
    actual: object,
) -> None:
    """StructuredReason always stores frozen values regardless of input type."""
    reason = StructuredReason(
        condition_id="c1",
        field_id="f1",
        operator="equals",
        expected=expected,
        actual=actual,
        label="test",
        source_reference="ref",
    )

    assert _is_frozen_value(reason.expected)
    assert _is_frozen_value(reason.actual)
    assert reason.expected == freeze_value(expected)
    assert reason.actual == freeze_value(actual)
