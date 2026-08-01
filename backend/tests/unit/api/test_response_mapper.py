"""Unit tests for owner-aware API response mapper.

Tests:
- relevance_score omission from API response
- requesting user gets actual values
- non-requesting user has actual values removed
- program_status included in item view
- legacy decisive_conditions still present
- optional dates on citations
"""

from datetime import UTC, datetime

from app.api.response_mapper import map_item_to_api_view, map_to_api_response
from app.orchestration import data_contracts as dc
from app.orchestration import state


def _make_workflow_item(
    *,
    item_id: str = "test_item",
    status: state.ItemStatus = state.ItemStatus.ELIGIBLE,
    program_status: str = "verified",
    decisive_conditions: tuple[state.DecisiveCondition, ...] = (),
    citations: tuple[state.Citation, ...] = (),
    amount_min: int | None = None,
    amount_max: int | None = None,
    amount_period: state.AmountPeriod | None = None,
    amount_currency: str | None = None,
) -> state.CandidateItem:
    return state.CandidateItem(
        item_id=item_id,
        kind=state.ItemKind.BENEFIT,
        status=status,
        program_status=program_status,
        decisive_conditions=decisive_conditions,
        citations=citations,
        amount_min=amount_min,
        amount_max=amount_max,
        amount_period=amount_period,
        amount_currency=amount_currency,
    )


class TestRelevanceScoreOmission:
    """Relevance score must NEVER appear in API response."""

    def test_item_view_has_no_relevance_score_field(self) -> None:
        """ItemView structurally cannot contain relevance_score."""
        item = _make_workflow_item()
        view = map_item_to_api_view(item, is_requesting_user=True)

        serialized = view.model_dump(by_alias=True)
        assert "relevance_score" not in serialized
        assert "relevanceScore" not in serialized

    def test_batch_response_has_no_relevance_score(self) -> None:
        items = (
            _make_workflow_item(item_id="a"),
            _make_workflow_item(item_id="b"),
        )
        views = map_to_api_response(items, is_requesting_user=True)

        for view in views:
            serialized = view.model_dump(by_alias=True)
            assert "relevanceScore" not in serialized
            assert "relevance_score" not in serialized


class TestRequestingUserGetsActualValues:
    """Requesting user sees actual values in decisive conditions."""

    def test_decisive_conditions_include_actual(self) -> None:
        condition = state.DecisiveCondition(
            field_id="relationship",
            expected="spouse",
            actual="sibling",
        )
        item = _make_workflow_item(decisive_conditions=(condition,))

        view = map_item_to_api_view(item, is_requesting_user=True)

        assert len(view.decisive_conditions) == 1
        assert view.decisive_conditions[0].actual == "sibling"

    def test_structured_reasons_include_actual(self) -> None:
        item = _make_workflow_item()
        reason = dc.StructuredReason(
            condition_id="cond_001",
            field_id="age_band",
            operator="gte",
            expected="65",
            actual="60",
            label="年齡條件",
            source_reference="ref_001",
        )

        view = map_item_to_api_view(
            item,
            is_requesting_user=True,
            domain_reasons=(reason,),
        )

        assert len(view.structured_reasons) == 1
        assert view.structured_reasons[0].actual == "60"


class TestNonRequestingUserActualRemoved:
    """Non-requesting user must not see actual values."""

    def test_decisive_conditions_actual_removed(self) -> None:
        condition = state.DecisiveCondition(
            field_id="income_band",
            expected="low",
            actual="high",
        )
        item = _make_workflow_item(decisive_conditions=(condition,))

        view = map_item_to_api_view(item, is_requesting_user=False)

        assert view.decisive_conditions[0].actual == ""

    def test_structured_reasons_actual_removed(self) -> None:
        item = _make_workflow_item()
        reason = dc.StructuredReason(
            condition_id="cond_002",
            field_id="residency",
            operator="eq",
            expected="domestic",
            actual="overseas",
            label="居住地條件",
            source_reference="ref_002",
        )

        view = map_item_to_api_view(
            item,
            is_requesting_user=False,
            domain_reasons=(reason,),
        )

        assert view.structured_reasons[0].actual is None

    def test_both_decisive_and_structured_actual_removed(self) -> None:
        """Non-requesting user: actual removed from both formats."""
        condition = state.DecisiveCondition(
            field_id="age_band",
            expected="senior",
            actual="middle",
        )
        item = _make_workflow_item(decisive_conditions=(condition,))
        reason = dc.StructuredReason(
            condition_id="cond_004",
            field_id="age_band",
            operator="gte",
            expected="65",
            actual="45",
            label="年齡條件",
            source_reference="ref_004",
        )

        view = map_item_to_api_view(
            item,
            is_requesting_user=False,
            domain_reasons=(reason,),
        )

        # Both legacy and new format have actual removed
        assert view.decisive_conditions[0].actual == ""
        assert view.structured_reasons[0].actual is None


