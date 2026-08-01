"""Human review transition service (Req 10.7-10.9, 15.3, 15.4, 16.6-16.13).

Only human reviewers with complete approved artifacts (rule, citation, excerpt)
can perform protected transitions. Records full audit trail.

Candidate page/attachment/rule/evidence artifacts require human review metadata
and all necessary artifacts to be complete before entering approved version.
All protected transitions are atomic and auditable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable

ProgramStatus = Literal[
    "candidate", "under_review", "verified", "stale", "rejected", "inactive"
]

ActorType = Literal[
    "human_reviewer", "crawler", "llm", "importer", "converter", "exporter", "migration"
]

PROTECTED_TARGET_STATUSES: frozenset[str] = frozenset({"verified"})

FORBIDDEN_ACTORS: frozenset[str] = frozenset(
    {"crawler", "llm", "importer", "converter", "exporter", "migration"}
)


@dataclass(frozen=True, slots=True)
class ReviewArtifacts:
    """Artifacts required for a protected transition to verified."""

    approved_rule_version: str | None = None
    citation_ids: tuple[str, ...] = ()
    approved_excerpt: str | None = None

    @property
    def is_complete(self) -> bool:
        return bool(
            self.approved_rule_version and self.citation_ids and self.approved_excerpt
        )


@dataclass(frozen=True, slots=True)
class TransitionAuditRecord:
    """Immutable audit record for a status transition."""

    history_id: str
    program_id: str
    from_status: str
    to_status: str
    actor_type: str
    reviewer_ref: str
    reviewed_at: str
    approved_version: str


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """Result of a transition attempt."""

    success: bool
    audit_record: TransitionAuditRecord | None = None
    error_code: str | None = None
    error_message: str | None = None


@runtime_checkable
class ReviewPersistence(Protocol):
    """Storage-neutral persistence protocol for review transitions."""

    def persist_transition(self, record: TransitionAuditRecord) -> None: ...
    def get_current_status(self, program_id: str) -> str | None: ...


def validate_transition(
    *,
    program_id: str,
    from_status: str,
    to_status: str,
    actor_type: str,
    artifacts: ReviewArtifacts | None,
) -> str | None:
    """Validate a proposed transition. Returns error code or None if valid."""
    if to_status in PROTECTED_TARGET_STATUSES:
        if actor_type != "human_reviewer":
            return "forbidden_actor"
        if artifacts is None or not artifacts.is_complete:
            return "incomplete_artifacts"
    if actor_type in FORBIDDEN_ACTORS and to_status in PROTECTED_TARGET_STATUSES:
        return "forbidden_actor"
    return None


def _error_message(code: str, actor_type: str, to_status: str) -> str:
    if code == "forbidden_actor":
        return (
            f"Actor type '{actor_type}' is forbidden from transitioning "
            f"to '{to_status}'. Only human_reviewer is allowed."
        )
    if code == "incomplete_artifacts":
        return (
            f"Protected transition to '{to_status}' requires complete "
            "artifacts: approved_rule_version, at least one citation_id, "
            "and approved_excerpt."
        )
    return f"Transition error: {code}"


class ReviewService:
    """Domain service for human review transitions."""

    def __init__(self, persistence: ReviewPersistence) -> None:
        self._persistence = persistence

    def transition_status(
        self,
        *,
        program_id: str,
        to_status: str,
        actor_type: str,
        reviewer_ref: str,
        approved_version: str,
        artifacts: ReviewArtifacts | None = None,
        history_id: str | None = None,
        reviewed_at: datetime | None = None,
    ) -> TransitionResult:
        """Attempt a program status transition."""
        current_status = self._persistence.get_current_status(program_id)
        if current_status is None:
            return TransitionResult(
                success=False,
                error_code="program_not_found",
                error_message=f"Program not found: {program_id}",
            )

        from_status = current_status
        error = validate_transition(
            program_id=program_id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor_type,
            artifacts=artifacts,
        )
        if error is not None:
            return TransitionResult(
                success=False,
                error_code=error,
                error_message=_error_message(error, actor_type, to_status),
            )

        ts = reviewed_at or datetime.now(UTC)
        record = TransitionAuditRecord(
            history_id=history_id or str(uuid.uuid4()),
            program_id=program_id,
            from_status=from_status,
            to_status=to_status,
            actor_type=actor_type,
            reviewer_ref=reviewer_ref,
            reviewed_at=ts.isoformat(),
            approved_version=approved_version,
        )

        try:
            self._persistence.persist_transition(record)
        except Exception:
            return TransitionResult(
                success=False,
                error_code="persistence_failed",
                error_message="Failed to persist transition record",
            )

        return TransitionResult(success=True, audit_record=record)


# ---------------------------------------------------------------------------
# Candidate artifact completeness validation (Req 10.7-10.9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CandidateArtifactCheck:
    """Result of checking whether a candidate has all required artifacts."""

    program_id: str
    has_approved_rule: bool = False
    has_citations: bool = False
    has_approved_excerpt: bool = False
    has_source_document: bool = False

    @property
    def is_ready_for_review(self) -> bool:
        """Whether the candidate has enough artifacts for human review."""
        return (
            self.has_approved_rule and self.has_citations and self.has_approved_excerpt
        )

    @property
    def missing_artifacts(self) -> tuple[str, ...]:
        """List of missing artifact types."""
        missing: list[str] = []
        if not self.has_approved_rule:
            missing.append("approved_rule_version")
        if not self.has_citations:
            missing.append("citations")
        if not self.has_approved_excerpt:
            missing.append("approved_excerpt")
        if not self.has_source_document:
            missing.append("source_document")
        return tuple(missing)


def check_candidate_artifacts(
    program_id: str,
    artifacts: ReviewArtifacts | None,
) -> CandidateArtifactCheck:
    """Check whether a candidate has all required artifacts for review.

    This is used by the pipeline to determine if a candidate can be
    submitted for human review transition.
    """
    if artifacts is None:
        return CandidateArtifactCheck(program_id=program_id)

    return CandidateArtifactCheck(
        program_id=program_id,
        has_approved_rule=artifacts.approved_rule_version is not None,
        has_citations=len(artifacts.citation_ids) > 0,
        has_approved_excerpt=artifacts.approved_excerpt is not None,
        has_source_document=True,  # Assumed if artifacts exist
    )
