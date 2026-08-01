"""Unit tests for deterministic candidate total ordering.

Covers:
- Status group ordering (verified before stale before under_review before candidate)
- Score descending within same status group
- None/missing score after valid scores
- item_id tie-break when scores are equal
- Deterministic: same input always produces same output
- Mixed statuses with various scores
- Empty input returns empty output
- Single item returns single item

Requirements: 8.1–8.6, 8.9–8.11.
"""

from __future__ import annotations

from app.application.candidate_sorting import sort_candidates
from app.orchestration.data_contracts import CandidateItem


def _make_item(
    item_id: str = "item-1",
    program_status: str = "candidate",
    relevance_score: int | float | None = None,
    display_name: str = "Test Item",
) -> CandidateItem:
    """Helper to create a CandidateItem with minimal boilerplate."""
    return CandidateItem(
        item_id=item_id,
        display_name=display_name,
        program_status=program_status,  # type: ignore[arg-type]
        relevance_score=relevance_score,
        missing_field_ids=(),
        prerequisites=(),
        produces=(),
    )


class TestStatusGroupOrdering:
    """Status ordering: verified→stale→under_review→candidate→rejected/inactive."""

    def test_verified_before_stale(self) -> None:
        items = [
            _make_item("b", "stale", 100),
            _make_item("a", "verified", 100),
        ]
        result = sort_candidates(items)
        assert result[0].item_id == "a"
        assert result[1].item_id == "b"

    def test_stale_before_under_review(self) -> None:
        items = [
            _make_item("b", "under_review", 100),
            _make_item("a", "stale", 100),
        ]
        result = sort_candidates(items)
        assert result[0].item_id == "a"
        assert result[1].item_id == "b"

    def test_under_review_before_candidate(self) -> None:
        items = [
            _make_item("b", "candidate", 100),
            _make_item("a", "under_review", 100),
        ]
        result = sort_candidates(items)
        assert result[0].item_id == "a"
        assert result[1].item_id == "b"

    def test_full_status_order(self) -> None:
        items = [
            _make_item("d", "candidate", 100),
            _make_item("b", "stale", 100),
            _make_item("c", "under_review", 100),
            _make_item("a", "verified", 100),
        ]
        result = sort_candidates(items)
        assert [r.item_id for r in result] == ["a", "b", "c", "d"]

    def test_rejected_and_inactive_sort_last(self) -> None:
        items = [
            _make_item("c", "rejected", 100),
            _make_item("a", "verified", 100),
            _make_item("d", "inactive", 100),
            _make_item("b", "candidate", 100),
        ]
        result = sort_candidates(items)
        # verified (a) → candidate (b) → rejected/inactive (c, d by item_id)
        assert result[0].item_id == "a"
        assert result[1].item_id == "b"
        # rejected and inactive share rank 4, sorted by item_id
        assert result[2].item_id == "c"
        assert result[3].item_id == "d"


class TestScoreDescendingWithinGroup:
    """Higher scores first within the same status group."""

    def test_higher_score_first(self) -> None:
        items = [
            _make_item("a", "candidate", 50),
            _make_item("b", "candidate", 90),
            _make_item("c", "candidate", 70),
        ]
        result = sort_candidates(items)
        assert [r.item_id for r in result] == ["b", "c", "a"]

    def test_float_scores(self) -> None:
        items = [
            _make_item("a", "verified", 3.14),
            _make_item("b", "verified", 9.99),
            _make_item("c", "verified", 6.28),
        ]
        result = sort_candidates(items)
        assert [r.item_id for r in result] == ["b", "c", "a"]

    def test_negative_scores(self) -> None:
        items = [
            _make_item("a", "candidate", -10),
            _make_item("b", "candidate", -5),
            _make_item("c", "candidate", 0),
        ]
        result = sort_candidates(items)
        assert [r.item_id for r in result] == ["c", "b", "a"]


class TestNoneMissingScoreAfterValid:
    """Items with None relevance_score sort after items with valid scores."""

    def test_none_after_valid_scores(self) -> None:
        items = [
            _make_item("a", "candidate", None),
            _make_item("b", "candidate", 50),
            _make_item("c", "candidate", 80),
        ]
        result = sort_candidates(items)
        # Valid scores first (descending), then None
        assert [r.item_id for r in result] == ["c", "b", "a"]

    def test_multiple_none_sorted_by_item_id(self) -> None:
        items = [
            _make_item("c", "stale", None),
            _make_item("a", "stale", None),
            _make_item("b", "stale", 10),
        ]
        result = sort_candidates(items)
        # b (score 10) first, then a, c (both None, by item_id)
        assert [r.item_id for r in result] == ["b", "a", "c"]

    def test_nan_normalized_to_none_sorts_last(self) -> None:
        """NaN is normalized to None by CandidateItem.__post_init__."""
        item_nan = _make_item("a", "candidate", float("nan"))
        item_valid = _make_item("b", "candidate", 50)
        # After construction, item_nan.relevance_score is None
        assert item_nan.relevance_score is None
        result = sort_candidates([item_nan, item_valid])
        assert [r.item_id for r in result] == ["b", "a"]

    def test_inf_normalized_to_none_sorts_last(self) -> None:
        """Infinity is normalized to None by CandidateItem.__post_init__."""
        item_inf = _make_item("a", "candidate", float("inf"))
        item_valid = _make_item("b", "candidate", 50)
        assert item_inf.relevance_score is None
        result = sort_candidates([item_inf, item_valid])
        assert [r.item_id for r in result] == ["b", "a"]


