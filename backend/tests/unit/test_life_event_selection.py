"""多事件選取規則。"""

from app.orchestration.life_event_selection import (
    MAX_CONFIRMED_LIFE_EVENTS,
    normalize_life_event_ids,
    pick_extra_candidate_life_events,
)
from app.orchestration.life_events import default_life_events


def test_normalize_dedupes_and_caps() -> None:
    registry = default_life_events()
    ids = normalize_life_event_ids(
        [
            "occupational_injury",
            "job_loss",
            "occupational_injury",
            "not_a_real_event",
            "caregiver_burden",
            "disability_onset",
            "long_term_care_need",
            "serious_illness",
        ],
        registry,
    )
    assert ids == (
        "occupational_injury",
        "job_loss",
        "caregiver_burden",
        "disability_onset",
        "long_term_care_need",
    )
    assert len(ids) == MAX_CONFIRMED_LIFE_EVENTS


def test_extra_candidates_are_related_and_limited() -> None:
    registry = default_life_events()
    extras = pick_extra_candidate_life_events(
        ("occupational_injury", "job_loss"), registry
    )
    assert len(extras) == 3
    assert "occupational_injury" not in extras
    assert "job_loss" not in extras
    assert all(registry.has(event_id) for event_id in extras)
