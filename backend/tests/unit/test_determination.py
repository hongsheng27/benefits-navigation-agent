"""驗證逐項判定組裝：找出就緒項目並判定。

## 為什麼這裡的期望值和之前不一樣

`CandidateItem.program_status` 的預設值是 `"candidate"`（依提案第 8 節與第 14 節：
沒有人明確說這筆資料審過，就必須當成候選）。候選資料**不做完整資格判斷**，一律回
需人工協助。

所以原本斷言「湊齊欄位就是 eligible」的測試改成斷言需人工協助；要測「湊齊欄位之後
真的走完整判定」的路徑，得把 `program_status` 明確設成 `"verified"`，代表資料層已經
有一筆經人工審查的方案。這不是 bug，是照提案的必然結果。
"""

from datetime import UTC, datetime, timedelta

from app.orchestration.data_contracts import EligibilityDecision
from app.orchestration.determination import (
    evaluate_ready_items,
    find_ready_item_ids,
    find_undeclared_item_ids,
)
from app.orchestration.field_registry import FieldRegistry
from app.orchestration.protocols import FixtureEligibilityService
from app.orchestration.state import (
    CandidateItem,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)


def _registry() -> FieldRegistry:
    return FieldRegistry.from_json()


def _eligible_service(*item_ids: str) -> FixtureEligibilityService:
    """一個對指定項目回「符合」的判定服務。

    代表資料層已經交出這些項目的已核准規則 —— 沒有它，離線環境本來就沒有可以下結論
    的依據。
    """
    return FixtureEligibilityService(
        decisions={
            item_id: EligibilityDecision(
                item_id=item_id,
                status="eligible",
                amount_min=None,
                amount_max=None,
                amount_period=None,
                amount_currency=None,
                missing_field_ids=(),
                reasons=(),
            )
            for item_id in item_ids
        }
    )


def _state(
    *,
    attributes: dict | None = None,
    items: tuple[CandidateItem, ...] | None = None,
) -> SessionState:
    now = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
    default_items = (
        CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
        CandidateItem(item_id="survivor_pension", kind=ItemKind.BENEFIT),
    )
    return SessionState(
        session_id="s_test",
        workflow_state=WorkflowState.EVALUATE_ELIGIBILITY,
        life_event="spouse_death",
        attributes=attributes or {},
        items=items if items is not None else default_items,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )


def test_no_items_ready_when_nothing_answered() -> None:
    ready = find_ready_item_ids(_state(), _registry())
    assert ready == frozenset()


def test_funeral_benefit_ready_when_its_field_answered() -> None:
    """funeral_benefit 需要所在地與投保身分。"""
    state = _state(
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
        }
    )
    ready = find_ready_item_ids(state, _registry())

    assert "funeral_benefit" in ready


def test_survivor_pension_needs_all_declared_fields() -> None:
    """survivor_pension 需要多個欄位，只答一個還不算就緒。"""
    state = _state(attributes={"deceased_insurance_type": "labor_insurance"})
    ready = find_ready_item_ids(state, _registry())

    assert "survivor_pension" not in ready


def test_survivor_pension_ready_with_all_fields() -> None:
    state = _state(
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
            "has_dependent_children": True,
            "applicant_age_band": "25_to_55",
        }
    )
    ready = find_ready_item_ids(state, _registry())

    assert "survivor_pension" in ready
    assert "funeral_benefit" in ready


def test_already_resolved_items_are_skipped() -> None:
    """已經定案的項目不會被找出來。"""
    items = (
        CandidateItem(
            item_id="funeral_benefit",
            kind=ItemKind.BENEFIT,
            status=ItemStatus.ELIGIBLE,
        ),
        CandidateItem(item_id="survivor_pension", kind=ItemKind.BENEFIT),
    )
    state = _state(
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
        },
        items=items,
    )
    ready = find_ready_item_ids(state, _registry())

    assert "funeral_benefit" not in ready


def test_a_verified_ready_item_gets_the_full_decision() -> None:
    """已審查過的方案湊齊欄位後，走完整判定並套用結果。"""
    items = (
        CandidateItem(
            item_id="funeral_benefit",
            kind=ItemKind.BENEFIT,
            program_status="verified",
        ),
        CandidateItem(
            item_id="survivor_pension",
            kind=ItemKind.BENEFIT,
            program_status="verified",
        ),
    )
    state = _state(
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
        },
        items=items,
    )

    result = evaluate_ready_items(
        state, _registry(), _eligible_service("funeral_benefit")
    )

    statuses = {item.item_id: item.status for item in result.items}
    assert statuses["funeral_benefit"] is ItemStatus.ELIGIBLE
    # survivor_pension 還沒湊齊，維持待確認。
    assert statuses["survivor_pension"] is ItemStatus.PENDING


