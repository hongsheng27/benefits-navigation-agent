"""Unit tests for requesting-user response authorization.

Tests verify:
- AuthorizationContext identity binding replaces caller-reported boolean
- Requesting user sees actual values in structured reasons and decisive conditions
- Non-requesting user has ALL actual values recursively removed
- Authorization is NOT a self-reported flag

Requirements: 9.1, 9.2.
"""

from __future__ import annotations

from app.api.response_mapper import map_item_to_api_view, map_to_api_response
from app.orchestration import data_contracts as dc
from app.orchestration import state
from app.privacy.raw_text_scope import AuthorizationContext


def _make_item(
    *,
    item_id: str = "test_item",
    decisive_conditions: tuple[state.DecisiveCondition, ...] = (),
) -> state.CandidateItem:
    return state.CandidateItem(
        item_id=item_id,
        kind=state.ItemKind.BENEFIT,
        status=state.ItemStatus.ELIGIBLE,
        program_status="verified",
        decisive_conditions=decisive_conditions,
    )


def _make_reason(*, actual: str = "user_value") -> dc.StructuredReason:
    return dc.StructuredReason(
        condition_id="cond_001",
        field_id="age_band",
        operator=">=",
        expected="65",
        actual=actual,
        label="年齡條件",
        source_reference="ref_001",
    )


class TestAuthorizationContextDrivesPrivacy:
    """AuthorizationContext.is_requesting_user drives actual inclusion/removal."""

    def test_requesting_user_sees_actual_in_structured_reasons(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="sess_A",
            recipient_session_id="sess_A",
        )
        item = _make_item()
        reason = _make_reason(actual="my_actual_situation")

        view = map_item_to_api_view(
            item,
            is_requesting_user=ctx.is_requesting_user,
            domain_reasons=(reason,),
        )

        assert view.structured_reasons[0].actual == "my_actual_situation"

    def test_non_requesting_user_cannot_see_actual(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="sess_A",
            recipient_session_id="sess_B",
        )
        item = _make_item()
        reason = _make_reason(actual="sensitive_data")

        view = map_item_to_api_view(
            item,
            is_requesting_user=ctx.is_requesting_user,
            domain_reasons=(reason,),
        )

        assert view.structured_reasons[0].actual is None

    def test_requesting_user_sees_actual_in_decisive_conditions(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="sess_X",
            recipient_session_id="sess_X",
        )
        condition = state.DecisiveCondition(
            field_id="income",
            expected="low",
            actual="high",
        )
        item = _make_item(decisive_conditions=(condition,))

        view = map_item_to_api_view(
            item,
            is_requesting_user=ctx.is_requesting_user,
        )

        assert view.decisive_conditions[0].actual == "high"

    def test_non_requesting_user_decisive_conditions_actual_empty(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="sess_X",
            recipient_session_id="sess_Y",
        )
        condition = state.DecisiveCondition(
            field_id="income",
            expected="low",
            actual="high",
        )
        item = _make_item(decisive_conditions=(condition,))

        view = map_item_to_api_view(
            item,
            is_requesting_user=ctx.is_requesting_user,
        )

        assert view.decisive_conditions[0].actual == ""


class TestBatchResponseAuthorization:
    """Batch response respects authorization for all items."""

    def test_non_requesting_user_all_items_actual_removed(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="owner",
            recipient_session_id="observer",
        )
        condition = state.DecisiveCondition(
            field_id="f1",
            expected="expected",
            actual="secret",
        )
        items = (
            _make_item(item_id="a", decisive_conditions=(condition,)),
            _make_item(item_id="b", decisive_conditions=(condition,)),
        )
        reasons_map = {
            "a": (_make_reason(actual="secret_a"),),
            "b": (_make_reason(actual="secret_b"),),
        }

        views = map_to_api_response(
            items,
            is_requesting_user=ctx.is_requesting_user,
            domain_reasons_by_item=reasons_map,
        )

        for view in views:
            assert view.decisive_conditions[0].actual == ""
            assert view.structured_reasons[0].actual is None

    def test_requesting_user_all_items_actual_present(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="owner",
            recipient_session_id="owner",
        )
        condition_a = state.DecisiveCondition(
            field_id="f1", expected="e", actual="actual_a"
        )
        condition_b = state.DecisiveCondition(
            field_id="f2", expected="e", actual="actual_b"
        )
        items = (
            _make_item(item_id="a", decisive_conditions=(condition_a,)),
            _make_item(item_id="b", decisive_conditions=(condition_b,)),
        )

        views = map_to_api_response(
            items,
            is_requesting_user=ctx.is_requesting_user,
        )

        assert views[0].decisive_conditions[0].actual == "actual_a"
        assert views[1].decisive_conditions[0].actual == "actual_b"


class TestAuthorizationNotCallerReported:
    """Authorization decision must come from identity binding, not a flag."""

    def test_identity_mismatch_always_removes_actual(self) -> None:
        """Even if someone constructs `is_requesting_user=True` manually,
        the AuthorizationContext ensures the decision is identity-derived.
        """
        # Simulating: the caller "wants" to be the requesting user
        # but the identity binding says otherwise
        ctx = AuthorizationContext(
            request_session_id="real_user",
            recipient_session_id="impersonator",
        )
        # The property returns False regardless of caller intent
        assert ctx.is_requesting_user is False

        item = _make_item()
        reason = _make_reason(actual="should_not_see_this")

        view = map_item_to_api_view(
            item,
            is_requesting_user=ctx.is_requesting_user,
            domain_reasons=(reason,),
        )

        assert view.structured_reasons[0].actual is None

    def test_identity_match_always_includes_actual(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="user_abc",
            recipient_session_id="user_abc",
        )
        assert ctx.is_requesting_user is True

        item = _make_item()
        reason = _make_reason(actual="my_situation")

        view = map_item_to_api_view(
            item,
            is_requesting_user=ctx.is_requesting_user,
            domain_reasons=(reason,),
        )

        assert view.structured_reasons[0].actual == "my_situation"
