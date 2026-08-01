"""Unit tests for domain→workflow mappers.

Tests:
- domain CandidateItem → workflow CandidateItem mapping
- EligibilityDecision → workflow item with status, reasons, amounts
- relevance_score is NEVER in output
- optional dates handling
"""

from datetime import UTC, datetime

from app.application.mappers import (
    map_domain_citations_to_workflow,
    map_domain_to_workflow,
)
from app.orchestration import data_contracts as dc
from app.orchestration import state


class TestMapDomainToWorkflowBasic:
    """Test basic domain CandidateItem → workflow CandidateItem mapping."""

    def test_pending_item_without_decision(self) -> None:
        """A candidate without decision should map to PENDING status."""
        candidate = dc.CandidateItem(
            item_id="funeral_benefit",
            display_name="喪葬給付",
            program_status="verified",
            relevance_score=0.85,
            missing_field_ids=("age_band", "relationship"),
            prerequisites=(),
            produces=(),
        )

        result = map_domain_to_workflow(candidate)

        assert result.item_id == "funeral_benefit"
        assert result.status == state.ItemStatus.PENDING
        assert result.program_status == "verified"
        assert result.missing_field_ids == ("age_band", "relationship")

    def test_relevance_score_never_in_output(self) -> None:
        """Relevance score must NEVER appear in the workflow CandidateItem."""
        candidate = dc.CandidateItem(
            item_id="test_item",
            display_name="Test",
            program_status="verified",
            relevance_score=99.5,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        )

        result = map_domain_to_workflow(candidate)

        # CandidateItem in state.py does not have a relevance_score field
        assert (
            not hasattr(result, "relevance_score")
            or "relevance_score" not in result.model_fields
        )

    def test_program_status_preserved_candidate(self) -> None:
        """program_status should be preserved on the workflow item."""
        candidate = dc.CandidateItem(
            item_id="test_item",
            display_name="Test",
            program_status="stale",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        )

        result = map_domain_to_workflow(candidate)
        assert result.program_status == "stale"

    def test_program_status_preserved_under_review(self) -> None:
        candidate = dc.CandidateItem(
            item_id="item_x",
            display_name="X",
            program_status="under_review",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        )

        result = map_domain_to_workflow(candidate)
        assert result.program_status == "under_review"


class TestMapDomainToWorkflowWithDecision:
    """Test mapping with EligibilityDecision."""

    def test_eligible_decision_maps_status(self) -> None:
        candidate = dc.CandidateItem(
            item_id="survivor_pension",
            display_name="遺屬年金",
            program_status="verified",
            relevance_score=0.9,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        )
        decision = dc.EligibilityDecision(
            item_id="survivor_pension",
            status="eligible",
            amount_min=5000,
            amount_max=10000,
            amount_period="monthly",
            amount_currency="TWD",
            missing_field_ids=(),
            reasons=(),
        )

        result = map_domain_to_workflow(candidate, decision)

        assert result.status == state.ItemStatus.ELIGIBLE
        assert result.amount_min == 5000
        assert result.amount_max == 10000
        assert result.amount_period == state.AmountPeriod.MONTHLY
        assert result.amount_currency == "TWD"

    def test_ineligible_with_structured_reasons(self) -> None:
        candidate = dc.CandidateItem(
            item_id="funeral_benefit",
            display_name="喪葬給付",
            program_status="verified",
            relevance_score=0.7,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        )
        reason = dc.StructuredReason(
            condition_id="cond_001",
            field_id="relationship",
            operator="eq",
            expected="spouse",
            actual="sibling",
            label="與亡者關係",
            source_reference="ref_001",
        )
        decision = dc.EligibilityDecision(
            item_id="funeral_benefit",
            status="ineligible",
            amount_min=None,
            amount_max=None,
            amount_period=None,
            amount_currency=None,
            missing_field_ids=(),
            reasons=(reason,),
        )

        result = map_domain_to_workflow(candidate, decision)

        assert result.status == state.ItemStatus.INELIGIBLE
        assert len(result.decisive_conditions) == 1
        dc_view = result.decisive_conditions[0]
        assert dc_view.field_id == "relationship"
        assert dc_view.expected == "spouse"
        assert dc_view.actual == "sibling"

    def test_needs_information_with_missing_fields(self) -> None:
        candidate = dc.CandidateItem(
            item_id="child_benefit",
            display_name="育兒津貼",
            program_status="verified",
            relevance_score=None,
            missing_field_ids=("income_band", "child_count"),
            prerequisites=(),
            produces=(),
        )
        decision = dc.EligibilityDecision(
            item_id="child_benefit",
            status="needs_information",
            amount_min=None,
            amount_max=None,
            amount_period=None,
            amount_currency=None,
            missing_field_ids=("child_count", "income_band"),
            reasons=(),
        )

        result = map_domain_to_workflow(candidate, decision)

        assert result.status == state.ItemStatus.NEEDS_INFORMATION
        # missing_field_ids from decision are sorted and deduped by EligibilityDecision
        assert "child_count" in result.missing_field_ids
        assert "income_band" in result.missing_field_ids

    def test_needs_human_review_status(self) -> None:
        candidate = dc.CandidateItem(
            item_id="stale_item",
            display_name="Stale",
            program_status="stale",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        )
        decision = dc.EligibilityDecision(
            item_id="stale_item",
            status="needs_human_review",
            amount_min=None,
            amount_max=None,
            amount_period=None,
            amount_currency=None,
            missing_field_ids=(),
            reasons=(),
        )

        result = map_domain_to_workflow(candidate, decision)

        assert result.status == state.ItemStatus.NEEDS_HUMAN_REVIEW
        assert result.program_status == "stale"

    def test_amount_quartet_all_none(self) -> None:
        """When no amount is known, all four fields are None."""
        candidate = dc.CandidateItem(
            item_id="admin_task",
            display_name="死亡登記",
            program_status="verified",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        )
        decision = dc.EligibilityDecision(
            item_id="admin_task",
            status="eligible",
            amount_min=None,
            amount_max=None,
            amount_period=None,
            amount_currency=None,
            missing_field_ids=(),
            reasons=(),
        )

        result = map_domain_to_workflow(candidate, decision)

        assert result.amount_min is None
        assert result.amount_max is None
        assert result.amount_period is None
        assert result.amount_currency is None

    def test_relevance_score_not_in_output_with_decision(self) -> None:
        """Even with a decision, relevance_score must not appear in output."""
        candidate = dc.CandidateItem(
            item_id="item_with_score",
            display_name="Score Item",
            program_status="verified",
            relevance_score=100,
            missing_field_ids=(),
            prerequisites=(),
            produces=(),
        )
        decision = dc.EligibilityDecision(
            item_id="item_with_score",
            status="eligible",
            amount_min=1000,
            amount_max=1000,
            amount_period="one_time",
            amount_currency="TWD",
            missing_field_ids=(),
            reasons=(),
        )

        result = map_domain_to_workflow(candidate, decision)

        # The workflow CandidateItem structurally cannot hold relevance_score
        serialized = result.model_dump()
        assert "relevance_score" not in serialized


