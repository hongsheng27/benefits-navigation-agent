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

- 官方依據檢索：`RETRIEVE_RULES` 仍是空操作，資料層還沒交出 `EvidenceRepository`
- 白話說明：`EXPLAIN_RESULT` 仍是空操作，還沒接模型

## 流程規則是真的，資料來源還不是

轉換規則、守門條件、自動推進與護欄都已經是最終行為。但**事件辨識仍是寫死的**
（等 LLM），**項目展開仍來自離線 fixture**（等資料層的 SQLite repository）。每一處
都有註解說明。

資料來源不由這個模組自己去拿，而是透過 `protocols.py` 的接縫注入（見 `advance()`
的具名參數）。目前注入的是不需要 SQLite 的離線實作，換成真實來源時這個模組不用改。
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.orchestration.determination import evaluate_ready_items, visible_items
from app.orchestration.field_registry import FieldRegistry
from app.orchestration.life_event_extraction import (
    DEFAULT_EXTRACTOR,
    LifeEventExtractorPort,
)
from app.orchestration.local_worker import RefreshWorkerPort
from app.orchestration.protocols import (
    CoverageScope,
    EligibilityService,
    EntitlementGraphRepository,
    EvidenceRepository,
    FixtureEligibilityService,
    FixtureEntitlementGraphRepository,
    LocalSourceRefreshService,
    PassThroughPrivacyGate,
    PrivacyGate,
    SourceRefreshService,
)
from app.orchestration.refresh_orchestration import respond_then_refresh
from app.orchestration.rule_adapter import adapt_graph_candidate
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

# 「還沒定案」的項目狀態。護欄的降級範圍與迴圈的回跳判斷共用這一份定義，避免兩邊
# 各寫一次集合而在之後走鐘。`DECLINED_BY_USER` 不在裡面：使用者已經決定不辦了，
# 那就是一種定案。
UNSETTLED_STATUSES: frozenset[ItemStatus] = frozenset(
    {ItemStatus.PENDING, ItemStatus.NEEDS_INFORMATION}
)

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


class UnknownFieldError(ValueError):
    """送來的欄位代號不在登記表上。

    帶的是**欄位代號**，不是使用者填的值。這一點是刻意的：錯誤會流到 HTTP 回應與
    紀錄檔，而那兩個地方都不得出現使用者輸入（Req 16.5）。

    `field_ids` 排序後才存，讓同一組違規欄位永遠得到同一個順序 —— 錯誤回應因此是
    可預期的，測試也不必去猜 dict 的迭代順序。
    """

    def __init__(self, field_ids: tuple[str, ...]) -> None:
        ordered = tuple(sorted(field_ids))
        super().__init__(f"未登記的欄位代號：{', '.join(ordered)}")
        self.field_ids = ordered


# 模組層的登記表快取。lazy 初始化，因為 `from_json` 會讀磁碟 —— 放在 import 時執行
# 會讓「匯入這個模組」變成一件可能失敗的事（例如登記表檔案還沒建好）。
_REGISTRY_CACHE: FieldRegistry | None = None


def default_registry() -> FieldRegistry:
    """取得共用的欄位登記表實例。

    登記表是啟動後不再變動的資料，每次呼叫都重讀一次磁碟只是浪費；更重要的是這樣
    整個請求週期內大家看到的是**同一份**登記表，不會出現「驗證用一份、算缺漏用另一
    份」的可能。
    """
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        _REGISTRY_CACHE = FieldRegistry.from_json()
    return _REGISTRY_CACHE


@dataclass(frozen=True)
class _Seams:
    """一次推進過程中會用到的外部依賴。

    把它們收在一個物件裡，是為了讓自動推進那一串內部函式的簽章不會隨著接縫變多而
    一直加參數。內容全部來自 `advance()` 的具名參數，所以呼叫端仍然能逐項替換。
    """

    registry: FieldRegistry
    entitlement_repository: EntitlementGraphRepository
    privacy_gate: PrivacyGate
    eligibility_service: EligibilityService
    source_refresh_service: SourceRefreshService
    coverage_scope: CoverageScope
    # 官方依據的檢索還沒接上（`RETRIEVE_RULES` 仍是空操作）。保留欄位是為了讓資料層
    # 交出 repository 時只需改 `_do_retrieve_rules`，不必再動 `advance()` 的簽章。
    evidence_repository: EvidenceRepository | None = None
    # 背景 refresh 的交付邊界。`None` 代表只排入 service 的佇列、不再往下交付。
    # 這個接縫只暴露 `submit()`，所以 request path 在型別上就沒有辦法同步執行
    # crawl 或 LLM（Req 11.10）。
    refresh_worker: RefreshWorkerPort | None = None
    # 事件辨識。預設是關鍵字比對，之後換 LLM 版時只換這個注入值。
    life_event_extractor: LifeEventExtractorPort = DEFAULT_EXTRACTOR


