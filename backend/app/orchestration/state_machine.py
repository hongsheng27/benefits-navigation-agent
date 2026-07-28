"""確定性的狀態轉換引擎。

這個模組是後端的骨幹：它決定「收到這個輸入之後，狀態怎麼變」。

## 三張宣告表

所有流程規則**集中在這三張表裡**，不散在各個處理函式中：

1. `ALLOWED_INPUTS` — 每個狀態接受哪些種類的輸入
2. `ENTRY_GUARDS` — 進入某個狀態之前的守門條件（不滿足就跳過）
3. `NOMINAL_PATH` — 正常路徑的下一步是什麼

改流程規則時只要改這三張表，不用翻整個檔案。

## 「一次推到底」

有些狀態不需要使用者做任何事就會自動往前（例如展開項目、檢索依據、判定資格）。
`advance` 收到一筆輸入後，不只走一步，而是**繼續自動推進直到下一個需要等使用者
的狀態**。前端一次呼叫就得到最終結果，不用反覆輪詢中間狀態。

哪些狀態「需要等使用者」由 `ALLOWED_INPUTS` 決定：如果那個狀態在表裡有值（集合
不是空的），就是需要等；空集合表示自動推進。

## 這個版本還沒有的

- 規則引擎（T9）：目前中間步驟的自動推進是空操作，不會真的判定資格
- 欄位登記表（T7）：不知道要問什麼
- 缺漏欄位計算（T8）：不知道哪些項目已經湊齊了
- 迴圈護欄（T6）：目前只有迭代計數，沒有「必須有進展」的檢查

這些都有對應的後續任務。這個模組提供的是**骨幹**：轉換規則、守門條件、自動推進，
讓那些任務有地方接入。

## 跟 `mock_advance.py` 的差別

`mock_advance.py` 是佔位的，它寫死了事件代號和候選項目，讓前端有東西可接。
這個模組是真正的流程控制，**但還沒有真正的資料來源** —— 事件辨識和項目展開暫時
仍由呼叫端提供，這裡只負責管「什麼時候能做什麼」。
"""

from collections.abc import Callable

from app.orchestration.state import (
    CandidateItem,
    ExitReason,
    ItemStatus,
    SessionState,
    WorkflowState,
)
from app.schemas.session import (
    AdvanceInput,
    AttributeAnswersInput,
    EventConfirmationInput,
    HelpRequestInput,
    ItemDeclineInput,
    LifeEventTextInput,
    ReferralChoiceInput,
    ReviewConfirmationInput,
)

# ---------------------------------------------------------------------------
# 政策參數
# ---------------------------------------------------------------------------

# 使用者說「不是這樣」的上限。超過走人工協助出口。
MAX_EVENT_RETRIES = 2

# 中間迴圈的迭代上限。
MAX_LOOP_ITERATIONS = 6

# ---------------------------------------------------------------------------
# 宣告表一：每個狀態接受哪些種類的輸入
# ---------------------------------------------------------------------------

# 空集合表示該狀態不等使用者輸入，會自動推進。
# HelpRequestInput 在任何需要等使用者的狀態都可以送。

ALLOWED_INPUTS: dict[WorkflowState, set[type]] = {
    WorkflowState.UNDERSTAND_EVENT: {
        LifeEventTextInput,
        EventConfirmationInput,
    },
    WorkflowState.RESOLVE_ENTITLEMENTS: set(),  # 自動推進
    WorkflowState.COLLECT_MISSING_FIELDS: {
        AttributeAnswersInput,
        ItemDeclineInput,
    },
    WorkflowState.RETRIEVE_RULES: set(),  # 自動推進
    WorkflowState.EVALUATE_ELIGIBILITY: set(),  # 自動推進
    WorkflowState.EXPLAIN_RESULT: set(),  # 自動推進
    WorkflowState.CONFIRM: {
        ReviewConfirmationInput,
        ReferralChoiceInput,
    },
    WorkflowState.COMPLETE: set(),  # 終點，不接受任何輸入
}

# ---------------------------------------------------------------------------
# 宣告表二：進入某個狀態的守門條件
# ---------------------------------------------------------------------------

# 守門條件回傳 True 表示可以進入，False 表示跳過（走 NOMINAL_PATH 的下一步）。
# 沒有列在這裡的狀態永遠可以進入。

type Guard = Callable[[SessionState], bool]

