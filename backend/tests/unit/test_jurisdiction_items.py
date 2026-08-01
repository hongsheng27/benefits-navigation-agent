"""所在地地方方案篩選。"""

from app.orchestration.jurisdiction_items import local_items_for_attributes
from app.orchestration.protocols import FixtureEntitlementGraphRepository


def test_local_items_only_for_matching_jurisdiction() -> None:
    assert local_items_for_attributes({}, life_event_ids=("spouse_death",)) == ()
    taipei = local_items_for_attributes(
        {"applicant_jurisdiction": "TPE"},
        life_event_ids=("spouse_death",),
    )
    assert {item.item_id for item in taipei} == {
        "taipei_green_funeral_incentive",
        "taipei_joint_funeral_service",
    }
    assert (
        local_items_for_attributes(
            {"applicant_jurisdiction": "unsure"},
            life_event_ids=("spouse_death",),
        )
        == ()
    )


def test_local_funeral_items_skip_non_death_events() -> None:
    """失業等非喪親事件即使選了縣市，也不應掛上環保葬。"""
    assert (
        local_items_for_attributes(
            {"applicant_jurisdiction": "NWT"},
            life_event_ids=("job_loss",),
        )
        == ()
    )
    assert (
        local_items_for_attributes(
            {"applicant_jurisdiction": "NWT"},
            life_event_ids=(),
        )
        == ()
    )


def test_local_funeral_items_when_any_death_event_present() -> None:
    items = local_items_for_attributes(
        {"applicant_jurisdiction": "NWT"},
        life_event_ids=("job_loss", "spouse_death"),
    )
    assert {item.item_id for item in items} == {
        "new_taipei_green_funeral_incentive"
    }


def test_expand_includes_local_when_jurisdiction_set() -> None:
    repo = FixtureEntitlementGraphRepository()
    base = repo.expand_from_event("spouse_death", {})
    with_local = repo.expand_from_event(
        "spouse_death", {"applicant_jurisdiction": "NWT"}
    )
    assert len(with_local) == len(base) + 1
    assert any(
        item.item_id == "new_taipei_green_funeral_incentive" for item in with_local
    )


def test_expand_job_loss_excludes_funeral_local() -> None:
    repo = FixtureEntitlementGraphRepository()
    items = repo.expand_from_event(
        "job_loss", {"applicant_jurisdiction": "NWT"}
    )
    assert {item.item_id for item in items} == {
        "unemployment_benefit",
        "employment_service",
    }
    assert "new_taipei_green_funeral_incentive" not in {
        item.item_id for item in items
    }
