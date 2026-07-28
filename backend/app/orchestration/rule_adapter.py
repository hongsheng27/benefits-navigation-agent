"""規則引擎的轉接層：把 EligibilityResult 轉成 CandidateItem。

這個模組是規則引擎（`app.rules.engine`）和 workflow 層之間的翻譯。
兩邊各自用自己的資料形狀，改動時不需要互相配合 —— 只有這裡要跟著動。

## 目前做到什麼

| 轉接項目 | 狀態 |
| --- | --- |
| status（四種判定結果） | ✅ |
| missing_field_ids | ✅ |
| 金額（amount → amount_min/max） | ✅ |
| amount_period | ❌ 規則欄位裡還沒有這個，先留空 |
| decisive_conditions | ❌ 規則引擎沒有輸出結構化條件，先留空 |
| citations | ❌ 目前規則引擎只有 source_url，不是完整的 Citation |

## decisive_conditions 為什麼留空

規則引擎判定「不符合」時只回一句中文（例如「需設籍該縣市」），不回「哪個欄位、
要求什麼、實際什麼」的三段結構。

轉接層不會自己反推，因為：
- 判定邏輯不能散在兩個地方
- 事後猜的風險是規則引擎改了邏輯但轉接層沒跟著改
- 錯的「差在哪個條件」比不顯示更糟

等資料層配合輸出結構化決定性條件後，只需要改這一個函式。
"""

from datetime import UTC, datetime

from app.orchestration.state import (
    CandidateItem,
    Citation,
    DecisiveCondition,
    ItemKind,
    ItemStatus,
)
from app.rules.engine import EligibilityResult

# 規則引擎的 status 字串對應到我們的列舉。
_STATUS_MAP: dict[str, ItemStatus] = {
    "eligible": ItemStatus.ELIGIBLE,
    "ineligible": ItemStatus.INELIGIBLE,
    "needs_information": ItemStatus.NEEDS_INFORMATION,
    "needs_human_review": ItemStatus.NEEDS_HUMAN_REVIEW,
}


def adapt_result(
    result: EligibilityResult,
    *,
    item_kind: ItemKind = ItemKind.BENEFIT,
) -> CandidateItem:
    """把一筆 EligibilityResult 轉成 CandidateItem。

    `item_kind` 由呼叫端提供，因為規則引擎不知道這個項目是福利還是行政事項。
    """
    status = _STATUS_MAP.get(result.status)
    if status is None:
        # 未知的 status 字串，安全降級為需人工協助。
        status = ItemStatus.NEEDS_HUMAN_REVIEW

    # 金額：規則引擎回單一 amount，映射到 min 和 max 都填同一個值。
    # amount_period 目前不在規則欄位裡，先留 None。
    amount_min = result.amount
    amount_max = result.amount

    # missing_field_ids：命名轉換。
    missing_field_ids = tuple(result.missing_inputs)

    # decisive_conditions：目前留空，等資料層配合。
    decisive_conditions: tuple[DecisiveCondition, ...] = ()

    # citations：目前規則引擎只有 source_url，組成最小的 Citation。
    citations: tuple[Citation, ...] = ()
    if result.source_url:
        citations = (
            Citation(
                document_id=f"{result.program_id}_source",
                title=result.program_name,
                publisher_name="",
                url=result.source_url,
            ),
        )

    return CandidateItem(
        item_id=result.program_id,
        kind=item_kind,
        status=status,
        missing_field_ids=missing_field_ids,
        decisive_conditions=decisive_conditions,
        citations=citations,
        amount_min=amount_min,
        amount_max=amount_max,
        amount_period=None,  # TODO: 等規則欄位增加發放性質
        amount_currency="TWD" if amount_min is not None else None,
        resolved_at=datetime.now(UTC)
        if status != ItemStatus.NEEDS_INFORMATION
        else None,
    )