ENTRY_GUARDS: dict[WorkflowState, Guard] = {
    # CONFIRM 只在有項目需要人工協助或資訊不足時才進入。
    # 全部乾淨定案就跳過，直接到 COMPLETE。
    WorkflowState.CONFIRM: lambda state: any(
        item.status in {ItemStatus.NEEDS_HUMAN_REVIEW, ItemStatus.NEEDS_INFORMATION}
        for item in state.items
    ),
    # EXPLAIN_RESULT 只在有已定案的項目時才有意義。
    # 如果所有項目都還在 PENDING（例如使用者全部選「不想辦」之後），跳過。
    WorkflowState.EXPLAIN_RESULT: lambda state: any(
        item.status not in {ItemStatus.PENDING, ItemStatus.DECLINED_BY_USER}
        for item in state.items
    ),
}

# ---------------------------------------------------------------------------
# 宣告表三：正常路徑的下一步
# ---------------------------------------------------------------------------

# 迴圈的回跳由 _should_loop_back 決定，不在這裡。
NOMINAL_PATH: dict[WorkflowState, WorkflowState] = {
    WorkflowState.UNDERSTAND_EVENT: WorkflowState.RESOLVE_ENTITLEMENTS,
    WorkflowState.RESOLVE_ENTITLEMENTS: WorkflowState.COLLECT_MISSING_FIELDS,
    WorkflowState.COLLECT_MISSING_FIELDS: WorkflowState.RETRIEVE_RULES,
    WorkflowState.RETRIEVE_RULES: WorkflowState.EVALUATE_ELIGIBILITY,
    WorkflowState.EVALUATE_ELIGIBILITY: WorkflowState.EXPLAIN_RESULT,
    WorkflowState.EXPLAIN_RESULT: WorkflowState.CONFIRM,
    WorkflowState.CONFIRM: WorkflowState.COMPLETE,
}


# ---------------------------------------------------------------------------
# 公開介面
# ---------------------------------------------------------------------------


class InvalidTransitionError(RuntimeError):
    """目前的狀態不接受這個輸入。

    帶著 `current_state` 讓 API 層可以回傳有意義的錯誤。
    """

    def __init__(self, current_state: WorkflowState) -> None:
        super().__init__(f"不接受此輸入於 {current_state.value}")
        self.current_state = current_state


class UnknownItemError(LookupError):
    """送來的項目代號不在候選清單裡。"""


def advance(state: SessionState, user_input: AdvanceInput) -> SessionState:
    """依輸入推進狀態，並自動走完不需要使用者的中間步驟。

    回傳的是一個新的 `SessionState`，不修改傳入的。
    """
    # 記住推進前的快照，護欄用它比較「有沒有進展」。
    state_before = state

    # HelpRequestInput 在任何需要等使用者的狀態都可以送。
    if isinstance(user_input, HelpRequestInput):
        if not ALLOWED_INPUTS.get(state.workflow_state):
            raise InvalidTransitionError(state.workflow_state)
        return state.model_copy(update={"exit_reason": ExitReason.USER_REQUESTED_HELP})

    # 檢查這個輸入在當前狀態是否合法。
    allowed = ALLOWED_INPUTS.get(state.workflow_state, set())
    if type(user_input) not in allowed:
        raise InvalidTransitionError(state.workflow_state)

    # 依輸入種類處理。
    new_state = _handle_input(state, user_input)

    # 自動推進：一直往前走，直到下一個需要等使用者的狀態。
    new_state = _auto_advance(new_state, state_before)

    return new_state


# ---------------------------------------------------------------------------
# 輸入處理
# ---------------------------------------------------------------------------


def _handle_input(state: SessionState, user_input: AdvanceInput) -> SessionState:
    """依輸入種類產生新狀態。這裡只處理「使用者做了什麼」，不處理自動推進。"""
    match user_input:
        case LifeEventTextInput():
            return _receive_life_event(state, user_input)
        case EventConfirmationInput():
            return _confirm_event(state, user_input)
        case AttributeAnswersInput():
            return _record_answers(state, user_input)
        case ItemDeclineInput():
            return _decline_item(state, user_input)
        case ReviewConfirmationInput():
            return _confirm_review(state, user_input)
        case ReferralChoiceInput():
            return state.model_copy(update={"referral_requested": user_input.requested})

    raise InvalidTransitionError(state.workflow_state)


def _receive_life_event(
    state: SessionState, user_input: LifeEventTextInput
) -> SessionState:
    """接收自由文字。

    真正的實作會呼叫 LLM 抽取事件代號與屬性（T21）。目前暫時用寫死的代號，
    讓流程可以走通。

    自由文字本身沒有被保存 —— SessionState 沒有欄位放它（ADR-0007）。
    """
    if state.life_event is not None:
        # 已經有事件代號了（使用者之前否認後要重新描述），先清掉。
        pass

    # TODO(T21): 呼叫 LLM 抽取事件代號。目前寫死。
    extracted_event = "spouse_death"

    return state.model_copy(update={"life_event": extracted_event})


