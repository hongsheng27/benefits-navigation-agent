"""逐項判定的組裝。

在迴圈的 EVALUATE_ELIGIBILITY 步驟裡被呼叫。它做三件事：

1. 找出「已經湊齊所有必要欄位」的項目
2. 對每一個湊齊的項目呼叫規則引擎
3. 把規則引擎的結果轉成 CandidateItem 寫回狀態

「已經湊齊」的判斷依據是：登記表裡被這個項目需要的欄位，全部都已經出現在
`state.attributes` 裡了。

## 還沒有 SQLite 連線

目前沒有連接真正的 SQLite（因為那屬於資料來源介面，T15–T18）。所以這個模組提供
兩個版本：

- `evaluate_ready_items`：需要一個 `sqlite3.Connection`，呼叫真正的規則引擎
- `evaluate_ready_items_stub`：不需要連線，直接把所有就緒項目標為 `eligible`

狀態機目前用 stub 版本。接上真正的 SQLite 時只需要把呼叫換掉。
"""

from datetime import UTC, datetime

from app.orchestration.field_registry import FieldRegistry
from app.orchestration.state import (
    ItemStatus,
    SessionState,
)


def find_ready_item_ids(
    state: SessionState,
    registry: FieldRegistry,
) -> frozenset[str]:
    """找出已經湊齊所有必要欄位、但還沒定案的項目。"""
    answered = frozenset(state.attributes.keys())
    ready: set[str] = set()

    for item in state.items:
        if item.status != ItemStatus.PENDING:
            continue

        # 這個項目需要哪些欄位。
        needed = registry.fields_for_items(frozenset({item.item_id}))
        needed_ids = {f.field_id for f in needed}

        if needed_ids <= answered:
            ready.add(item.item_id)

    return frozenset(ready)


def evaluate_ready_items_stub(
    state: SessionState,
    registry: FieldRegistry,
) -> SessionState:
    """不需要 SQLite 的佔位版本。把就緒的項目全部標為 eligible。

    這是為了讓流程能走通。接上真正的規則引擎後換掉。
    """
    ready_ids = find_ready_item_ids(state, registry)

    if not ready_ids:
        return state

    now = datetime.now(UTC)
    new_items = tuple(
        item.model_copy(
            update={
                "status": ItemStatus.ELIGIBLE,
                "resolved_at": now,
                "missing_field_ids": (),
            }
        )
        if item.item_id in ready_ids
        else item
        for item in state.items
    )

    return state.model_copy(update={"items": new_items})