def advance(
    state: SessionState,
    user_input: AdvanceInput,
    *,
    registry: FieldRegistry | None = None,
    entitlement_repository: EntitlementGraphRepository | None = None,
    privacy_gate: PrivacyGate | None = None,
    eligibility_service: EligibilityService | None = None,
    source_refresh_service: SourceRefreshService | None = None,
    coverage_scope: CoverageScope | None = None,
    evidence_repository: EvidenceRepository | None = None,
    refresh_worker: RefreshWorkerPort | None = None,
    life_event_extractor: LifeEventExtractorPort | None = None,
) -> SessionState:
    """依輸入推進狀態，並自動走完不需要使用者的中間步驟。

    回傳的是一個新的 `SessionState`，不修改傳入的。

    所有接縫都是具名參數且可以省略，預設值是不需要 SQLite 的離線實作。資料層交出
    SQLite repository 後逐個換掉即可，這個模組不用改（Req 19）。顯式注入 refresh
    service 時也必須提供 coverage scope，避免服務看似啟用卻因空 scope 靜默不工作。
    """
    if source_refresh_service is not None and coverage_scope is None:
        raise ValueError(
            "coverage_scope is required when source_refresh_service is provided"
        )

    seams = _Seams(
        registry=registry if registry is not None else default_registry(),
        entitlement_repository=(
            entitlement_repository
            if entitlement_repository is not None
            else FixtureEntitlementGraphRepository()
        ),
        privacy_gate=(
            privacy_gate if privacy_gate is not None else PassThroughPrivacyGate()
        ),
        # 預設的判定服務沒有任何已核准規則，所以它對每一項都回「需人工協助」。
        # 那是誠實的預設值：離線環境本來就沒有可以下結論的依據。
        eligibility_service=(
            eligibility_service
            if eligibility_service is not None
            else FixtureEligibilityService()
        ),
        # 預設的來源表是空的，所以 coverage 查詢回空、不會排任何 refresh。真正的
        # 來源表由呼叫端注入。
        source_refresh_service=(
            source_refresh_service
            if source_refresh_service is not None
            else LocalSourceRefreshService()
        ),
        # Scope 必須由 composition/caller 明確提供；預設空 scope 不猜所有來源都相關。
        coverage_scope=(
            coverage_scope
            if coverage_scope is not None
            else CoverageScope(source_ids=(), domain_tags=())
        ),
        evidence_repository=evidence_repository,
        refresh_worker=refresh_worker,
        life_event_extractor=(
            life_event_extractor
            if life_event_extractor is not None
            else DEFAULT_EXTRACTOR
        ),
    )

    # 流程已經結束就不再接受任何輸入（Req 1.5、Req 5.3）。
    #
    # 這道檢查必須放在 help_request 的分支**之前**。否則一個已經因為護欄而結束的
    # session 還能再送一次 help_request，把 exit_reason 從 LOOP_LIMIT_REACHED 覆寫成
    # USER_REQUESTED_HELP —— 出口的原因會變成假的。
    #
    # 放在最開頭也順帶擋掉「已結束的 session 送答案還能讓 loop_iterations 繼續加」
    # 的破口，那會讓 design.md 的 Property 4（迭代有界）不成立。
    if state.exit_reason is not None or state.workflow_state == WorkflowState.COMPLETE:
        raise InvalidTransitionError(state.workflow_state)

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
    new_state = _handle_input(state, user_input, seams)

    # 自動推進：一直往前走，直到下一個需要等使用者的狀態。
    new_state = _auto_advance(new_state, state_before, seams)

    return new_state


# ---------------------------------------------------------------------------
# 輸入處理
# ---------------------------------------------------------------------------


def _handle_input(
    state: SessionState, user_input: AdvanceInput, seams: _Seams
) -> SessionState:
    """依輸入種類產生新狀態。這裡只處理「使用者做了什麼」，不處理自動推進。"""
    match user_input:
        case LifeEventTextInput():
            return _receive_life_event(state, user_input, seams.life_event_extractor)
        case EventConfirmationInput():
            return _confirm_event(state, user_input)
        case AttributeAnswersInput():
            return _record_answers(state, user_input, seams)
        case ItemDeclineInput():
            return _decline_item(state, user_input)
        case ReviewConfirmationInput():
            return _confirm_review(state, user_input)
        case ReferralChoiceInput():
            return state.model_copy(update={"referral_requested": user_input.requested})

    raise InvalidTransitionError(state.workflow_state)


