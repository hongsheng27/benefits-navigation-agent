"""Unit tests for the pure deterministic Rule DSL evaluator.

Covers all 8 operators, nested all_of/any_of logic, reason collection,
and type handling.
"""

from __future__ import annotations

import pytest

from app.orchestration.data_contracts import StructuredReason
from app.rules.dsl import AllOf, AnyOf, Condition
from app.rules.evaluator import evaluate_rule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cond(
    field_id: str,
    operator: str,
    expected: object,
    *,
    condition_id: str = "c1",
    label: str = "test condition",
    source_reference: str = "ref-001",
) -> Condition:
    """Shorthand to create a Condition node."""
    return Condition(
        condition_id=condition_id,
        field_id=field_id,
        operator=operator,
        expected=expected,
        label=label,
        source_reference=source_reference,
    )


# ---------------------------------------------------------------------------
# Operator tests: all 8 operators with valid typed values
# ---------------------------------------------------------------------------


class TestOperatorEquals:
    def test_string_equal(self) -> None:
        result = evaluate_rule(
            _cond("city", "==", "Taipei"),
            {"city": "Taipei"},
        )
        assert result.satisfied is True

    def test_string_not_equal(self) -> None:
        result = evaluate_rule(
            _cond("city", "==", "Taipei"),
            {"city": "Kaohsiung"},
        )
        assert result.satisfied is False

    def test_int_equal(self) -> None:
        result = evaluate_rule(
            _cond("age", "==", 65),
            {"age": 65},
        )
        assert result.satisfied is True


class TestOperatorNotEquals:
    def test_different_values(self) -> None:
        result = evaluate_rule(
            _cond("status", "!=", "inactive"),
            {"status": "active"},
        )
        assert result.satisfied is True

    def test_same_values(self) -> None:
        result = evaluate_rule(
            _cond("status", "!=", "active"),
            {"status": "active"},
        )
        assert result.satisfied is False


class TestOperatorGreaterThanOrEqual:
    def test_equal(self) -> None:
        result = evaluate_rule(_cond("age", ">=", 65), {"age": 65})
        assert result.satisfied is True

    def test_greater(self) -> None:
        result = evaluate_rule(_cond("age", ">=", 65), {"age": 70})
        assert result.satisfied is True

    def test_less(self) -> None:
        result = evaluate_rule(_cond("age", ">=", 65), {"age": 60})
        assert result.satisfied is False


class TestOperatorLessThanOrEqual:
    def test_equal(self) -> None:
        result = evaluate_rule(_cond("income", "<=", 50000), {"income": 50000})
        assert result.satisfied is True

    def test_less(self) -> None:
        result = evaluate_rule(_cond("income", "<=", 50000), {"income": 30000})
        assert result.satisfied is True

    def test_greater(self) -> None:
        result = evaluate_rule(_cond("income", "<=", 50000), {"income": 60000})
        assert result.satisfied is False


class TestOperatorGreaterThan:
    def test_greater(self) -> None:
        result = evaluate_rule(_cond("days", ">", 30), {"days": 31})
        assert result.satisfied is True

    def test_equal(self) -> None:
        result = evaluate_rule(_cond("days", ">", 30), {"days": 30})
        assert result.satisfied is False

    def test_less(self) -> None:
        result = evaluate_rule(_cond("days", ">", 30), {"days": 29})
        assert result.satisfied is False


class TestOperatorLessThan:
    def test_less(self) -> None:
        result = evaluate_rule(_cond("days", "<", 90), {"days": 89})
        assert result.satisfied is True

    def test_equal(self) -> None:
        result = evaluate_rule(_cond("days", "<", 90), {"days": 90})
        assert result.satisfied is False

    def test_greater(self) -> None:
        result = evaluate_rule(_cond("days", "<", 90), {"days": 91})
        assert result.satisfied is False