class TestItemIdTieBreak:
    """item_id ascending as tie-breaker when scores are equal or both missing."""

    def test_same_score_tiebreak_by_id(self) -> None:
        items = [
            _make_item("z", "candidate", 80),
            _make_item("a", "candidate", 80),
            _make_item("m", "candidate", 80),
        ]
        result = sort_candidates(items)
        assert [r.item_id for r in result] == ["a", "m", "z"]

    def test_both_none_tiebreak_by_id(self) -> None:
        items = [
            _make_item("z", "candidate", None),
            _make_item("a", "candidate", None),
        ]
        result = sort_candidates(items)
        assert [r.item_id for r in result] == ["a", "z"]


class TestDeterministic:
    """Same input always produces same output."""

    def test_repeated_sort_same_result(self) -> None:
        items = [
            _make_item("c", "candidate", 50),
            _make_item("a", "verified", 90),
            _make_item("b", "stale", None),
            _make_item("d", "under_review", 70),
        ]
        first = sort_candidates(items)
        second = sort_candidates(items)
        third = sort_candidates(items)
        assert first == second == third

    def test_different_input_order_same_result(self) -> None:
        items_a = [
            _make_item("a", "candidate", 50),
            _make_item("b", "verified", 90),
            _make_item("c", "stale", 70),
        ]
        items_b = [
            _make_item("c", "stale", 70),
            _make_item("a", "candidate", 50),
            _make_item("b", "verified", 90),
        ]
        assert sort_candidates(items_a) == sort_candidates(items_b)


class TestMixedStatusesAndScores:
    """Complex scenarios mixing statuses and scores."""

    def test_mixed_statuses_and_scores(self) -> None:
        items = [
            _make_item("e", "candidate", 100),
            _make_item("a", "verified", 50),
            _make_item("b", "verified", 80),
            _make_item("c", "stale", None),
            _make_item("d", "under_review", 60),
            _make_item("f", "candidate", None),
        ]
        result = sort_candidates(items)
        # verified: b(80) → a(50)
        # stale: c(None)
        # under_review: d(60)
        # candidate: e(100) → f(None)
        assert [r.item_id for r in result] == ["b", "a", "c", "d", "e", "f"]

    def test_all_same_status_sorted_by_score_then_id(self) -> None:
        items = [
            _make_item("c", "candidate", 50),
            _make_item("a", "candidate", 50),
            _make_item("b", "candidate", 90),
        ]
        result = sort_candidates(items)
        # b(90) first, then a, c (same score=50, by item_id)
        assert [r.item_id for r in result] == ["b", "a", "c"]


class TestEdgeCases:
    """Edge cases: empty input and single item."""

    def test_empty_input_returns_empty(self) -> None:
        assert sort_candidates([]) == []
        assert sort_candidates(()) == []

    def test_single_item_returns_single(self) -> None:
        item = _make_item("only", "verified", 42)
        result = sort_candidates([item])
        assert result == [item]

    def test_original_not_mutated(self) -> None:
        items = [
            _make_item("b", "candidate", 50),
            _make_item("a", "verified", 90),
        ]
        original_order = list(items)
        sort_candidates(items)
        # Original list unchanged
        assert items == original_order


class TestScoreDoesNotAffectEligibility:
    """Score is purely for ordering and does not change eligibility semantics."""

    def test_zero_score_does_not_filter_item(self) -> None:
        items = [
            _make_item("a", "candidate", 0),
            _make_item("b", "candidate", 100),
        ]
        result = sort_candidates(items)
        # Both items preserved, just ordered
        assert len(result) == 2
        assert {r.item_id for r in result} == {"a", "b"}

    def test_negative_score_does_not_filter_item(self) -> None:
        items = [
            _make_item("a", "candidate", -999),
            _make_item("b", "candidate", 100),
        ]
        result = sort_candidates(items)
        assert len(result) == 2
        assert {r.item_id for r in result} == {"a", "b"}
