"""Property 9: Candidate total ordering 與 score non-exposure.

**Validates: Requirements 8.1–8.11**

Verifies:
- sort_candidates() produces a stable total order regardless of input permutation.
- Score never affects eligibility (item set preservation).
- Serialization (API view and domain→workflow mapper) never exposes score,
  range, or percentage fields.
"""

from __future__ import annotations

import random
import re

from hypothesis import given, settings
from hypothesis import strategies as st

from app.application.candidate_sorting import sort_candidates
from app.application.mappers import map_domain_to_workflow
from app.api.response_mapper import map_item_to_api_view
from app.orchestration.data_contracts import CandidateItem, ProgramStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_STATUSES: list[ProgramStatus] = [
    "verified",
    "stale",
    "under_review",
    "candidate",
    "rejected",
    "inactive",
]

_STATUS_ORDER: dict[str, int] = {
    "verified": 0,
    "stale": 1,
    "under_review": 2,
    "candidate": 3,
    "rejected": 4,
    "inactive": 4,
}

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_item_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=1,
    max_size=12,
)

_scores = st.one_of(
    st.none(),
    st.integers(min_value=-1000, max_value=1000),
    st.floats(
        min_value=-1000.0,
        max_value=1000.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)

_statuses = st.sampled_from(_VALID_STATUSES)


@st.composite
def _candidate_item(draw: st.DrawFn) -> CandidateItem:
    """Generate a CandidateItem with random id, status, and score."""
    item_id = draw(_item_ids)
    status = draw(_statuses)
    score = draw(_scores)
    return CandidateItem(
        item_id=item_id,
        display_name=f"Item {item_id}",
        program_status=status,
        relevance_score=score,
        missing_field_ids=(),
        prerequisites=(),
        produces=(),
    )


@st.composite
def _candidate_list(draw: st.DrawFn) -> list[CandidateItem]:
    """Generate a list of CandidateItems with unique item_ids."""
    n = draw(st.integers(min_value=0, max_value=15))
    items: list[CandidateItem] = []
    used_ids: set[str] = set()
    for _ in range(n):
        item = draw(_candidate_item())
        # Ensure unique item_ids for deterministic ordering
        if item.item_id in used_ids:
            suffix = str(len(used_ids))
            item = CandidateItem(
                item_id=item.item_id + suffix,
                display_name=item.display_name,
                program_status=item.program_status,
                relevance_score=item.relevance_score,
                missing_field_ids=(),
                prerequisites=(),
                produces=(),
            )
        used_ids.add(item.item_id)
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# Property 9.1: Stable total ordering (shuffle invariance)
# ---------------------------------------------------------------------------


@given(candidates=_candidate_list())
@settings(max_examples=200, deadline=5000)
def test_sort_is_shuffle_invariant(candidates: list[CandidateItem]) -> None:
    """Sorting the same items in any input order produces the same result.

    This verifies Requirements 8.3, 8.4, 8.5, 8.11: deterministic ordering
    regardless of input permutation.
    """
    if len(candidates) == 0:
        assert sort_candidates(candidates) == []
        return

    reference = sort_candidates(candidates)

    # Shuffle the input and sort again
    shuffled = list(candidates)
    random.shuffle(shuffled)
    result = sort_candidates(shuffled)

    assert result == reference, (
        "sort_candidates must produce the same output regardless of input order"
    )


@given(candidates=_candidate_list())
@settings(max_examples=200, deadline=5000)
def test_status_group_ordering_respected(candidates: list[CandidateItem]) -> None:
    """Within the sorted result, status group ordering is always respected.

    Requirements 8.3: verified→stale→under_review→candidate→rejected/inactive.
    """
    result = sort_candidates(candidates)

    for i in range(len(result) - 1):
        rank_a = _STATUS_ORDER.get(result[i].program_status, 4)
        rank_b = _STATUS_ORDER.get(result[i + 1].program_status, 4)
        assert rank_a <= rank_b, (
            f"Status ordering violated: {result[i].program_status} (rank {rank_a}) "
            f"should not come after {result[i + 1].program_status} (rank {rank_b})"
        )


@given(candidates=_candidate_list())
@settings(max_examples=200, deadline=5000)
def test_within_status_group_valid_scores_descending(
    candidates: list[CandidateItem],
) -> None:
    """Within the same status group, valid scores sort descending.

    Requirements 8.4: Relevance_Score descending with item_id ascending tie-break.
    Requirements 8.5: None scores always come after valid scores.
    """
    result = sort_candidates(candidates)

    for i in range(len(result) - 1):
        a, b = result[i], result[i + 1]
        # Only check within the same status group
        if _STATUS_ORDER.get(a.program_status, 4) != _STATUS_ORDER.get(
            b.program_status, 4
        ):
            continue

        score_a = a.relevance_score
        score_b = b.relevance_score

        if score_a is not None and score_b is not None:
            # Both valid: a.score >= b.score (descending)
            # If equal, item_id ascending
            if score_a == score_b:
                assert a.item_id <= b.item_id, (
                    f"Tie-break violated: {a.item_id} should be <= {b.item_id} "
                    f"when scores are equal ({score_a})"
                )
            else:
                assert score_a > score_b, (
                    f"Score ordering violated: {score_a} should be > {score_b} "
                    f"within same group"
                )
        elif score_a is not None and score_b is None:
            # Valid before None: correct
            pass
        elif score_a is None and score_b is not None:
            # None before valid: WRONG
            assert False, (
                f"None score ({a.item_id}) must not come before "
                f"valid score ({b.item_id}, score={score_b})"
            )
        else:
            # Both None: item_id ascending
            assert a.item_id <= b.item_id, (
                f"Tie-break violated for both-None: "
                f"{a.item_id} should be <= {b.item_id}"
            )


# ---------------------------------------------------------------------------
# Property 9.2: Score does not affect eligibility (item set preservation)
# ---------------------------------------------------------------------------


@given(candidates=_candidate_list(), data=st.data())
@settings(max_examples=200, deadline=5000)
def test_score_does_not_filter_items(
    candidates: list[CandidateItem], data: st.DataObject
) -> None:
    """Changing only the score never changes the set of items returned.

    Requirements 8.9: Eligibility_Service SHALL exclude using Relevance_Score
    to determine or modify Eligibility_Status.

    Score = 0, negative, large positive, None all preserve the item.
    """
    result = sort_candidates(candidates)

    # All items must be preserved (no filtering)
    assert len(result) == len(candidates)
    assert {r.item_id for r in result} == {c.item_id for c in candidates}

    # Now mutate scores randomly and verify same item set
    mutated = []
    for c in candidates:
        new_score = data.draw(
            st.one_of(
                st.none(),
                st.just(0),
                st.integers(min_value=-9999, max_value=9999),
                st.floats(
                    min_value=-9999.0,
                    max_value=9999.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
            ),
            label=f"new_score_{c.item_id}",
        )
        mutated.append(
            CandidateItem(
                item_id=c.item_id,
                display_name=c.display_name,
                program_status=c.program_status,
                relevance_score=new_score,
                missing_field_ids=c.missing_field_ids,
                prerequisites=c.prerequisites,
                produces=c.produces,
            )
        )

    mutated_result = sort_candidates(mutated)
    assert len(mutated_result) == len(mutated)
    assert {r.item_id for r in mutated_result} == {c.item_id for c in candidates}


# ---------------------------------------------------------------------------
# Property 9.3: Serialization never contains score/range/percentage
# ---------------------------------------------------------------------------

_SCORE_KEYS = {"relevance_score", "score", "relevanceScore", "relevance_Score"}
_PERCENTAGE_PATTERN = re.compile(r"\d+(\.\d+)?%")


def _check_dict_no_score(d: dict, path: str = "") -> None:
    """Recursively check a dict has no score-related keys or percentage values."""
    for key, value in d.items():
        full_path = f"{path}.{key}" if path else key
        # Check key names
        assert key.lower() not in {k.lower() for k in _SCORE_KEYS}, (
            f"Score-related key found at {full_path}"
        )
        assert "score" not in key.lower(), (
            f"Score-related key '{key}' found at {full_path}"
        )
        # Check string values for percentage patterns
        if isinstance(value, str):
            assert not _PERCENTAGE_PATTERN.search(value), (
                f"Percentage pattern found in {full_path}: {value}"
            )
        elif isinstance(value, dict):
            _check_dict_no_score(value, full_path)
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    _check_dict_no_score(item, f"{full_path}[{i}]")


@given(candidates=_candidate_list())
@settings(max_examples=200, deadline=5000)
def test_api_view_never_contains_score(candidates: list[CandidateItem]) -> None:
    """map_domain_to_workflow output never contains relevance_score.

    Requirements 8.7, 8.8: API_Response_Mapper SHALL exclude relevance_score,
    ranges, and derived percentages.
    """
    from app.orchestration import state

    for candidate in candidates:
        # map_domain_to_workflow: data_contracts.CandidateItem → state.CandidateItem
        workflow_item = map_domain_to_workflow(candidate)

        # Verify the workflow item has no relevance_score attribute exposed
        workflow_dict = workflow_item.model_dump()
        _check_dict_no_score(workflow_dict)

        # map_item_to_api_view: state.CandidateItem → ItemView
        api_view = map_item_to_api_view(
            workflow_item,
            is_requesting_user=True,
        )
        api_dict = api_view.model_dump()
        _check_dict_no_score(api_dict)


@given(
    score=st.one_of(
        st.none(),
        st.integers(min_value=-10000, max_value=10000),
        st.floats(
            min_value=-10000.0,
            max_value=10000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    ),
    status=_statuses,
)
@settings(max_examples=200, deadline=5000)
def test_api_view_excludes_score_for_all_score_values(
    score: int | float | None,
    status: ProgramStatus,
) -> None:
    """For any valid score value, the serialized API view never includes score fields.

    Requirements 8.7, 8.8: No field values contain percentage patterns or
    score-like numeric ranges.
    """
    candidate = CandidateItem(
        item_id="test-item",
        display_name="Test Item",
        program_status=status,
        relevance_score=score,
        missing_field_ids=(),
        prerequisites=(),
        produces=(),
    )

    # Through domain→workflow mapper
    workflow_item = map_domain_to_workflow(candidate)
    workflow_dict = workflow_item.model_dump()
    _check_dict_no_score(workflow_dict)

    # Through API response mapper
    api_view = map_item_to_api_view(workflow_item, is_requesting_user=True)
    api_dict = api_view.model_dump()
    _check_dict_no_score(api_dict)

    # Also check non-requesting user path
    api_view_other = map_item_to_api_view(workflow_item, is_requesting_user=False)
    api_dict_other = api_view_other.model_dump()
    _check_dict_no_score(api_dict_other)
