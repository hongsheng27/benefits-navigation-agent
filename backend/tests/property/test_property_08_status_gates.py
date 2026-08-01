"""Property 8: Program status gate matrix.

**Validates: Requirements 5.10–5.12, 7.1–7.8, 7.11, 16.3, 16.4, 16.14**

For status × rule count × citation completeness × attributes, verifies
visibility, result/error, and engine call count (presence/absence of reasons).

Uses fake repositories (same pattern as unit tests) with Hypothesis strategies
to explore the full status gate matrix.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.application.eligibility_service import (
    DeterministicEligibilityService,
    NonEvaluableStatusError,
)
from app.orchestration.data_contracts import (
    Citation,
    EligibilityDecision,
    FieldRegistryEntry,
    ProgramStatus,
    StructuredReason,
)
from app.rules.dsl import AllOf, AnyOf, Condition, RuleDefinition, RuleNode
from app.rules.evaluation import ApprovedAmount

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INT_FIELD_IDS = ("f0", "f1", "f2")
STR_FIELD_IDS = ("f3", "f4")
ALL_FIELD_IDS = INT_FIELD_IDS + STR_FIELD_IDS

COMPARISON_OPERATORS = ("==", "!=", ">=", "<=", ">", "<")
COLLECTION_OPERATORS = ("in", "not_in")
ALL_OPERATORS = COMPARISON_OPERATORS + COLLECTION_OPERATORS

# ---------------------------------------------------------------------------
# Fake Repositories
# ---------------------------------------------------------------------------


class FakeRuleRepository:
    """In-memory fake rule repository for property testing."""

    def __init__(
        self,
        *,
        status: ProgramStatus = "candidate",
        rule: RuleDefinition | None = None,
        amount: ApprovedAmount | None = None,
    ) -> None:
        self._status = status
        self._rule = rule
        self._amount = amount

    def get_program_status(self, item_id: str) -> ProgramStatus:
        return self._status

    def get_approved_rule(self, item_id: str) -> RuleDefinition | None:
        return self._rule

    def get_approved_amount(self, item_id: str) -> ApprovedAmount | None:
        return self._amount

    def get_required_field_entries(self, item_id: str) -> Sequence[FieldRegistryEntry]:
        return ()


class FakeEvidenceRepository:
    """In-memory fake evidence repository.

    When complete=True, returns one citation per requested reference.
    When complete=False, returns no citations (simulating incomplete evidence).
    """

    def __init__(self, *, complete: bool = True) -> None:
        self._complete = complete

    def get_citations_for_references(
        self,
        item_id: str,
        source_references: Sequence[str],
    ) -> Sequence[Citation]:
        if not self._complete:
            return ()
        # Return one citation per reference → full coverage
        return tuple(
            Citation(
                document_id=f"doc-{ref}",
                title=f"Title for {ref}",
                publisher="Test Publisher",
                published_at=datetime(2024, 1, 1, tzinfo=UTC),
                effective_at=datetime(2024, 1, 1, tzinfo=UTC),
                url=f"https://example.com/{ref}",
                excerpt=f"Excerpt for {ref}",
                retrieved_at=datetime(2024, 6, 1, tzinfo=UTC),
            )
            for ref in source_references
        )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_int_values = st.integers(min_value=-50, max_value=50)
_str_values = st.sampled_from(["alpha", "beta", "gamma", "delta", "epsilon"])


@st.composite
def _condition(draw: st.DrawFn, counter: list[int]) -> Condition:
    """Generate a leaf Condition with type-consistent field/expected."""
    use_int = draw(st.booleans())
    if use_int:
        field_id = draw(st.sampled_from(INT_FIELD_IDS))
        operator = draw(st.sampled_from(ALL_OPERATORS))
        if operator in COLLECTION_OPERATORS:
            expected = draw(st.lists(_int_values, min_size=1, max_size=3).map(tuple))
        else:
            expected = draw(_int_values)
    else:
        field_id = draw(st.sampled_from(STR_FIELD_IDS))
        operator = draw(st.sampled_from(ALL_OPERATORS))
        if operator in COLLECTION_OPERATORS:
            expected = draw(st.lists(_str_values, min_size=1, max_size=3).map(tuple))
        else:
            expected = draw(_str_values)

    counter[0] += 1
    cid = f"c{counter[0]}"

    return Condition(
        condition_id=cid,
        field_id=field_id,
        operator=operator,
        expected=expected,
        label=f"label_{cid}",
        source_reference=f"ref_{cid}",
    )


@st.composite
def _rule_tree(draw: st.DrawFn) -> RuleNode:
    """Generate a valid recursive Rule DSL tree."""
    counter = [0]
    leaf = _condition(counter)

    tree = draw(
        st.recursive(
            leaf,
            lambda children: st.one_of(
                st.tuples(children, children).map(
                    lambda t: AllOf(children=(t[0], t[1]))
                ),
                st.tuples(children, children).map(
                    lambda t: AnyOf(children=(t[0], t[1]))
                ),
                children.map(lambda c: AllOf(children=(c,))),
            ),
            max_leaves=5,
        )
    )
    return tree


def _collect_field_ids(node: RuleNode) -> set[str]:
    """Collect all field_ids referenced in the tree."""
    if isinstance(node, Condition):
        return {node.field_id}
    if isinstance(node, (AllOf, AnyOf)):
        result: set[str] = set()
        for child in node.children:
            result.update(_collect_field_ids(child))
        return result
    return set()  # pragma: no cover


def _collect_source_references(node: RuleNode) -> set[str]:
    """Collect all source_reference values from the tree."""
    if isinstance(node, Condition):
        return {node.source_reference}
    if isinstance(node, (AllOf, AnyOf)):
        result: set[str] = set()
        for child in node.children:
            result.update(_collect_source_references(child))
        return result
    return set()  # pragma: no cover


@st.composite
def _rule_definition(draw: st.DrawFn) -> RuleDefinition:
    """Generate a valid RuleDefinition with a random tree."""
    tree = draw(_rule_tree())
    field_ids = tuple(sorted(_collect_field_ids(tree)))
    source_refs = tuple(sorted(_collect_source_references(tree)))

    return RuleDefinition(
        rule_id="rule-test",
        item_id="item-test",
        version=1,
        dsl_version="1.0",
        required_field_ids=field_ids,
        root=tree,
        source_references=source_refs,
    )


@st.composite
def _complete_attributes(draw: st.DrawFn, field_ids: tuple[str, ...]) -> dict[str, Any]:
    """Generate attributes that cover ALL required fields."""
    attrs: dict[str, Any] = {}
    for fid in field_ids:
        if fid in INT_FIELD_IDS:
            attrs[fid] = draw(_int_values)
        else:
            attrs[fid] = draw(_str_values)
    return attrs


@st.composite
def _partial_attributes(draw: st.DrawFn, field_ids: tuple[str, ...]) -> dict[str, Any]:
    """Generate attributes that are MISSING at least one required field."""
    if len(field_ids) == 0:
        return {}
    # Choose a strict subset of field_ids (at least one missing)
    include_count = draw(st.integers(min_value=0, max_value=len(field_ids) - 1))
    included = draw(
        st.sampled_from(
            [
                combo
                for r in range(include_count, include_count + 1)
                for combo in _combinations(field_ids, r)
            ]
        )
        if include_count > 0
        else st.just(())
    )

    attrs: dict[str, Any] = {}
    for fid in included:
        if fid in INT_FIELD_IDS:
            attrs[fid] = draw(_int_values)
        else:
            attrs[fid] = draw(_str_values)
    return attrs


def _combinations(items: tuple[str, ...], r: int) -> list[tuple[str, ...]]:
    """Simple combinations helper to avoid importing itertools in strategy."""
    from itertools import combinations

    return list(combinations(items, r))


_random_user_attributes = st.fixed_dictionaries(
    {},
    optional={
        fid: _int_values if fid in INT_FIELD_IDS else _str_values
        for fid in ALL_FIELD_IDS
    },
)


# ---------------------------------------------------------------------------
# Helper to build service
# ---------------------------------------------------------------------------


def _build_service(
    *,
    status: ProgramStatus,
    rule: RuleDefinition | None = None,
    amount: ApprovedAmount | None = None,
    citations_complete: bool = True,
) -> DeterministicEligibilityService:
    """Build a DeterministicEligibilityService with fake repos."""
    rule_repo = FakeRuleRepository(status=status, rule=rule, amount=amount)
    evidence_repo = FakeEvidenceRepository(complete=citations_complete)
    return DeterministicEligibilityService(rule_repo, evidence_repo)


# ---------------------------------------------------------------------------
# Property 8.1: verified + approved rule + complete citations + all fields
#   → engine IS called, status is eligible or ineligible
# ---------------------------------------------------------------------------


@given(rule=_rule_definition(), data=st.data())
@settings(max_examples=150, deadline=5000)
def test_verified_with_rule_complete_citations_all_fields_calls_engine(
    rule: RuleDefinition, data: st.DataObject
) -> None:
    """Verified + approved rule + complete citations + all required fields
    → engine IS called (reasons non-empty), status is eligible or ineligible,
    decision has proper item_id.
    """
    # Generate complete attributes for all required fields
    attrs: dict[str, Any] = {}
    for fid in rule.required_field_ids:
        if fid in INT_FIELD_IDS:
            attrs[fid] = data.draw(_int_values)
        else:
            attrs[fid] = data.draw(_str_values)

    service = _build_service(
        status="verified",
        rule=rule,
        citations_complete=True,
    )

    decision = service.evaluate("item-test", attrs)

    # Engine was called: reasons should have at least one StructuredReason
    assert len(decision.reasons) > 0, "Engine should be called (reasons non-empty)"
    assert all(isinstance(r, StructuredReason) for r in decision.reasons)

    # Status must be eligible or ineligible (never needs_information or needs_human_review)
    assert decision.status in ("eligible", "ineligible"), (
        f"Expected eligible/ineligible, got {decision.status}"
    )

    # Decision has proper item_id
    assert decision.item_id == "item-test"


# ---------------------------------------------------------------------------
# Property 8.2: candidate or under_review → needs_human_review, no engine call
# ---------------------------------------------------------------------------


@given(
    status=st.sampled_from(["candidate", "under_review"]),
    rule=_rule_definition(),
    data=st.data(),
)
@settings(max_examples=100, deadline=5000)
def test_candidate_or_under_review_always_needs_human_review(
    status: ProgramStatus, rule: RuleDefinition, data: st.DataObject
) -> None:
    """candidate/under_review → engine NOT called, status is needs_human_review,
    no amount returned, regardless of rule, citations, or attributes.
    """
    # Random attributes (may or may not be complete)
    attrs = data.draw(_random_user_attributes)

    service = _build_service(
        status=status,
        rule=rule,
        citations_complete=data.draw(st.booleans()),
    )

    decision = service.evaluate("item-test", attrs)

    assert decision.status == "needs_human_review"
    assert decision.reasons == (), "Engine should NOT be called (reasons empty)"
    assert decision.amount_min is None
    assert decision.amount_max is None
    assert decision.amount_period is None
    assert decision.amount_currency is None


# ---------------------------------------------------------------------------
# Property 8.3: stale → needs_human_review, no engine call
# ---------------------------------------------------------------------------


@given(
    rule=_rule_definition(),
    data=st.data(),
)
@settings(max_examples=100, deadline=5000)
def test_stale_always_needs_human_review(
    rule: RuleDefinition, data: st.DataObject
) -> None:
    """stale → engine NOT called, status is needs_human_review, no amount.
    Regardless of rule, citations, or attributes.
    """
    attrs = data.draw(_random_user_attributes)

    service = _build_service(
        status="stale",
        rule=rule,
        citations_complete=data.draw(st.booleans()),
    )

    decision = service.evaluate("item-test", attrs)

    assert decision.status == "needs_human_review"
    assert decision.reasons == (), "Engine should NOT be called (reasons empty)"
    assert decision.amount_min is None
    assert decision.amount_max is None
    assert decision.amount_period is None
    assert decision.amount_currency is None


# ---------------------------------------------------------------------------
# Property 8.4: rejected/inactive → NonEvaluableStatusError
# ---------------------------------------------------------------------------


@given(
    status=st.sampled_from(["rejected", "inactive"]),
    data=st.data(),
)
@settings(max_examples=100, deadline=5000)
def test_rejected_or_inactive_raises_non_evaluable_error(
    status: ProgramStatus, data: st.DataObject
) -> None:
    """rejected/inactive → NonEvaluableStatusError with item_id and status."""
    attrs = data.draw(_random_user_attributes)
    rule = data.draw(_rule_definition())

    service = _build_service(
        status=status,
        rule=rule,
        citations_complete=data.draw(st.booleans()),
    )

    with pytest.raises(NonEvaluableStatusError) as exc_info:
        service.evaluate("item-test", attrs)

    assert exc_info.value.item_id == "item-test"
    assert exc_info.value.status == status


# ---------------------------------------------------------------------------
# Property 8.5: verified + NO approved rule → needs_human_review, no engine
# ---------------------------------------------------------------------------


@given(data=st.data())
@settings(max_examples=100, deadline=5000)
def test_verified_no_rule_needs_human_review(data: st.DataObject) -> None:
    """verified + no approved rule → needs_human_review, engine NOT called."""
    attrs = data.draw(_random_user_attributes)

    service = _build_service(
        status="verified",
        rule=None,  # No approved rule
        citations_complete=data.draw(st.booleans()),
    )

    decision = service.evaluate("item-test", attrs)

    assert decision.status == "needs_human_review"
    assert decision.reasons == (), "Engine should NOT be called (reasons empty)"


# ---------------------------------------------------------------------------
# Property 8.6: verified + approved rule + INCOMPLETE citations → downgrade
# ---------------------------------------------------------------------------


@given(rule=_rule_definition(), data=st.data())
@settings(max_examples=150, deadline=5000)
def test_verified_incomplete_citations_downgrades_to_human_review(
    rule: RuleDefinition, data: st.DataObject
) -> None:
    """verified + approved rule + incomplete citations → needs_human_review.
    Reasons may or may not be present (evaluation happens, then downgrade).
    """
    # Generate complete attributes so evaluation proceeds past missing-fields gate
    attrs: dict[str, Any] = {}
    for fid in rule.required_field_ids:
        if fid in INT_FIELD_IDS:
            attrs[fid] = data.draw(_int_values)
        else:
            attrs[fid] = data.draw(_str_values)

    service = _build_service(
        status="verified",
        rule=rule,
        citations_complete=False,  # Incomplete citations
    )

    decision = service.evaluate("item-test", attrs)

    # Conservative downgrade to needs_human_review
    assert decision.status == "needs_human_review", (
        f"Expected needs_human_review with incomplete citations, got {decision.status}"
    )


# ---------------------------------------------------------------------------
# Property 8.7: verified + approved rule + missing required fields
#   → needs_information, missing_field_ids non-empty sorted, no engine
# ---------------------------------------------------------------------------


@given(rule=_rule_definition(), data=st.data())
@settings(max_examples=150, deadline=5000)
def test_verified_missing_fields_returns_needs_information(
    rule: RuleDefinition, data: st.DataObject
) -> None:
    """verified + approved rule + missing required fields → needs_information,
    missing_field_ids is non-empty sorted tuple, engine NOT called.
    """
    # Only provide a strict subset of required fields (at least one missing)
    if len(rule.required_field_ids) == 0:
        # Edge case: no required fields means we can't test "missing" scenario
        # Skip this example (rule with no required fields is tested in 8.1)
        return

    # Pick a strict subset to include (0 to n-1 fields)
    n = len(rule.required_field_ids)
    include_count = data.draw(st.integers(min_value=0, max_value=n - 1))
    included_fields = list(rule.required_field_ids)[:include_count]

    attrs: dict[str, Any] = {}
    for fid in included_fields:
        if fid in INT_FIELD_IDS:
            attrs[fid] = data.draw(_int_values)
        else:
            attrs[fid] = data.draw(_str_values)

    service = _build_service(
        status="verified",
        rule=rule,
        citations_complete=True,
    )

    decision = service.evaluate("item-test", attrs)

    assert decision.status == "needs_information"
    assert len(decision.missing_field_ids) > 0, "missing_field_ids must be non-empty"
    # Must be sorted
    assert decision.missing_field_ids == tuple(sorted(decision.missing_field_ids))
    # Engine NOT called: no reasons
    assert decision.reasons == (), "Engine should NOT be called for missing fields"
