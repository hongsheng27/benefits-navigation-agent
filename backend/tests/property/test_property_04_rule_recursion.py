"""Property 4: Rule DSL recursive semantics.

**Validates: Requirements 5.3, 5.4, 5.5, 5.6, 5.7**

For any valid and arbitrarily deep Rule DSL tree with complete typed attributes,
`all_of`'s result equals the conjunction of all children, `any_of`'s result equals
the disjunction of at least one child, and the result equals a simple independent
reference evaluator.

Uses an independent reference evaluator (NOT production code) as the oracle.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.orchestration.data_contracts import FrozenValue
from app.rules.dsl import AllOf, AnyOf, Condition, RuleNode
from app.rules.evaluator import evaluate_rule

# ---------------------------------------------------------------------------
# Fixed field IDs used by the generator — each has a fixed type to avoid
# type mismatch errors when comparing int vs str.
# ---------------------------------------------------------------------------

# Fields f0, f1, f2 are integer-typed; f3, f4 are string-typed
INT_FIELD_IDS = ("f0", "f1", "f2")
STR_FIELD_IDS = ("f3", "f4")
ALL_FIELD_IDS = INT_FIELD_IDS + STR_FIELD_IDS

# Operators
COMPARISON_OPERATORS = ("==", "!=", ">=", "<=", ">", "<")
COLLECTION_OPERATORS = ("in", "not_in")
ALL_OPERATORS = COMPARISON_OPERATORS + COLLECTION_OPERATORS


# ---------------------------------------------------------------------------
# Independent reference evaluator (NOT using production code)
# ---------------------------------------------------------------------------


def _reference_compare(actual: Any, operator: str, expected: FrozenValue) -> bool:
    """Independent comparison logic for all supported operators."""
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if operator == ">=":
        return actual >= expected  # type: ignore[operator]
    if operator == "<=":
        return actual <= expected  # type: ignore[operator]
    if operator == ">":
        return actual > expected  # type: ignore[operator]
    if operator == "<":
        return actual < expected  # type: ignore[operator]
    if operator == "in":
        if not isinstance(expected, tuple):
            return actual == expected
        return actual in expected
    if operator == "not_in":
        if not isinstance(expected, tuple):
            return actual != expected
        return actual not in expected
    raise ValueError(f"Unknown operator: {operator}")


def reference_evaluate(node: RuleNode, attrs: dict[str, Any]) -> bool:
    """Independent recursive evaluator — does NOT call production code."""
    if isinstance(node, Condition):
        actual = attrs.get(node.field_id)
        return _reference_compare(actual, node.operator, node.expected)
    if isinstance(node, AllOf):
        return all(reference_evaluate(child, attrs) for child in node.children)
    if isinstance(node, AnyOf):
        return any(reference_evaluate(child, attrs) for child in node.children)
    raise ValueError(f"Unknown node type: {type(node)}")


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
        expected: FrozenValue = draw(
            st.lists(_int_values, min_size=1, max_size=4).map(tuple)
        )
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
        expected: FrozenValue = draw(
            st.lists(_str_values, min_size=1, max_size=4).map(tuple)
        )
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

    # Use recursive strategy for tree generation
    leaf = _leaf_condition(counter)

    tree = draw(
        st.recursive(
            leaf,
            lambda children: st.one_of(
                # AllOf with 1 child
                children.map(lambda c: AllOf(children=(c,))),
                # AllOf with 2 children
                st.tuples(children, children).map(
                    lambda t: AllOf(children=(t[0], t[1]))
                ),
                # AllOf with 3 children
                st.tuples(children, children, children).map(
                    lambda t: AllOf(children=(t[0], t[1], t[2]))
                ),
                # AnyOf with 1 child
                children.map(lambda c: AnyOf(children=(c,))),
                # AnyOf with 2 children
                st.tuples(children, children).map(
                    lambda t: AnyOf(children=(t[0], t[1]))
                ),
                # AnyOf with 3 children
                st.tuples(children, children, children).map(
                    lambda t: AnyOf(children=(t[0], t[1], t[2]))
                ),
            ),
            max_leaves=10,
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
def _tree_and_attributes(draw: st.DrawFn) -> tuple[RuleNode, dict[str, Any]]:
    """Generate a valid Rule DSL tree AND complete typed user_attributes."""
    tree = draw(_rule_tree())

    # Collect field_ids from the tree and generate matching-type attributes
    field_ids = _collect_field_ids(tree)

    attrs: dict[str, Any] = {}
    for field_id in field_ids:
        if field_id in INT_FIELD_IDS:
            attrs[field_id] = draw(_int_values)
        else:
            # String field — generate values that sometimes match and sometimes don't
            attrs[field_id] = draw(_str_values)

    return tree, attrs


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(data=_tree_and_attributes())
@settings(max_examples=200, deadline=5000)
def test_rule_dsl_recursive_semantics_match_reference_evaluator(
    data: tuple[RuleNode, dict[str, Any]],
) -> None:
    """Property 4: Production evaluator matches independent reference evaluator.

    For any valid and arbitrarily deep Rule DSL tree with complete typed attributes,
    the production evaluator's satisfied result must equal the independent reference
    evaluator's boolean result.
    """
    tree, user_attributes = data

    # Production evaluator
    production_result = evaluate_rule(tree, user_attributes)

    # Independent reference evaluator
    reference_result = reference_evaluate(tree, user_attributes)

    assert production_result.satisfied == reference_result, (
        f"Production ({production_result.satisfied}) != "
        f"Reference ({reference_result}) for tree={tree}, attrs={user_attributes}"
    )


@given(data=_tree_and_attributes())
@settings(max_examples=200, deadline=5000)
def test_all_of_is_conjunction_of_children(
    data: tuple[RuleNode, dict[str, Any]],
) -> None:
    """For any AllOf node in the tree, its result equals the conjunction of children.

    This verifies the all_of semantics independently.
    """
    tree, user_attributes = data

    def _verify_all_of_semantics(node: RuleNode) -> None:
        if isinstance(node, AllOf):
            # Evaluate the AllOf node
            all_of_result = evaluate_rule(node, user_attributes)
            # Evaluate each child independently
            child_results = [
                evaluate_rule(child, user_attributes).satisfied
                for child in node.children
            ]
            # AllOf should be conjunction
            expected_satisfied = all(child_results)
            assert all_of_result.satisfied == expected_satisfied, (
                f"AllOf result ({all_of_result.satisfied}) != "
                f"conjunction of children ({expected_satisfied})"
            )
            # Recurse into children
            for child in node.children:
                _verify_all_of_semantics(child)
        elif isinstance(node, AnyOf):
            for child in node.children:
                _verify_all_of_semantics(child)

    _verify_all_of_semantics(tree)


@given(data=_tree_and_attributes())
@settings(max_examples=200, deadline=5000)
def test_any_of_is_disjunction_of_children(
    data: tuple[RuleNode, dict[str, Any]],
) -> None:
    """For any AnyOf node in the tree, its result equals the disjunction of children.

    This verifies the any_of semantics independently.
    """
    tree, user_attributes = data

    def _verify_any_of_semantics(node: RuleNode) -> None:
        if isinstance(node, AnyOf):
            # Evaluate the AnyOf node
            any_of_result = evaluate_rule(node, user_attributes)
            # Evaluate each child independently
            child_results = [
                evaluate_rule(child, user_attributes).satisfied
                for child in node.children
            ]
            # AnyOf should be disjunction
            expected_satisfied = any(child_results)
            assert any_of_result.satisfied == expected_satisfied, (
                f"AnyOf result ({any_of_result.satisfied}) != "
                f"disjunction of children ({expected_satisfied})"
            )
            # Recurse into children
            for child in node.children:
                _verify_any_of_semantics(child)
        elif isinstance(node, AllOf):
            for child in node.children:
                _verify_any_of_semantics(child)

    _verify_any_of_semantics(tree)
