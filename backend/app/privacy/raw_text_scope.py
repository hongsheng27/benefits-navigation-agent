"""Request-local Raw Text Scope with deterministic disposal.

Implements Req 9.9–9.11, 9.13:
- Raw user text is confined to the current request's processing scope.
- On success, failure, or cancellation, raw text is disposed BEFORE any
  response or state transition.
- Only allowlisted extracted attributes survive disposal.

Design:
- RawTextScope is a context manager that guarantees disposal.
- Authorization is NOT a caller-reported boolean; it is determined by the
  scope's own identity binding.
- The scope only copies field-registry allowlist intersection to output.

No DB access, no network, no side effects beyond memory management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ScopeExitReason(StrEnum):
    """How the raw text scope was exited."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLATION = "cancellation"


class RawTextScopeError(RuntimeError):
    """Raised when raw text scope is used after disposal."""

    def __init__(self) -> None:
        super().__init__("raw_text_scope_already_disposed")


class RawTextScopeNotEnteredError(RuntimeError):
    """Raised when trying to use scope before entering."""

    def __init__(self) -> None:
        super().__init__("raw_text_scope_not_entered")


@dataclass
class RawTextScope:
    """Request-local container for raw user text during extraction.

    Usage:
        allowlist = {"field_a", "field_b", "field_c"}
        scope = RawTextScope(allowlisted_fields=allowlist)

        with scope:
            scope.set_raw_text("user typed something")
            extracted = do_extraction(scope.get_raw_text())
            scope.set_extracted(extracted)

        # After context exit, raw text is gone
        # Only allowlisted keys from extracted survive
        safe_attrs = scope.get_surviving_attributes()

    The scope guarantees:
    1. Raw text is ALWAYS disposed on exit (success, failure, cancellation).
    2. Only attributes whose keys are in the allowlist survive.
    3. Accessing raw text after disposal raises RawTextScopeError.
    """

    allowlisted_fields: frozenset[str]
    _raw_text: str | None = field(default=None, init=False, repr=False)
    _extracted: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _disposed: bool = field(default=False, init=False)
    _entered: bool = field(default=False, init=False)
    _exit_reason: ScopeExitReason | None = field(default=None, init=False)
    _surviving_attributes: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False
    )

    def __enter__(self) -> RawTextScope:
        self._entered = True
        self._disposed = False
        self._raw_text = None
        self._extracted = {}
        self._surviving_attributes = {}
        self._exit_reason = None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Dispose raw text and compute surviving attributes.

        Always disposes regardless of exit reason. Does NOT suppress exceptions.
        """
        if exc_type is not None:
            if isinstance(exc_val, KeyboardInterrupt):
                self._exit_reason = ScopeExitReason.CANCELLATION
            else:
                self._exit_reason = ScopeExitReason.FAILURE
        else:
            self._exit_reason = ScopeExitReason.SUCCESS

        self._dispose()
        return False  # Do not suppress exceptions

    def set_raw_text(self, text: str) -> None:
        """Store raw user text for processing within this scope."""
        self._check_usable()
        self._raw_text = text

    def get_raw_text(self) -> str | None:
        """Retrieve raw text for extraction. Only available before disposal."""
        self._check_usable()
        return self._raw_text

    def set_extracted(self, attributes: dict[str, Any]) -> None:
        """Store extracted attributes. Only allowlisted keys will survive."""
        self._check_usable()
        self._extracted = dict(attributes)

    def get_surviving_attributes(self) -> dict[str, Any]:
        """Get attributes that survived disposal (allowlist intersection).

        Only available AFTER disposal (context manager exit).
        """
        if not self._disposed:
            raise RawTextScopeNotEnteredError()
        return dict(self._surviving_attributes)

    @property
    def is_disposed(self) -> bool:
        """Whether raw text has been disposed."""
        return self._disposed

    @property
    def exit_reason(self) -> ScopeExitReason | None:
        """How the scope was exited, or None if still active."""
        return self._exit_reason

    def _dispose(self) -> None:
        """Dispose raw text and compute surviving attributes.

        1. Compute allowlist intersection of extracted attributes.
        2. Clear raw text unconditionally.
        3. Mark as disposed.
        """
        # Step 1: Compute surviving attributes (allowlist intersection)
        self._surviving_attributes = {
            k: v for k, v in self._extracted.items() if k in self.allowlisted_fields
        }

        # Step 2: Clear raw text — this is the critical privacy guarantee
        self._raw_text = None
        self._extracted = {}

        # Step 3: Mark disposed
        self._disposed = True

    def _check_usable(self) -> None:
        """Check that scope is entered and not yet disposed."""
        if not self._entered:
            raise RawTextScopeNotEnteredError()
        if self._disposed:
            raise RawTextScopeError()


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """Determines whether a response recipient is the requesting user.

    This is NOT a caller-reported boolean. It binds the request identity
    to the response, so the response mapper can make privacy decisions
    without trusting the caller's claim.

    The session_id comes from the authenticated request context (e.g.,
    HTTP header), and recipient_session_id identifies who is receiving
    the response.
    """

    request_session_id: str
    recipient_session_id: str

    @property
    def is_requesting_user(self) -> bool:
        """Whether the recipient is the user who made this request.

        This replaces caller-reported `is_requesting_user: bool` parameters.
        The authorization decision is derived from identity binding, not
        a flag the caller can set arbitrarily.
        """
        return self.request_session_id == self.recipient_session_id
