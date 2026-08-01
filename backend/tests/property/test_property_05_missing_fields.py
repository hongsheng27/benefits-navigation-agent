"""Property 5: Missing fields 阻止完整 evaluation.

**Validates: Requirements 5.2, 7.9, 16.4**

When any required field is missing from user attributes, evaluate_eligibility()
must return status="needs_information" with sorted unique missing field IDs,
empty reasons, all amount fields as None, and ZERO calls to the recursive engine
(evaluate_rule).

Uses unittest.mock.patch to verify evaluate_rule is never called when fields
are missing.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from app.rules.dsl import AllOf, AnyOf, Condition, RuleDefinition, RuleNode
from app.rules.evaluation import evaluate_eligibility

# ---------------------------------------------------------------------------
# Fixed field IDs — same types as Property 4 for consistency
# ---------------------------------------------------------------------------

INT_FIELD_IDS = ("f0", "f1", "f2")
STR_FIELD_IDS = ("f3", "f4")
ALL_FIELD_IDS = INT_FIELD_IDS + STR_FIELD_IDS

COMPARISON_OPERATORS = ("==", "!=", ">=", "<=", ">", "<")
COLLECTION_OPERATORS = ("in", "not_in")
ALL_OPERATORS = COMPARISON_OPERATORS + COLLECTION_OPERATORS


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_int_values = st.integers(min_value=-50, max_value=50)
_str_values = st.sampled_from(["alpha", "beta", "gamma", "delta", "epsilon"])


@st.composite
def _int_condition(draw: st.DrawFn, counter: list[int]) -> Condition:
    """Generate a Condition node for an integer-typed field."""
    field_id = draw(st.sampled_from(INT_FIELD_IDS))
    operator = draw(st.sampled_from(ALL_OPERATORS))

    if operator in COLLECTION_OPERATORS:
        expected = draw(st.lists(_int_values, min_size=1, max_size=4).map(tuple))
    else:
        expected = draw(_int_values)

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
def _str_condition(draw: st.DrawFn, counter: list[int]) -> Condition:
    """Generate a Condition node for a string-typed field."""
    field_id = draw(st.sampled_from(STR_FIELD_IDS))
    operator = draw(st.sampled_from(ALL_OPERATORS))

    if operator in COLLECTION_OPERATORS:
        expected = draw(st.lists(_str_values, min_size=1, max_size=4).map(tuple))
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
def _leaf_condition(draw: st.DrawFn, counter: list[int]) -> Condition:
    """Generate a leaf Condition with type-consistent field/expected."""
    use_int = draw(st.booleans())
    if use_int:
        return draw(_int_condition(counter))
    else:
        return draw(_str_condition(counter))


@st.composite
def _rule_tree(draw: st.DrawFn) -> RuleNode:
    """Generate a valid recursive Rule DSL tree with type-consistent conditions."""
    counter = [0]
    leaf = _leaf_condition(counter)

    tree = draw(
        st.recursive(
            leaf,
            lambda children: st.one_of(
                children.map(lambda c: AllOf(children=(c,))),
                st.tuples(children, children).map(
                    lambda t: AllOf(children=(t[0], t[1]))
                ),
                st.tuples(children, children, children).map(
                    lambda t: AllOf(children=(t[0], t[1], t[2]))
                ),
                children.map(lambda c: AnyOf(children=(c,))),
                st.tuples(children, children).map(
                    lambda t: AnyOf(children=(t[0], t[1]))
                ),
                st.tuples(children, children, children).map(
                    lambda t: AnyOf(children=(t[0], t[1], t[2]))
                ),
            ),
            max_leaves=8,
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
    return set()


@st.composite
def _rule_definition_with_missing_fields(
    draw: st.DrawFn,
) -> tuple[RuleDefinition, dict[str, Any], set[str]]:
    """Generate a valid RuleDefinition and user_attributes missing at least one field.

    Returns (rule_definition, user_attributes, expected_missing_set).
    """
    tree = draw(_rule_tree())
    field_ids = _collect_field_ids(tree)

    # Ensure at least one field exists in the tree
    if not field_ids:
        # Force a condition so we have fields
        counter = [100]
        tree = draw(_leaf_condition(counter))
        field_ids = _collect_field_ids(tree)

    required_field_ids = tuple(sorted(field_ids))

    # Choose which fields to omit (at least one)
    field_list = sorted(field_ids)
    # Draw a non-empty subset of fields to omit
    omit_mask = draw(
        st.lists(
            st.booleans(),
            min_size=len(field_list),
            max_size=len(field_list),
        ).filter(lambda mask: any(mask))  # at least one True = at least one omitted
    )

    omitted_fields: set[str] = set()
    provided_fields: set[str] = set()
    for field_id, omit in zip(field_list, omit_mask):
        if omit:
            omitted_fields.add(field_id)
        else:
            provided_fields.add(field_id)

    # Generate attributes for provided fields only
    attrs: dict[str, Any] = {}
    for field_id in provided_fields:
        if field_id in INT_FIELD_IDS:
            attrs[field_id] = draw(_int_values)
        else:
            attrs[field_id] = draw(_str_values)

    rule_def = RuleDefinition(
        rule_id="rule_prop5",
        item_id="item_prop5",
        version=1,
        dsl_version="1.0",
        required_field_ids=required_field_ids,
        root=tree,
        source_references=("src_ref_1",),
    )

    return rule_def, attrs, omitted_fields


@st.composite
def _rule_definition_all_fields_missing(
    draw: st.DrawFn,
) -> tuple[RuleDefinition, dict[str, Any], set[str]]:
    """Generate a RuleDefinition where ALL required fields are missing."""
    tree = draw(_rule_tree())
    field_ids = _collect_field_ids(tree)

    if not field_ids:
        counter = [200]
        tree = draw(_leaf_condition(counter))
        field_ids = _collect_field_ids(tree)

    required_field_ids = tuple(sorted(field_ids))

    rule_def = RuleDefinition(
        rule_id="rule_prop5_all",
        item_id="item_prop5_all",
        version=1,
        dsl_version="1.0",
        required_field_ids=required_field_ids,
        root=tree,
        source_references=("src_ref_1",),
    )

    # Provide NO attributes at all
    return rule_def, {}, field_ids


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(data=_rule_definition_with_missing_fields())
@settings(max_examples=200, deadline=5000)
def test_missing_fields_returns_sorted_unique_ids_and_zero_engine_calls(
    data: tuple[RuleDefinition, dict[str, Any], set[str]],
) -> None:
    """Property 5: Missing required fields prevents evaluation and returns correct IDs.

    When user_attributes are missing at least one required field:
    - status == "needs_information"
    - missing_field_ids == tuple(sorted(set(actual_missing)))
    - reasons == ()
    - All amount fields are None
    - evaluate_rule is NEVER called (zero engine invocations)
    """
    rule_def, user_attributes, expected_missing = data

    with patch("app.rules.evaluation.evaluate_rule") as mock_evaluate_rule:
        decision = evaluate_eligibility(rule_def, user_attributes)

    # Status must be needs_information
    assert decision.status == "needs_information", (
        f"Expected status='needs_information', got '{decision.status}'"
    )

    # missing_field_ids must be sorted and unique, matching expected
    expected_ids = tuple(sorted(expected_missing))
    assert decision.missing_field_ids == expected_ids, (
        f"Expected missing_field_ids={expected_ids}, "
        f"got {decision.missing_field_ids}"
    )

    # Reasons must be empty
    assert decision.reasons == (), (
        f"Expected empty reasons, got {decision.reasons}"
    )

    # All amount fields must be None
    assert decision.amount_min is None
    assert decision.amount_max is None
    assert decision.amount_period is None
    assert decision.amount_currency is None

    # evaluate_rule must NOT have been called
    assert mock_evaluate_rule.call_count == 0, (
        f"evaluate_rule was called {mock_evaluate_rule.call_count} times, "
        f"expected 0 calls when fields are missing"
    )


@given(data=_rule_definition_all_fields_missing())
@settings(max_examples=200, deadline=5000)
def test_all_fields_missing_returns_all_required_ids_zero_engine_calls(
    data: tuple[RuleDefinition, dict[str, Any], set[str]],
) -> None:
    """When ALL required fields are missing, all are reported and no engine call happens.

    This is the maximal missing case: user_attributes is empty, so every
    required_field_id should appear in missing_field_ids.
    """
    rule_def, user_attributes, expected_missing = data

    with patch("app.rules.evaluation.evaluate_rule") as mock_evaluate_rule:
        decision = evaluate_eligibility(rule_def, user_attributes)

    assert decision.status == "needs_information"
    assert decision.missing_field_ids == tuple(sorted(expected_missing))
    assert decision.reasons == ()
    assert decision.amount_min is None
    assert decision.amount_max is None
    assert decision.amount_period is None
    assert decision.amount_currency is None
    assert mock_evaluate_rule.call_count == 0


@given(data=_rule_definition_with_missing_fields())
@settings(max_examples=200, deadline=5000)
def test_missing_field_ids_is_always_sorted_and_deduplicated(
    data: tuple[RuleDefinition, dict[str, Any], set[str]],
) -> None:
    """The returned missing_field_ids tuple is always sorted and contains no duplicates.

    This verifies the idempotent sorted-set semantics regardless of which subset
    of fields is missing.
    """
    rule_def, user_attributes, _expected_missing = data

    decision = evaluate_eligibility(rule_def, user_attributes)

    # Verify sorted
    ids_list = list(decision.missing_field_ids)
    assert ids_list == sorted(ids_list), (
        f"missing_field_ids not sorted: {decision.missing_field_ids}"
    )

    # Verify no duplicates
    assert len(ids_list) == len(set(ids_list)), (
        f"missing_field_ids has duplicates: {decision.missing_field_ids}"
    )

    # Verify non-empty (at least one field is missing by construction)
    assert len(ids_list) > 0, "Expected at least one missing field ID"