class TestOperatorIn:
    def test_value_in_tuple(self) -> None:
        result = evaluate_rule(
            _cond("remains_type", "in", ("ash", "bone", "eco")),
            {"remains_type": "ash"},
        )
        assert result.satisfied is True

    def test_value_not_in_tuple(self) -> None:
        result = evaluate_rule(
            _cond("remains_type", "in", ("ash", "bone", "eco")),
            {"remains_type": "other"},
        )
        assert result.satisfied is False

    def test_value_in_single_element_tuple(self) -> None:
        result = evaluate_rule(
            _cond("type", "in", ("only_one",)),
            {"type": "only_one"},
        )
        assert result.satisfied is True


class TestOperatorNotIn:
    def test_value_not_in_tuple(self) -> None:
        result = evaluate_rule(
            _cond("status", "not_in", ("rejected", "inactive")),
            {"status": "active"},
        )
        assert result.satisfied is True

    def test_value_in_tuple(self) -> None:
        result = evaluate_rule(
            _cond("status", "not_in", ("rejected", "inactive")),
            {"status": "rejected"},
        )
        assert result.satisfied is False


# ---------------------------------------------------------------------------
# Nested all_of tests
# ---------------------------------------------------------------------------


class TestAllOf:
    def test_all_children_true(self) -> None:
        tree = AllOf(
            children=(
                _cond("age", ">=", 65, condition_id="c1"),
                _cond("city", "==", "Taipei", condition_id="c2"),
                _cond("registered", "==", True, condition_id="c3"),
            )
        )
        result = evaluate_rule(tree, {"age": 70, "city": "Taipei", "registered": True})
        assert result.satisfied is True
        assert len(result.reasons) == 3

    def test_one_child_false(self) -> None:
        tree = AllOf(
            children=(
                _cond("age", ">=", 65, condition_id="c1"),
                _cond("city", "==", "Taipei", condition_id="c2"),
                _cond("registered", "==", True, condition_id="c3"),
            )
        )
        result = evaluate_rule(
            tree, {"age": 70, "city": "Kaohsiung", "registered": True}
        )
        assert result.satisfied is False
        # Only the false condition's reasons are collected
        assert len(result.reasons) == 1
        assert result.reasons[0].condition_id == "c2"

    def test_multiple_children_false(self) -> None:
        tree = AllOf(
            children=(
                _cond("age", ">=", 65, condition_id="c1"),
                _cond("city", "==", "Taipei", condition_id="c2"),
            )
        )
        result = evaluate_rule(tree, {"age": 30, "city": "Kaohsiung"})
        assert result.satisfied is False
        assert len(result.reasons) == 2


# ---------------------------------------------------------------------------
# Nested any_of tests
# ---------------------------------------------------------------------------


class TestAnyOf:
    def test_all_false(self) -> None:
        tree = AnyOf(
            children=(
                _cond("type", "==", "ash", condition_id="c1"),
                _cond("type", "==", "bone", condition_id="c2"),
                _cond("type", "==", "eco", condition_id="c3"),
            )
        )
        result = evaluate_rule(tree, {"type": "other"})
        assert result.satisfied is False
        # All alternatives' reasons collected
        assert len(result.reasons) == 3

    def test_one_true(self) -> None:
        tree = AnyOf(
            children=(
                _cond("type", "==", "ash", condition_id="c1"),
                _cond("type", "==", "bone", condition_id="c2"),
                _cond("type", "==", "eco", condition_id="c3"),
            )
        )
        result = evaluate_rule(tree, {"type": "bone"})
        assert result.satisfied is True
        # Only the satisfied branch's reason
        assert len(result.reasons) == 1
        assert result.reasons[0].condition_id == "c2"

    def test_first_child_true(self) -> None:
        tree = AnyOf(
            children=(
                _cond("type", "==", "ash", condition_id="c1"),
                _cond("type", "==", "bone", condition_id="c2"),
            )
        )
        result = evaluate_rule(tree, {"type": "ash"})
        assert result.satisfied is True
        assert result.reasons[0].condition_id == "c1"