def _receive_life_event(
    state: SessionState,
    user_input: LifeEventTextInput,
    extractor: LifeEventExtractorPort,
) -> SessionState:
    """接收自由文字，抽出事件代號。

    抽取器只能從 `LIFE_EVENT_CODES` 這個封閉集合裡選一個，認不出來時回 `None`。
    `None` 不是錯誤，是一個正常答案 —— 它代表「我沒把握」，而把沒把握說出來
    遠比猜一個代號安全：猜錯會把使用者帶到完全不相干的方案。

    認不出來時給重試機會（`MAX_EVENT_RETRIES`），超過上限才走人工協助出口。
    這裡用 `EVENT_NOT_RECOGNIZED` 而不是 `EVENT_RETRY_LIMIT_REACHED`，兩者語意
    不同：前者是系統聽不懂，後者是系統聽懂了但使用者說不對。

    自由文字本身沒有被保存 —— SessionState 沒有欄位放它（ADR-0007）。
    """
    extracted_event = extractor.extract(user_input.text)

    if extracted_event is None:
        retries = state.event_retry_count + 1
        update: dict[str, object] = {
            "life_event": None,
            "event_retry_count": retries,
        }
        if retries > MAX_EVENT_RETRIES:
            update["exit_reason"] = ExitReason.EVENT_NOT_RECOGNIZED
        return state.model_copy(update=update)

    # 直接覆寫 life_event，所以使用者否認後重新描述也會正確更新。
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
    state: SessionState, user_input: AttributeAnswersInput, seams: _Seams
) -> SessionState:
    """記下一組答案並推進到迴圈的下一步。

    先擋掉不在登記表上的欄位代號（Req 9）。**任何一個代號沒登記就拒絕整筆**，不做
    部分接受也不靜默丟棄：
    - 部分接受會讓使用者以為答案都收到了，其實少了一題
    - 靜默丟棄會讓 bug（前端送錯代號）在畫面上看起來像正常運作

    這道檢查是隱私閘門的核心。`AttributeValue` 的 `str` 沒有長度上限，所以只要有
    未登記的代號能寫進 `state.attributes`，任何一段自由文字都能藉著它被保存下來，
    再經 `SessionSnapshot.attributes` 原值回到前端 —— 那正是 ADR-0007 要防的事。
    """
    unknown = tuple(
        field_id for field_id in user_input.answers if not seams.registry.has(field_id)
    )
    if unknown:
        raise UnknownFieldError(unknown)

    # 代號合格之後，值本身再交給隱私閘門。Phase 2 的閘門原樣回傳；型別與選項的
    # 驗證屬於 Req 16.3（T11），換掉閘門的實作就能加上，狀態機不用改。
    accepted = seams.privacy_gate.validate_attributes(
        dict(user_input.answers), seams.registry
    )

    merged = dict(state.attributes)
    merged.update(accepted)

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
    state: SessionState, state_before_input: SessionState, seams: _Seams
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
        state = _execute_auto_step(state, seams)

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


def _execute_auto_step(state: SessionState, seams: _Seams) -> SessionState:
    """在自動推進的狀態裡執行動作。

    目前多數都是空操作（T7–T10 之後才會有內容）。
    """
    match state.workflow_state:
        case WorkflowState.RESOLVE_ENTITLEMENTS:
            return _do_resolve_entitlements(state, seams)
        case WorkflowState.RETRIEVE_RULES:
            return _do_retrieve_rules(state, seams)
        case WorkflowState.EVALUATE_ELIGIBILITY:
            return _do_evaluate_eligibility(state, seams)
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

    return any(item.status in UNSETTLED_STATUSES for item in state.items)