class TestMapDomainCitationsToWorkflow:
    """Test citation mapping with optional dates."""

    def test_basic_citation_mapping(self) -> None:
        citation = dc.Citation(
            document_id="doc_001",
            title="勞工保險條例第 62 條",
            publisher="勞動部",
            published_at=datetime(2023, 1, 15, tzinfo=UTC),
            effective_at=datetime(2023, 3, 1, tzinfo=UTC),
            url="https://law.example.gov/62",
            excerpt="被保險人死亡時...",
            retrieved_at=datetime(2024, 6, 1, tzinfo=UTC),
        )

        result = map_domain_citations_to_workflow((citation,))

        assert len(result) == 1
        c = result[0]
        assert c.document_id == "doc_001"
        assert c.title == "勞工保險條例第 62 條"
        assert c.publisher_name == "勞動部"  # publisher → publisher_name
        assert c.published_at == "2023-01-15T00:00:00+00:00"
        assert c.url == "https://law.example.gov/62"
        assert c.excerpt == "被保險人死亡時..."

    def test_citation_with_none_published_at(self) -> None:
        """When published_at is None, it should map to None."""
        citation = dc.Citation(
            document_id="doc_002",
            title="Unknown Date Document",
            publisher="Test Publisher",
            published_at=None,
            effective_at=None,
            url="https://example.com",
            excerpt="",
            retrieved_at=None,
        )

        result = map_domain_citations_to_workflow((citation,))
        assert result[0].published_at is None

    def test_multiple_citations(self) -> None:
        citations = (
            dc.Citation(
                document_id="doc_a",
                title="Title A",
                publisher="Pub A",
                published_at=datetime(2022, 6, 1, tzinfo=UTC),
                effective_at=None,
                url="https://a.example.com",
                excerpt="Excerpt A",
                retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            dc.Citation(
                document_id="doc_b",
                title="Title B",
                publisher="Pub B",
                published_at=None,
                effective_at=datetime(2023, 1, 1, tzinfo=UTC),
                url="https://b.example.com",
                excerpt="Excerpt B",
                retrieved_at=None,
            ),
        )

        result = map_domain_citations_to_workflow(citations)
        assert len(result) == 2
        assert result[0].document_id == "doc_a"
        assert result[1].document_id == "doc_b"