# ---------------------------------------------------------------------------
# Deeply nested tree (all_of containing any_of containing conditions)
# ---------------------------------------------------------------------------


class TestDeeplyNested:
    def test_all_of_containing_any_of_satisfied(self) -> None:
        """all_of([age >= 65, any_of([city == Taipei, city == Kaohsiung])])"""
        tree = AllOf(
            children=(
                _cond("age", ">=", 65, condition_id="c1"),
                AnyOf(
                    children=(
                        _cond("city", "==", "Taipei", condition_id="c2"),
                        _cond("city", "==", "Kaohsiung", condition_id="c3"),
                    )
                ),
            )
        )
        result = evaluate_rule(tree, {"age": 70, "city": "Kaohsiung"})
        assert result.satisfied is True

    def test_all_of_containing_any_of_not_satisfied(self) -> None:
        """all_of fails because inner any_of fails."""
        tree = AllOf(
            children=(
                _cond("age", ">=", 65, condition_id="c1"),
                AnyOf(
                    children=(
                        _cond("city", "==", "Taipei", condition_id="c2"),
                        _cond("city", "==", "Kaohsiung", condition_id="c3"),
                    )
                ),
            )
        )
        result = evaluate_rule(tree, {"age": 70, "city": "Tainan"})
        assert result.satisfied is False
        # Reasons from the failed any_of branch
        condition_ids = {r.condition_id for r in result.reasons}
        assert "c2" in condition_ids
        assert "c3" in condition_ids

    def test_any_of_containing_all_of(self) -> None:
        """any_of([all_of([age >= 65, eco == True]), income <= 20000])"""
        tree = AnyOf(
            children=(
                AllOf(
                    children=(
                        _cond("age", ">=", 65, condition_id="c1"),
                        _cond("eco", "==", True, condition_id="c2"),
                    )
                ),
                _cond("income", "<=", 20000, condition_id="c3"),
            )
        )
        # First branch fails (eco is False), second branch succeeds
        result = evaluate_rule(tree, {"age": 70, "eco": False, "income": 15000})
        assert result.satisfied is True
        assert result.reasons[0].condition_id == "c3"


# ---------------------------------------------------------------------------
# Operator type handling (int/float/str comparisons)
# ---------------------------------------------------------------------------


class TestTypeHandling:
    def test_float_comparison(self) -> None:
        result = evaluate_rule(_cond("income", "<=", 50000.5), {"income": 50000.0})
        assert result.satisfied is True

    def test_int_float_cross_comparison(self) -> None:
        result = evaluate_rule(_cond("amount", ">=", 1000), {"amount": 1000.0})
        assert result.satisfied is True

    def test_string_ordering(self) -> None:
        # Lexicographic comparison
        result = evaluate_rule(
            _cond("date", ">=", "2024-01-01"), {"date": "2024-06-15"}
        )
        assert result.satisfied is True

    def test_none_attribute_equals(self) -> None:
        result = evaluate_rule(_cond("field", "==", None), {"field": None})
        assert result.satisfied is True

    def test_missing_attribute_is_none(self) -> None:
        # When field is missing from user_attributes, get() returns None
        result = evaluate_rule(_cond("missing_field", "==", None), {})
        assert result.satisfied is True


# ---------------------------------------------------------------------------
# Reason structure correctness
# ---------------------------------------------------------------------------


