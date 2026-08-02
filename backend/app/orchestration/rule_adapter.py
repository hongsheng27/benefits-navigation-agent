"""資料層與 workflow 之間的轉接層。

這個模組是資料層形狀（`app.orchestration.data_contracts`、`app.rules.engine`）和
workflow 形狀（`app.orchestration.state`）之間的翻譯。兩邊各自用自己的資料形狀，
改動時不需要互相配合 —— 只有這裡要跟著動。

三個方向：

| 函式 | 從 | 到 |
| --- | --- | --- |
| `adapt_graph_candidate` | `data_contracts.CandidateItem` | `state.CandidateItem` |
| `apply_decision` | `data_contracts.EligibilityDecision` | `state.CandidateItem` |
| `adapt_result` | `rules.engine.EligibilityResult` | `state.CandidateItem` |

依提案第 7 節，`program_id` ↔ `item_id` 的映射與欄位命名差異都由 adapter 處理，
workflow 不因為資料表欄名改變而改自己的形狀。

## `adapt_result`（SQL 規則引擎那條路）目前做到什麼

| 轉接項目 | 狀態 |
| --- | --- |
| status（四種判定結果） | ✅ |
| missing_field_ids | ✅ |
| 金額（amount → amount_min/max） | ✅ |
| amount_period | ❌ 規則欄位裡還沒有這個，先留空 |
| decisive_conditions | ❌ 規則引擎沒有輸出結構化條件，先留空 |
| citations | ❌ 目前規則引擎只有 source_url，不是完整的 Citation |

## 現階段不會有任何項目回報「不符合資格」

因為 `decisive_conditions` 恆為空，而「不符合但說不出差在哪個條件」一律降級為
`NEEDS_HUMAN_REVIEW`（Req 12.3），所以規則引擎判定 ineligible 的項目**現在全部走
人工協助**。

這是刻意的取捨：沒有理由的「你不符合」比轉人工更糟 —— 使用者無法判斷是自己真的不
符合、還是系統看錯了，也不知道下一步該做什麼。等資料層開始輸出結構化決定性條件，
這個降級就會自動停止觸發，不需要再改一次程式。

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

from app.orchestration import data_contracts
from app.orchestration.state import (
    AmountPeriod,
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

# 哪些項目代號是「必須辦理的行政事項」而不是「可以申請的福利」。
#
# 這個區分不在 `data_contracts.CandidateItem` 裡，因為提案第 7 節的契約沒有它。
# 但畫面上這個區分很重要：不能讓使用者把「你符合死亡登記的資格」讀成一項可以選擇
# 放棄的福利。所以先由 adapter 用一份已知清單判斷，其餘一律視為福利。
#
# 這是 adapter 的暫行職責。資料層若之後在契約裡帶上這個分類，這份清單就可以刪掉。
_ADMINISTRATIVE_ITEM_IDS: frozenset[str] = frozenset(
    {
        "death_registration",
        "health_insurance_change",
        "occupational_injury_recognition_follow_up",
        "disability_assessment",
        "long_term_care_assessment",
        "caregiver_support_contact",
    }
)


def adapt_graph_candidate(
    candidate: data_contracts.CandidateItem,
) -> CandidateItem:
    """把資料層交出來的候選方案轉成 workflow 的項目。

    只搬「這一項是什麼」，不搬任何判定結果：新項目一律從 `PENDING` 開始，因為資料層
    不知道也不該決定這位使用者符不符合。

    `relevance_score` 刻意**不**搬進 workflow 形狀。它只代表相關性，不代表符合資格的
    機率或程度（提案第 7 節），而 `state.CandidateItem` 目前沒有任何欄位承載排序用的
    分數 —— 硬塞一個進去會讓下游有機會把它讀成「有多符合」。它是否要露給前端仍是
    提案第 12 節第 3 項的待決策項目。
    """
    kind = (
        ItemKind.ADMINISTRATIVE
        if candidate.item_id in _ADMINISTRATIVE_ITEM_IDS
        else ItemKind.BENEFIT
    )
    return CandidateItem(
        item_id=candidate.item_id,
        kind=kind,
        display_name=candidate.display_name,
        summary=candidate.summary,
        program_status=candidate.program_status,
        missing_field_ids=candidate.missing_field_ids,
    )


def _decisive_conditions(
    reasons: tuple[data_contracts.StructuredReason, ...],
) -> tuple[DecisiveCondition, ...]:
    """把結構化原因轉成 workflow 的決定性條件。

    `StructuredReason.expected` 與 `actual` 的型別是 `Any`，而 `DecisiveCondition`
    只接受去識別化的三種值（布林、整數、字串代號）。型別對不上的原因（例如巢狀的
    條件 JSON）**整筆略過**，不硬轉成字串 —— 錯的「差在哪一條」比不顯示更糟，而略過
    之後 `downgrade_unexplained_ineligible` 會接手把說不出理由的「不符合」降級。

    `actual` 在這裡被搬進 workflow 形狀是允許的：它會回給提出請求的使用者。它不得
    進入紀錄檔，而 `app.observability.logging` 的允許欄位清單裡沒有任何欄位能容納它。
    """
    converted: list[DecisiveCondition] = []
    for reason in reasons:
        if not isinstance(reason.expected, bool | int | str):
            continue
        if not isinstance(reason.actual, bool | int | str):
            continue
        converted.append(
            DecisiveCondition(
                field_id=reason.field_id,
                expected=reason.expected,
                actual=reason.actual,
            )
        )
    return tuple(converted)


def apply_decision(
    item: CandidateItem,
    decision: data_contracts.EligibilityDecision,
    *,
    now: datetime | None = None,
) -> CandidateItem:
    """把一筆判定結果套回既有的項目。

    回傳新的項目，不修改傳入的那一個。`kind` 與 `program_status` 保留；判定結果不會
    改變「這一項是什麼」，也不會改變資料層對它的治理狀態。缺漏欄位則以這次
    decision 的 `missing_field_ids` 為準，避免 `needs_information` 沿用過期清單。

    未知的 status 字串安全降級為需人工協助：那代表資料層送來了我們不認識的結論，
    猜它的意思比說「需要人看一下」危險。
    """
    resolved_at = now if now is not None else datetime.now(UTC)

    status = _STATUS_MAP.get(decision.status, ItemStatus.NEEDS_HUMAN_REVIEW)
    decisive_conditions = _decisive_conditions(decision.reasons)
    status = downgrade_unexplained_ineligible(status, decisive_conditions)

    return item.model_copy(
        update={
            "status": status,
            "missing_field_ids": decision.missing_field_ids,
            "decisive_conditions": decisive_conditions,
            "amount_min": decision.amount_min,
            "amount_max": decision.amount_max,
            "amount_period": (
                AmountPeriod(decision.amount_period)
                if decision.amount_period is not None
                else None
            ),
            "amount_currency": decision.amount_currency,
            # 只有「資訊不足」還沒定案，其餘三種都是結論。
            "resolved_at": (
                None if status is ItemStatus.NEEDS_INFORMATION else resolved_at
            ),
        }
    )


def downgrade_unexplained_ineligible(
    status: ItemStatus,
    decisive_conditions: tuple[DecisiveCondition, ...],
) -> ItemStatus:
    """「不符合」而說不出決定性條件時，改成需人工協助（Req 12.3）。

    分成獨立函式的理由是可測試性：`adapt_result` 目前**永遠**產生空的
    decisive_conditions，所以從它那邊無法驗證「有條件時不降級」這一半的規則。等資料層
    開始輸出結構化條件，那條路徑就會被真正走到，而規則本身不需要再改。

    其他狀態原樣回傳。
    """
    if status is ItemStatus.INELIGIBLE and not decisive_conditions:
        return ItemStatus.NEEDS_HUMAN_REVIEW
    return status


def adapt_result(
    result: EligibilityResult,
    *,
    item_kind: ItemKind = ItemKind.BENEFIT,
) -> CandidateItem:
    """把一筆 EligibilityResult 轉成 CandidateItem。

    `item_kind` 由呼叫端提供，因為規則引擎不知道這個項目是福利還是行政事項。

    注意「不符合資格」目前一定會被降級為需人工協助，理由見模組開頭。呼叫端不需要
    為此做任何事，但看到結果裡沒有 INELIGIBLE 時不必懷疑是 bug。
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

    status = downgrade_unexplained_ineligible(status, decisive_conditions)

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
        # 只有「資訊不足」還沒定案，其餘四種都是結論，包含降級後的需人工協助 ——
        # 那也是一個結論（交給人處理），所以照樣蓋上定案時間。
        resolved_at=datetime.now(UTC)
        if status != ItemStatus.NEEDS_INFORMATION
        else None,
    )
