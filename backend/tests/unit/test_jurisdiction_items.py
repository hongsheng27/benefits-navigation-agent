"""所在地地方方案篩選。"""

from app.orchestration.jurisdiction_items import local_items_for_attributes
from app.orchestration.protocols import FixtureEntitlementGraphRepository


def test_local_items_only_for_matching_jurisdiction() -> None:
    assert local_items_for_attributes({}) == ()
    taipei = local_items_for_attributes({"applicant_jurisdiction": "TPE"})
    assert {item.item_id for item in taipei} == {
        "taipei_green_funeral_incentive",
        "taipei_joint_funeral_service",
    }
    assert local_items_for_attributes({"applicant_jurisdiction": "unsure"}) == ()


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
