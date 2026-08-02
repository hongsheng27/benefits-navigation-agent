"""多生命事件選取的共用規則：去重、上限、候補三個。

LLM 只建議已登記的事件代號；補助清單仍由 expand 聯集決定。
"""

from __future__ import annotations

from collections.abc import Sequence

from app.orchestration.life_events import LifeEventRegistry

MAX_CONFIRMED_LIFE_EVENTS = 5
MAX_EXTRA_CANDIDATE_LIFE_EVENTS = 3

# 常見共現：用來補「另外三個可能相關」選項（確定性，不靠模型灌水）。
_RELATED_EVENTS: dict[str, tuple[str, ...]] = {
    "occupational_injury": (
        "job_loss",
        "disability_onset",
        "long_term_care_need",
        "caregiver_burden",
    ),
    "job_loss": (
        "unpaid_leave",
        "low_income_hardship",
        "caregiver_burden",
        "occupational_injury",
    ),
    "caregiver_burden": (
        "long_term_care_need",
        "disability_onset",
        "job_loss",
        "mental_health_crisis",
    ),
    "long_term_care_need": (
        "caregiver_burden",
        "disability_onset",
        "serious_illness",
    ),
    "disability_onset": (
        "long_term_care_need",
        "caregiver_burden",
        "serious_illness",
    ),
    "spouse_death": (
        "job_loss",
        "low_income_hardship",
        "mental_health_crisis",
    ),
    "parent_death": (
        "spouse_death",
        "other_relative_death",
        "job_loss",
    ),
    "serious_illness": (
        "disability_onset",
        "long_term_care_need",
        "job_loss",
    ),
}


def normalize_life_event_ids(
    event_ids: Sequence[str],
    registry: LifeEventRegistry,
    *,
    max_count: int = MAX_CONFIRMED_LIFE_EVENTS,
) -> tuple[str, ...]:
    """保留順序去重，只留登記表內代號，並截斷上限。"""
    seen: set[str] = set()
    result: list[str] = []
    for event_id in event_ids:
        if event_id in seen or not registry.has(event_id):
            continue
        seen.add(event_id)
        result.append(event_id)
        if len(result) >= max_count:
            break
    return tuple(result)


def pick_extra_candidate_life_events(
    selected: Sequence[str],
    registry: LifeEventRegistry,
    *,
    limit: int = MAX_EXTRA_CANDIDATE_LIFE_EVENTS,
) -> tuple[str, ...]:
    """依共現表為已選事件補最多三個未選候補。"""
    selected_set = set(selected)
    extras: list[str] = []
    for event_id in selected:
        for related in _RELATED_EVENTS.get(event_id, ()):
            if related in selected_set or related in extras:
                continue
            if not registry.has(related):
                continue
            extras.append(related)
            if len(extras) >= limit:
                return tuple(extras)

    # 共現不足時，用登記表其餘事件補滿（穩定順序）。
    if len(extras) < limit:
        for definition in registry.definitions():
            event_id = definition.event_id
            if event_id in selected_set or event_id in extras:
                continue
            extras.append(event_id)
            if len(extras) >= limit:
                break
    return tuple(extras)
