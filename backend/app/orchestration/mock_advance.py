"""狀態機的臨時替代品，讓前端可以先接上後端。

## 這個檔案會被整個刪除

真正的流程控制屬於 `state_machine.py`：八個狀態的轉換規則、每個狀態的工具允許
清單、迴圈的四道護欄、條件性的 `CONFIRM`。那些還沒實作。

這裡提供的是**剛好足夠讓前端走一遍**的推進：送出文字會得到一個事件代號，確認之後
會得到一組候選項目。實作真正的狀態機時，把 `advance` 的呼叫換掉並刪除本檔案即可，
API 層不需要跟著改。

## 這裡的資料是寫死的

- 不管使用者輸入什麼，事件一律回 `spouse_death`。沒有呼叫任何模型。
- 四個候選項目與使用者的情況無關，全部標 `PENDING`。
- 沒有任何資格判定，沒有官方依據，沒有金額。
- 屬性照收，沒有欄位 allowlist 檢查。

項目與事件的代號取自 `README.md` 的 MVP 情境（死亡登記、喪葬給付、遺屬年金、
全民健康保險身分變更）。代號本身是暫定的，entitlement graph 建立後可能改名，
所以不要在別處硬寫它們。

回應會帶 `ImplementationNotice`，讓前端可以在畫面上標示這些是佔位資料。
"""

from app.orchestration.state import (
    CandidateItem,
    ExitReason,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)
from app.schemas.session import (
    AdvanceInput,
    AttributeAnswersInput,
    EventConfirmationInput,
    HelpRequestInput,
    ImplementationNotice,
    ItemDeclineInput,
    LifeEventTextInput,
    PendingCapability,
    ReferralChoiceInput,
    ReviewConfirmationInput,
)

# 使用者說「不是這樣」的次數上限。真正的上限屬於狀態機的政策，這裡只是先讓出口
# 存在，避免使用者卡在第一步。
MAX_EVENT_RETRIES = 2

# 寫死的事件代號。真正的值由 LLM 抽取後交給使用者確認。
PLACEHOLDER_LIFE_EVENT = "spouse_death"

# 寫死的候選項目。真正的清單由 entitlement graph 依事件查出。
PLACEHOLDER_ITEMS: tuple[CandidateItem, ...] = (
    CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),
    CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
    CandidateItem(item_id="survivor_pension", kind=ItemKind.BENEFIT),
    CandidateItem(item_id="health_insurance_change", kind=ItemKind.ADMINISTRATIVE),
)

PLACEHOLDER_NOTICE = "（此為後端傳來的暫時資料，尚未進行真實的事件辨識與資格判定）"

# 目前完全沒有實作的能力。實作完成就從這裡移除。
PENDING_CAPABILITIES: tuple[PendingCapability, ...] = (
    PendingCapability.LIFE_EVENT_EXTRACTION,
    PendingCapability.ENTITLEMENT_GRAPH,
    PendingCapability.STATE_MACHINE,
    PendingCapability.FIELD_REGISTRY,
    PendingCapability.RULE_EVALUATION,
    PendingCapability.OFFICIAL_CITATIONS,
    PendingCapability.PLAIN_LANGUAGE_EXPLANATION,
    PendingCapability.ACTION_PLAN,
    PendingCapability.PRIVACY_GATE,
)


def implementation_notice() -> ImplementationNotice:
    """描述這份回應有多少是真的。"""
    return ImplementationNotice(
        is_mock=True,
        pending=PENDING_CAPABILITIES,
        placeholder_notice=PLACEHOLDER_NOTICE,
    )


class NotAllowedInStateError(RuntimeError):
    """這個狀態不接受這種輸入。

    真正的守門條件屬於狀態機。這裡只擋最明顯的情況，例如在流程中段又送自由文字。
    """


class UnknownItemError(LookupError):
    """送來的項目代號不在候選清單裡。"""