def _confirm_event(
    state: SessionState, user_input: EventConfirmationInput
) -> SessionState:
    """使用者確認或否認事件。"""
    if state.life_event is None:
        # 還沒有事件代號就送確認，不合法。
        raise InvalidTransitionError(state.workflow_state)

    if user_input.confirmed:
        # 確認成功，往前推到 RESOLVE_ENTITLEMENTS。
        # 自動推進會接手往後走。
        return state.model_copy(
            update={"workflow_state": WorkflowState.RESOLVE_ENTITLEMENTS}
        )

    # 否認：清掉事件代號，累加重試計數。
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
    """記下一組答案並推進到迴圈的下一步。

    `_state_before_loop_iteration` 會被 `_auto_advance` 在進入 RETRIEVE_RULES 之前
    快照，用來比較「這一圈有沒有進展」。
    """
    merged = dict(state.attributes)
    merged.update(user_input.answers)

    return state.model_copy(
        update={
            "attributes": merged,
            "workflow_state": WorkflowState.RETRIEVE_RULES,
            "loop_iterations": state.loop_iterations + 1,
        }
    )


def _decline_item(state: SessionState, user_input: ItemDeclineInput) -> SessionState:
    """把一個項目標記為使用者不想辦。"""
    if user_input.item_id not in {item.item_id for item in state.items}:
        raise UnknownItemError

    new_items = tuple(
        item.model_copy(update={"status": ItemStatus.DECLINED_BY_USER})
        if item.item_id == user_input.item_id
        else item
        for item in state.items
    )

    return state.model_copy(update={"items": new_items})


def _confirm_review(
    state: SessionState, user_input: ReviewConfirmationInput
) -> SessionState:
    """複查後確認或退回修改。"""
    if user_input.confirmed:
        return state.model_copy(update={"workflow_state": WorkflowState.COMPLETE})

    # 退回修改：回到追問欄位。
    return state.model_copy(
        update={"workflow_state": WorkflowState.COLLECT_MISSING_FIELDS}
    )


# ---------------------------------------------------------------------------
# 自動推進
# ---------------------------------------------------------------------------


def _auto_advance(
    state: SessionState, state_before_input: SessionState
) -> SessionState:
    """從當前狀態開始，自動走完不需要使用者的中間步驟。

    停止條件：
    - 到達一個需要等使用者的狀態（ALLOWED_INPUTS 裡有值）
    - 到達終點（COMPLETE）
    - 已經有 exit_reason（流程結束）
    - 迴圈判斷需要回到 COLLECT_MISSING_FIELDS

    護欄檢查在 EVALUATE_ELIGIBILITY 完成後觸發。
    `state_before_input` 是使用者這次操作之前的快照，用來判斷有沒有進展。
    """
    max_auto_steps = 20
    steps = 0

    while steps < max_auto_steps:
        steps += 1

        if state.exit_reason is not None:
            break
        if state.workflow_state == WorkflowState.COMPLETE:
            break

        allowed = ALLOWED_INPUTS.get(state.workflow_state, set())
        if allowed:
            break

        # 執行自動步驟。
        state = _execute_auto_step(state)

        # 如果剛做完 EVALUATE_ELIGIBILITY，跑護欄。
        if state.workflow_state == WorkflowState.EVALUATE_ELIGIBILITY:
            state = _check_loop_guardrails(state, state_before_input)
            if state.exit_reason is not None:
                break

        # 走到下一步。
        next_ws = _resolve_next_state(state)
        if next_ws is None:
            break

        state = state.model_copy(update={"workflow_state": next_ws})

    return state


def _execute_auto_step(state: SessionState) -> SessionState:
    """在自動推進的狀態裡執行動作。

    目前多數都是空操作（T7–T10 之後才會有內容）。
    """
    match state.workflow_state:
        case WorkflowState.RESOLVE_ENTITLEMENTS:
            return _do_resolve_entitlements(state)
        case WorkflowState.RETRIEVE_RULES:
            return _do_retrieve_rules(state)
        case WorkflowState.EVALUATE_ELIGIBILITY:
            return _do_evaluate_eligibility(state)
        case WorkflowState.EXPLAIN_RESULT:
            return _do_explain_result(state)

    return state


