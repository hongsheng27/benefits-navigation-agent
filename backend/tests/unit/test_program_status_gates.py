"""驗證資料治理狀態的安全閘門，以及單一項目失敗的隔離。

閘門的規則來自提案第 8 節：

| `program_status` | 期望行為 |
| --- | --- |
| `verified` | 走完整確定性判定 |
| `candidate`／`under_review` | 可以顯示，但一律回需人工協助 |
| `rejected`／`inactive` | 完全不出現在結果裡 |
| `stale` | 顯示警示、不執行完整判定，固定回需人工協助（owner 核准方案 B） |
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.orchestration.data_contracts import EligibilityDecision
from app.orchestration.determination import evaluate_ready_items, gated_status
from app.orchestration.field_registry import FieldRegistry
from app.orchestration.protocols import FixtureEligibilityService, UserAttributes
from app.orchestration.state import (
    CandidateItem,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)

_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)

# funeral_benefit 在種子登記表裡只需要這一個欄位，所以答了它就算就緒。
_ANSWERED = {"deceased_insurance_type": "labor_insurance"}


def _registry() -> FieldRegistry:
    return FieldRegistry.from_json()


def _eligible(item_id: str) -> EligibilityDecision:
    return EligibilityDecision(
        item_id=item_id,
        status="eligible",
        amount_min=10000,
        amount_max=10000,
        amount_period="one_time",
        amount_currency="TWD",
        missing_field_ids=(),
        reasons=(),
    )


class _ExplodingEligibilityService:
    """對指定項目拋例外的判定服務。

    模擬「某一項的規則資料有問題」。用假物件而不是給
    `FixtureEligibilityService` 加一個開關，是為了不讓離線實作長出只有測試會用的行為。
    """

    def __init__(self, failing_item_id: str, decisions: dict[str, EligibilityDecision]):
        self._failing_item_id = failing_item_id
        self._decisions = decisions

    def get_required_fields(self, item_id: str) -> tuple:
        del item_id
        return ()

    def evaluate(
        self, item_id: str, user_attributes: UserAttributes
    ) -> EligibilityDecision:
        del user_attributes
        if item_id == self._failing_item_id:
            msg = "規則資料損壞"
            raise RuntimeError(msg)
        return self._decisions[item_id]

    def evaluate_many(
        self, item_ids: list[str], user_attributes: UserAttributes
    ) -> tuple[EligibilityDecision, ...]:
        return tuple(self.evaluate(item_id, user_attributes) for item_id in item_ids)


def _state(items: tuple[CandidateItem, ...]) -> SessionState:
    return SessionState(
        session_id="s_test",
        workflow_state=WorkflowState.EVALUATE_ELIGIBILITY,
        life_event="spouse_death",
        attributes=dict(_ANSWERED),
        items=items,
        created_at=_NOW,
        updated_at=_NOW,
        expires_at=_NOW + timedelta(hours=2),
    )


def _item(program_status: str, item_id: str = "funeral_benefit") -> CandidateItem:
    return CandidateItem(
        item_id=item_id,
        kind=ItemKind.BENEFIT,
        program_status=program_status,  # type: ignore[arg-type]
    )


def _statuses(state: SessionState) -> dict[str, ItemStatus]:
    return {item.item_id: item.status for item in state.items}


# ---------------------------------------------------------------------------
# 閘門一：verified 走完整判定
# ---------------------------------------------------------------------------


def test_a_verified_item_runs_the_full_deterministic_evaluation() -> None:
    """已審查的方案拿到完整結論，包含金額。"""
    service = FixtureEligibilityService(
        decisions={"funeral_benefit": _eligible("funeral_benefit")}
    )

    result = evaluate_ready_items(_state((_item("verified"),)), _registry(), service)

    item = result.items[0]
    assert item.status is ItemStatus.ELIGIBLE
    assert (item.amount_min, item.amount_max) == (10000, 10000)
    assert item.amount_period is not None


# ---------------------------------------------------------------------------
# 閘門二：candidate 與 under_review 只能回需人工協助
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("program_status", ["candidate", "under_review"])
def test_unconfirmed_items_never_get_a_verdict(program_status: str) -> None:
    """尚未二次確認的資料可以顯示，但不能給資格結論。

    即使判定服務願意回「符合」，閘門也不會去問它。
    """
    service = FixtureEligibilityService(
        decisions={"funeral_benefit": _eligible("funeral_benefit")}
    )

    result = evaluate_ready_items(
        _state((_item(program_status),)), _registry(), service
    )

    assert result.items[0].status is ItemStatus.NEEDS_HUMAN_REVIEW
    # 「可以顯示」的部分：項目仍然留在清單裡。
    assert len(result.items) == 1


# ---------------------------------------------------------------------------
# 閘門三：rejected 與 inactive 完全不出現
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("program_status", ["rejected", "inactive"])
def test_hidden_items_leave_the_candidate_list(program_status: str) -> None:
    """被拒絕或已停辦的方案不進入候選結果，也不進入資格評估。

    清單上出現一項辦不了的事，使用者仍然會去問，所以連顯示都不行。
    """
    items = (_item(program_status), _item("verified", item_id="survivor_pension"))
    service = FixtureEligibilityService()

    result = evaluate_ready_items(_state(items), _registry(), service)

    assert "funeral_benefit" not in _statuses(result)
    assert "survivor_pension" in _statuses(result)


# ---------------------------------------------------------------------------
# 閘門四：stale 方案 B
# ---------------------------------------------------------------------------


def test_a_stale_item_always_needs_human_review() -> None:
    """`stale` 可見但不執行完整判定，固定交給人看。

    Owner 已選定方案 B；不得使用最後一次驗證快照產生完整資格結論。
    """
    service = FixtureEligibilityService(
        decisions={"funeral_benefit": _eligible("funeral_benefit")}
    )

    result = evaluate_ready_items(_state((_item("stale"),)), _registry(), service)

    assert result.items[0].status is ItemStatus.NEEDS_HUMAN_REVIEW


def test_the_gate_function_covers_every_documented_status() -> None:
    """閘門對六種狀態都有明確答案，沒有靠預設值蒙過去的。"""
    assert gated_status("verified") is None
    assert gated_status("candidate") is ItemStatus.NEEDS_HUMAN_REVIEW
    assert gated_status("under_review") is ItemStatus.NEEDS_HUMAN_REVIEW
    assert gated_status("stale") is ItemStatus.NEEDS_HUMAN_REVIEW
    # rejected／inactive 在進到閘門之前就被濾掉，但萬一走到這裡也不能給結論。
    assert gated_status("rejected") is ItemStatus.NEEDS_HUMAN_REVIEW
    assert gated_status("inactive") is ItemStatus.NEEDS_HUMAN_REVIEW


# ---------------------------------------------------------------------------
# 單一項目失敗的隔離
# ---------------------------------------------------------------------------


def test_one_failing_item_does_not_affect_the_others() -> None:
    """一項的規則資料壞掉，只有那一項變成需人工協助。

    讓一項的失敗連帶整份清單失敗，使用者會從「有兩項可以辦」變成「什麼都沒有」。
    """
    items = (
        _item("verified", item_id="funeral_benefit"),
        _item("verified", item_id="survivor_pension"),
    )
    state = _state(items).model_copy(
        update={
            "attributes": {
                **_ANSWERED,
                "has_dependent_children": True,
                "applicant_age_band": "25_to_55",
            }
        }
    )
    service = _ExplodingEligibilityService(
        failing_item_id="funeral_benefit",
        decisions={"survivor_pension": _eligible("survivor_pension")},
    )

    result = evaluate_ready_items(state, _registry(), service)

    statuses = _statuses(result)
    assert statuses["funeral_benefit"] is ItemStatus.NEEDS_HUMAN_REVIEW
    assert statuses["survivor_pension"] is ItemStatus.ELIGIBLE


def test_a_failing_item_is_still_marked_as_resolved() -> None:
    """失敗的項目要有結論時間，否則它會永遠留在「還在處理」的樣子。"""
    state = _state((_item("verified"),))
    service = _ExplodingEligibilityService(
        failing_item_id="funeral_benefit", decisions={}
    )

    result = evaluate_ready_items(state, _registry(), service)

    assert result.items[0].resolved_at is not None