class TestProgramStatusIncluded:
    """program_status must be included in item view."""

    def test_verified_status(self) -> None:
        item = _make_workflow_item(program_status="verified")
        view = map_item_to_api_view(item, is_requesting_user=True)
        assert view.program_status == "verified"

    def test_stale_status(self) -> None:
        item = _make_workflow_item(program_status="stale")
        view = map_item_to_api_view(item, is_requesting_user=True)
        assert view.program_status == "stale"

    def test_candidate_status(self) -> None:
        item = _make_workflow_item(program_status="candidate")
        view = map_item_to_api_view(item, is_requesting_user=True)
        assert view.program_status == "candidate"

    def test_program_status_in_camel_case_serialization(self) -> None:
        item = _make_workflow_item(program_status="under_review")
        view = map_item_to_api_view(item, is_requesting_user=True)
        serialized = view.model_dump(by_alias=True)
        assert serialized["programStatus"] == "under_review"


class TestLegacyDecisiveConditionsPresent:
    """Legacy decisive_conditions still present alongside structured_reasons."""

    def test_both_formats_coexist(self) -> None:
        condition = state.DecisiveCondition(
            field_id="employment_type",
            expected="insured",
            actual="uninsured",
        )
        item = _make_workflow_item(decisive_conditions=(condition,))
        reason = dc.StructuredReason(
            condition_id="cond_003",
            field_id="employment_type",
            operator="eq",
            expected="insured",
            actual="uninsured",
            label="投保身分",
            source_reference="ref_003",
        )

        view = map_item_to_api_view(
            item,
            is_requesting_user=True,
            domain_reasons=(reason,),
        )

        # Both legacy and new format present
        assert len(view.decisive_conditions) == 1
        assert len(view.structured_reasons) == 1
        assert view.decisive_conditions[0].field_id == "employment_type"
        assert view.structured_reasons[0].field_id == "employment_type"

    def test_legacy_camel_case_alias(self) -> None:
        """decisiveConditions should appear in camelCase serialization."""
        condition = state.DecisiveCondition(
            field_id="age",
            expected=65,
            actual=60,
        )
        item = _make_workflow_item(decisive_conditions=(condition,))
        view = map_item_to_api_view(item, is_requesting_user=True)
        serialized = view.model_dump(by_alias=True)
        assert "decisiveConditions" in serialized


class TestCitationOptionalDates:
    """Citations should include effective_at and retrieved_at when present."""

    def test_dates_from_domain_citation(self) -> None:
        workflow_citation = state.Citation(
            document_id="doc_001",
            title="Test Law",
            publisher_name="Ministry",
            published_at="2023-01-15T00:00:00+00:00",
            url="https://law.example.gov",
            excerpt="Test excerpt",
        )
        domain_citation = dc.Citation(
            document_id="doc_001",
            title="Test Law",
            publisher="Ministry",
            published_at=datetime(2023, 1, 15, tzinfo=UTC),
            effective_at=datetime(2023, 3, 1, tzinfo=UTC),
            url="https://law.example.gov",
            excerpt="Test excerpt",
            retrieved_at=datetime(2024, 6, 15, tzinfo=UTC),
        )
        item = _make_workflow_item(citations=(workflow_citation,))

        view = map_item_to_api_view(
            item,
            is_requesting_user=True,
            domain_citations=(domain_citation,),
        )

        assert view.citations[0].effective_at == "2023-03-01T00:00:00+00:00"
        assert view.citations[0].retrieved_at == "2024-06-15T00:00:00+00:00"

    def test_none_dates_remain_none(self) -> None:
        workflow_citation = state.Citation(
            document_id="doc_002",
            title="Another Law",
            publisher_name="Ministry",
            published_at=None,
            url="https://example.com",
            excerpt="",
        )
        domain_citation = dc.Citation(
            document_id="doc_002",
            title="Another Law",
            publisher="Ministry",
            published_at=None,
            effective_at=None,
            url="https://example.com",
            excerpt="",
            retrieved_at=None,
        )
        item = _make_workflow_item(citations=(workflow_citation,))

        view = map_item_to_api_view(
            item,
            is_requesting_user=True,
            domain_citations=(domain_citation,),
        )

        assert view.citations[0].effective_at is None
        assert view.citations[0].retrieved_at is None
        assert view.citations[0].published_at is None

    def test_publisher_name_alias_preserved(self) -> None:
        """publisherName should appear in camelCase serialization."""
        workflow_citation = state.Citation(
            document_id="doc_003",
            title="Law Title",
            publisher_name="勞動部",
            published_at=None,
            url="https://example.com",
            excerpt="",
        )
        item = _make_workflow_item(citations=(workflow_citation,))

        view = map_item_to_api_view(item, is_requesting_user=True)
        serialized = view.citations[0].model_dump(by_alias=True)
        assert "publisherName" in serialized
        assert serialized["publisherName"] == "勞動部"


