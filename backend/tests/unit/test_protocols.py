"""驗證接縫的 Phase 2 實作。

這兩個實作刻意很小，測試的重點只有「行為符合宣告」：pass-through 真的什麼都不改，
fixture 真的只回它有資料的事件。
"""

from app.orchestration.field_registry import FieldRegistry
from app.orchestration.protocols import (
    FixtureEntitlementSource,
    PassThroughPrivacyGate,
)
from app.orchestration.state import ItemKind, ItemStatus


def test_pass_through_gate_returns_the_same_answers() -> None:
    """Phase 2 的閘門不改任何值。"""
    gate = PassThroughPrivacyGate()
    answers = {"deceased_insurance_type": "labor_insurance", "count": 2}

    result = gate.validate_attributes(answers, FieldRegistry(()))

    assert result == answers


def test_pass_through_gate_does_not_alias_the_input() -> None:
    """回傳的是複本，所以之後改動其中一邊不會波及另一邊。"""
    gate = PassThroughPrivacyGate()
    answers = {"has_dependent_children": True}

    result = gate.validate_attributes(answers, FieldRegistry(()))
    result["has_dependent_children"] = False

    assert answers["has_dependent_children"] is True


def test_fixture_source_expands_the_mvp_event() -> None:
    """MVP 情境（配偶過世）回四個項目，全部尚未判定。"""
    source = FixtureEntitlementSource()

    items = source.resolve("spouse_death")

    assert [item.item_id for item in items] == [
        "death_registration",
        "funeral_benefit",
        "survivor_pension",
        "health_insurance_change",
    ]
    assert all(item.status is ItemStatus.PENDING for item in items)
    assert items[0].kind is ItemKind.ADMINISTRATIVE
    assert items[1].kind is ItemKind.BENEFIT


def test_fixture_source_returns_nothing_for_an_unknown_event() -> None:
    """沒有資料就回空，不猜一組項目 —— 猜錯會讓使用者白跑一趟。"""
    source = FixtureEntitlementSource()

    assert source.resolve("unmapped_event") == ()
