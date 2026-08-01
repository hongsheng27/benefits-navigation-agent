"""驗證示範用資料能走到完整判定，而且沒有污染預設值。

三個案例：注入示範資料後喪葬給付真的變「符合」（正常路徑）、
其餘三項不受影響（邊界）、以及不注入時仍然全部是需人工協助（守住 ADR-0014）。

第三個是這一組裡最重要的。ADR-0014 的整個重點是「預設路徑永遠不會產生 verified」，
如果之後有人把示範資料設成預設值，只有那個測試會失敗。
"""

from app.orchestration.demo_fixtures import (
    DEMO_EXPECTED_VALUE,
    DEMO_FIELD_ID,
    DEMO_ITEM_ID,
    DemoEntitlementGraphRepository,
    demo_eligibility_service,
    demo_language_model,
)
from app.orchestration.session_store import InMemorySessionStore
from app.orchestration.state import AmountPeriod, ItemStatus, SessionState
from app.orchestration.state_machine import advance
from app.schemas.session import (
    AttributeAnswersInput,
    EventConfirmationInput,
    LifeEventTextInput,
)


def _run_to_determination(*, with_demo: bool) -> SessionState:
    """跑完整條流程直到判定完成，回傳最後的狀態。

    `with_demo=False` 時只注入語言模型，其餘接縫全部走正式預設值 —— 這樣第三個測試
    才真的在測預設的判定行為，而不是測一組我們自己組出來的參數。

    語言模型**兩種情況都要注入**，因為 `advance()` 的預設模型沒有登記任何答案，
    事件辨識會失敗，流程根本走不到判定那一步。這裡注入等於明講一個假設：
    「假設模型把這段描述辨識成配偶過世」。那個假設本身不是這個測試要驗證的東西。
    """
    seams: dict = {"language_model": demo_language_model()}
    if with_demo:
        seams["entitlement_repository"] = DemoEntitlementGraphRepository()
        seams["eligibility_service"] = demo_eligibility_service()

    state = InMemorySessionStore().create()
    state = advance(state, LifeEventTextInput(text="配偶過世"), **seams)
    state = advance(state, EventConfirmationInput(confirmed=True), **seams)
    return advance(
        state,
        AttributeAnswersInput(
            answers={
                "applicant_jurisdiction": "TPE",
                DEMO_FIELD_ID: DEMO_EXPECTED_VALUE,
                "has_dependent_children": True,
                "applicant_age_band": "25_to_55",
            }
        ),
        **seams,
    )


def _item(state: SessionState, item_id: str):
    """從狀態裡取出某一項。找不到就讓測試在這裡失敗，而不是回 None 讓後面誤判。"""
    for item in state.items:
        if item.item_id == item_id:
            return item
    raise AssertionError(f"候選清單裡沒有 {item_id}")


def test_demo_fixtures_settle_the_demo_item_as_eligible() -> None:
    """正常路徑：注入示範資料後，喪葬給付走完整判定並帶出金額與決定性條件。"""
    state = _run_to_determination(with_demo=True)
    item = _item(state, DEMO_ITEM_ID)

    assert item.status is ItemStatus.ELIGIBLE
    assert item.program_status == "verified"
    assert item.amount_period is AmountPeriod.ONE_TIME
    assert item.amount_currency == "TWD"
    assert item.amount_min == item.amount_max
    assert item.resolved_at is not None

    # 「說得出理由」是這個專案的核心約束，所以判定必須帶得出決定性條件。
    assert len(item.decisive_conditions) == 1
    condition = item.decisive_conditions[0]
    assert condition.field_id == DEMO_FIELD_ID
    assert condition.expected == DEMO_EXPECTED_VALUE
    assert condition.actual == DEMO_EXPECTED_VALUE


def test_demo_fixtures_do_not_promote_the_other_items() -> None:
    """邊界：只有一項被填到底，其餘三項仍是候選狀態且不下結論。"""
    state = _run_to_determination(with_demo=True)

    others = [item for item in state.items if item.item_id != DEMO_ITEM_ID]
    assert others, "示範資料應該保留其餘項目，不是只剩一項"

    for item in others:
        assert item.program_status == "candidate"
        assert item.status is not ItemStatus.ELIGIBLE


def test_defaults_still_resolve_everything_to_human_review() -> None:
    """失敗情境：完全不注入時，不得有任何項目走到完整判定。

    這一條守的是 ADR-0014。示範資料如果哪天變成預設值，這裡會失敗。
    """
    state = _run_to_determination(with_demo=False)

    assert state.items, "預設路徑仍應展開候選項目"
    for item in state.items:
        assert item.program_status == "candidate"
        assert item.status is ItemStatus.NEEDS_HUMAN_REVIEW
