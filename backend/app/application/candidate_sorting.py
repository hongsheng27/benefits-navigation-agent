"""Deterministic total ordering for candidate items.

Sorts candidates by:
1. Program status safety group (verified → stale → under_review → candidate;
   rejected/inactive sort last).
2. Relevance score descending within the same status group.
3. Items with None relevance_score sort AFTER items with valid finite scores.
4. item_id ascending as deterministic tie-breaker.

Score is purely for ordering — it never affects eligibility determination.
No candidate content (display_name, field IDs, prerequisites, etc.) is included
in any logged event.

Requirements: 8.1–8.6, 8.9–8.11.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.orchestration.data_contracts import CandidateItem, ProgramStatus

logger = logging.getLogger(__name__)

# Status group ordering: lower number = higher priority.
_STATUS_ORDER: dict[ProgramStatus, int] = {
    "verified": 0,
    "stale": 1,
    "under_review": 2,
    "candidate": 3,
    "rejected": 4,
    "inactive": 4,
}


def _sort_key(item: CandidateItem) -> tuple[int, int, float, str]:
    """Build a deterministic composite sort key for a CandidateItem.

    Returns a tuple of:
    - status group order (int, ascending)
    - score-missing flag (0 = has valid score, 1 = None/missing)
    - negated score for descending order (higher score first)
    - item_id for ascending tie-break
    """
    status_rank = _STATUS_ORDER.get(item.program_status, 4)

    score = item.relevance_score
    if score is None:
        # None sorts after valid scores within the same group.
        score_missing = 1
        neg_score = 0.0
    else:
        score_missing = 0
        neg_score = -float(score)

    return (status_rank, score_missing, neg_score, item.item_id)


def sort_candidates(candidates: Sequence[CandidateItem]) -> list[CandidateItem]:
    """Return a new list of candidates in deterministic total order.

    The function is pure and side-effect-free aside from a safe data-quality
    log when normalized scores are detected. The same input always produces the
    same output (deterministic).

    Args:
        candidates: A sequence of CandidateItem instances to sort.

    Returns:
        A new sorted list. The original sequence is not modified.
    """
    # Detect items with None score that might indicate normalization from
    # NaN/infinity (done by CandidateItem.__post_init__). Log a safe
    # data-quality event with only item count — no candidate content.
    none_score_count = sum(1 for c in candidates if c.relevance_score is None)
    if none_score_count > 0:
        # Safe event: only contains a count, no candidate content.
        logger.info(
            "candidate_sorting_data_quality: %d item(s) with missing/normalized score",
            none_score_count,
        )

    return sorted(candidates, key=_sort_key)
