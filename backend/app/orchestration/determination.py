"""逐項判定的組裝。

在迴圈的 EVALUATE_ELIGIBILITY 步驟裡被呼叫。它做三件事：

1. 找出「已經湊齊所有必要欄位」的項目
2. 對每一個湊齊的項目呼叫規則引擎
3. 把規則引擎的結果轉成 CandidateItem 寫回狀態

「已經湊齊」的判斷依據是：登記表裡被這個項目需要的欄位，全部都已經出現在
`state.attributes` 裡了。

## 還沒有 SQLite 連線

目前沒有連接真正的 SQLite（那屬於資料來源介面，T15–T18），所以只有
`evaluate_ready_items_stub`：不需要連線，把就緒項目標為 `eligible`。

接上真正的規則引擎時，在這個模組加一個 `evaluate_ready_items(state, registry,
connection)`，用 `rule_adapter.adapt_result` 轉換結果，然後把 `state_machine.py`
的 `_do_evaluate_eligibility` 改成呼叫它。

## 沒有宣告任何欄位的項目

如果一個項目在登記表裡沒有任何欄位宣告 `used_by` 包含它，那代表**登記表的資料還沒
填完**，不代表它「沒有條件所以符合」。

這種項目會被標成 `NEEDS_HUMAN_REVIEW` 而不是 `ELIGIBLE`。理由是本專案的原則：
說不出理由的判定要降級。把資料缺漏誤判成「你符合資格」比誠實說「需要人看一下」
危險得多 —— 使用者可能因此白跑一趟。
"""

from datetime import UTC, datetime

from app.orchestration.field_registry import FieldRegistry
from app.orchestration.state import (
    CandidateItem,
    ItemStatus,
    SessionState,
)


def find_ready_item_ids(
    state: SessionState,
    registry: FieldRegistry,
) -> frozenset[str]:
    """找出已經湊齊所有必要欄位、但還沒定案的項目。

    沒有宣告任何欄位的項目**不算就緒** —— 那是資料缺漏，由
    `find_undeclared_item_ids` 另外處理。
    """
    answered = frozenset(state.attributes.keys())
    ready: set[str] = set()

    for item in state.items:
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

    for item in state.items:
        if item.status != ItemStatus.PENDING:
            continue

        needed = registry.fields_for_items(frozenset({item.item_id}))
        if not needed:
            undeclared.add(item.item_id)

    return frozenset(undeclared)


def evaluate_ready_items_stub(
    state: SessionState,
    registry: FieldRegistry,
) -> SessionState:
    """不需要 SQLite 的佔位版本。

    - 就緒的項目（欄位都答齊了）標為 `ELIGIBLE`
    - 登記表沒有宣告任何欄位的項目標為 `NEEDS_HUMAN_REVIEW`

    接上真正的規則引擎後換掉第一項；第二項的行為應該保留。
    """
    ready_ids = find_ready_item_ids(state, registry)
    undeclared_ids = find_undeclared_item_ids(state, registry)

    if not ready_ids and not undeclared_ids:
        return state

    now = datetime.now(UTC)

    def _resolve(item: CandidateItem) -> CandidateItem:
        if item.item_id in ready_ids:
            return item.model_copy(
                update={
                    "status": ItemStatus.ELIGIBLE,
                    "resolved_at": now,
                    "missing_field_ids": (),
                }
            )
        if item.item_id in undeclared_ids:
            return item.model_copy(
                update={
                    "status": ItemStatus.NEEDS_HUMAN_REVIEW,
                    "resolved_at": now,
                }
            )
        return item

    new_items = tuple(_resolve(item) for item in state.items)

    return state.model_copy(update={"items": new_items})