class TestReasonStructure:
    def test_reasons_include_correct_fields(self) -> None:
        cond = Condition(
            condition_id="cond-age-check",
            field_id="applicant_age",
            operator=">=",
            expected=65,
            label="申請者年齡需滿 65 歲",
            source_reference="ref-taipei-elderly-001",
        )
        result = evaluate_rule(cond, {"applicant_age": 70})
        assert result.satisfied is True
        assert len(result.reasons) == 1

        reason = result.reasons[0]
        assert reason.condition_id == "cond-age-check"
        assert reason.field_id == "applicant_age"
        assert reason.operator == ">="
        assert reason.expected == 65
        assert reason.actual == 70
        assert reason.label == "申請者年齡需滿 65 歲"
        assert reason.source_reference == "ref-taipei-elderly-001"

    def test_failed_reason_captures_actual(self) -> None:
        cond = Condition(
            condition_id="cond-income",
            field_id="household_income",
            operator="<=",
            expected=30000,
            label="家庭月收入不得超過三萬",
            source_reference="ref-income-limit",
        )
        result = evaluate_rule(cond, {"household_income": 50000})
        assert result.satisfied is False
        assert result.reasons[0].actual == 50000
        assert result.reasons[0].expected == 30000

    def test_reason_is_structured_reason_instance(self) -> None:
        result = evaluate_rule(_cond("x", "==", 1), {"x": 1})
        assert isinstance(result.reasons[0], StructuredReason)


# ---------------------------------------------------------------------------
# EvaluationResult is frozen
# ---------------------------------------------------------------------------


class TestEvaluationResultImmutability:
    def test_frozen(self) -> None:
        result = evaluate_rule(_cond("x", "==", 1), {"x": 1})
        with pytest.raises(AttributeError):
            result.satisfied = False  # type: ignore[misc]

    def test_reasons_tuple(self) -> None:
        result = evaluate_rule(_cond("x", "==", 1), {"x": 1})
        assert isinstance(result.reasons, tuple)


# ---------------------------------------------------------------------------
# 3-level nesting: all_of(any_of(all_of(...))) deep nesting
# ---------------------------------------------------------------------------


class TestThreeLevelNesting:
    """Verify evaluator handles 3+ levels of nested boolean groups."""

    def test_all_of_any_of_all_of_satisfied(self) -> None:
        """all_of([any_of([all_of([c1, c2]), c3]), c4]) — satisfied path."""
        tree = AllOf(
            children=(
                AnyOf(
                    children=(
                        AllOf(
                            children=(
                                _cond("score", ">=", 80, condition_id="c1"),
                                _cond("level", "==", "advanced", condition_id="c2"),
                            )
                        ),
                        _cond("vip", "==", True, condition_id="c3"),
                    )
                ),
                _cond("active", "==", True, condition_id="c4"),
            )
        )
        # Inner all_of satisfied, outer all_of satisfied
        result = evaluate_rule(
            tree, {"score": 90, "level": "advanced", "vip": False, "active": True}
        )
        assert result.satisfied is True

    def test_all_of_any_of_all_of_fallback_to_alternative(self) -> None:
        """all_of([any_of([all_of([c1, c2]), c3]), c4]) — first alternative fails, second succeeds."""
        tree = AllOf(
            children=(
                AnyOf(
                    children=(
                        AllOf(
                            children=(
                                _cond("score", ">=", 80, condition_id="c1"),
                                _cond("level", "==", "advanced", condition_id="c2"),
                            )
                        ),
                        _cond("vip", "==", True, condition_id="c3"),
                    )
                ),
                _cond("active", "==", True, condition_id="c4"),
            )
        )
        # Inner all_of fails (score too low), but vip=True satisfies any_of
        result = evaluate_rule(
            tree, {"score": 50, "level": "basic", "vip": True, "active": True}
        )
        assert result.satisfied is True
        # Reason from c3 (the vip condition) should be present
        condition_ids = {r.condition_id for r in result.reasons}
        assert "c3" in condition_ids

    def test_all_of_any_of_all_of_fully_unsatisfied(self) -> None:
        """all_of([any_of([all_of([c1, c2]), c3]), c4]) — both alternatives fail."""
        tree = AllOf(
            children=(
                AnyOf(
                    children=(
                        AllOf(
                            children=(
                                _cond("score", ">=", 80, condition_id="c1"),
                                _cond("level", "==", "advanced", condition_id="c2"),
                            )
                        ),
                        _cond("vip", "==", True, condition_id="c3"),
                    )
                ),
                _cond("active", "==", True, condition_id="c4"),
            )
        )
        # Neither inner all_of nor c3 is satisfied, and active is False
        result = evaluate_rule(
            tree, {"score": 50, "level": "basic", "vip": False, "active": False}
        )
        assert result.satisfied is False

    def test_any_of_all_of_any_of_nesting(self) -> None:
        """any_of([all_of([any_of([c1, c2]), c3]), c4]) — 3-level nesting."""
        tree = AnyOf(
            children=(
                AllOf(
                    children=(
                        AnyOf(
                            children=(
                                _cond("tier", "==", "gold", condition_id="c1"),
                                _cond("tier", "==", "platinum", condition_id="c2"),
                            )
                        ),
                        _cond("years", ">=", 5, condition_id="c3"),
                    )
                ),
                _cond("override", "==", True, condition_id="c4"),
            )
        )
        # First branch: inner any_of satisfied (tier=gold), c3 satisfied (years=10)
        result = evaluate_rule(
            tree, {"tier": "gold", "years": 10, "override": False}
        )
        assert result.satisfied is True


