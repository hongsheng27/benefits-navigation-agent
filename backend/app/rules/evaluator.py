"""Pure deterministic recursive Rule DSL evaluator.

Takes a RuleNode (from dsl.py) and a UserAttributes mapping, returns a boolean
result plus collected StructuredReason items. No eval(), no DB access, no
program ID branches, no hardcoded thresholds/deadlines/amounts.

Same inputs always produce same output (referential transparency).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.orchestration.data_contracts import FrozenValue, StructuredReason
from app.rules.dsl import AllOf, AnyOf, Condition, RuleNode

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

UserAttributes = Mapping[str, Any]
"""User attributes mapping: field_id -> attribute value."""


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Result of evaluating a RuleNode tree against user attributes."""

    satisfied: bool
    reasons: tuple[StructuredReason, ...]


# ---------------------------------------------------------------------------
# Operator dispatch table
# ---------------------------------------------------------------------------

# Explicit dispatch: no eval(), no exec(), no getattr() on user code.


def _op_eq(actual: Any, expected: FrozenValue) -> bool:
    return actual == expected


def _op_ne(actual: Any, expected: FrozenValue) -> bool:
    return actual != expected


def _op_ge(actual: Any, expected: FrozenValue) -> bool:
    return actual >= expected  # type: ignore[operator]


def _op_le(actual: Any, expected: FrozenValue) -> bool:
    return actual <= expected  # type: ignore[operator]


def _op_gt(actual: Any, expected: FrozenValue) -> bool:
    return actual > expected  # type: ignore[operator]


def _op_lt(actual: Any, expected: FrozenValue) -> bool:
    return actual < expected  # type: ignore[operator]


def _op_in(actual: Any, expected: FrozenValue) -> bool:
    """Value is in the expected collection (tuple)."""
    if not isinstance(expected, tuple):
        return actual == expected
    return actual in expected


def _op_not_in(actual: Any, expected: FrozenValue) -> bool:
    """Value is not in the expected collection (tuple)."""
    if not isinstance(expected, tuple):
        return actual != expected
    return actual not in expected


_OPERATOR_DISPATCH: dict[str, object] = {
    "==": _op_eq,
    "!=": _op_ne,
    ">=": _op_ge,
    "<=": _op_le,
    ">": _op_gt,
    "<": _op_lt,
    "in": _op_in,
    "not_in": _op_not_in,
}


# ---------------------------------------------------------------------------
# Internal recursive evaluation
# ---------------------------------------------------------------------------


def _evaluate_condition(
    condition: Condition, user_attributes: UserAttributes
) -> EvaluationResult:
    """Evaluate a single leaf Condition node."""
    actual = user_attributes.get(condition.field_id)
    op_fn = _OPERATOR_DISPATCH.get(condition.operator)

    if op_fn is None:
        # Unknown operator: treat as unsatisfied (caller should validate DSL)
        reason = StructuredReason(
            condition_id=condition.condition_id,
            field_id=condition.field_id,
            operator=condition.operator,
            expected=condition.expected,
            actual=actual,
            label=condition.label,
            source_reference=condition.source_reference,
        )
        return EvaluationResult(satisfied=False, reasons=(reason,))

    satisfied = op_fn(actual, condition.expected)

    reason = StructuredReason(
        condition_id=condition.condition_id,
        field_id=condition.field_id,
        operator=condition.operator,
        expected=condition.expected,
        actual=actual,
        label=condition.label,
        source_reference=condition.source_reference,
    )
    return EvaluationResult(satisfied=satisfied, reasons=(reason,))


def _evaluate_node(node: RuleNode, user_attributes: UserAttributes) -> EvaluationResult:
    """Recursively evaluate a RuleNode tree."""
    if isinstance(node, Condition):
        return _evaluate_condition(node, user_attributes)

    if isinstance(node, AllOf):
        # All children must be true for overall true.
        all_reasons: list[StructuredReason] = []
        all_satisfied = True
        false_reasons: list[StructuredReason] = []

        for child in node.children:
            child_result = _evaluate_node(child, user_attributes)
            all_reasons.extend(child_result.reasons)
            if not child_result.satisfied:
                all_satisfied = False
                false_reasons.extend(child_result.reasons)

        if all_satisfied:
            # Success: collect all evaluated conditions for traceability
            return EvaluationResult(satisfied=True, reasons=tuple(all_reasons))
        else:
            # Failure: collect all direct/nested leaves that caused false
            return EvaluationResult(satisfied=False, reasons=tuple(false_reasons))

    if isinstance(node, AnyOf):
        # At least one child must be true for overall true.
        all_false_reasons: list[StructuredReason] = []
        first_true_reasons: tuple[StructuredReason, ...] = ()

        for child in node.children:
            child_result = _evaluate_node(child, user_attributes)
            if child_result.satisfied:
                # Success: collect reasons from the satisfied branch
                first_true_reasons = child_result.reasons
                break
            else:
                # Collect each alternative's decisive false leaves
                all_false_reasons.extend(child_result.reasons)

        if first_true_reasons:
            return EvaluationResult(satisfied=True, reasons=first_true_reasons)
        else:
            # All alternatives failed
            return EvaluationResult(satisfied=False, reasons=tuple(all_false_reasons))

    # Should not reach here with valid DSL nodes
    return EvaluationResult(satisfied=False, reasons=())  # pragma: no cover


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_rule(root: RuleNode, user_attributes: UserAttributes) -> EvaluationResult:
    """Evaluate a Rule DSL tree against user attributes.

    Pure function: same inputs always produce same output.

    Parameters
    ----------
    root : RuleNode
        The root node of a validated Rule DSL tree (AllOf, AnyOf, or Condition).
    user_attributes : UserAttributes
        Mapping of field_id -> attribute value for the user being evaluated.

    Returns
    -------
    EvaluationResult
        Whether the rule is satisfied, plus collected StructuredReason items.
    """
    return _evaluate_node(root, user_attributes)
