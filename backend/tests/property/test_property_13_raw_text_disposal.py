"""Property 13: Raw text disposal.

**Validates: Requirements 9.9–9.11, 9.13**

Feature: data-layer-rule-engine, Property 13: for every extraction outcome,
raw text is disposed before a SessionState transition and only the intersection
of extracted keys and the field-registry allowlist reaches that state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.orchestration.state import SessionState
from app.privacy.raw_text_scope import (
    RawTextScope,
    RawTextScopeError,
    ScopeExitReason,
)

_FIELD_IDS = (
    "age_band",
    "relationship",
    "income_band",
    "residency",
    "employment_type",
    "insurance_years",
    "deceased_date",
    "marital_status",
    "disability_level",
    "household_size",
)
_SAFE_ATTRIBUTE_TEXT = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    max_size=24,
)
_ATTRIBUTE_VALUES = st.one_of(
    _SAFE_ATTRIBUTE_TEXT,
    st.integers(min_value=0, max_value=100),
    st.booleans(),
)
_EXIT_MODES = st.sampled_from(("success", "failure", "cancellation"))


class _SyntheticExtractionFailure(Exception):
    """Synthetic failure used only to exercise scope cleanup."""


def _exit_scope(
    scope: RawTextScope,
    *,
    raw_text: str,
    extracted: dict[str, bool | int | str],
    exit_mode: Literal["success", "failure", "cancellation"],
) -> None:
    """Exercise each supported extraction exit without suppressing cleanup."""
    try:
        with scope:
            scope.set_raw_text(raw_text)
            scope.set_extracted(extracted)
            if exit_mode == "failure":
                raise _SyntheticExtractionFailure
            if exit_mode == "cancellation":
                raise KeyboardInterrupt
    except (_SyntheticExtractionFailure, KeyboardInterrupt):
        pass


def _transition_state_after_disposal(scope: RawTextScope) -> SessionState:
    """Model the workflow transition, refusing to run until disposal completed."""
    assert scope.is_disposed is True
    with pytest.raises(RawTextScopeError):
        scope.get_raw_text()

    now = datetime.now(timezone.utc)
    return SessionState(
        session_id="synthetic-property-13-session",
        attributes=scope.get_surviving_attributes(),
        created_at=now,
        updated_at=now,
        expires_at=now,
    )


@given(
    nonce=st.integers(min_value=0, max_value=1_000_000_000),
    allowlist=st.frozensets(st.sampled_from(_FIELD_IDS), max_size=len(_FIELD_IDS)),
    extracted=st.dictionaries(
        keys=st.sampled_from(_FIELD_IDS),
        values=_ATTRIBUTE_VALUES,
        max_size=len(_FIELD_IDS),
    ),
    exit_mode=_EXIT_MODES,
)
@settings(max_examples=150, deadline=None)
def test_property_13_raw_text_disposal_precedes_state_transition(
    nonce: int,
    allowlist: frozenset[str],
    extracted: dict[str, bool | int | str],
    exit_mode: Literal["success", "failure", "cancellation"],
) -> None:
    """All exits dispose raw input before state transition and keep only safe keys."""
    scope = RawTextScope(allowlisted_fields=allowlist)

    _exit_scope(
        scope,
        raw_text=f"synthetic-raw-text-{nonce}",
        extracted=extracted,
        exit_mode=exit_mode,
    )
    state = _transition_state_after_disposal(scope)

    assert scope.exit_reason == ScopeExitReason(exit_mode)
    assert scope._raw_text is None
    assert scope._extracted == {}
    assert state.attributes == {
        field_id: value for field_id, value in extracted.items() if field_id in allowlist
    }
    assert set(state.attributes).issubset(allowlist)
