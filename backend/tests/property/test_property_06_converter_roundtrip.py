"""Property 6: Converter deterministic lossless round trip.

**Validates: Requirements 6.1, 6.5–6.8, 15.7**

For any converter version representable legal nested Rule DSL:
- canonical→projection→canonical must preserve rule/version, required fields,
  tree semantics, condition fields, labels and source references.
- For any legal attributes, before and after status, missing IDs, reason
  condition IDs are identical.
- Repeated conversion produces byte-identical output.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.orchestration.data_contracts import FrozenValue
from app.rules.compatibility import (
    compute_canonical_hash,
    convert_from_projection,
    convert_to_projection,
)
from app.rules.dsl import AllOf, AnyOf, Condition, RuleDefinition, RuleNode
from app.rules.evaluator import evaluate_rule

# ---------------------------------------------------------------------------
# Fixed field IDs — reuse same pattern as Property 4
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
def _rule_tree(draw: st.DrawFn) -> tuple[RuleNode, set[str]]:
    """Generate a valid recursive Rule DSL tree.

    Returns the tree and the set of field_ids used.
    """
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

    field_ids = _collect_field_ids(tree)
    return tree, field_ids


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


@st.composite
def _rule_definition(draw: st.DrawFn) -> RuleDefinition:
    """Generate a complete valid RuleDefinition with metadata."""
    tree, field_ids = draw(_rule_tree())

    rule_id = draw(st.sampled_from(["rule_a", "rule_b", "rule_c"]))
    item_id = draw(st.sampled_from(["item_1", "item_2", "item_3"]))
    version = draw(st.integers(min_value=1, max_value=100))
    source_refs = draw(
        st.lists(
            st.sampled_from(["src_1", "src_2", "src_3", "src_4"]),
            min_size=1,
            max_size=3,
        ).map(tuple)
    )

    return RuleDefinition(
        rule_id=rule_id,
        item_id=item_id,
        version=version,
        dsl_version="1.0",
        required_field_ids=tuple(sorted(field_ids)),
        root=tree,
        source_references=source_refs,
    )


@st.composite
def _rule_definition_and_attributes(
    draw: st.DrawFn,
) -> tuple[RuleDefinition, dict[str, Any]]:
    """Generate a RuleDefinition and complete typed user attributes."""
    rule = draw(_rule_definition())

    attrs: dict[str, Any] = {}
    for field_id in rule.required_field_ids:
        if field_id in INT_FIELD_IDS:
            attrs[field_id] = draw(_int_values)
        else:
            attrs[field_id] = draw(_str_values)

    return rule, attrs


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(rule=_rule_definition())
@settings(max_examples=200, deadline=5000)
def test_determinism_repeated_conversion_identical(rule: RuleDefinition) -> None:
    """Determinism: convert_to_projection called twice produces identical rows.

    For any valid RuleDefinition, two independent calls to convert_to_projection
    must produce the exact same list of ProjectionRow objects.
    """
    rows_1 = convert_to_projection(rule)
    rows_2 = convert_to_projection(rule)

    assert rows_1 == rows_2, (
        f"Non-deterministic conversion: first call produced {len(rows_1)} rows, "
        f"second call produced {len(rows_2)} rows"
    )


@given(rule=_rule_definition())
@settings(max_examples=200, deadline=5000)
def test_byte_equivalence_canonical_hash_stable(rule: RuleDefinition) -> None:
    """Byte equivalence: compute_canonical_hash of both conversions is identical.

    The SHA-256 hash of the projection must be stable across repeated conversions.
    """
    rows_1 = convert_to_projection(rule)
    rows_2 = convert_to_projection(rule)

    hash_1 = compute_canonical_hash(rows_1)
    hash_2 = compute_canonical_hash(rows_2)

    assert hash_1 == hash_2, (
        f"Hash mismatch: {hash_1} != {hash_2} for the same RuleDefinition"
    )


@given(rule=_rule_definition())
@settings(max_examples=200, deadline=5000)
def test_lossless_round_trip_exact_equality(rule: RuleDefinition) -> None:
    """Lossless round trip: convert_from_projection(convert_to_projection(rule)) == rule.

    The reconstructed RuleDefinition must be exactly equal to the original.
    """
    rows = convert_to_projection(rule)
    reconstructed = convert_from_projection(rows)

    assert reconstructed == rule, (
        f"Round trip failed.\n"
        f"Original:      {rule}\n"
        f"Reconstructed: {reconstructed}"
    )


@given(data=_rule_definition_and_attributes())
@settings(max_examples=200, deadline=5000)
def test_semantic_equivalence_evaluation_preserved(
    data: tuple[RuleDefinition, dict[str, Any]],
) -> None:
    """Semantic equivalence: evaluation produces same results before and after round trip.

    For the same random user_attributes, evaluating the original rule root and
    the round-tripped root produces the same satisfied boolean and the same set
    of reason.condition_id values.
    """
    rule, user_attributes = data

    # Evaluate original
    original_result = evaluate_rule(rule.root, user_attributes)

    # Round-trip
    rows = convert_to_projection(rule)
    reconstructed = convert_from_projection(rows)

    # Evaluate reconstructed
    reconstructed_result = evaluate_rule(reconstructed.root, user_attributes)

    # Same satisfied status
    assert original_result.satisfied == reconstructed_result.satisfied, (
        f"Satisfied mismatch: original={original_result.satisfied}, "
        f"reconstructed={reconstructed_result.satisfied}"
    )

    # Same reason condition IDs
    original_condition_ids = {r.condition_id for r in original_result.reasons}
    reconstructed_condition_ids = {r.condition_id for r in reconstructed_result.reasons}

    assert original_condition_ids == reconstructed_condition_ids, (
        f"Reason condition IDs differ.\n"
        f"Original:      {sorted(original_condition_ids)}\n"
        f"Reconstructed: {sorted(reconstructed_condition_ids)}"
    )


@given(rule=_rule_definition())
@settings(max_examples=200, deadline=5000)
def test_field_preservation_metadata_intact(rule: RuleDefinition) -> None:
    """Field preservation: all metadata fields survive the round trip.

    After round trip, rule_id, item_id, version, dsl_version,
    required_field_ids, and source_references are all preserved.
    """
    rows = convert_to_projection(rule)
    reconstructed = convert_from_projection(rows)

    assert reconstructed.rule_id == rule.rule_id, (
        f"rule_id: {reconstructed.rule_id} != {rule.rule_id}"
    )
    assert reconstructed.item_id == rule.item_id, (
        f"item_id: {reconstructed.item_id} != {rule.item_id}"
    )
    assert reconstructed.version == rule.version, (
        f"version: {reconstructed.version} != {rule.version}"
    )
    assert reconstructed.dsl_version == rule.dsl_version, (
        f"dsl_version: {reconstructed.dsl_version} != {rule.dsl_version}"
    )
    assert reconstructed.required_field_ids == rule.required_field_ids, (
        f"required_field_ids: {reconstructed.required_field_ids} != "
        f"{rule.required_field_ids}"
    )
    assert reconstructed.source_references == rule.source_references, (
        f"source_references: {reconstructed.source_references} != "
        f"{rule.source_references}"
    )
