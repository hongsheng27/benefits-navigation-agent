"""Tests that state machine uses only injected fakes, zero DB calls.

Validates:
- When all fakes supplied to advance(), zero sqlite3.connect calls
- State machine can complete a full workflow cycle using only fakes

Requirements traced: 2.6, 2.8, 2.9.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.orchestration.data_contracts import CandidateItem, GraphRelation
from app.orchestration.protocols import CoverageScope
from app.orchestration.state import SessionState, WorkflowState
from app.schemas.session import EventConfirmationInput, LifeEventTextInput
from app.testing.fakes import (
    FakeEligibilityService,
    FakeEntitlementGraphRepository,
    FakeEvidenceRepository,
    FakeSourceRefreshService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEATH_REG = CandidateItem(
    item_id="death_registration",
    display_name="死亡登記",
    program_status="candidate",
    relevance_score=None,
    missing_field_ids=(),
    prerequisites=(),
    produces=(
        GraphRelation(target_id="funeral_benefit", display_name="喪葬給付", canonical_order=0),
    ),
)

_FUNERAL = CandidateItem(
    item_id="funeral_benefit",
    display_name="喪葬給付",
    program_status="candidate",
    relevance_score=None,
    missing_field_ids=(),
    prerequisites=(
        GraphRelation(target_id="death_registration", display_name="死亡登記", canonical_order=0),
    ),
    produces=(),
)

_FAKE_GRAPH = FakeEntitlementGraphRepository(
    items_by_event={"spouse_death": (_DEATH_REG, _FUNERAL)},
)
_FAKE_ELIG = FakeEligibilityService()
_FAKE_EVIDENCE = FakeEvidenceRepository()
_FAKE_REFRESH = FakeSourceRefreshService()
_SCOPE = CoverageScope(source_ids=(), domain_tags=())


def _make_session() -> SessionState:
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    return SessionState(
        session_id="s_fake_test",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )


def _advance_with_fakes(state: SessionState, user_input):
    """Advance using all four fakes."""
    from app.orchestration.state_machine import advance

    return advance(
        state,
        user_input,
        entitlement_repository=_FAKE_GRAPH,
        eligibility_service=_FAKE_ELIG,
        evidence_repository=_FAKE_EVIDENCE,
        source_refresh_service=_FAKE_REFRESH,
        coverage_scope=_SCOPE,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestZeroDBCallsWithFakes:
    """When all fakes are supplied, sqlite3.connect is never called."""

    def test_advance_with_fakes_no_sqlite_connect(self) -> None:
        """Single advance step with fakes opens zero DB connections."""
        state = _make_session()

        with patch("sqlite3.connect") as mock_connect:
            _advance_with_fakes(state, LifeEventTextInput(text="配偶過世"))
            mock_connect.assert_not_called()

    def test_full_cycle_no_sqlite_connect(self) -> None:
        """Complete workflow from start to COMPLETE without any sqlite3 call."""
        state = _make_session()

        with patch("sqlite3.connect") as mock_connect:
            # Step 1: user describes event
            state = _advance_with_fakes(state, LifeEventTextInput(text="配偶過世"))

            # Step 2: user confirms event → auto-advances through the cycle
            state = _advance_with_fakes(state, EventConfirmationInput(confirmed=True))

            mock_connect.assert_not_called()

    def test_full_cycle_reaches_terminal_state(self) -> None:
        """With fakes, the workflow reaches a terminal or waiting state."""
        state = _make_session()

        # Describe and confirm event
        state = _advance_with_fakes(state, LifeEventTextInput(text="配偶過世"))
        state = _advance_with_fakes(state, EventConfirmationInput(confirmed=True))

        # Should have resolved items and reached a state that needs user or is done
        terminal_or_waiting = {
            WorkflowState.COLLECT_MISSING_FIELDS,
            WorkflowState.CONFIRM,
            WorkflowState.COMPLETE,
        }
        assert state.workflow_state in terminal_or_waiting or state.exit_reason is not None

    def test_items_populated_from_fake_graph(self) -> None:
        """Fakes graph repository items flow into session state."""
        state = _make_session()

        state = _advance_with_fakes(state, LifeEventTextInput(text="配偶過世"))
        state = _advance_with_fakes(state, EventConfirmationInput(confirmed=True))

        # Items should come from our fake graph
        item_ids = {item.item_id for item in state.items}
        assert "death_registration" in item_ids or "funeral_benefit" in item_ids


class TestStateMachineDoesNotImportSqlite:
    """Verify state_machine module itself doesn't directly use sqlite3."""

    def test_no_sqlite3_in_state_machine_source(self) -> None:
        """The state_machine module does not import sqlite3."""
        import inspect

        from app.orchestration import state_machine

        source = inspect.getsource(state_machine)
        assert "import sqlite3" not in source
        assert "sqlite3.connect" not in source
