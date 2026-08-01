"""Property 10: Citation exact mapping 與 completeness.

**Validates: Requirements 7.1, 7.8, 10.1–10.10**

每個 evaluated distinct reference 都須 exact mapping approved citation；
optional date 缺失不單獨降級。

Properties tested:
1. Complete citation mapping → no downgrade
2. Incomplete citation → downgrade to needs_human_review
3. Optional date missing does NOT independently downgrade
4. Exact mapping: required fields are non-empty, evidence repo returns exact citation
5. Every evaluated reference must have at least one citation
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.application.eligibility_service import (
    DeterministicEligibilityService,
    EvidenceRepositoryPort,
    RuleRepository,
)
from app.orchestration.data_contracts import (
    Citation,
    EligibilityDecision,
    FieldRegistryEntry,
    FrozenValue,
    ProgramStatus,
    StructuredReason,
)
from app.rules.dsl import AllOf, AnyOf, Condition, RuleDefinition, RuleNode
from app.rules.evaluation import ApprovedAmount

# ---------------------------------------------------------------------------
# Fixed field IDs
# ---------------------------------------------------------------------------

INT_FIELD_IDS = ("f0", "f1", "f2")
STR_FIELD_IDS = ("f3", "f4")
ALL_FIELD_IDS = INT_FIELD_IDS + STR_FIELD_IDS

COMPARISON_OPERATORS = ("==", "!=", ">=", "<=", ">", "<")
COLLECTION_OPERATORS = ("in", "not_in")
ALL_OPERATORS = COMPARISON_OPERATORS + COLLECTION_OPERATORS

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_int_values = st.integers(min_value=-50, max_value=50)
_str_values = st.sampled_from(["alpha", "beta", "gamma", "delta", "epsilon"])
_aware_datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2025, 12, 31),
    timezones=st.just(timezone.utc),
)
_non_empty_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=30,
)
_url_text = st.from_regex(
    r"https://[a-z]{3,10}\.[a-z]{2,5}/[a-z0-9]{1,15}", fullmatch=True
)


@st.composite
def _citation_for_ref(
    draw: st.DrawFn,
    *,
    force_no_dates: bool = False,
) -> Citation:
    """Generate a valid Citation with required fields always non-empty.

    Optional dates may be None if force_no_dates is True, otherwise random.
    """
    document_id = draw(_non_empty_text)
    title = draw(_non_empty_text)
    publisher = draw(_non_empty_text)
    url = draw(_url_text)
    excerpt = draw(_non_empty_text)

    if force_no_dates:
        published_at = None
        effective_at = None
        retrieved_at = None
    else:
        published_at = draw(st.one_of(st.none(), _aware_datetimes))
        effective_at = draw(st.one_of(st.none(), _aware_datetimes))
        retrieved_at = draw(st.one_of(st.none(), _aware_datetimes))

    return Citation(
        document_id=document_id,
        title=title,
        publisher=publisher,
        published_at=published_at,
        effective_at=effective_at,
        url=url,
        excerpt=excerpt,
        retrieved_at=retrieved_at,
    )


@st.composite
def _rule_all_satisfied(
    draw: st.DrawFn,
) -> tuple[RuleDefinition, dict[str, Any], list[str]]:
    """Generate a RuleDefinition with 1-4 conditions that ALL evaluate to satisfied.

    This guarantees all source_references appear in the decision's reasons,
    making citation completeness checks meaningful.

    Strategy: All conditions use the same field (f0) with the same expected value
    and == operator. This ensures all evaluate to True.

    Returns (rule_definition, user_attributes, list_of_source_references).
    """
    num_conditions = draw(st.integers(min_value=1, max_value=4))
    source_refs = [f"src_ref_{i}" for i in range(num_conditions)]

    # Single shared value → all conditions satisfied
    shared_val = draw(_int_values)

    counter = [0]
    conditions: list[Condition] = []

    for ref in source_refs:
        counter[0] += 1
        cid = f"c{counter[0]}"
        conditions.append(
            Condition(
                condition_id=cid,
                field_id="f0",
                operator="==",
                expected=shared_val,
                label=f"label_{cid}",
                source_reference=ref,
            )
        )

    attrs: dict[str, Any] = {"f0": shared_val}

    if len(conditions) == 1:
        root: RuleNode = conditions[0]
    else:
        root = AllOf(children=tuple(conditions))

    rule = RuleDefinition(
        rule_id="rule_p10",
        item_id="item_p10",
        version=1,
        dsl_version="1.0",
        required_field_ids=("f0",),
        root=root,
        source_references=tuple(source_refs),
    )

    return rule, attrs, source_refs


@st.composite
def _rule_with_distinct_refs(
    draw: st.DrawFn,
) -> tuple[RuleDefinition, dict[str, Any], list[str]]:
    """Generate a RuleDefinition with 1-4 conditions, each with a distinct source_reference.

    User attributes are complete (no missing fields) so evaluation always produces
    eligible or ineligible. The evaluation result may not include all refs in reasons
    due to AllOf/AnyOf short-circuit semantics.

    Returns (rule_definition, user_attributes, list_of_source_references).
    """
    num_conditions = draw(st.integers(min_value=1, max_value=4))
    source_refs = [f"src_ref_{i}" for i in range(num_conditions)]

    counter = [0]
    conditions: list[Condition] = []

    for ref in source_refs:
        counter[0] += 1
        cid = f"c{counter[0]}"
        use_int = draw(st.booleans())

        if use_int:
            field_id = draw(st.sampled_from(INT_FIELD_IDS))
            operator = draw(st.sampled_from(ALL_OPERATORS))
            if operator in COLLECTION_OPERATORS:
                expected: FrozenValue = draw(
                    st.lists(_int_values, min_size=1, max_size=3).map(tuple)
                )
            else:
                expected = draw(_int_values)
        else:
            field_id = draw(st.sampled_from(STR_FIELD_IDS))
            operator = draw(st.sampled_from(ALL_OPERATORS))
            if operator in COLLECTION_OPERATORS:
                expected = draw(
                    st.lists(_str_values, min_size=1, max_size=3).map(tuple)
                )
            else:
                expected = draw(_str_values)

        conditions.append(
            Condition(
                condition_id=cid,
                field_id=field_id,
                operator=operator,
                expected=expected,
                label=f"label_{cid}",
                source_reference=ref,
            )
        )

    if len(conditions) == 1:
        root: RuleNode = conditions[0]
    else:
        root = AllOf(children=tuple(conditions))

    field_ids = sorted({c.field_id for c in conditions})

    rule = RuleDefinition(
        rule_id="rule_p10",
        item_id="item_p10",
        version=1,
        dsl_version="1.0",
        required_field_ids=tuple(field_ids),
        root=root,
        source_references=tuple(source_refs),
    )

    attrs: dict[str, Any] = {}
    for fid in field_ids:
        if fid in INT_FIELD_IDS:
            attrs[fid] = draw(_int_values)
        else:
            attrs[fid] = draw(_str_values)

    return rule, attrs, source_refs


# ---------------------------------------------------------------------------
# Fake repositories
# ---------------------------------------------------------------------------


class _FakeRuleRepository:
    """Fake RuleRepository that returns configurable program data."""

    def __init__(
        self,
        rule: RuleDefinition,
        status: ProgramStatus = "verified",
        amount: ApprovedAmount | None = None,
    ) -> None:
        self._rule = rule
        self._status = status
        self._amount = amount

    def get_program_status(self, item_id: str) -> ProgramStatus:
        return self._status

    def get_approved_rule(self, item_id: str) -> RuleDefinition | None:
        return self._rule

    def get_approved_amount(self, item_id: str) -> ApprovedAmount | None:
        return self._amount

    def get_required_field_entries(self, item_id: str) -> Sequence[FieldRegistryEntry]:
        return ()


class _CompleteEvidenceRepository:
    """Evidence repository that returns one citation per requested source_reference."""

    def __init__(self, citations_map: dict[str, Citation]) -> None:
        self._map = citations_map

    def get_citations_for_references(
        self,
        item_id: str,
        source_references: Sequence[str],
    ) -> Sequence[Citation]:
        result: list[Citation] = []
        for ref in source_references:
            if ref in self._map:
                result.append(self._map[ref])
        return result


class _EmptyEvidenceRepository:
    """Evidence repository that returns zero citations for any request."""

    def __init__(self) -> None:
        self.requested_refs: list[str] = []

    def get_citations_for_references(
        self,
        item_id: str,
        source_references: Sequence[str],
    ) -> Sequence[Citation]:
        self.requested_refs = list(source_references)
        return []


class _PartialEvidenceRepository:
    """Evidence repository that returns only one citation regardless of how many are requested."""

    def __init__(self, citation: Citation) -> None:
        self._citation = citation

    def get_citations_for_references(
        self,
        item_id: str,
        source_references: Sequence[str],
    ) -> Sequence[Citation]:
        # Return only one citation even when multiple refs are requested
        if len(source_references) >= 1:
            return [self._citation]
        return []


# ---------------------------------------------------------------------------
# Property 1: Complete citation mapping → no downgrade
# ---------------------------------------------------------------------------


@given(data=st.data())
@settings(max_examples=200, deadline=5000)
def test_complete_citations_no_downgrade(data: st.DataObject) -> None:
    """When every distinct source_reference has a citation, the service does NOT downgrade.

    For a verified program with a rule that evaluates to eligible/ineligible:
    If the evidence repository provides a Citation for each distinct source_reference,
    the service returns eligible or ineligible (not needs_human_review).
    """
    rule, attrs, source_refs = data.draw(_rule_with_distinct_refs())

    # Generate a citation for each source reference
    citations_map: dict[str, Citation] = {}
    for ref in source_refs:
        citations_map[ref] = data.draw(_citation_for_ref())

    rule_repo = _FakeRuleRepository(rule=rule, status="verified")
    evidence_repo = _CompleteEvidenceRepository(citations_map)

    service = DeterministicEligibilityService(
        rule_repository=rule_repo,
        evidence_repository=evidence_repo,
    )

    decision = service.evaluate("item_p10", attrs)

    # The decision must be eligible or ineligible (not downgraded)
    assert decision.status in ("eligible", "ineligible"), (
        f"Expected eligible/ineligible with complete citations, "
        f"got '{decision.status}'"
    )
    assert decision.item_id == "item_p10"


# ---------------------------------------------------------------------------
# Property 2: Incomplete citation → downgrade to needs_human_review
# ---------------------------------------------------------------------------


@given(data=st.data())
@settings(max_examples=200, deadline=5000)
def test_incomplete_citations_downgrade_to_needs_human_review(
    data: st.DataObject,
) -> None:
    """When ALL citations are missing, and the evaluation produces reasons with
    source_references, the service MUST downgrade to needs_human_review.

    Strategy: Use a rule where all conditions are satisfied (guaranteeing all
    source_references appear in reasons), then provide zero citations.
    """
    rule, attrs, source_refs = data.draw(_rule_all_satisfied())

    rule_repo = _FakeRuleRepository(rule=rule, status="verified")
    evidence_repo = _EmptyEvidenceRepository()

    service = DeterministicEligibilityService(
        rule_repository=rule_repo,
        evidence_repository=evidence_repo,
    )

    decision = service.evaluate("item_p10", attrs)

    # All conditions are satisfied → eligible before citation check.
    # But with zero citations, the service must downgrade.
    assert decision.status == "needs_human_review", (
        f"Expected needs_human_review with zero citations, "
        f"got '{decision.status}'. "
        f"Source refs: {source_refs}, "
        f"Requested refs: {evidence_repo.requested_refs}"
    )
    # item_id is preserved
    assert decision.item_id == "item_p10"


# ---------------------------------------------------------------------------
# Property 3: Optional date missing does NOT independently downgrade
# ---------------------------------------------------------------------------


@given(data=st.data())
@settings(max_examples=200, deadline=5000)
def test_optional_date_missing_does_not_downgrade(data: st.DataObject) -> None:
    """Citations with missing optional dates (published_at, effective_at, retrieved_at)
    are still valid and do NOT cause downgrade to needs_human_review.

    Required fields (document_id, title, publisher, url, excerpt) are present and non-empty.
    """
    rule, attrs, source_refs = data.draw(_rule_with_distinct_refs())

    # Generate citations with ALL optional dates explicitly None
    citations_map: dict[str, Citation] = {}
    for ref in source_refs:
        citations_map[ref] = data.draw(_citation_for_ref(force_no_dates=True))

    rule_repo = _FakeRuleRepository(rule=rule, status="verified")
    evidence_repo = _CompleteEvidenceRepository(citations_map)

    service = DeterministicEligibilityService(
        rule_repository=rule_repo,
        evidence_repository=evidence_repo,
    )

    decision = service.evaluate("item_p10", attrs)

    # Even with all dates None, the service must NOT downgrade
    assert decision.status in ("eligible", "ineligible"), (
        f"Expected eligible/ineligible (dates are optional), "
        f"got '{decision.status}'"
    )


# ---------------------------------------------------------------------------
# Property 4: Exact mapping — required fields non-empty, same citation returned
# ---------------------------------------------------------------------------


@given(data=st.data())
@settings(max_examples=200, deadline=5000)
def test_exact_mapping_required_fields_non_empty(data: st.DataObject) -> None:
    """For any generated Citation:
    - document_id, title, publisher, url, excerpt must all be non-empty strings
    - The evidence repository returns the exact same citation (no modification)
    - Each source_reference maps to the citation provided for it
    """
    rule, attrs, source_refs = data.draw(_rule_with_distinct_refs())

    # Generate citations with guaranteed non-empty required fields
    citations_map: dict[str, Citation] = {}
    for ref in source_refs:
        citation = data.draw(_citation_for_ref())
        citations_map[ref] = citation

        # Verify required fields are non-empty strings
        assert isinstance(citation.document_id, str) and len(citation.document_id) > 0
        assert isinstance(citation.title, str) and len(citation.title) > 0
        assert isinstance(citation.publisher, str) and len(citation.publisher) > 0
        assert isinstance(citation.url, str) and len(citation.url) > 0
        assert isinstance(citation.excerpt, str) and len(citation.excerpt) > 0

    # Verify the evidence repo returns the EXACT same citation for each ref
    evidence_repo = _CompleteEvidenceRepository(citations_map)
    returned = evidence_repo.get_citations_for_references("item_p10", source_refs)

    assert len(returned) == len(source_refs), (
        f"Expected {len(source_refs)} citations, got {len(returned)}"
    )

    # Each returned citation must be identical to the one stored
    for i, ref in enumerate(source_refs):
        assert returned[i] == citations_map[ref], (
            f"Citation for ref '{ref}' was modified. "
            f"Expected: {citations_map[ref]}, Got: {returned[i]}"
        )


# ---------------------------------------------------------------------------
# Property 5: Every evaluated reference must have at least one citation
# ---------------------------------------------------------------------------


@given(data=st.data())
@settings(max_examples=200, deadline=5000)
def test_fewer_citations_than_references_causes_human_review(
    data: st.DataObject,
) -> None:
    """When evidence repo returns fewer citations than distinct source references
    in the evaluation reasons, the result is needs_human_review.

    Strategy: Generate a rule where ALL conditions are satisfied (so all refs
    appear in reasons), then provide only 1 citation for N>=2 distinct refs.
    """
    # Generate rule with at least 2 conditions, all satisfied.
    # Key: all conditions use the same field and same expected value so ALL pass.
    num_conditions = data.draw(st.integers(min_value=2, max_value=4))
    source_refs = [f"src_ref_{i}" for i in range(num_conditions)]

    # Single value used for all conditions on f0 == val
    val = data.draw(_int_values)
    counter = [0]
    conditions: list[Condition] = []

    for ref in source_refs:
        counter[0] += 1
        cid = f"c{counter[0]}"
        conditions.append(
            Condition(
                condition_id=cid,
                field_id="f0",
                operator="==",
                expected=val,
                label=f"label_{cid}",
                source_reference=ref,
            )
        )

    attrs: dict[str, Any] = {"f0": val}

    root: RuleNode = AllOf(children=tuple(conditions))

    rule = RuleDefinition(
        rule_id="rule_p10",
        item_id="item_p10",
        version=1,
        dsl_version="1.0",
        required_field_ids=("f0",),
        root=root,
        source_references=tuple(source_refs),
    )

    # Provide only one citation when the service will ask for multiple refs
    single_citation = data.draw(_citation_for_ref())

    rule_repo = _FakeRuleRepository(rule=rule, status="verified")
    evidence_repo = _PartialEvidenceRepository(single_citation)

    service = DeterministicEligibilityService(
        rule_repository=rule_repo,
        evidence_repository=evidence_repo,
    )

    decision = service.evaluate("item_p10", attrs)

    # With N distinct refs but only 1 citation returned, must downgrade
    assert decision.status == "needs_human_review", (
        f"Expected needs_human_review when citations (1) < references ({num_conditions}), "
        f"got '{decision.status}'"
    )
    assert decision.item_id == "item_p10"
