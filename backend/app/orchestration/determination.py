"""逐項判定的組裝，以及資料治理狀態的安全閘門。

在迴圈的 EVALUATE_ELIGIBILITY 步驟裡被呼叫。它做四件事：

1. 把不該出現的方案（`rejected`／`inactive`）從候選清單移除
2. 依 `program_status` 決定「這一項可不可以做完整資格判定」
3. 對可以判定且欄位湊齊的項目呼叫 `EligibilityService`
4. 把判定結果轉成 `CandidateItem` 寫回狀態

「已經湊齊」的判斷依據是：登記表裡被這個項目需要的欄位，全部都已經出現在
`state.attributes` 裡了。

## 資料治理狀態的閘門（提案第 8 節）

| `program_status` | 這裡的行為 |
| --- | --- |
| `verified` | 執行完整確定性判定 |
| `candidate`／`under_review` | 可以顯示，但不做完整判斷，一律回需人工協助 |
| `rejected`／`inactive` | 隱藏，不進入候選結果，也不進入資格評估 |
| `stale` | 顯示警示、**不執行完整判定**，固定回 `NEEDS_HUMAN_REVIEW`（方案 B） |

`stale` 已由 owner 選定方案 B：保留在候選清單中，讓使用者知道這一項可能相關並看見
資料已過期的警示；但過期規則不得進入完整確定性判定，也不得使用最後一次快照產生
`eligible`／`ineligible`。這個邊界把「可見性」與「可判定性」分開，避免過期資料被
誤當成仍有效的資格依據。

## 單一項目失敗不影響其他項目

規則引擎對某一項拋例外時，只有那一項被標成 `NEEDS_HUMAN_REVIEW`，其餘項目照常判定。
理由是一次諮詢通常同時展開四、五項：讓一項的資料問題連帶讓整份清單失敗，使用者會
從「有三項可以辦」變成「什麼都沒有」。

紀錄檔只寫項目代號、結果狀態與例外**類別**。例外訊息可能引用使用者提供的值，所以
`log_event` 走 `exc_info`，由 `app.observability.logging` 的格式器只取類別與堆疊。

## 沒有宣告任何欄位的項目

如果一個項目在登記表裡沒有任何欄位宣告 `used_by` 包含它，那代表**登記表的資料還沒
填完**，不代表它「沒有條件所以符合」。

這種項目會被標成 `NEEDS_HUMAN_REVIEW` 而不是 `ELIGIBLE`。理由是本專案的原則：
說不出理由的判定要降級。把資料缺漏誤判成「你符合資格」比誠實說「需要人看一下」
危險得多 —— 使用者可能因此白跑一趟。
"""

import logging
from datetime import UTC, datetime

from app.observability.logging import log_event
from app.orchestration.field_registry import FieldRegistry
from app.orchestration.protocols import EligibilityService
from app.orchestration.rule_adapter import apply_decision
from app.orchestration.state import (
    CandidateItem,
    ItemStatus,
    SessionState,
)

HIDDEN_PROGRAM_STATUSES: frozenset[str] = frozenset({"rejected", "inactive"})
"""不得進入候選結果或資格評估的資料治理狀態。

被拒絕或已停辦的方案連「顯示」都不行：清單上出現一項辦不了的事，使用者仍然會去問。
"""

FULL_EVALUATION_PROGRAM_STATUSES: frozenset[str] = frozenset({"verified"})
"""唯一可以執行完整確定性判定的資料治理狀態。"""

_STALE_STATUS: ItemStatus = ItemStatus.NEEDS_HUMAN_REVIEW
"""Owner 核准的 stale 方案 B：可見、有警示、不做完整判定、固定轉人工。"""


def visible_items(items: tuple[CandidateItem, ...]) -> tuple[CandidateItem, ...]:
    """濾掉 `rejected`／`inactive` 的方案（提案第 8 節）。"""
    return tuple(
        item for item in items if item.program_status not in HIDDEN_PROGRAM_STATUSES
    )


def find_ready_item_ids(
    state: SessionState,
    registry: FieldRegistry,
) -> frozenset[str]:
    """找出已經湊齊所有必要欄位、但還沒定案的項目。

    沒有宣告任何欄位的項目**不算就緒** —— 那是資料缺漏，由
    `find_undeclared_item_ids` 另外處理。被隱藏的方案也不算就緒，它們不進入評估。
    """
    answered = frozenset(state.attributes.keys())
    ready: set[str] = set()

    for item in visible_items(state.items):
        if item.status != ItemStatus.PENDING:
            continue

        needed = registry.fields_for_items(frozenset({item.item_id}))
        needed_ids = {f.field_id for f in needed}

        # 沒有宣告任何欄位 → 資料缺漏，不當成就緒。
        if not needed_ids:
            continue

        if needed_ids <= answered:
            ready.add(item.item_id)

    return frozenset(ready)


