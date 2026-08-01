"""Unit tests for the human review transition service.

Validates:
- Human reviewer with complete artifacts CAN transition to verified
- Non-human actors are BLOCKED from protected transitions
- Incomplete artifacts are BLOCKED
- Non-protected transitions work for human_reviewer
- Audit trail records correct fields
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from backend.app.curation.review_service import (
    FORBIDDEN_ACTORS,
    ReviewArtifacts,
    ReviewService,
    TransitionAuditRecord,
    validate_transition,
)


class FakePersistence:
    """In-memory fake implementing ReviewPersistence protocol."""

    def __init__(self, statuses: dict[str, str] | None = None) -> None:
        self.statuses: dict[str, str] = statuses or {}
        self.records: list[TransitionAuditRecord] = []

    def persist_transition(self, record: TransitionAuditRecord) -> None:
        self.records.append(record)
        self.statuses[record.program_id] = record.to_status

    def get_current_status(self, program_id: str) -> str | None:
        return self.statuses.get(program_id)


def _complete_artifacts() -> ReviewArtifacts:
    return ReviewArtifacts(
        approved_rule_version="v1.0",
        citation_ids=("cite-001",),
        approved_excerpt="第十五條規定...",
    )


FIXED_TIME = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)


class TestValidateTransition:
    """Pure validation function tests."""

    def test_human_reviewer_with_artifacts_allowed(self) -> None:
        error = validate_transition(
            program_id="death_registration",
            from_status="under_review",
            to_status="verified",
            actor_type="human_reviewer",
            artifacts=_complete_artifacts(),
        )
        assert error is None

    @pytest.mark.parametrize("actor", sorted(FORBIDDEN_ACTORS))
    def test_forbidden_actors_blocked(self, actor: str) -> None:
        error = validate_transition(
            program_id="death_registration",
            from_status="under_review",
            to_status="verified",
            actor_type=actor,
            artifacts=_complete_artifacts(),
        )
        assert error == "forbidden_actor"

    def test_missing_rule_version_blocked(self) -> None:
        error = validate_transition(
            program_id="death_registration",
            from_status="under_review",
            to_status="verified",
            actor_type="human_reviewer",
            artifacts=ReviewArtifacts(
                approved_rule_version=None,
                citation_ids=("cite-001",),
                approved_excerpt="text",
            ),
        )
        assert error == "incomplete_artifacts"

    def test_missing_citation_blocked(self) -> None:
        error = validate_transition(
            program_id="death_registration",
            from_status="under_review",
            to_status="verified",
            actor_type="human_reviewer",
            artifacts=ReviewArtifacts(
                approved_rule_version="v1.0",
                citation_ids=(),
                approved_excerpt="text",
            ),
        )
        assert error == "incomplete_artifacts"

    def test_missing_excerpt_blocked(self) -> None:
        error = validate_transition(
            program_id="death_registration",
            from_status="under_review",
            to_status="verified",
            actor_type="human_reviewer",
            artifacts=ReviewArtifacts(
                approved_rule_version="v1.0",
                citation_ids=("cite-001",),
                approved_excerpt=None,
            ),
        )
        assert error == "incomplete_artifacts"

    def test_no_artifacts_blocked(self) -> None:
        error = validate_transition(
            program_id="death_registration",
            from_status="under_review",
            to_status="verified",
            actor_type="human_reviewer",
            artifacts=None,
        )
        assert error == "incomplete_artifacts"

    def test_non_protected_transition_allowed_without_artifacts(self) -> None:
        error = validate_transition(
            program_id="death_registration",
            from_status="candidate",
            to_status="under_review",
            actor_type="human_reviewer",
            artifacts=None,
        )
        assert error is None


class TestReviewService:
    """Integration tests with fake persistence."""

    def test_successful_transition_to_verified(self) -> None:
        persistence = FakePersistence({"death_registration": "under_review"})
        service = ReviewService(persistence)

        result = service.transition_status(
            program_id="death_registration",
            to_status="verified",
            actor_type="human_reviewer",
            reviewer_ref="reviewer-001",
            approved_version="v1.0",
            artifacts=_complete_artifacts(),
            reviewed_at=FIXED_TIME,
        )

        assert result.success is True
        assert result.audit_record is not None
        assert result.audit_record.program_id == "death_registration"
        assert result.audit_record.from_status == "under_review"
        assert result.audit_record.to_status == "verified"
        assert result.audit_record.actor_type == "human_reviewer"
        assert result.audit_record.reviewer_ref == "reviewer-001"
        assert result.audit_record.approved_version == "v1.0"
        assert FIXED_TIME.isoformat() in result.audit_record.reviewed_at

    def test_audit_record_persisted(self) -> None:
        persistence = FakePersistence({"labor_funeral_grant": "under_review"})
        service = ReviewService(persistence)

        service.transition_status(
            program_id="labor_funeral_grant",
            to_status="verified",
            actor_type="human_reviewer",
            reviewer_ref="reviewer-002",
            approved_version="v2.0",
            artifacts=_complete_artifacts(),
            reviewed_at=FIXED_TIME,
        )

        assert len(persistence.records) == 1
        assert persistence.records[0].program_id == "labor_funeral_grant"
        assert persistence.statuses["labor_funeral_grant"] == "verified"

    def test_forbidden_actor_blocked(self) -> None:
        persistence = FakePersistence({"death_registration": "under_review"})
        service = ReviewService(persistence)

        result = service.transition_status(
            program_id="death_registration",
            to_status="verified",
            actor_type="crawler",
            reviewer_ref="crawl-bot",
            approved_version="v1.0",
            artifacts=_complete_artifacts(),
        )

        assert result.success is False
        assert result.error_code == "forbidden_actor"
        assert len(persistence.records) == 0

    def test_incomplete_artifacts_blocked(self) -> None:
        persistence = FakePersistence({"death_registration": "under_review"})
        service = ReviewService(persistence)

        result = service.transition_status(
            program_id="death_registration",
            to_status="verified",
            actor_type="human_reviewer",
            reviewer_ref="reviewer-001",
            approved_version="v1.0",
            artifacts=ReviewArtifacts(approved_rule_version="v1.0"),
        )

        assert result.success is False
        assert result.error_code == "incomplete_artifacts"
        assert len(persistence.records) == 0

    def test_program_not_found(self) -> None:
        persistence = FakePersistence({})
        service = ReviewService(persistence)

        result = service.transition_status(
            program_id="nonexistent",
            to_status="verified",
            actor_type="human_reviewer",
            reviewer_ref="reviewer-001",
            approved_version="v1.0",
            artifacts=_complete_artifacts(),
        )

        assert result.success is False
        assert result.error_code == "program_not_found"

    def test_non_protected_transition_succeeds(self) -> None:
        persistence = FakePersistence({"death_registration": "candidate"})
        service = ReviewService(persistence)

        result = service.transition_status(
            program_id="death_registration",
            to_status="under_review",
            actor_type="human_reviewer",
            reviewer_ref="reviewer-001",
            approved_version="v1.0",
            artifacts=None,
        )

        assert result.success is True
        assert result.audit_record is not None
        assert result.audit_record.to_status == "under_review"
        assert persistence.statuses["death_registration"] == "under_review"

    def test_persistence_failure_returns_error(self) -> None:
        class FailingPersistence:
            def persist_transition(self, record: TransitionAuditRecord) -> None:
                raise RuntimeError("DB connection lost")

            def get_current_status(self, program_id: str) -> str | None:
                return "candidate"

        service = ReviewService(FailingPersistence())

        result = service.transition_status(
            program_id="death_registration",
            to_status="under_review",
            actor_type="human_reviewer",
            reviewer_ref="reviewer-001",
            approved_version="v1.0",
        )

        assert result.success is False
        assert result.error_code == "persistence_failed"

    def test_all_six_mvp_ids_can_be_reviewed(self) -> None:
        mvp_ids = [
            "death_registration",
            "labor_funeral_grant",
            "national_pension_funeral_grant",
            "labor_survivor_pension",
            "national_pension_survivor_pension",
            "nhi_status_change",
        ]
        persistence = FakePersistence({pid: "under_review" for pid in mvp_ids})
        service = ReviewService(persistence)

        for pid in mvp_ids:
            result = service.transition_status(
                program_id=pid,
                to_status="verified",
                actor_type="human_reviewer",
                reviewer_ref="reviewer-team",
                approved_version="v1.0",
                artifacts=_complete_artifacts(),
                reviewed_at=FIXED_TIME,
            )
            assert result.success is True, f"Failed for {pid}"

        assert len(persistence.records) == 6
