"""Unit tests for DeterministicEligibilityService.

Covers:
- verified + complete citations → full evaluation (eligible/ineligible)
- verified + missing citations → downgrade to needs_human_review
- verified + missing fields → needs_information
- candidate/under_review → needs_human_review, engine not called
- stale → needs_human_review, engine not called
- rejected/inactive → NonEvaluableStatusError raised
- verified + no approved rule → needs_human_review
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.application.eligibility_service import (
    DeterministicEligibilityService,
    NonEvaluableStatusError,
)
from app.orchestration.data_contracts import (
    Citation,
    FieldRegistryEntry,
    ProgramStatus,
)
from app.rules.dsl import AllOf, Condition, RuleDefinition
from app.rules.evaluation import ApprovedAmount

# ---------------------------------------------------------------------------
# Fake implementations for testing
# ---------------------------------------------------------------------------


class FakeRuleRepository:
    """In-memory fake rule repository for unit testing."""

    def __init__(
        self,
        *,
        statuses: dict[str, ProgramStatus] | None = None,
        rules: dict[str, RuleDefinition | None] | None = None,
        amounts: dict[str, ApprovedAmount | None] | None = None,
        fields: dict[str, Sequence[FieldRegistryEntry]] | None = None,
    ) -> None:
        self._statuses = statuses or {}
        self._rules = rules or {}
        self._amounts = amounts or {}
        self._fields = fields or {}

    def get_program_status(self, item_id: str) -> ProgramStatus:
        return self._statuses.get(item_id, "candidate")

    def get_approved_rule(self, item_id: str) -> RuleDefinition | None:
        return self._rules.get(item_id)

    def get_approved_amount(self, item_id: str) -> ApprovedAmount | None:
        return self._amounts.get(item_id)

    def get_required_field_entries(self, item_id: str) -> Sequence[FieldRegistryEntry]:
        return self._fields.get(item_id, ())


class FakeEvidenceRepository:
    """In-memory fake evidence repository for unit testing.

    By default returns enough citations to cover all requested references.
    Set `incomplete_refs` to simulate missing citations for specific references.
    """

    def __init__(
        self,
        *,
        citations: Sequence[Citation] | None = None,
        incomplete_refs: frozenset[str] | None = None,
    ) -> None:
        self._citations = citations
        self._incomplete_refs = incomplete_refs or frozenset()

    def get_citations_for_references(
        self,
        item_id: str,
        source_references: Sequence[str],
    ) -> Sequence[Citation]:
        if self._citations is not None:
            return self._citations

        # Auto-generate one citation per reference, excluding incomplete ones
        from datetime import UTC, datetime

        result = []
        for ref in source_references:
            if ref not in self._incomplete_refs:
                result.append(
                    Citation(
                        document_id=f"doc-{ref}",
                        title=f"Title for {ref}",
                        publisher="Test Publisher",
                        published_at=datetime(2024, 1, 1, tzinfo=UTC),
                        effective_at=datetime(2024, 1, 1, tzinfo=UTC),
                        url=f"https://example.com/{ref}",
                        excerpt=f"Excerpt for {ref}",
                        retrieved_at=datetime(2024, 6, 1, tzinfo=UTC),
                    )
                )
        return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SIMPLE_RULE = RuleDefinition(
    rule_id="rule-001",
    item_id="item-A",
    version=1,
    dsl_version="1.0",
    required_field_ids=("age", "income"),
    root=AllOf(
        children=(
            Condition(
                condition_id="c1",
                field_id="age",
                operator=">=",
                expected=18,
                label="Must be 18 or older",
                source_reference="ref-age-law",
            ),
            Condition(
                condition_id="c2",
                field_id="income",
                operator="<=",
                expected=50000,
                label="Income threshold",
                source_reference="ref-income-reg",
            ),
        )
    ),
    source_references=("ref-age-law", "ref-income-reg"),
)

_APPROVED_AMOUNT = ApprovedAmount(
    amount_min=3000,
    amount_max=5000,
    amount_period="monthly",
    amount_currency="TWD",
)


def _build_service(
    *,
    statuses: dict[str, ProgramStatus] | None = None,
    rules: dict[str, RuleDefinition | None] | None = None,
    amounts: dict[str, ApprovedAmount | None] | None = None,
    fields: dict[str, Sequence[FieldRegistryEntry]] | None = None,
    incomplete_refs: frozenset[str] | None = None,
    citations: Sequence[Citation] | None = None,
) -> DeterministicEligibilityService:
    """Helper to build service with test fakes."""
    rule_repo = FakeRuleRepository(
        statuses=statuses,
        rules=rules,
        amounts=amounts,
        fields=fields,
    )
    evidence_repo = FakeEvidenceRepository(
        citations=citations,
        incomplete_refs=incomplete_refs,
    )
    return DeterministicEligibilityService(rule_repo, evidence_repo)


# ---------------------------------------------------------------------------
# Tests: verified + complete citations → full evaluation
# ---------------------------------------------------------------------------


class TestVerifiedCompleteCitations:
    """Verified program with complete citations evaluates fully."""

    def test_eligible_with_amount(self) -> None:
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
            amounts={"item-A": _APPROVED_AMOUNT},
        )

        decision = service.evaluate("item-A", {"age": 25, "income": 30000})

        assert decision.status == "eligible"
        assert decision.item_id == "item-A"
        assert decision.amount_min == 3000
        assert decision.amount_max == 5000
        assert decision.amount_period == "monthly"
        assert decision.amount_currency == "TWD"
        assert len(decision.reasons) > 0
        assert decision.missing_field_ids == ()

    def test_ineligible_no_amount(self) -> None:
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
            amounts={"item-A": _APPROVED_AMOUNT},
        )

        # age < 18 fails the rule
        decision = service.evaluate("item-A", {"age": 16, "income": 30000})

        assert decision.status == "ineligible"
        assert decision.amount_min is None  # not eligible, no amount
        assert len(decision.reasons) > 0


# ---------------------------------------------------------------------------
# Tests: verified + missing citations → downgrade
# ---------------------------------------------------------------------------


class TestVerifiedMissingCitations:
    """Verified program with incomplete citations downgrades to needs_human_review."""

    def test_downgrade_when_citation_missing(self) -> None:
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
            amounts={"item-A": _APPROVED_AMOUNT},
            # One of the source references has no citation
            incomplete_refs=frozenset({"ref-income-reg"}),
        )

        decision = service.evaluate("item-A", {"age": 25, "income": 30000})

        assert decision.status == "needs_human_review"
        assert decision.amount_min is None
        assert decision.amount_max is None

    def test_downgrade_preserves_reasons(self) -> None:
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
            incomplete_refs=frozenset({"ref-age-law"}),
        )

        decision = service.evaluate("item-A", {"age": 25, "income": 30000})

        assert decision.status == "needs_human_review"
        # Reasons from evaluation are preserved for traceability
        assert len(decision.reasons) > 0

    def test_downgrade_preserves_item_id(self) -> None:
        """Citation gap downgrade preserves item_id in decision."""
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
            amounts={"item-A": _APPROVED_AMOUNT},
            incomplete_refs=frozenset({"ref-income-reg"}),
        )

        decision = service.evaluate("item-A", {"age": 25, "income": 30000})

        assert decision.status == "needs_human_review"
        assert decision.item_id == "item-A"
        # Amount stripped on downgrade
        assert decision.amount_min is None
        assert decision.amount_max is None


# ---------------------------------------------------------------------------
# Tests: verified + missing fields → needs_information
# ---------------------------------------------------------------------------


class TestVerifiedMissingFields:
    """Verified program with missing required fields returns needs_information."""

    def test_missing_single_field(self) -> None:
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
        )

        # Only provide 'age', missing 'income'
        decision = service.evaluate("item-A", {"age": 25})

        assert decision.status == "needs_information"
        assert decision.missing_field_ids == ("income",)
        assert decision.reasons == ()

    def test_missing_multiple_fields_sorted(self) -> None:
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
        )

        # Provide no fields
        decision = service.evaluate("item-A", {})

        assert decision.status == "needs_information"
        assert decision.missing_field_ids == ("age", "income")


# ---------------------------------------------------------------------------
# Tests: candidate/under_review → needs_human_review, engine not called
# ---------------------------------------------------------------------------


class TestCandidateUnderReview:
    """candidate and under_review statuses return needs_human_review."""

    @pytest.mark.parametrize("status", ["candidate", "under_review"])
    def test_returns_needs_human_review(self, status: ProgramStatus) -> None:
        service = _build_service(
            statuses={"item-X": status},
            # Even if a rule exists, it should NOT be called
            rules={"item-X": _SIMPLE_RULE},
        )

        decision = service.evaluate("item-X", {"age": 25, "income": 30000})

        assert decision.status == "needs_human_review"
        assert decision.item_id == "item-X"
        assert decision.amount_min is None
        assert decision.missing_field_ids == ()
        assert decision.reasons == ()

    @pytest.mark.parametrize("status", ["candidate", "under_review"])
    def test_engine_not_called_no_structured_reasons(
        self, status: ProgramStatus
    ) -> None:
        """Engine call count = 0 for non-verified statuses."""
        service = _build_service(
            statuses={"item-X": status},
            rules={"item-X": _SIMPLE_RULE},
            amounts={"item-X": _APPROVED_AMOUNT},
        )

        decision = service.evaluate("item-X", {"age": 25, "income": 30000})

        # No reasons means engine was never invoked
        assert decision.reasons == ()
        # No amount means approved amount was never applied
        assert decision.amount_min is None
        assert decision.amount_max is None
        assert decision.amount_period is None
        assert decision.amount_currency is None


# ---------------------------------------------------------------------------
# Tests: stale → needs_human_review, engine not called
# ---------------------------------------------------------------------------


class TestStale:
    """stale status returns needs_human_review without engine invocation."""

    def test_stale_returns_needs_human_review(self) -> None:
        service = _build_service(
            statuses={"item-S": "stale"},
            rules={"item-S": _SIMPLE_RULE},
        )

        decision = service.evaluate("item-S", {"age": 25, "income": 30000})

        assert decision.status == "needs_human_review"
        assert decision.item_id == "item-S"
        assert decision.amount_min is None
        assert decision.reasons == ()

    def test_stale_engine_not_called_no_amount(self) -> None:
        """Engine call count = 0 for stale: no reasons, no amount."""
        service = _build_service(
            statuses={"item-S": "stale"},
            rules={"item-S": _SIMPLE_RULE},
            amounts={"item-S": _APPROVED_AMOUNT},
        )

        decision = service.evaluate("item-S", {"age": 25, "income": 30000})

        assert decision.reasons == ()
        assert decision.amount_min is None
        assert decision.amount_max is None
        assert decision.amount_period is None
        assert decision.amount_currency is None


# ---------------------------------------------------------------------------
# Tests: rejected/inactive → NonEvaluableStatusError
# ---------------------------------------------------------------------------


class TestRejectedInactive:
    """rejected and inactive statuses raise NonEvaluableStatusError."""

    @pytest.mark.parametrize("status", ["rejected", "inactive"])
    def test_raises_non_evaluable_error(self, status: ProgramStatus) -> None:
        service = _build_service(
            statuses={"item-R": status},
        )

        with pytest.raises(NonEvaluableStatusError) as exc_info:
            service.evaluate("item-R", {"age": 25})

        assert exc_info.value.item_id == "item-R"
        assert exc_info.value.status == status
        assert status in str(exc_info.value)

    @pytest.mark.parametrize("status", ["rejected", "inactive"])
    def test_error_is_data_layer_error_subclass(self, status: ProgramStatus) -> None:
        service = _build_service(statuses={"item-R": status})

        from app.orchestration.data_errors import DataLayerError

        with pytest.raises(DataLayerError):
            service.evaluate("item-R", {})


# ---------------------------------------------------------------------------
# Tests: verified + no approved rule → needs_human_review
# ---------------------------------------------------------------------------


class TestVerifiedNoApprovedRule:
    """Verified program with no approved rule returns needs_human_review."""

    def test_no_rule_returns_needs_human_review(self) -> None:
        service = _build_service(
            statuses={"item-N": "verified"},
            rules={"item-N": None},  # explicitly no rule
        )

        decision = service.evaluate("item-N", {"age": 25})

        assert decision.status == "needs_human_review"
        assert decision.item_id == "item-N"
        assert decision.amount_min is None

    def test_rule_not_in_dict_returns_needs_human_review(self) -> None:
        """Rule repository returns None for unknown items."""
        service = _build_service(
            statuses={"item-N": "verified"},
            # rules dict doesn't have item-N → get_approved_rule returns None
        )

        decision = service.evaluate("item-N", {"age": 25})

        assert decision.status == "needs_human_review"


# ---------------------------------------------------------------------------
# Tests: evaluate_many
# ---------------------------------------------------------------------------


class TestEvaluateMany:
    """evaluate_many iterates over items correctly."""

    def test_evaluates_multiple_items(self) -> None:
        rule_b = RuleDefinition(
            rule_id="rule-002",
            item_id="item-B",
            version=1,
            dsl_version="1.0",
            required_field_ids=("age",),
            root=Condition(
                condition_id="c1",
                field_id="age",
                operator=">=",
                expected=65,
                label="Senior citizen",
                source_reference="ref-senior",
            ),
            source_references=("ref-senior",),
        )

        service = _build_service(
            statuses={
                "item-A": "verified",
                "item-B": "verified",
                "item-C": "candidate",
            },
            rules={
                "item-A": _SIMPLE_RULE,
                "item-B": rule_b,
            },
        )

        decisions = service.evaluate_many(
            ["item-A", "item-B", "item-C"],
            {"age": 70, "income": 30000},
        )

        assert len(decisions) == 3
        assert decisions[0].item_id == "item-A"
        assert decisions[0].status == "eligible"
        assert decisions[1].item_id == "item-B"
        assert decisions[1].status == "eligible"
        assert decisions[2].item_id == "item-C"
        assert decisions[2].status == "needs_human_review"


# ---------------------------------------------------------------------------
# Tests: get_required_fields delegates
# ---------------------------------------------------------------------------


class TestGetRequiredFields:
    """get_required_fields delegates to rule repository."""

    def test_delegates_to_repository(self) -> None:
        entry = FieldRegistryEntry(
            field_id="age",
            data_type="integer",
            allowed_values=(),
            prompt_label="What is your age?",
            why_needed="Age determines eligibility threshold",
            pii_classification="quasi_identifier",
        )

        service = _build_service(fields={"item-A": [entry]})

        result = service.get_required_fields("item-A")

        assert len(result) == 1
        assert result[0].field_id == "age"


# ---------------------------------------------------------------------------
# Tests: Relevance score does not affect eligibility (Req 8.9)
# ---------------------------------------------------------------------------


class TestScoreDoesNotAffectEligibility:
    """Relevance score is never part of EligibilityDecision outputs.

    The EligibilityService evaluates using rule DSL conditions only.
    There is no relevance_score field on EligibilityDecision, and the service
    does not consult or expose any score value.
    """

    def test_eligible_decision_has_no_score_field(self) -> None:
        """EligibilityDecision structurally has no relevance_score."""
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
            amounts={"item-A": _APPROVED_AMOUNT},
        )

        decision = service.evaluate("item-A", {"age": 25, "income": 30000})

        assert decision.status == "eligible"
        # EligibilityDecision does not have a relevance_score attribute
        assert not hasattr(decision, "relevance_score")

    def test_ineligible_decision_has_no_score_field(self) -> None:
        """Ineligible decisions also have no relevance_score."""
        service = _build_service(
            statuses={"item-A": "verified"},
            rules={"item-A": _SIMPLE_RULE},
        )

        decision = service.evaluate("item-A", {"age": 16, "income": 30000})

        assert decision.status == "ineligible"
        assert not hasattr(decision, "relevance_score")

    def test_needs_human_review_decision_has_no_score_field(self) -> None:
        """needs_human_review decisions also have no relevance_score."""
        service = _build_service(
            statuses={"item-S": "stale"},
        )

        decision = service.evaluate("item-S", {})

        assert decision.status == "needs_human_review"
        assert not hasattr(decision, "relevance_score")
