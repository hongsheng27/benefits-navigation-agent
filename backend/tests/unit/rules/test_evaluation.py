"""Unit tests for app.rules.evaluation — higher-level evaluation orchestration.

Covers:
- Missing required field → needs_information with sorted missing IDs
- All fields present → runs evaluation, returns eligible/ineligible
- StructuredReason correctly propagated from evaluator
- Amount included when approved and eligible
- Amount NOT included when approved but ineligible
- Amount NOT included when not provided
- Amount all-None invariant (no partial amounts)
- Multiple missing fields → all listed, sorted, deduplicated
- Empty user_attributes with required fields → all listed as missing
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.orchestration.data_contracts import StructuredReason
from app.rules.dsl import AllOf, Condition, RuleDefinition
from app.rules.evaluation import ApprovedAmount, evaluate_eligibility

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_condition(
    condition_id: str = "c1",
    field_id: str = "age",
    operator: str = ">=",
    expected: int = 18,
    label: str = "年滿 18 歲",
    source_reference: str = "ref-001",
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
    conditions: tuple[Condition, ...] | None = None,
    required_field_ids: tuple[str, ...] | None = None,
    item_id: str = "item-001",
) -> RuleDefinition:
    """Create a simple RuleDefinition with AllOf root."""
    if conditions is None:
        conditions = (_make_condition(),)
    if required_field_ids is None:
        required_field_ids = tuple(c.field_id for c in conditions)
    return RuleDefinition(
        rule_id="rule-001",
        item_id=item_id,
        version=1,
        dsl_version="1.0",
        required_field_ids=required_field_ids,
        root=AllOf(children=conditions),
        source_references=("ref-001",),
    )


def _make_amount() -> ApprovedAmount:
    return ApprovedAmount(
        amount_min=5000,
        amount_max=10000,
        amount_period="monthly",
        amount_currency="TWD",
    )


# ---------------------------------------------------------------------------
# Missing required fields → needs_information, NO evaluation
# ---------------------------------------------------------------------------


class TestMissingRequiredFields:
    """When required fields are missing, return needs_information immediately."""

    def test_single_missing_field(self) -> None:
        rule = _make_rule()
        # user_attributes is empty — "age" is missing
        decision = evaluate_eligibility(rule, {})

        assert decision.status == "needs_information"
        assert decision.missing_field_ids == ("age",)
        assert decision.amount_min is None
        assert decision.amount_max is None
        assert decision.amount_period is None
        assert decision.amount_currency is None
        assert decision.reasons == ()

    def test_multiple_missing_fields_sorted_deduplicated(self) -> None:
        conditions = (
            _make_condition(condition_id="c1", field_id="income"),
            _make_condition(condition_id="c2", field_id="age"),
            _make_condition(condition_id="c3", field_id="income"),  # duplicate
        )
        rule = _make_rule(
            conditions=conditions,
            required_field_ids=("income", "age"),
        )
        decision = evaluate_eligibility(rule, {})

        assert decision.status == "needs_information"
        # Sorted and deduplicated
        assert decision.missing_field_ids == ("age", "income")
        assert decision.reasons == ()

    def test_empty_user_attributes_all_fields_missing(self) -> None:
        conditions = (
            _make_condition(condition_id="c1", field_id="age"),
            _make_condition(condition_id="c2", field_id="city"),
            _make_condition(condition_id="c3", field_id="income"),
        )
        rule = _make_rule(
            conditions=conditions,
            required_field_ids=("age", "city", "income"),
        )
        decision = evaluate_eligibility(rule, {})

        assert decision.status == "needs_information"
        assert decision.missing_field_ids == ("age", "city", "income")
        assert decision.reasons == ()

    def test_no_evaluation_happens_when_fields_missing(self) -> None:
        """The recursive Rule Engine call count MUST be zero when fields are missing."""
        rule = _make_rule()

        with patch("app.rules.evaluation.evaluate_rule") as mock_eval:
            decision = evaluate_eligibility(rule, {})

        mock_eval.assert_not_called()
        assert decision.status == "needs_information"

    def test_partial_fields_provided(self) -> None:
        """When some but not all required fields are provided."""
        conditions = (
            _make_condition(condition_id="c1", field_id="age"),
            _make_condition(condition_id="c2", field_id="income"),
        )
        rule = _make_rule(
            conditions=conditions,
            required_field_ids=("age", "income"),
        )
        # Only provide 'age', 'income' is missing
        decision = evaluate_eligibility(rule, {"age": 25})

        assert decision.status == "needs_information"
        assert decision.missing_field_ids == ("income",)
        assert decision.reasons == ()


# ---------------------------------------------------------------------------
# Full evaluation — eligible / ineligible
# ---------------------------------------------------------------------------


class TestFullEvaluation:
    """When all required fields are present, evaluate and return eligible/ineligible."""

    def test_eligible_when_satisfied(self) -> None:
        rule = _make_rule()
        decision = evaluate_eligibility(rule, {"age": 25})

        assert decision.status == "eligible"
        assert decision.missing_field_ids == ()
        assert len(decision.reasons) > 0

    def test_ineligible_when_not_satisfied(self) -> None:
        rule = _make_rule()
        decision = evaluate_eligibility(rule, {"age": 10})

        assert decision.status == "ineligible"
        assert decision.missing_field_ids == ()
        assert len(decision.reasons) > 0

    def test_item_id_propagated(self) -> None:
        rule = _make_rule(item_id="benefit-xyz")
        decision = evaluate_eligibility(rule, {"age": 25})

        assert decision.item_id == "benefit-xyz"


# ---------------------------------------------------------------------------
# StructuredReason propagation
# ---------------------------------------------------------------------------


class TestStructuredReasonPropagation:
    """StructuredReason correctly propagated from evaluator."""

    def test_reasons_contain_condition_details(self) -> None:
        rule = _make_rule()
        decision = evaluate_eligibility(rule, {"age": 25})

        assert len(decision.reasons) == 1
        reason = decision.reasons[0]
        assert isinstance(reason, StructuredReason)
        assert reason.condition_id == "c1"
        assert reason.field_id == "age"
        assert reason.operator == ">="
        assert reason.expected == 18
        assert reason.actual == 25
        assert reason.label == "年滿 18 歲"
        assert reason.source_reference == "ref-001"

    def test_multiple_reasons_from_multiple_conditions(self) -> None:
        conditions = (
            _make_condition(
                condition_id="c1", field_id="age", operator=">=", expected=18
            ),
            _make_condition(
                condition_id="c2", field_id="income", operator="<=", expected=50000
            ),
        )
        rule = _make_rule(
            conditions=conditions,
            required_field_ids=("age", "income"),
        )
        decision = evaluate_eligibility(rule, {"age": 25, "income": 30000})

        assert decision.status == "eligible"
        assert len(decision.reasons) == 2
        condition_ids = {r.condition_id for r in decision.reasons}
        assert condition_ids == {"c1", "c2"}


# ---------------------------------------------------------------------------
# Amount mapping
# ---------------------------------------------------------------------------


class TestAmountMapping:
    """Amount included when approved and eligible, excluded otherwise."""

    def test_amount_included_when_approved_and_eligible(self) -> None:
        rule = _make_rule()
        amount = _make_amount()
        decision = evaluate_eligibility(rule, {"age": 25}, approved_amount=amount)

        assert decision.status == "eligible"
        assert decision.amount_min == 5000
        assert decision.amount_max == 10000
        assert decision.amount_period == "monthly"
        assert decision.amount_currency == "TWD"

    def test_amount_not_included_when_approved_but_ineligible(self) -> None:
        rule = _make_rule()
        amount = _make_amount()
        decision = evaluate_eligibility(rule, {"age": 10}, approved_amount=amount)

        assert decision.status == "ineligible"
        assert decision.amount_min is None
        assert decision.amount_max is None
        assert decision.amount_period is None
        assert decision.amount_currency is None

    def test_amount_not_included_when_not_provided(self) -> None:
        rule = _make_rule()
        decision = evaluate_eligibility(rule, {"age": 25}, approved_amount=None)

        assert decision.status == "eligible"
        assert decision.amount_min is None
        assert decision.amount_max is None
        assert decision.amount_period is None
        assert decision.amount_currency is None

    def test_amount_all_none_invariant_no_partial_amounts(self) -> None:
        """Amount fields are either ALL present or ALL None. No partial."""
        rule = _make_rule()

        # Without approved amount
        decision1 = evaluate_eligibility(rule, {"age": 25})
        amount_fields = (
            decision1.amount_min,
            decision1.amount_max,
            decision1.amount_period,
            decision1.amount_currency,
        )
        present = [f is not None for f in amount_fields]
        assert all(p is False for p in present)

        # With approved amount and eligible
        amount = _make_amount()
        decision2 = evaluate_eligibility(rule, {"age": 25}, approved_amount=amount)
        amount_fields2 = (
            decision2.amount_min,
            decision2.amount_max,
            decision2.amount_period,
            decision2.amount_currency,
        )
        present2 = [f is not None for f in amount_fields2]
        assert all(p is True for p in present2)

    def test_amount_not_included_when_missing_fields(self) -> None:
        """Even if approved_amount is provided, missing fields → no amount."""
        rule = _make_rule()
        amount = _make_amount()
        decision = evaluate_eligibility(rule, {}, approved_amount=amount)

        assert decision.status == "needs_information"
        assert decision.amount_min is None
        assert decision.amount_max is None
        assert decision.amount_period is None
        assert decision.amount_currency is None


# ---------------------------------------------------------------------------
# ApprovedAmount dataclass
# ---------------------------------------------------------------------------


class TestApprovedAmount:
    """ApprovedAmount is frozen and has expected fields."""

    def test_frozen(self) -> None:
        amount = _make_amount()
        try:
            amount.amount_min = 999  # type: ignore[misc]
            raise AssertionError("Should have raised")
        except AttributeError:
            pass

    def test_fields(self) -> None:
        amount = ApprovedAmount(
            amount_min=1000,
            amount_max=2000,
            amount_period="one_time",
            amount_currency="USD",
        )
        assert amount.amount_min == 1000
        assert amount.amount_max == 2000
        assert amount.amount_period == "one_time"
        assert amount.amount_currency == "USD"


# ---------------------------------------------------------------------------
# Amount boundary cases
# ---------------------------------------------------------------------------


class TestAmountBoundaries:
    """Amount min == max (fixed), min < max (range), and min > max (invalid)."""

    def test_fixed_amount_min_equals_max(self) -> None:
        """Fixed amount: min == max is valid and propagated correctly."""
        rule = _make_rule()
        amount = ApprovedAmount(
            amount_min=3000,
            amount_max=3000,
            amount_period="one_time",
            amount_currency="TWD",
        )
        decision = evaluate_eligibility(rule, {"age": 25}, approved_amount=amount)

        assert decision.status == "eligible"
        assert decision.amount_min == 3000
        assert decision.amount_max == 3000
        assert decision.amount_period == "one_time"
        assert decision.amount_currency == "TWD"

    def test_range_amount_min_less_than_max(self) -> None:
        """Range amount: min < max is valid."""
        rule = _make_rule()
        amount = ApprovedAmount(
            amount_min=1000,
            amount_max=5000,
            amount_period="monthly",
            amount_currency="TWD",
        )
        decision = evaluate_eligibility(rule, {"age": 25}, approved_amount=amount)

        assert decision.status == "eligible"
        assert decision.amount_min == 1000
        assert decision.amount_max == 5000

    def test_amount_all_none_for_unknown(self) -> None:
        """Unknown amount: all four fields are None."""
        rule = _make_rule()
        decision = evaluate_eligibility(rule, {"age": 25}, approved_amount=None)

        assert decision.status == "eligible"
        assert decision.amount_min is None
        assert decision.amount_max is None
        assert decision.amount_period is None
        assert decision.amount_currency is None


# ---------------------------------------------------------------------------
# EligibilityDecision __post_init__ validation
# ---------------------------------------------------------------------------


class TestEligibilityDecisionPostInit:
    """EligibilityDecision amount invariants enforced by __post_init__."""

    def test_amount_min_greater_than_max_raises(self) -> None:
        """amount_min > amount_max raises ValueError."""
        from app.orchestration.data_contracts import EligibilityDecision

        with pytest.raises(ValueError, match="amount_min must be <= amount_max"):
            EligibilityDecision(
                item_id="item-001",
                status="eligible",
                amount_min=10000,
                amount_max=5000,
                amount_period="monthly",
                amount_currency="TWD",
                missing_field_ids=(),
                reasons=(),
            )

    def test_partial_amount_raises(self) -> None:
        """Providing some but not all amount fields raises ValueError."""
        from app.orchestration.data_contracts import EligibilityDecision

        with pytest.raises(ValueError, match="amount quartet must be all-or-none"):
            EligibilityDecision(
                item_id="item-001",
                status="eligible",
                amount_min=5000,
                amount_max=10000,
                amount_period=None,
                amount_currency="TWD",
                missing_field_ids=(),
                reasons=(),
            )

    def test_missing_field_ids_sorted_deduped_by_post_init(self) -> None:
        """missing_field_ids are sorted and deduplicated by __post_init__."""
        from app.orchestration.data_contracts import EligibilityDecision

        decision = EligibilityDecision(
            item_id="item-001",
            status="needs_information",
            amount_min=None,
            amount_max=None,
            amount_period=None,
            amount_currency=None,
            missing_field_ids=("income", "age", "income", "city"),
            reasons=(),
        )
        assert decision.missing_field_ids == ("age", "city", "income")


# ---------------------------------------------------------------------------
# Zero engine calls when fields missing
# ---------------------------------------------------------------------------


class TestZeroEngineCallsWhenMissing:
    """Verify the recursive Rule Engine call count is zero when fields are missing."""

    def test_engine_not_called_single_missing(self) -> None:
        """Single missing field: evaluate_rule is never called."""
        rule = _make_rule()
        with patch("app.rules.evaluation.evaluate_rule") as mock_eval:
            evaluate_eligibility(rule, {})
        mock_eval.assert_not_called()

    def test_engine_not_called_multiple_missing(self) -> None:
        """Multiple missing fields: evaluate_rule is never called."""
        conditions = (
            _make_condition(condition_id="c1", field_id="age"),
            _make_condition(condition_id="c2", field_id="income"),
        )
        rule = _make_rule(
            conditions=conditions,
            required_field_ids=("age", "income"),
        )
        with patch("app.rules.evaluation.evaluate_rule") as mock_eval:
            evaluate_eligibility(rule, {"age": 25})  # income still missing
        mock_eval.assert_not_called()
