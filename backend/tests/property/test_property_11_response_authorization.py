"""Property 11: Requesting-user response authorization.

**Validates: Requirements 9.1, 9.2**

Feature: data-layer-rule-engine, Property 11: only the current requesting
user's response retains necessary actual values; every other recipient's
recursive response projection removes them.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel

from app.api.response_mapper import map_to_api_response
from app.orchestration import data_contracts as dc
from app.orchestration import state
from app.privacy.raw_text_scope import AuthorizationContext
from app.schemas.session import DecisiveConditionView, StructuredReasonView

_SYNTHETIC_OPERATORS = ("==", "!=", ">=", "<=", ">", "<", "in", "not_in")
_SYNTHETIC_PERIODS: tuple[dc.AmountPeriod, ...] = (
    "one_time",
    "monthly",
    "annual",
)


@st.composite
def _eligibility_decision(
    draw: st.DrawFn,
    *,
    item_index: int,
) -> dc.EligibilityDecision:
    """Generate one valid decision containing synthetic structured reasons."""
    item_nonce = draw(st.integers(min_value=0, max_value=1_000_000))
    reason_count = draw(st.integers(min_value=1, max_value=4))
    reasons = tuple(
        dc.StructuredReason(
            condition_id=(
                f"synthetic_condition_{item_index}_{reason_index}_{item_nonce}"
            ),
            field_id=f"synthetic_field_{item_index}_{reason_index}",
            operator=draw(st.sampled_from(_SYNTHETIC_OPERATORS)),
            expected=(f"synthetic_expected_{item_index}_{reason_index}_{item_nonce}"),
            actual=f"synthetic_actual_{item_index}_{reason_index}_{item_nonce}",
            label=f"synthetic_label_{item_index}_{reason_index}",
            source_reference=f"synthetic_source_{item_index}_{reason_index}",
        )
        for reason_index in range(reason_count)
    )

    if draw(st.booleans()):
        amount_min = draw(st.integers(min_value=0, max_value=100_000))
        amount_max = draw(st.integers(min_value=amount_min, max_value=100_000))
        amount_period = draw(st.sampled_from(_SYNTHETIC_PERIODS))
        amount_currency = "XTS"
    else:
        amount_min = None
        amount_max = None
        amount_period = None
        amount_currency = None

    return dc.EligibilityDecision(
        item_id=f"synthetic_item_{item_index}_{item_nonce}",
        status=draw(st.sampled_from(("eligible", "ineligible"))),
        amount_min=amount_min,
        amount_max=amount_max,
        amount_period=amount_period,
        amount_currency=amount_currency,
        missing_field_ids=(),
        reasons=reasons,
    )


@st.composite
def _eligibility_decisions(
    draw: st.DrawFn,
) -> tuple[dc.EligibilityDecision, ...]:
    item_count = draw(st.integers(min_value=2, max_value=5))
    return tuple(
        draw(_eligibility_decision(item_index=item_index))
        for item_index in range(item_count)
    )


def _to_workflow_item(
    decision: dc.EligibilityDecision,
    *,
    item_index: int,
) -> state.CandidateItem:
    """Build the legacy-compatible response input from a generated decision."""
    decisive_conditions = tuple(
        state.DecisiveCondition(
            field_id=reason.field_id,
            expected=str(reason.expected),
            actual=str(reason.actual),
        )
        for reason in decision.reasons
    )
    amount_period = (
        state.AmountPeriod(decision.amount_period)
        if decision.amount_period is not None
        else None
    )
    return state.CandidateItem(
        item_id=decision.item_id,
        kind=(
            state.ItemKind.BENEFIT
            if item_index % 2 == 0
            else state.ItemKind.ADMINISTRATIVE
        ),
        status=state.ItemStatus(decision.status),
        program_status="verified",
        decisive_conditions=decisive_conditions,
        amount_min=decision.amount_min,
        amount_max=decision.amount_max,
        amount_period=amount_period,
        amount_currency=decision.amount_currency,
    )


def _iter_projected_actuals(value: object) -> Iterator[tuple[str, object]]:
    """Recursively inspect response models without using mapper implementation logic."""
    if isinstance(value, StructuredReasonView):
        yield "structured", value.actual
        return
    if isinstance(value, DecisiveConditionView):
        yield "legacy", value.actual
        return
    if isinstance(value, BaseModel):
        for field_name in type(value).model_fields:
            yield from _iter_projected_actuals(getattr(value, field_name))
        return
    if isinstance(value, Mapping):
        for nested_value in value.values():
            yield from _iter_projected_actuals(nested_value)
        return
    if isinstance(value, (tuple, list)):
        for nested_value in value:
            yield from _iter_projected_actuals(nested_value)


@given(
    decisions=_eligibility_decisions(),
    requester_nonce=st.integers(min_value=0, max_value=1_000_000),
    recipient_nonces=st.lists(
        st.integers(min_value=0, max_value=1_000_000),
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
@settings(max_examples=150, deadline=None)
def test_property_11_requesting_user_response_authorization(
    decisions: tuple[dc.EligibilityDecision, ...],
    requester_nonce: int,
    recipient_nonces: list[int],
) -> None:
    """Identity-derived authorization controls every nested actual projection."""
    requester_id = f"synthetic_requester_{requester_nonce}"
    contexts = (
        AuthorizationContext(
            request_session_id=requester_id,
            recipient_session_id=requester_id,
        ),
        *(
            AuthorizationContext(
                request_session_id=requester_id,
                recipient_session_id=f"synthetic_recipient_{recipient_nonce}",
            )
            for recipient_nonce in recipient_nonces
        ),
    )
    items = tuple(
        _to_workflow_item(decision, item_index=item_index)
        for item_index, decision in enumerate(decisions)
    )
    reasons_by_item = {decision.item_id: decision.reasons for decision in decisions}
    expected_actual_field_count = (
        sum(len(decision.reasons) for decision in decisions) * 2
    )

    for context in contexts:
        # Independent oracle: authorization follows identity equality, never a
        # caller-reported authorization value.
        oracle_is_requesting_user = (
            context.request_session_id == context.recipient_session_id
        )
        assert context.is_requesting_user is oracle_is_requesting_user

        views = map_to_api_response(
            items,
            is_requesting_user=context.is_requesting_user,
            domain_reasons_by_item=reasons_by_item,
        )
        assert len(views) == len(decisions)

        for view, item, decision in zip(views, items, decisions, strict=True):
            source_actuals = tuple(str(reason.actual) for reason in decision.reasons)
            structured_actuals = tuple(
                reason.actual for reason in view.structured_reasons
            )
            legacy_actuals = tuple(
                condition.actual for condition in view.decisive_conditions
            )

            if oracle_is_requesting_user:
                assert structured_actuals == source_actuals
                assert legacy_actuals == tuple(
                    condition.actual for condition in item.decisive_conditions
                )
            else:
                assert structured_actuals == (None,) * len(source_actuals)
                assert legacy_actuals == ("",) * len(source_actuals)

        recursive_actuals = tuple(_iter_projected_actuals(views))
        assert len(recursive_actuals) == expected_actual_field_count
        if not oracle_is_requesting_user:
            assert all(
                actual is None if projection == "structured" else actual == ""
                for projection, actual in recursive_actuals
            )