def _resolve_next_state(state: SessionState) -> WorkflowState | None:
    """決定下一步去哪。考慮迴圈回跳和守門條件。"""
    current = state.workflow_state

    # 在判定完成後，檢查是否需要回到追問欄位（迴圈）。
    if current == WorkflowState.EVALUATE_ELIGIBILITY:
        if _should_loop_back(state):
            return WorkflowState.COLLECT_MISSING_FIELDS

    # 照正常路徑。
    next_ws = NOMINAL_PATH.get(current)
    if next_ws is None:
        return None

    # 檢查守門條件。
    guard = ENTRY_GUARDS.get(next_ws)
    if guard is not None and not guard(state):
        # 跳過這個狀態，再往後找。
        # 暫存 state 的 workflow_state 設成那個被跳過的，然後遞迴往後。
        skipped = state.model_copy(update={"workflow_state": next_ws})
        return _resolve_next_state(skipped)

    return next_ws


def _should_loop_back(state: SessionState) -> bool:
    """判定完成後，是否還有項目需要更多欄位。

    如果有任何項目仍然是 PENDING 或 NEEDS_INFORMATION，而且迭代次數還沒到上限，
    就回到追問步驟。

    注意：到達上限或沒有進展時，不在這裡設 exit_reason —— 那由 _check_loop_guardrails
    負責，在 _auto_advance 裡的合適時機呼叫。這個函式只回答「要不要回去」。
    """
    if state.loop_iterations >= MAX_LOOP_ITERATIONS:
        return False

    return any(
        item.status in {ItemStatus.PENDING, ItemStatus.NEEDS_INFORMATION}
        for item in state.items
        if item.status != ItemStatus.DECLINED_BY_USER
    )


def _check_loop_guardrails(
    state: SessionState, state_before_iteration: SessionState
) -> SessionState:
    """在迴圈的 EVALUATE_ELIGIBILITY 結束後，檢查兩道護欄。

    護欄一：迭代上限
    如果已經繞了 MAX_LOOP_ITERATIONS 圈但還有項目未定案，設 exit_reason。

    護欄二：必須有進展
    比較這一圈開始前和結束後的狀態。「進展」的定義是：
    - 至少一個項目的 status 改變了，或
    - attributes 的鍵的數量增加了（收到了新的答案）

    兩者都沒有就表示死循環 —— 一直問同樣的問題卻得不到新資訊。
    """
    # 護欄一：到上限了嗎
    if state.loop_iterations >= MAX_LOOP_ITERATIONS:
        has_unsettled = any(
            item.status in {ItemStatus.PENDING, ItemStatus.NEEDS_INFORMATION}
            for item in state.items
            if item.status != ItemStatus.DECLINED_BY_USER
        )
        if has_unsettled:
            return state.model_copy(
                update={"exit_reason": ExitReason.LOOP_LIMIT_REACHED}
            )

    # 護欄二：有進展嗎
    # 只有在已經繞了至少一圈之後才檢查（第一圈一定是新的）
    if state.loop_iterations > 1:
        old_statuses = {
            item.item_id: item.status for item in state_before_iteration.items
        }
        new_statuses = {item.item_id: item.status for item in state.items}
        status_changed = old_statuses != new_statuses

        old_attr_count = len(state_before_iteration.attributes)
        new_attr_count = len(state.attributes)
        attrs_grew = new_attr_count > old_attr_count

        if not status_changed and not attrs_grew:
            return state.model_copy(update={"exit_reason": ExitReason.NO_PROGRESS})

    return state


# ---------------------------------------------------------------------------
# 自動步驟的實作（目前多數是佔位的）
# ---------------------------------------------------------------------------


# 寫死的候選項目，跟 mock_advance.py 一樣。
# TODO(T15): 改成從 entitlement graph 查。
_PLACEHOLDER_ITEMS: tuple[CandidateItem, ...] = (
    CandidateItem(item_id="death_registration", kind="administrative"),
    CandidateItem(item_id="funeral_benefit", kind="benefit"),
    CandidateItem(item_id="survivor_pension", kind="benefit"),
    CandidateItem(item_id="health_insurance_change", kind="administrative"),
)


def _do_resolve_entitlements(state: SessionState) -> SessionState:
    """展開候選項目。

    TODO(T15): 從 entitlement graph 查，不是寫死的。
    """
    if state.items:
        # 已經有項目了（例如退回修改後再走一次），不重複展開。
        return state

    return state.model_copy(update={"items": _PLACEHOLDER_ITEMS})


def _do_retrieve_rules(state: SessionState) -> SessionState:
    """檢索官方依據。

    TODO(T9): 從資料層取。目前是空操作。
    """
    return state


def _do_evaluate_eligibility(state: SessionState) -> SessionState:
    """判定資格。

    TODO(T9, T10): 呼叫規則引擎。目前是空操作，所有項目維持 PENDING。
    """
    return state


def _do_explain_result(state: SessionState) -> SessionState:
    """產出白話說明。

    TODO(T22): 呼叫 LLM。目前是空操作。
    """
    return state
