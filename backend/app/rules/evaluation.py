"""Higher-level evaluation orchestration.

Checks required fields BEFORE recursive evaluation, maps EvaluationResult to
EligibilityDecision, and handles approved amount mapping. No DB access, no
hardcoded program-specific logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.orchestration.data_contracts import EligibilityDecision
from app.rules.dsl import RuleDefinition
from app.rules.evaluator import EvaluationResult, UserAttributes, evaluate_rule


@dataclass(frozen=True, slots=True)
class ApprovedAmount:
    """Approved amount quartet for a benefit program.

    Only used when a human reviewer has explicitly approved the amount range.
    NEVER parsed from citation text, labels, or excerpts.
    """

    amount_min: int
    amount_max: int
    amount_period: str  # matches AmountPeriod literal
    amount_currency: str


def evaluate_eligibility(
    rule: RuleDefinition,
    user_attributes: UserAttributes,
    approved_amount: ApprovedAmount | None = None,
) -> EligibilityDecision:
    """Evaluate eligibility for a single rule against user attributes.

    1. If any required field is missing, returns immediately with
       status="needs_information" and sorted missing field IDs.
       No recursive evaluation happens.

    2. If all fields are present, evaluates the rule tree and maps:
       - satisfied=True  → status="eligible"
       - satisfied=False → status="ineligible"

    3. Amount is included only when provided AND rule is satisfied.

    Parameters
    ----------
    rule : RuleDefinition
        The rule definition containing required_field_ids and root node.
    user_attributes : UserAttributes
        Mapping of field_id -> attribute value for the user.
    approved_amount : ApprovedAmount | None
        Optional pre-approved amount quartet. Never parsed from text.

    Returns
    -------
    EligibilityDecision
        The eligibility decision with structured reasons and amount.
    """
    # Step 1: Check required fields BEFORE any evaluation
    provided_keys = set(user_attributes.keys())
    required_set = set(rule.required_field_ids)
    missing = required_set - provided_keys

    if missing:
        # Return immediately — no recursive evaluation
        return EligibilityDecision(
            item_id=rule.item_id,
            status="needs_information",
            amount_min=None,
            amount_max=None,
            amount_period=None,
            amount_currency=None,
            missing_field_ids=tuple(sorted(missing)),
            reasons=(),
        )

    # Step 2: Full evaluation
    result: EvaluationResult = evaluate_rule(rule.root, user_attributes)

    status = "eligible" if result.satisfied else "ineligible"

    # Step 3: Amount mapping — only when approved AND eligible
    if approved_amount is not None and result.satisfied:
        return EligibilityDecision(
            item_id=rule.item_id,
            status=status,
            amount_min=approved_amount.amount_min,
            amount_max=approved_amount.amount_max,
            amount_period=approved_amount.amount_period,
            amount_currency=approved_amount.amount_currency,
            missing_field_ids=(),
            reasons=result.reasons,
        )

    # No amount: either not provided or not satisfied
    return EligibilityDecision(
        item_id=rule.item_id,
        status=status,
        amount_min=None,
        amount_max=None,
        amount_period=None,
        amount_currency=None,
        missing_field_ids=(),
        reasons=result.reasons,
    )