def test_a_candidate_ready_item_goes_to_human_review_instead() -> None:
    """同樣湊齊欄位，但資料只是候選 → 不做完整判斷（提案第 8 節）。

    這個測試取代原本的 test_stub_marks_ready_items_as_eligible。差別就是
    `program_status`：預設的 `"candidate"` 讓結論從「符合」變成「需人工協助」。
    """
    state = _state(
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
        }
    )

    result = evaluate_ready_items(
        state, _registry(), _eligible_service("funeral_benefit")
    )

    statuses = {item.item_id: item.status for item in result.items}
    assert statuses["funeral_benefit"] is ItemStatus.NEEDS_HUMAN_REVIEW


def test_resolved_items_get_a_timestamp() -> None:
    state = _state(
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
        }
    )

    result = evaluate_ready_items(
        state, _registry(), _eligible_service("funeral_benefit")
    )

    funeral = next(i for i in result.items if i.item_id == "funeral_benefit")
    assert funeral.resolved_at is not None


def test_nothing_changes_when_no_item_can_be_settled() -> None:
    """沒有任何項目狀態改變時回傳同一個物件。

    項目設成 `"verified"`：候選狀態的項目一進評估就會被閘門定案，那樣就測不到
    「什麼都沒變」這條路。
    """
    items = (
        CandidateItem(
            item_id="funeral_benefit",
            kind=ItemKind.BENEFIT,
            program_status="verified",
        ),
    )
    state = _state(items=items, attributes={})

    result = evaluate_ready_items(state, _registry(), FixtureEligibilityService())

    assert result is state


def test_items_with_no_declared_fields_are_flagged_as_undeclared() -> None:
    """登記表沒有宣告任何欄位的項目，屬於資料缺漏。"""
    items = (
        CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
        CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),
    )
    state = _state(items=items)

    undeclared = find_undeclared_item_ids(state, _registry())

    # death_registration 在種子登記表裡沒有任何欄位宣告 used_by 包含它。
    assert "death_registration" in undeclared
    assert "funeral_benefit" not in undeclared


def test_undeclared_items_are_not_counted_as_ready() -> None:
    """沒有宣告欄位不等於「沒有條件所以就緒」。"""
    items = (CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),)
    state = _state(items=items, attributes={"anything": "value"})

    ready = find_ready_item_ids(state, _registry())

    assert "death_registration" not in ready


def test_undeclared_items_become_needs_human_review() -> None:
    """資料缺漏的項目標成需人工協助，不是符合資格。

    把資料缺漏誤判成「你符合資格」比誠實說「需要人看一下」危險 ——
    使用者可能因此白跑一趟。

    兩個項目都標成 `"verified"`，才能證明降級的原因是**登記表沒有宣告欄位**，
    而不是被資料治理狀態的閘門擋下來。
    """
    items = (
        CandidateItem(
            item_id="death_registration",
            kind=ItemKind.ADMINISTRATIVE,
            program_status="verified",
        ),
        CandidateItem(
            item_id="funeral_benefit",
            kind=ItemKind.BENEFIT,
            program_status="verified",
        ),
    )
    state = _state(
        items=items,
        attributes={
            "applicant_jurisdiction": "TPE",
            "deceased_insurance_type": "labor_insurance",
        },
    )

    result = evaluate_ready_items(
        state, _registry(), _eligible_service("funeral_benefit")
    )
    statuses = {i.item_id: i.status for i in result.items}

    assert statuses["death_registration"] is ItemStatus.NEEDS_HUMAN_REVIEW
    assert statuses["funeral_benefit"] is ItemStatus.ELIGIBLE


def test_undeclared_items_alone_still_change_state() -> None:
    """只有資料缺漏的項目時，也要回傳新的狀態（不是原封不動）。"""
    items = (
        CandidateItem(
            item_id="death_registration",
            kind=ItemKind.ADMINISTRATIVE,
            program_status="verified",
        ),
    )
    state = _state(items=items)

    result = evaluate_ready_items(state, _registry(), FixtureEligibilityService())

    assert result is not state
    assert result.items[0].status is ItemStatus.NEEDS_HUMAN_REVIEW
