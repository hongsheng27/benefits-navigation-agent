"""Tests for the canonical immutable Rule DSL tree and validator.

Covers:
- Valid tree construction succeeds
- Frozen/immutable (cannot reassign fields)
- Empty children in AllOf/AnyOf raises RuleValidationError
- Duplicate condition_id raises RuleValidationError
- Invalid operator raises RuleValidationError
- Condition field_id not in required_field_ids raises RuleValidationError
- Empty source_reference on condition raises RuleValidationError
- Extra required_field_ids (not used by conditions) raises RuleValidationError
- Unrecognized dsl_version raises RuleValidationError
- Nested tree validation works (deeply nested AllOf/AnyOf/Condition)
"""

import pytest

from app.rules.dsl import (
    DSL_VERSION,
    OPERATOR_ALLOWLIST_V1,
    OPERATOR_ALLOWLISTS,
    AllOf,
    AnyOf,
    Condition,
    RuleDefinition,
    RuleNode,
    RuleValidationError,
    RuleVersion,
    validate_rule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_condition(
    condition_id: str = "c1",
    field_id: str = "field_a",
    operator: str = "==",
    expected: object = "value",
    label: str = "Test condition",
    source_reference: str = "src_ref_1",
) -> Condition:
    return Condition(
        condition_id=condition_id,
        field_id=field_id,
        operator=operator,
        expected=expected,
        label=label,
        source_reference=source_reference,
    )


def _make_rule(
    root: RuleNode,
    required_field_ids: tuple[str, ...] | None = None,
    dsl_version: str = DSL_VERSION,
) -> RuleDefinition:
    """Build a RuleDefinition with required_field_ids derived from leaf conditions."""
    if required_field_ids is None:
        required_field_ids = tuple(sorted(_collect_leaf_fields(root)))
    return RuleDefinition(
        rule_id="rule_1",
        item_id="item_1",
        version=1,
        dsl_version=dsl_version,
        required_field_ids=required_field_ids,
        root=root,
        source_references=("src_ref_1",),
    )


def _collect_leaf_fields(node: RuleNode) -> set[str]:
    """Recursively collect field_ids from leaf conditions."""
    if isinstance(node, Condition):
        return {node.field_id}
    if isinstance(node, (AllOf, AnyOf)):
        fields: set[str] = set()
        for child in node.children:
            fields |= _collect_leaf_fields(child)
        return fields
    return set()  # pragma: no cover


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_dsl_version_is_string(self):
        """DSL_VERSION is a non-empty string."""
        assert isinstance(DSL_VERSION, str)
        assert DSL_VERSION == "1.0"

    def test_operator_allowlist_v1_is_frozenset(self):
        """OPERATOR_ALLOWLIST_V1 is a frozenset with expected operators."""
        assert isinstance(OPERATOR_ALLOWLIST_V1, frozenset)
        assert OPERATOR_ALLOWLIST_V1 == frozenset(
            {"==", "!=", ">=", "<=", ">", "<", "in", "not_in"}
        )

    def test_operator_allowlists_maps_version(self):
        """OPERATOR_ALLOWLISTS maps DSL_VERSION to OPERATOR_ALLOWLIST_V1."""
        assert DSL_VERSION in OPERATOR_ALLOWLISTS
        assert OPERATOR_ALLOWLISTS[DSL_VERSION] is OPERATOR_ALLOWLIST_V1

    def test_rule_version_is_alias_for_rule_definition(self):
        """RuleVersion is a backward-compatible alias for RuleDefinition."""
        assert RuleVersion is RuleDefinition

    def test_rule_validation_error_is_value_error(self):
        """RuleValidationError is a subclass of ValueError."""
        assert issubclass(RuleValidationError, ValueError)


# ---------------------------------------------------------------------------
# Valid tree construction
# ---------------------------------------------------------------------------


class TestValidConstruction:
    def test_simple_condition_tree(self):
        """A single condition as root is valid."""
        cond = _make_condition()
        rule = _make_rule(cond)
        validate_rule(rule)  # should not raise

    def test_allof_with_conditions(self):
        """AllOf with multiple conditions is valid."""
        root = AllOf(
            children=(
                _make_condition("c1", "field_a"),
                _make_condition("c2", "field_b"),
            )
        )
        rule = _make_rule(root)
        validate_rule(rule)

    def test_anyof_with_conditions(self):
        """AnyOf with multiple conditions is valid."""
        root = AnyOf(
            children=(
                _make_condition("c1", "field_a"),
                _make_condition("c2", "field_b"),
            )
        )
        rule = _make_rule(root)
        validate_rule(rule)


# ---------------------------------------------------------------------------
# Frozen/immutable
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_frozen_condition_rejects_reassignment(self):
        """Condition dataclass rejects attribute reassignment."""
        cond = _make_condition()
        with pytest.raises(AttributeError):
            cond.field_id = "other_field"  # type: ignore[misc]

    def test_frozen_allof_rejects_reassignment(self):
        """AllOf dataclass rejects attribute reassignment."""
        node = AllOf(children=(_make_condition(),))
        with pytest.raises(AttributeError):
            node.children = ()  # type: ignore[misc]

    def test_frozen_anyof_rejects_reassignment(self):
        """AnyOf dataclass rejects attribute reassignment."""
        node = AnyOf(children=(_make_condition(),))
        with pytest.raises(AttributeError):
            node.children = ()  # type: ignore[misc]

    def test_frozen_rule_definition_rejects_reassignment(self):
        """RuleDefinition dataclass rejects attribute reassignment."""
        rule = _make_rule(_make_condition())
        with pytest.raises(AttributeError):
            rule.version = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Empty children in AllOf/AnyOf raises RuleValidationError
# ---------------------------------------------------------------------------


class TestGroupNonEmpty:
    def test_allof_empty_children_raises(self):
        """AllOf with no children fails validation."""
        root = AllOf(children=())
        rule = _make_rule(root, required_field_ids=())
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "group_empty"
        assert "AllOf" in str(exc_info.value)

    def test_anyof_empty_children_raises(self):
        """AnyOf with no children fails validation."""
        root = AnyOf(children=())
        rule = _make_rule(root, required_field_ids=())
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "group_empty"
        assert "AnyOf" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Duplicate condition_id raises RuleValidationError
# ---------------------------------------------------------------------------


class TestDuplicateConditionId:
    def test_duplicate_ids_in_flat_allof(self):
        """Same condition_id used twice fails validation."""
        root = AllOf(
            children=(
                _make_condition("c1", "field_a"),
                _make_condition("c1", "field_b"),
            )
        )
        rule = _make_rule(root)
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "duplicate_condition_id"
        assert "c1" in str(exc_info.value)

    def test_duplicate_ids_across_nested_groups(self):
        """Duplicate condition_id across different groups fails."""
        root = AllOf(
            children=(
                AnyOf(children=(_make_condition("c1", "field_a"),)),
                _make_condition("c1", "field_b"),
            )
        )
        rule = _make_rule(root)
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "duplicate_condition_id"


# ---------------------------------------------------------------------------
# Invalid operator raises RuleValidationError
# ---------------------------------------------------------------------------


class TestInvalidOperator:
    def test_unknown_operator_raises(self):
        """Operator not in allowlist fails validation."""
        cond = _make_condition(operator="LIKE")
        rule = _make_rule(cond)
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "invalid_operator"
        assert "LIKE" in str(exc_info.value)

    @pytest.mark.parametrize(
        "op", ["==", "!=", ">=", "<=", ">", "<", "in", "not_in"]
    )
    def test_valid_operators_pass(self, op: str):
        """All MVP allowlist operators pass validation."""
        cond = _make_condition(operator=op)
        rule = _make_rule(cond)
        validate_rule(rule)


# ---------------------------------------------------------------------------
# Condition field_id not in required_field_ids raises RuleValidationError
# ---------------------------------------------------------------------------


class TestFieldNotInRequired:
    def test_field_id_not_in_required_raises(self):
        """Condition referencing field_id absent from required_field_ids fails."""
        cond = _make_condition("c1", "field_a")
        # required_field_ids does NOT include field_a
        rule = _make_rule(cond, required_field_ids=("field_b",))
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "field_not_in_required"
        assert "field_a" in str(exc_info.value)

    def test_field_id_in_required_passes(self):
        """Condition field_id present in required_field_ids passes."""
        cond = _make_condition("c1", "field_a")
        rule = _make_rule(cond, required_field_ids=("field_a",))
        validate_rule(rule)


# ---------------------------------------------------------------------------
# Empty source_reference on condition raises RuleValidationError
# ---------------------------------------------------------------------------


class TestEmptySourceReference:
    def test_empty_source_reference_raises(self):
        """Condition with empty source_reference fails."""
        cond = Condition(
            condition_id="c1",
            field_id="field_a",
            operator="==",
            expected="value",
            label="Test",
            source_reference="",
        )
        rule = _make_rule(cond)
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "missing_source_reference"

    def test_present_source_reference_passes(self):
        """Condition with non-empty source_reference passes."""
        cond = _make_condition(source_reference="official_doc_123")
        rule = _make_rule(cond)
        validate_rule(rule)


# ---------------------------------------------------------------------------
# Extra required_field_ids (not used by conditions) raises RuleValidationError
# ---------------------------------------------------------------------------


class TestExtraRequiredFieldIds:
    def test_extra_required_field_ids_raises(self):
        """required_field_ids listing field not in any leaf condition fails."""
        cond = _make_condition("c1", "field_a")
        rule = _make_rule(cond, required_field_ids=("field_a", "field_x"))
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "extra_required_field_ids"
        assert "field_x" in str(exc_info.value)

    def test_exact_required_field_ids_passes(self):
        """required_field_ids matching leaf field_ids exactly passes."""
        root = AllOf(
            children=(
                _make_condition("c1", "field_a"),
                _make_condition("c2", "field_b"),
            )
        )
        rule = _make_rule(root, required_field_ids=("field_a", "field_b"))
        validate_rule(rule)


# ---------------------------------------------------------------------------
# Unrecognized dsl_version raises RuleValidationError
# ---------------------------------------------------------------------------


class TestUnrecognizedDslVersion:
    def test_unsupported_dsl_version_raises(self):
        """Unknown DSL version fails validation."""
        cond = _make_condition()
        rule = _make_rule(cond, dsl_version="99.0")
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "unsupported_dsl_version"
        assert "99.0" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Nested tree validation (deeply nested AllOf/AnyOf/Condition)
# ---------------------------------------------------------------------------


class TestNestedTreeValidation:
    def test_deeply_nested_valid_tree(self):
        """Deeply nested AllOf/AnyOf tree passes validation."""
        root = AllOf(
            children=(
                AnyOf(
                    children=(
                        AllOf(
                            children=(
                                _make_condition("c1", "field_a"),
                                _make_condition("c2", "field_b"),
                            )
                        ),
                        _make_condition("c3", "field_c"),
                    )
                ),
                _make_condition("c4", "field_d"),
            )
        )
        rule = _make_rule(root)
        validate_rule(rule)

    def test_nested_empty_group_raises(self):
        """Empty group nested inside valid group fails."""
        root = AllOf(
            children=(
                _make_condition("c1", "field_a"),
                AnyOf(children=()),
            )
        )
        rule = _make_rule(root, required_field_ids=("field_a",))
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "group_empty"

    def test_nested_duplicate_condition_id_raises(self):
        """Duplicate ID deeply nested still detected."""
        root = AllOf(
            children=(
                AnyOf(
                    children=(
                        AllOf(
                            children=(
                                _make_condition("c1", "field_a"),
                            )
                        ),
                    )
                ),
                _make_condition("c1", "field_b"),
            )
        )
        rule = _make_rule(root)
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "duplicate_condition_id"

    def test_nested_invalid_operator_raises(self):
        """Invalid operator in deeply nested condition detected."""
        root = AllOf(
            children=(
                _make_condition("c1", "field_a"),
                AnyOf(
                    children=(
                        _make_condition("c2", "field_b", operator="BETWEEN"),
                    )
                ),
            )
        )
        rule = _make_rule(root, required_field_ids=("field_a", "field_b"))
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "invalid_operator"

    def test_nested_empty_source_reference_raises(self):
        """Empty source_reference in deeply nested condition detected."""
        root = AnyOf(
            children=(
                AllOf(
                    children=(
                        Condition(
                            condition_id="c1",
                            field_id="field_a",
                            operator="==",
                            expected="v",
                            label="deep",
                            source_reference="",
                        ),
                    )
                ),
            )
        )
        rule = _make_rule(root, required_field_ids=("field_a",))
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "missing_source_reference"

    def test_multiple_conditions_same_field_passes(self):
        """Multiple conditions referencing same field_id is valid."""
        root = AllOf(
            children=(
                _make_condition("c1", "field_a", operator=">=", expected=18),
                _make_condition("c2", "field_a", operator="<=", expected=65),
            )
        )
        rule = _make_rule(root, required_field_ids=("field_a",))
        validate_rule(rule)


# ---------------------------------------------------------------------------
# Invalid node type raises RuleValidationError
# ---------------------------------------------------------------------------


class TestInvalidNodeType:
    def test_non_dsl_object_as_root_raises(self):
        """Passing a non-DSL object as root raises RuleValidationError."""
        # Use a plain string as an invalid node
        rule = RuleDefinition(
            rule_id="rule_1",
            item_id="item_1",
            version=1,
            dsl_version=DSL_VERSION,
            required_field_ids=(),
            root="not_a_valid_node",  # type: ignore[arg-type]
            source_references=("src_ref_1",),
        )
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "invalid_node_type"

    def test_invalid_node_nested_in_group_raises(self):
        """Invalid node type nested in AllOf children raises RuleValidationError."""
        root = AllOf(
            children=(
                _make_condition("c1", "field_a"),
                42,  # type: ignore[arg-type]
            )
        )
        rule = _make_rule(root, required_field_ids=("field_a",))
        with pytest.raises(RuleValidationError) as exc_info:
            validate_rule(rule)
        assert exc_info.value.code == "invalid_node_type"