def advance(state: SessionState, user_input: AdvanceInput) -> SessionState:
    """依輸入回傳一份新的 state。

    不修改傳進來的 state：`SessionState` 是 frozen，每一步都產生新物件。
    """
    match user_input:
        case LifeEventTextInput():
            return _receive_life_event(state)
        case EventConfirmationInput():
            return _confirm_event(state, confirmed=user_input.confirmed)
        case AttributeAnswersInput():
            return _record_answers(state, user_input)
        case ItemDeclineInput():
            return _decline_item(state, user_input.item_id)
        case ReviewConfirmationInput():
            return _confirm_review(state, confirmed=user_input.confirmed)
        case ReferralChoiceInput():
            return state.model_copy(update={"referral_requested": user_input.requested})
        case HelpRequestInput():
            return state.model_copy(
                update={"exit_reason": ExitReason.USER_REQUESTED_HELP}
            )

    raise NotAllowedInStateError


def _receive_life_event(state: SessionState) -> SessionState:
    """接收自由文字，回一個寫死的事件代號等使用者確認。

    自由文字本身沒有被使用，也沒有被保存 —— 這裡沒有任何欄位存放它，符合 ADR-0007。
    真正實作時會呼叫 LLM 抽取，然後同樣丟棄原文。
    """
    if state.workflow_state is not WorkflowState.UNDERSTAND_EVENT:
        raise NotAllowedInStateError

    return state.model_copy(update={"life_event": PLACEHOLDER_LIFE_EVENT})


def _confirm_event(state: SessionState, *, confirmed: bool) -> SessionState:
    """使用者確認或否認系統理解的事件。"""
    if state.workflow_state is not WorkflowState.UNDERSTAND_EVENT:
        raise NotAllowedInStateError
    if state.life_event is None:
        raise NotAllowedInStateError

    if confirmed:
        return state.model_copy(
            update={
                "workflow_state": WorkflowState.RESOLVE_ENTITLEMENTS,
                "items": PLACEHOLDER_ITEMS,
            }
        )

    retries = state.event_retry_count + 1
    if retries > MAX_EVENT_RETRIES:
        return state.model_copy(
            update={
                "life_event": None,
                "event_retry_count": retries,
                "exit_reason": ExitReason.EVENT_RETRY_LIMIT_REACHED,
            }
        )

    return state.model_copy(update={"life_event": None, "event_retry_count": retries})


def _record_answers(
    state: SessionState, user_input: AttributeAnswersInput
) -> SessionState:
    """記下一組答案。

    沒有欄位 allowlist 檢查，所以任何代號都會被接受。真正的驗證屬於 `app.privacy`，
    因此 `PRIVACY_GATE` 列在未實作清單裡。
    """
    if state.workflow_state is WorkflowState.UNDERSTAND_EVENT:
        raise NotAllowedInStateError

    merged = dict(state.attributes)
    merged.update(user_input.answers)

    return state.model_copy(
        update={
            "workflow_state": WorkflowState.COLLECT_MISSING_FIELDS,
            "attributes": merged,
        }
    )


def _decline_item(state: SessionState, item_id: str) -> SessionState:
    """把一個項目標記為使用者不想辦。"""
    if item_id not in {item.item_id for item in state.items}:
        raise UnknownItemError

    return state.model_copy(
        update={
            "items": tuple(
                item.model_copy(update={"status": ItemStatus.DECLINED_BY_USER})
                if item.item_id == item_id
                else item
                for item in state.items
            )
        }
    )


def _confirm_review(state: SessionState, *, confirmed: bool) -> SessionState:
    """複查後確認，進入完成。

    真正的流程會在這裡重算受影響的項目；這裡只推進狀態。
    """
    if not confirmed:
        return state.model_copy(
            update={"workflow_state": WorkflowState.COLLECT_MISSING_FIELDS}
        )

    return state.model_copy(update={"workflow_state": WorkflowState.COMPLETE})
