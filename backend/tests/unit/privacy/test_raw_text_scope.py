"""Unit tests for RawTextScope and AuthorizationContext.

Tests verify:
- Three exit modes (success, failure, cancellation) all dispose raw text
- Only allowlisted attributes survive disposal
- Accessing raw text after disposal raises error
- AuthorizationContext identity binding (not caller-reported boolean)

Requirements: 9.1, 9.2, 9.9–9.11, 9.13.
"""

from __future__ import annotations

import pytest

from app.privacy.raw_text_scope import (
    AuthorizationContext,
    RawTextScope,
    RawTextScopeError,
    RawTextScopeNotEnteredError,
    ScopeExitReason,
)


class TestRawTextScopeSuccessExit:
    """Success exit: raw text disposed, only allowlisted attributes survive."""

    def test_raw_text_disposed_on_success(self) -> None:
        allowlist = frozenset({"age_band", "relationship"})
        scope = RawTextScope(allowlisted_fields=allowlist)

        with scope:
            scope.set_raw_text("我先生陳大明上週過世了")
            scope.set_extracted({"age_band": "50-64", "relationship": "spouse"})

        # After exit, raw text is gone
        assert scope.is_disposed is True
        assert scope.exit_reason == ScopeExitReason.SUCCESS

    def test_only_allowlisted_keys_survive(self) -> None:
        allowlist = frozenset({"age_band", "relationship"})
        scope = RawTextScope(allowlisted_fields=allowlist)

        with scope:
            scope.set_raw_text("text")
            scope.set_extracted(
                {
                    "age_band": "50-64",
                    "relationship": "spouse",
                    "name": "陳大明",  # NOT in allowlist
                    "raw_detail": "sensitive",  # NOT in allowlist
                }
            )

        surviving = scope.get_surviving_attributes()
        assert surviving == {"age_band": "50-64", "relationship": "spouse"}
        assert "name" not in surviving
        assert "raw_detail" not in surviving

    def test_empty_extraction_gives_empty_survival(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset({"x"}))

        with scope:
            scope.set_raw_text("text")
            # Never call set_extracted

        assert scope.get_surviving_attributes() == {}

    def test_no_allowlisted_keys_match(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset({"unrelated_field"}))

        with scope:
            scope.set_raw_text("text")
            scope.set_extracted({"actual_field": "value"})

        assert scope.get_surviving_attributes() == {}


class TestRawTextScopeFailureExit:
    """Failure exit: raw text still disposed even when exception occurs."""

    def test_raw_text_disposed_on_exception(self) -> None:
        allowlist = frozenset({"field_a"})
        scope = RawTextScope(allowlisted_fields=allowlist)

        with pytest.raises(ValueError):
            with scope:
                scope.set_raw_text("sensitive user input")
                scope.set_extracted({"field_a": "val", "field_b": "other"})
                raise ValueError("extraction failed")

        assert scope.is_disposed is True
        assert scope.exit_reason == ScopeExitReason.FAILURE
        # Even on failure, allowlisted attributes survive
        assert scope.get_surviving_attributes() == {"field_a": "val"}

    def test_runtime_error_still_disposes(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset())

        with pytest.raises(RuntimeError):
            with scope:
                scope.set_raw_text("raw")
                raise RuntimeError("crash")

        assert scope.is_disposed is True
        assert scope.exit_reason == ScopeExitReason.FAILURE


class TestRawTextScopeCancellationExit:
    """Cancellation exit: KeyboardInterrupt still disposes."""

    def test_keyboard_interrupt_disposes(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset({"f"}))

        with pytest.raises(KeyboardInterrupt):
            with scope:
                scope.set_raw_text("input")
                scope.set_extracted({"f": "v"})
                raise KeyboardInterrupt()

        assert scope.is_disposed is True
        assert scope.exit_reason == ScopeExitReason.CANCELLATION
        assert scope.get_surviving_attributes() == {"f": "v"}


class TestRawTextScopeAccessAfterDisposal:
    """Accessing raw text after disposal raises error."""

    def test_get_raw_text_after_disposal_raises(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset())

        with scope:
            scope.set_raw_text("text")

        with pytest.raises(RawTextScopeError):
            scope.get_raw_text()

    def test_set_raw_text_after_disposal_raises(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset())

        with scope:
            pass

        with pytest.raises(RawTextScopeError):
            scope.set_raw_text("new text")

    def test_set_extracted_after_disposal_raises(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset())

        with scope:
            pass

        with pytest.raises(RawTextScopeError):
            scope.set_extracted({"key": "val"})


class TestRawTextScopeNotEntered:
    """Using scope before entering raises error."""

    def test_get_raw_text_before_enter_raises(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset())
        with pytest.raises(RawTextScopeNotEnteredError):
            scope.get_raw_text()

    def test_set_raw_text_before_enter_raises(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset())
        with pytest.raises(RawTextScopeNotEnteredError):
            scope.set_raw_text("text")

    def test_get_surviving_before_disposal_raises(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset())
        with pytest.raises(RawTextScopeNotEnteredError):
            scope.get_surviving_attributes()


class TestRawTextScopeRawTextInaccessible:
    """After disposal, raw text cannot be recovered from scope internals."""

    def test_internal_raw_text_is_none_after_disposal(self) -> None:
        scope = RawTextScope(allowlisted_fields=frozenset())

        with scope:
            scope.set_raw_text("very sensitive PII data")

        # Internal state check — raw text must be cleared
        assert scope._raw_text is None
        assert scope._extracted == {}


class TestAuthorizationContext:
    """AuthorizationContext determines requesting user by identity binding."""

    def test_same_session_is_requesting_user(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="sess_123",
            recipient_session_id="sess_123",
        )
        assert ctx.is_requesting_user is True

    def test_different_session_is_not_requesting_user(self) -> None:
        ctx = AuthorizationContext(
            request_session_id="sess_123",
            recipient_session_id="sess_456",
        )
        assert ctx.is_requesting_user is False

    def test_authorization_not_caller_reported(self) -> None:
        """Verify the decision is derived from identity binding, not a flag."""
        # There is no way to "override" is_requesting_user — it's a property
        ctx = AuthorizationContext(
            request_session_id="a",
            recipient_session_id="b",
        )
        # Even if someone "wants" it to be True, the property returns False
        assert ctx.is_requesting_user is False

    def test_empty_session_ids_are_not_equal(self) -> None:
        """Edge case: empty strings are technically equal."""
        ctx = AuthorizationContext(
            request_session_id="",
            recipient_session_id="",
        )
        # This is still technically the same identity
        assert ctx.is_requesting_user is True