# ---------------------------------------------------------------------------
# Invalid/incompatible type handling
# ---------------------------------------------------------------------------


class TestIncompatibleTypes:
    """Verify behavior when incompatible types are compared."""

    def test_string_gt_int_raises_type_error(self) -> None:
        """Comparing str > int raises TypeError (Python semantics)."""
        with pytest.raises(TypeError):
            evaluate_rule(_cond("field_x", ">", 10), {"field_x": "not_a_number"})

    def test_none_gt_int_raises_type_error(self) -> None:
        """Comparing None > int raises TypeError."""
        with pytest.raises(TypeError):
            evaluate_rule(_cond("field_x", ">", 10), {"field_x": None})

    def test_none_ge_int_raises_type_error(self) -> None:
        """Comparing None >= int raises TypeError."""
        with pytest.raises(TypeError):
            evaluate_rule(_cond("field_x", ">=", 5), {"field_x": None})


# ---------------------------------------------------------------------------
# Edge case: `in` operator with empty tuple
# ---------------------------------------------------------------------------


class TestInOperatorEmptyTuple:
    """Verify `in` operator behavior with empty expected tuple."""

    def test_value_in_empty_tuple_is_false(self) -> None:
        """Any value `in` empty tuple is always False."""
        result = evaluate_rule(
            _cond("category", "in", ()),
            {"category": "anything"},
        )
        assert result.satisfied is False

    def test_none_in_empty_tuple_is_false(self) -> None:
        """None `in` empty tuple is False."""
        result = evaluate_rule(
            _cond("category", "in", ()),
            {"category": None},
        )
        assert result.satisfied is False

    def test_not_in_empty_tuple_is_true(self) -> None:
        """Any value `not_in` empty tuple is always True."""
        result = evaluate_rule(
            _cond("category", "not_in", ()),
            {"category": "anything"},
        )
        assert result.satisfied is True


# ---------------------------------------------------------------------------
# Unknown operator handling
# ---------------------------------------------------------------------------


class TestUnknownOperator:
    """Verify evaluator handles unknown operators gracefully."""

    def test_unknown_operator_returns_unsatisfied(self) -> None:
        """Unknown operator yields satisfied=False with reason."""
        result = evaluate_rule(
            _cond("field_x", "LIKE", "%pattern%"),
            {"field_x": "some_pattern"},
        )
        assert result.satisfied is False
        assert len(result.reasons) == 1
        assert result.reasons[0].operator == "LIKE"

    def test_unknown_operator_captures_actual_value(self) -> None:
        """Unknown operator reason still captures the actual value."""
        result = evaluate_rule(
            _cond("field_x", "BETWEEN", (1, 100)),
            {"field_x": 50},
        )
        assert result.satisfied is False
        assert result.reasons[0].actual == 50
