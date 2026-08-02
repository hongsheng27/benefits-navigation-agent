"""Compatibility aliases between the current workflow and legacy DB events.

The frontend/workflow owns the canonical IDs from ``data/life_events``.  The
first RDS ingestion script used broader historical IDs.  Repositories try the
canonical ID first and only fall back to these aliases, so a curated canonical
node always wins once it exists.
"""

from __future__ import annotations

EVENT_ID_ALIASES: dict[str, tuple[str, ...]] = {
    "spouse_death": ("death_of_family_member",),
    "parent_death": ("death_of_family_member",),
    "child_death": ("death_of_family_member",),
    "sibling_death": ("death_of_family_member",),
    "other_relative_death": ("death_of_family_member",),
    "job_loss": ("unemployment",),
    "unpaid_leave": ("unemployment",),
    "occupational_injury": ("work_injury",),
    "youth_employment_hardship": ("career_start",),
    "low_income_hardship": ("poverty",),
    "disability_onset": ("disability",),
    "long_term_care_need": ("long_term_care",),
    "caregiver_burden": ("long_term_care",),
    "mental_health_crisis": ("mental_health",),
    "pregnancy": ("childbirth_and_childcare",),
    "childbirth": ("childbirth_and_childcare",),
    "childcare_hardship": ("childbirth_and_childcare",),
    "school_expense_hardship": ("education_expense",),
    "housing_insecurity": ("housing_need",),
    "natural_disaster": ("disaster",),
    "new_immigrant_hardship": ("new_immigrant",),
    "indigenous_welfare_need": ("indigenous_rights",),
}


def event_id_candidates(canonical_event_id: str) -> tuple[str, ...]:
    """Return canonical first, followed by distinct legacy aliases."""
    aliases = EVENT_ID_ALIASES.get(canonical_event_id, ())
    return tuple(dict.fromkeys((canonical_event_id, *aliases)))
