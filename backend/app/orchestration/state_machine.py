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

- 已驗證官方依據：`RETRIEVE_RULES` 會附上候選資料供查閱，但 Case 2 尚無人工核對 citation
- 白話說明：`EXPLAIN_RESULT` 仍是空操作，還沒接模型

## 流程規則是真的，資料來源還不全是

轉換規則、守門條件、自動推進與護欄都已經是最終行為。**事件辨識已經接上真實模型**
（`_receive_life_event` → `llm/tasks/resolve_life_event.py`）。正式本機 runtime 已由
composition root 注入 SQLite repositories；測試仍可明確注入 fixture。

資料來源不由這個模組自己去拿，而是透過 `protocols.py` 的接縫注入（見 `advance()`
的具名參數）。SQLite／PostgreSQL 與離線 fixture 都使用同一組 contracts。
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.llm.fake import FakeLanguageModel
from app.llm.port import LanguageModelPort
from app.llm.tasks.collect_attributes import (
    AttributeCollectionError,
    collect_attributes_from_reply,
)
from app.llm.tasks.resolve_life_event import resolve_life_event
from app.observability.logging import log_event
from app.orchestration.data_contracts import CandidateItem as GraphCandidateItem
from app.orchestration.determination import evaluate_ready_items, visible_items
from app.orchestration.field_registry import FieldRegistry
from app.orchestration.life_event_selection import (
    MAX_CONFIRMED_LIFE_EVENTS,
    normalize_life_event_ids,
    pick_extra_candidate_life_events,
)
from app.orchestration.life_events import LifeEventRegistry, default_life_events
from app.orchestration.local_worker import RefreshWorkerPort
from app.orchestration.missing_fields import compute_question_groups
from app.orchestration.protocols import (
    CoverageScope,
    EligibilityService,
    EntitlementGraphRepository,
    EvidenceRepository,
    FixtureEligibilityService,
    FixtureEntitlementGraphRepository,
    LocalSourceRefreshService,
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
from app.orchestration.state import (
    Citation as WorkflowCitation,
)
from app.privacy.attribute_gate import RegistryBackedPrivacyGate
from app.schemas.session import (
    AdvanceInput,
    AttributeAnswersInput,
    AttributeChatTurnInput,
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
        AttributeChatTurnInput,
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

from typing import TypeAlias

Guard: TypeAlias = "Callable[[SessionState], bool]"

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
    language_model: LanguageModelPort
    life_events: LifeEventRegistry
    coverage_scope: CoverageScope
    # 官方資料 repository。候選資料只供結果頁查閱；verified 路徑才可支撐資格判定。
    evidence_repository: EvidenceRepository | None = None
    # 背景 refresh 的交付邊界。`None` 代表只排入 service 的佇列、不再往下交付。
    # 這個接縫只暴露 `submit()`，所以 request path 在型別上就沒有辦法同步執行
    # crawl 或 LLM（Req 11.10）。
    refresh_worker: RefreshWorkerPort | None = None


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
    language_model: LanguageModelPort | None = None,
    life_events: LifeEventRegistry | None = None,
    evidence_repository: EvidenceRepository | None = None,
    refresh_worker: RefreshWorkerPort | None = None,
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
            privacy_gate if privacy_gate is not None else RegistryBackedPrivacyGate()
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
        # 預設是不連網路的實作，而且它**沒有登記任何答案**，所以預設情況下事件辨識會
        # 失敗並回 `event_not_recognized`。那是誠實的預設值：沒有注入真實模型時，
        # 系統確實看不懂使用者在說什麼，不該假裝看懂（ADR-0015）。
        language_model=(
            language_model if language_model is not None else FakeLanguageModel()
        ),
        life_events=(life_events if life_events is not None else default_life_events()),
        # Scope 必須由 composition/caller 明確提供；預設空 scope 不猜所有來源都相關。
        coverage_scope=(
            coverage_scope
            if coverage_scope is not None
            else CoverageScope(source_ids=(), domain_tags=())
        ),
        evidence_repository=evidence_repository,
        refresh_worker=refresh_worker,
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
            return _receive_life_event(state, user_input, seams)
        case EventConfirmationInput():
            return _confirm_event(state, user_input, seams)
        case AttributeAnswersInput():
            return _record_answers(state, user_input, seams)
        case AttributeChatTurnInput():
            return _collect_from_chat(state, user_input, seams)
        case ItemDeclineInput():
            return _decline_item(state, user_input)
        case ReviewConfirmationInput():
            return _confirm_review(state, user_input)
        case ReferralChoiceInput():
            return state.model_copy(update={"referral_requested": user_input.requested})

    raise InvalidTransitionError(state.workflow_state)


def _apply_life_events(
    state: SessionState,
    event_ids: tuple[str, ...],
    *,
    extras: tuple[str, ...] | None = None,
    registry: LifeEventRegistry | None = None,
) -> SessionState:
    """同步 life_events / life_event / 候補選項。"""
    normalized = event_ids
    if registry is not None:
        normalized = normalize_life_event_ids(event_ids, registry)
    extra = extras
    if extra is None and registry is not None:
        extra = pick_extra_candidate_life_events(normalized, registry)
    if extra is None:
        extra = ()
    return state.model_copy(
        update={
            "life_events": normalized,
            "life_event": normalized[0] if normalized else None,
            "extra_candidate_life_events": extra,
        }
    )


def _receive_life_event(
    state: SessionState, user_input: LifeEventTextInput, seams: _Seams
) -> SessionState:
    """接收自由文字，交給模型對應成一組事件代號（最多五個）。

    **這段文字只存在於這個函式的呼叫範圍內。** 回傳只有代號，原文不會進 state。
    """
    event_ids = resolve_life_event(
        user_input.text,
        model=seams.language_model,
        registry=seams.life_events,
    )
    return _apply_life_events(state, event_ids, registry=seams.life_events)


def _confirm_event(
    state: SessionState,
    user_input: EventConfirmationInput,
    seams: _Seams,
) -> SessionState:
    """使用者確認或否認事件（可多選，最多五個）。"""
    if not state.life_events and state.life_event is None:
        raise InvalidTransitionError(state.workflow_state)

    if user_input.confirmed:
        allowed = set(state.life_events) | set(state.extra_candidate_life_events)
        if state.life_event:
            allowed.add(state.life_event)
        if user_input.event_ids is not None:
            chosen = normalize_life_event_ids(user_input.event_ids, seams.life_events)
        elif state.life_events:
            chosen = state.life_events
        elif state.life_event:
            chosen = (state.life_event,)
        else:
            chosen = ()
        # 只能勾建議或候補裡的代號；過濾未知項。
        chosen = tuple(event_id for event_id in chosen if event_id in allowed)[
            :MAX_CONFIRMED_LIFE_EVENTS
        ]
        if not chosen:
            raise InvalidTransitionError(state.workflow_state)
        updated = _apply_life_events(
            state, chosen, extras=(), registry=seams.life_events
        )
        return updated.model_copy(
            update={
                "workflow_state": WorkflowState.RESOLVE_ENTITLEMENTS,
                "extra_candidate_life_events": (),
            }
        )

    retries = state.event_retry_count + 1
    cleared = _apply_life_events(state, (), extras=())
    if retries > MAX_EVENT_RETRIES:
        return cleared.model_copy(
            update={
                "event_retry_count": retries,
                "exit_reason": ExitReason.EVENT_RETRY_LIMIT_REACHED,
            }
        )
    return cleared.model_copy(update={"event_retry_count": retries})


def _resolved_event_ids(state: SessionState) -> tuple[str, ...]:
    """取得權威事件清單；舊測試與 fixture 只有單數欄位時仍可運作。"""
    if state.life_events:
        return state.life_events
    if state.life_event is not None:
        return (state.life_event,)
    return ()


def _expand_all_events(
    state: SessionState, seams: _Seams
) -> Iterator[GraphCandidateItem]:
    """依事件順序展開候選項目，並以 item ID 去重。"""
    seen_item_ids: set[str] = set()
    for event_id in _resolved_event_ids(state):
        for candidate in seams.entitlement_repository.expand_from_event(
            event_id, state.attributes
        ):
            if candidate.item_id in seen_item_ids:
                continue
            seen_item_ids.add(candidate.item_id)
            yield candidate


def _refresh_entitlements(state: SessionState, seams: _Seams) -> SessionState:
    """用最新結構化答案重查相關項目，同時保留仍存在項目的判定狀態。

    這是 repository 的一般能力：目前 fixture 用它篩 Case 2、配偶過世 fixture 用它加入
    地方項目；未來 SQLite adapter 也會在同一個呼叫點依 graph conditions 回傳結果。
    """
    event_ids = _resolved_event_ids(state)
    if not event_ids:
        return state
    if "occupational_injury" not in event_ids:
        return _merge_local_entitlements(state)

    existing_by_id = {item.item_id: item for item in state.items}
    refreshed: list[CandidateItem] = []
    for candidate in _expand_all_events(state, seams):
        incoming = adapt_graph_candidate(candidate)
        existing = existing_by_id.get(incoming.item_id)
        if existing is None:
            refreshed.append(incoming)
            continue
        refreshed.append(
            existing.model_copy(
                update={
                    "display_name": incoming.display_name,
                    "summary": incoming.summary,
                    "program_status": incoming.program_status,
                    "missing_field_ids": incoming.missing_field_ids,
                }
            )
        )

    visible = visible_items(tuple(refreshed))
    if visible == state.items:
        return state
    return state.model_copy(update={"items": visible})


def _merge_local_entitlements(state: SessionState) -> SessionState:
    """既有配偶過世流程只依所在地增刪地方項目，避免重展開全國項目。"""
    from app.orchestration.jurisdiction_items import (
        LOCAL_ITEM_IDS,
        local_items_for_attributes,
    )

    kept = tuple(item for item in state.items if item.item_id not in LOCAL_ITEM_IDS)
    life_event_ids = state.life_events or (
        (state.life_event,) if state.life_event else ()
    )
    local = local_items_for_attributes(state.attributes, life_event_ids=life_event_ids)
    if not local:
        if len(kept) == len(state.items):
            return state
        return state.model_copy(update={"items": kept})

    existing_ids = {item.item_id for item in kept}
    extras = tuple(
        adapt_graph_candidate(candidate)
        for candidate in local
        if candidate.item_id not in existing_ids
    )
    merged = kept + extras
    if merged == state.items:
        return state
    return state.model_copy(update={"items": merged})


# 對話蒐集用正面問句（purpose 只說明「為什麼問」，不能當題目）。
# 文案與 frontend `FIELD_LABELS` 對齊；查不到時退回簡短正面句，絕不貼 purpose。
_COLLECTOR_FIELD_QUESTIONS: dict[str, str] = {
    "applicant_jurisdiction": "你主要在哪個縣市辦理或居住？",
    "caregiver_relationship": "你和需要照顧的人是什麼關係？",
    "disability_cause": "造成失能的原因是？",
    "occupational_injury_recognition": "是否已經取得職業災害認定？",
    "care_recipient_insurance_type": "被照顧者目前是哪一種投保身分？",
    "disability_assessment_status": "目前是否已辦理身心障礙鑑定？",
    "current_care_arrangement": "目前主要由誰照顧？",
    "caregiver_employment_impact": "照顧目前如何影響你的工作？",
    "involuntary_job_loss": "這次是否屬於非自願離職？",
    "deceased_insurance_type": "過世者生前的投保身分是？",
    "has_dependent_children": "家中是否有未成年子女？",
    "applicant_age_band": "你目前的年齡大約在哪個範圍？",
}


def _default_collector_question(state: SessionState, seams: _Seams) -> str | None:
    """依第一個缺漏欄位產生下一句正面問句。"""
    groups = compute_question_groups(state, seams.registry)
    if not groups or not groups[0].questions:
        return None
    field_id = groups[0].questions[0].field_id
    if seams.registry.get(field_id) is None:
        return None
    return _COLLECTOR_FIELD_QUESTIONS.get(field_id, f"可以補充「{field_id}」嗎？")


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

    # 代號合格之後，值本身再交給隱私閘門。預設的 `RegistryBackedPrivacyGate` 會依登記表
    # 驗證型別與選項，不合法就拒絕整筆（T11 已完成）。這裡的呼叫方式當初就設計成
    # 可替換，所以加上驗證時狀態機一行都沒改。
    accepted = seams.privacy_gate.validate_attributes(
        dict(user_input.answers), seams.registry
    )

    merged = dict(state.attributes)
    merged.update(accepted)

    updated = state.model_copy(
        update={
            "attributes": merged,
            "workflow_state": WorkflowState.RETRIEVE_RULES,
            "loop_iterations": state.loop_iterations + 1,
            "collector_question": None,
        }
    )
    return _refresh_entitlements(updated, seams)


def _collect_from_chat(
    state: SessionState, user_input: AttributeChatTurnInput, seams: _Seams
) -> SessionState:
    """對話式補欄位：抽取 attributes，未齊則留在 COLLECT_MISSING_FIELDS。"""
    groups = compute_question_groups(state, seams.registry)
    missing_fields = []
    for group in groups:
        for question in group.questions:
            field = seams.registry.get(question.field_id)
            if field is not None:
                missing_fields.append(field)

    try:
        collected = collect_attributes_from_reply(
            user_input.text,
            fields=missing_fields,
            model=seams.language_model,
            registry=seams.registry,
        )
    except AttributeCollectionError:
        # 抽不到就留在原狀態，換一句預設追問；不中斷整次諮詢。
        log_event(
            "attribute_chat_fallback",
            tool="collect_attributes",
            outcome="unavailable",
        )
        return state.model_copy(
            update={
                "collector_question": _default_collector_question(state, seams)
                or "可以再說清楚一點嗎？或改用下方選項作答。",
                "loop_iterations": state.loop_iterations + 1,
            }
        )

    if collected.attributes:
        accepted = seams.privacy_gate.validate_attributes(
            dict(collected.attributes), seams.registry
        )
    else:
        accepted = {}

    merged = dict(state.attributes)
    merged.update(accepted)
    updated = state.model_copy(update={"attributes": merged})
    updated = _refresh_entitlements(updated, seams)

    still_missing = compute_question_groups(updated, seams.registry)
    if still_missing:
        next_q = collected.next_question or _default_collector_question(updated, seams)
        return updated.model_copy(
            update={
                "workflow_state": WorkflowState.COLLECT_MISSING_FIELDS,
                "collector_question": next_q,
                "loop_iterations": state.loop_iterations + 1,
            }
        )

    return updated.model_copy(
        update={
            "workflow_state": WorkflowState.RETRIEVE_RULES,
            "collector_question": None,
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
                # 護欄中止流程。`guard` 記的是哪一道護欄，不是任何使用者資料。
                log_event(
                    "loop_guardrail_triggered",
                    session_id=state.session_id,
                    state=state.workflow_state.value,
                    guard=state.exit_reason.value,
                    agent_iterations=state.loop_iterations,
                )
                break

        # 走到下一步。
        next_ws = _resolve_next_state(state)
        if next_ws is None:
            break

        # 每一個內部轉換都記一筆。ADR-0007 把除錯手段限縮到只剩狀態轉換 ——
        # 使用者的文字不留、值不進紀錄檔，所以這些狀態名稱幾乎是唯一能查的東西。
        log_event(
            "state_transitioned",
            session_id=state.session_id,
            state=state.workflow_state.value,
            next_state=next_ws.value,
            transition="auto_advance",
        )
        state = state.model_copy(update={"workflow_state": next_ws})

    if (
        state.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS
        and not state.collector_question
    ):
        state = state.model_copy(
            update={"collector_question": _default_collector_question(state, seams)}
        )

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
            log_event(
                "loop_iteration_started",
                session_id=state.session_id,
                state=current.value,
                next_state=WorkflowState.COLLECT_MISSING_FIELDS.value,
                transition="loop_back",
                agent_iterations=state.loop_iterations,
            )
            return WorkflowState.COLLECT_MISSING_FIELDS

    # 照正常路徑。
    next_ws = NOMINAL_PATH.get(current)
    if next_ws is None:
        return None

    # 檢查守門條件。
    guard = ENTRY_GUARDS.get(next_ws)
    if guard is not None and not guard(state):
        # 記下「哪個狀態因為哪道守門條件被跳過」。沒有這一筆，之後看到流程直接從
        # explain_result 跳到 complete 時無法分辨是守門條件生效還是轉換表寫錯。
        log_event(
            "state_skipped",
            session_id=state.session_id,
            state=current.value,
            next_state=next_ws.value,
            guard=f"entry_guard:{next_ws.value}",
        )
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

    event_ids = state.life_events or (
        (state.life_event,) if state.life_event is not None else ()
    )
    if not event_ids:
        return state

    # 複合情境：各事件展開後聯集去重；同一項目合併 source_life_events。
    merged_by_id: dict[str, CandidateItem] = {}
    for event_id in event_ids:
        candidates = seams.entitlement_repository.expand_from_event(
            event_id, state.attributes
        )
        for candidate in candidates:
            adapted = adapt_graph_candidate(candidate).model_copy(
                update={"source_life_events": (event_id,)}
            )
            existing = merged_by_id.get(adapted.item_id)
            if existing is None:
                merged_by_id[adapted.item_id] = adapted
                continue
            sources = tuple(dict.fromkeys([*existing.source_life_events, event_id]))
            merged_by_id[adapted.item_id] = existing.model_copy(
                update={"source_life_events": sources}
            )
    items = visible_items(tuple(merged_by_id.values()))

    # coverage 目前只用來決定要不要排 refresh。把它露給前端需要新的對外欄位，
    # 那屬於還沒開始的前端契約那一批。
    #
    # `respond_then_refresh` 保證這裡只做兩件事：讀一次目前的 committed coverage
    # 狀態、把工作排進佇列。它不等待任何抓取、附件處理或 LLM（Req 11.1、11.10），
    # 而且 worker 的延遲或失敗都不會改變這一輪的回應（Req 11.8）。
    # 複數事件各自查 committed coverage 並排 refresh；不等待抓取或 LLM。
    for event_id in event_ids:
        respond_then_refresh(
            seams.source_refresh_service,
            event_id,
            seams.coverage_scope,
            worker=seams.refresh_worker,
        )

    if not items:
        return state

    return state.model_copy(update={"items": items})


def _do_retrieve_rules(state: SessionState, seams: _Seams) -> SessionState:
    """Attach database-backed official material for result-page display.

    Candidate citations are deliberately kept out of ``evaluate_ready_items``;
    only the verified citation path may support an eligibility determination.
    """
    repository = seams.evidence_repository
    if repository is None:
        return state

    items: list[CandidateItem] = []
    for item in state.items:
        try:
            citations = repository.get_candidate_citations(item.item_id)
        except Exception as exc:  # noqa: BLE001 - isolate one unavailable source
            log_event(
                "candidate_evidence_lookup_failed",
                benefit_id=item.item_id,
                error_type=type(exc).__name__,
            )
            items.append(item)
            continue

        mapped = tuple(
            WorkflowCitation(
                document_id=citation.document_id,
                title=citation.title,
                publisher_name=citation.publisher,
                published_at=(
                    citation.published_at.isoformat()
                    if citation.published_at is not None
                    else None
                ),
                url=citation.url,
                excerpt=citation.excerpt,
            )
            for citation in citations
        )
        items.append(item.model_copy(update={"citations": mapped}))

    return state.model_copy(update={"items": tuple(items)})


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