class TestScoreOmissionFromSerializedJson:
    """Score must never appear in serialized JSON output."""

    def test_model_dump_json_has_no_score(self) -> None:
        """JSON serialization structurally cannot contain relevance score."""
        item = _make_workflow_item(item_id="test")
        view = map_item_to_api_view(item, is_requesting_user=True)

        json_str = view.model_dump_json(by_alias=True)
        assert "relevanceScore" not in json_str
        assert "relevance_score" not in json_str
        assert "score" not in json_str.lower() or "score" in "relevanceScore"
        # More precise: check that "score" as a standalone key doesn't appear
        import json

        data = json.loads(json_str)
        assert "relevanceScore" not in data
        assert "relevance_score" not in data


class TestLegacyAliasesInJson:
    """Legacy aliases must be present in camelCase serialized JSON."""

    def test_decisive_conditions_camel_case_in_json(self) -> None:
        """decisiveConditions appears in JSON output."""
        condition = state.DecisiveCondition(
            field_id="income",
            expected="low",
            actual="high",
        )
        item = _make_workflow_item(decisive_conditions=(condition,))
        view = map_item_to_api_view(item, is_requesting_user=True)

        json_str = view.model_dump_json(by_alias=True)
        assert "decisiveConditions" in json_str

    def test_structured_reasons_camel_case_in_json(self) -> None:
        """structuredReasons appears in JSON output."""
        item = _make_workflow_item()
        reason = dc.StructuredReason(
            condition_id="cond_005",
            field_id="income",
            operator="lte",
            expected="50000",
            actual="60000",
            label="收入條件",
            source_reference="ref_005",
        )
        view = map_item_to_api_view(
            item, is_requesting_user=True, domain_reasons=(reason,)
        )

        json_str = view.model_dump_json(by_alias=True)
        assert "structuredReasons" in json_str

    def test_program_status_camel_case_in_json(self) -> None:
        """programStatus appears in JSON output."""
        item = _make_workflow_item(program_status="verified")
        view = map_item_to_api_view(item, is_requesting_user=True)

        json_str = view.model_dump_json(by_alias=True)
        assert "programStatus" in json_str


class TestOptionalDateNullHandling:
    """Optional date None→null handling in serialized output."""

    def test_none_dates_serialize_to_null(self) -> None:
        """None dates become null in JSON output."""
        import json

        workflow_citation = state.Citation(
            document_id="doc_null",
            title="No Dates Law",
            publisher_name="Ministry",
            published_at=None,
            url="https://example.com",
            excerpt="",
        )
        domain_citation = dc.Citation(
            document_id="doc_null",
            title="No Dates Law",
            publisher="Ministry",
            published_at=None,
            effective_at=None,
            url="https://example.com",
            excerpt="",
            retrieved_at=None,
        )
        item = _make_workflow_item(citations=(workflow_citation,))

        view = map_item_to_api_view(
            item,
            is_requesting_user=True,
            domain_citations=(domain_citation,),
        )

        json_str = view.model_dump_json(by_alias=True)
        data = json.loads(json_str)
        citation_data = data["citations"][0]
        assert citation_data["publishedAt"] is None
        assert citation_data["effectiveAt"] is None
        assert citation_data["retrievedAt"] is None

    def test_present_dates_serialize_to_string(self) -> None:
        """Present dates become ISO strings in JSON output."""
        import json

        workflow_citation = state.Citation(
            document_id="doc_full",
            title="Full Dates Law",
            publisher_name="Ministry",
            published_at="2024-01-01T00:00:00+00:00",
            url="https://example.com",
            excerpt="",
        )
        domain_citation = dc.Citation(
            document_id="doc_full",
            title="Full Dates Law",
            publisher="Ministry",
            published_at=datetime(2024, 1, 1, tzinfo=UTC),
            effective_at=datetime(2024, 6, 1, tzinfo=UTC),
            url="https://example.com",
            excerpt="",
            retrieved_at=datetime(2024, 7, 1, tzinfo=UTC),
        )
        item = _make_workflow_item(citations=(workflow_citation,))

        view = map_item_to_api_view(
            item,
            is_requesting_user=True,
            domain_citations=(domain_citation,),
        )

        json_str = view.model_dump_json(by_alias=True)
        data = json.loads(json_str)
        citation_data = data["citations"][0]
        assert citation_data["effectiveAt"] is not None
        assert citation_data["retrievedAt"] is not None
        assert "2024" in citation_data["effectiveAt"]
        assert "2024" in citation_data["retrievedAt"]