def find_undeclared_item_ids(
    state: SessionState,
    registry: FieldRegistry,
) -> frozenset[str]:
    """找出「登記表裡沒有任何欄位宣告需要它」的待定案項目。

    這代表登記表的資料還沒填完。這種項目應該標成需人工協助，不是符合資格。
    """
    undeclared: set[str] = set()

    for item in visible_items(state.items):
        if item.status != ItemStatus.PENDING:
            continue

        needed = registry.fields_for_items(frozenset({item.item_id}))
        if not needed:
            undeclared.add(item.item_id)

    return frozenset(undeclared)


def gated_status(program_status: str) -> ItemStatus | None:
    """資料治理狀態擋不擋這一項的完整判定。

    回 `None` 表示可以走完整判定；回一個 `ItemStatus` 表示直接用它定案。
    抽成獨立函式是為了讓五種閘門行為可以逐一被測到，不必每次都組一份完整 state。
    """
    if program_status in FULL_EVALUATION_PROGRAM_STATUSES:
        return None
    if program_status == "stale":
        return _STALE_STATUS
    # candidate / under_review：可以顯示，但沒有二次確認過的資料不能給結論。
    return ItemStatus.NEEDS_HUMAN_REVIEW


def evaluate_ready_items(
    state: SessionState,
    registry: FieldRegistry,
    eligibility_service: EligibilityService,
) -> SessionState:
    """對候選清單跑一輪判定，回傳新的狀態。

    處理順序（每一項各自獨立）：

    1. 已經定案的項目不重跑
    2. `rejected`／`inactive` 從清單移除
    3. 非 `verified` 的資料治理狀態直接依閘門定案
    4. 登記表沒有宣告任何欄位 → 需人工協助
    5. 欄位還沒湊齊 → 維持待確認
    6. 其餘呼叫 `EligibilityService`，單一項目失敗只影響那一項

    沒有任何項目改變時回傳原本的物件，讓呼叫端可以用 `is` 判斷有沒有變化。
    """
    ready_ids = find_ready_item_ids(state, registry)
    undeclared_ids = find_undeclared_item_ids(state, registry)
    now = datetime.now(UTC)

    resolved = tuple(
        _resolve_item(
            item,
            state=state,
            ready_ids=ready_ids,
            undeclared_ids=undeclared_ids,
            eligibility_service=eligibility_service,
            now=now,
        )
        for item in visible_items(state.items)
    )

    if resolved == state.items:
        return state

    return state.model_copy(update={"items": resolved})


def _resolve_item(
    item: CandidateItem,
    *,
    state: SessionState,
    ready_ids: frozenset[str],
    undeclared_ids: frozenset[str],
    eligibility_service: EligibilityService,
    now: datetime,
) -> CandidateItem:
    """判定單一項目。這個函式不會拋例外，所以一項的失敗不會波及其他項目。"""
    if item.status != ItemStatus.PENDING:
        return item

    if item.item_id in undeclared_ids:
        return item.model_copy(
            update={"status": ItemStatus.NEEDS_HUMAN_REVIEW, "resolved_at": now}
        )

    # 欄位還沒湊齊：維持 PENDING，讓缺漏欄位迴圈繼續問。
    # 不可對未就緒的 candidate 提前套用閘門定案，否則一題一題作答時
    # 所有項目會在第一輪就被定成 needs_human_review，追問直接中斷。
    if item.item_id not in ready_ids:
        return item

    blocked = gated_status(item.program_status)
    if blocked is not None:
        return item.model_copy(update={"status": blocked, "resolved_at": now})

    try:
        decision = eligibility_service.evaluate(item.item_id, state.attributes)
    except Exception:
        # 只記代號、結果與例外類別。例外訊息可能引用使用者提供的值，所以走
        # exc_info，由格式器只取類別名稱與堆疊框架。
        log_event(
            "item_evaluation_failed",
            level=logging.ERROR,
            exc_info=True,
            benefit_id=item.item_id,
            eligibility_status=ItemStatus.NEEDS_HUMAN_REVIEW.value,
        )
        return item.model_copy(
            update={"status": ItemStatus.NEEDS_HUMAN_REVIEW, "resolved_at": now}
        )

    return apply_decision(item, decision, now=now)