def _check_loop_guardrails(
    state: SessionState, state_before_iteration: SessionState
) -> SessionState:
    """在迴圈的 EVALUATE_ELIGIBILITY 結束後，檢查兩道護欄。

    護欄一：迭代上限
    如果已經繞了 MAX_LOOP_ITERATIONS 圈但還有項目未定案，設 exit_reason，並把那些
    未定案的項目降級為需人工協助。

    護欄二：必須有進展
    比較這一圈開始前和結束後的狀態。「進展」的定義是：
    - 至少一個項目的 status 改變了，或
    - attributes 的鍵的數量增加了（收到了新的答案）

    兩者都沒有就表示死循環 —— 一直問同樣的問題卻得不到新資訊。
    """
    # 護欄一：到上限了嗎
    if state.loop_iterations >= MAX_LOOP_ITERATIONS:
        has_unsettled = any(item.status in UNSETTLED_STATUSES for item in state.items)
        if has_unsettled:
            return state.model_copy(
                update={
                    "exit_reason": ExitReason.LOOP_LIMIT_REACHED,
                    "items": _downgrade_unsettled_items(state.items),
                }
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


def _downgrade_unsettled_items(
    items: tuple[CandidateItem, ...],
) -> tuple[CandidateItem, ...]:
    """把還沒定案的項目改成需人工協助。

    迭代上限觸發時流程就結束了，如果項目還留在 `PENDING`，使用者拿到的清單上會有
    永遠不會有答案的項目 —— 系統等於承認「我問到放棄，但不告訴你怎麼辦」。降級成
    需人工協助至少指出一條路可走（Req 5.2、Req 17.4）。

    已定案的狀態（ELIGIBLE / INELIGIBLE / NEEDS_HUMAN_REVIEW / DECLINED_BY_USER）
    一律不動：護欄不該推翻已經有結論的判定。
    """
    return tuple(
        item.model_copy(update={"status": ItemStatus.NEEDS_HUMAN_REVIEW})
        if item.status in UNSETTLED_STATUSES
        else item
        for item in items
    )


# ---------------------------------------------------------------------------
# 自動步驟的實作（目前多數是佔位的）
# ---------------------------------------------------------------------------


def _do_resolve_entitlements(state: SessionState, seams: _Seams) -> SessionState:
    """展開候選項目，並順手觸發來源刷新。

    項目從 `EntitlementGraphRepository` 來，不是從這個模組裡的常數。資料層交出的是
    `data_contracts.CandidateItem`（帶資料治理狀態），這裡用 `adapt_graph_candidate`
    轉成 workflow 的 `state.CandidateItem`（帶判定狀態）。

    `rejected` 與 `inactive` 的方案在這裡就被濾掉，不進入候選結果（提案第 8 節）。
    `determination` 那邊還會再濾一次 —— 兩層都做，是因為項目也可能從其他路徑進到
    state 裡（例如之後從持久化的 session 讀回來）。

    來源刷新在項目展開之後才呼叫，而且不會等待任何抓取：使用者這次拿到的答案完全
    依目前本機資料產生（提案第 9 節第 1 項）。
    """
    if state.items:
        # 已經有項目了（例如退回修改後再走一次），不重複展開。
        return state

    if state.life_event is None:
        # 還沒有事件代號就沒有東西可以展開。理論上到不了這裡（要先確認事件才會進
        # RESOLVE_ENTITLEMENTS），但不猜一組項目比較安全。
        return state

    candidates = seams.entitlement_repository.expand_from_event(
        state.life_event, state.attributes
    )
    items = visible_items(
        tuple(adapt_graph_candidate(candidate) for candidate in candidates)
    )

    # coverage 目前只用來決定要不要排 refresh。把它露給前端需要新的對外欄位，
    # 那屬於還沒開始的前端契約那一批。
    #
    # `respond_then_refresh` 保證這裡只做兩件事：讀一次目前的 committed coverage
    # 狀態、把工作排進佇列。它不等待任何抓取、附件處理或 LLM（Req 11.1、11.10），
    # 而且 worker 的延遲或失敗都不會改變這一輪的回應（Req 11.8）。
    respond_then_refresh(
        seams.source_refresh_service,
        state.life_event,
        seams.coverage_scope,
        worker=seams.refresh_worker,
    )

    if not items:
        # 認得事件代號，但 entitlement graph 裡沒有對應的項目。
        #
        # 在事件辨識還寫死的時候這條路走不到，所以一直沒有出口；現在辨識會回真實
        # 代號了，「聽懂了但沒資料」變成常見情況（例如長照目前就是這樣）。不設出口
        # 的話使用者會停在一個沒有項目、也沒有原因的空白畫面。
        #
        # 暫時沿用 `EVENT_NOT_RECOGNIZED`：從使用者的角度，「認不出你的情況」與
        # 「對應不到任何項目」的結果一樣是「這裡幫不上忙，請找人」。兩者要分開報
        # 就得新增一個 ExitReason，那是對外契約的變動，留給前端一起決定。
        return state.model_copy(update={"exit_reason": ExitReason.EVENT_NOT_RECOGNIZED})

    return state.model_copy(update={"items": items})


def _do_retrieve_rules(state: SessionState, seams: _Seams) -> SessionState:
    """檢索官方依據。

    目前是空操作：`seams.evidence_repository` 的接縫已經備好，但資料層還沒交出實作，
    而編一份「官方依據」比沒有依據更糟。
    """
    del seams  # 接縫已經備好，還沒有實作可以注入。
    return state


def _do_evaluate_eligibility(state: SessionState, seams: _Seams) -> SessionState:
    """判定資格。

    閘門與逐項判定都在 `determination` 裡。登記表用的是傳進來的同一份實例 ——
    之前這裡每次呼叫都自己 `from_json()` 讀一次磁碟，也把依賴藏起來。
    """
    return evaluate_ready_items(state, seams.registry, seams.eligibility_service)


def _do_explain_result(state: SessionState) -> SessionState:
    """產出白話說明。

    TODO(T22): 呼叫 LLM。目前是空操作。
    """
    return state
