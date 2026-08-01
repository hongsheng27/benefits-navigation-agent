"""Session 端點：建立、推進、查詢、清除。

這個模組只做傳輸：讀 header、取出 state、呼叫推進、寫回、組出回應。流程判斷不在
這裡，而在 `app.orchestration`。

## session_id 走 header

`session_id` 是持有即通行的憑證，放在網址會被瀏覽記錄、referrer 與伺服器日誌帶走，
所以走 `X-Session-Id`。因此推進與查詢的路徑是 `/sessions/advance` 與
`/sessions/current`，而不是把 id 嵌在路徑裡。

## 目前的推進是佔位的

推進由 `app.orchestration.state_machine` 負責。回應裡的 `implementation` 會說明哪些
能力還沒實作（見 `app.api.implementation`），讓前端可以在畫面上標示。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.api.errors import ApiError
from app.api.implementation import implementation_notice
from app.application.composition import ApplicationDependencies
from app.observability.logging import log_event
from app.orchestration import state_machine
from app.orchestration.missing_fields import compute_question_groups
from app.orchestration.protocols import CoverageScope
from app.orchestration.session_store import (
    SESSION_ID_HEADER,
    InMemorySessionStore,
    SessionExpiredError,
    SessionNotFoundError,
)
from app.orchestration.state import SessionState, WorkflowState
from app.schemas.session import (
    AdvanceRequest,
    ErrorCode,
    QuestionGroupView,
    SessionSnapshot,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_store(request: Request) -> InMemorySessionStore:
    """從應用程式取出 session store。

    掛在 app 上而不是模組層級的全域變數，讓每個 `create_app()` 建出的實例互相隔離，
    測試之間不會互相污染。
    """
    return request.app.state.session_store


def get_dependencies(request: Request) -> ApplicationDependencies:
    """從應用程式取出 composition root 建立的 dependencies。

    Routes 不自行建立 adapters (Req 2.5)。
    """
    return request.app.state.dependencies


def require_session_state(
    store: Annotated[InMemorySessionStore, Depends(get_store)],
    session_id: Annotated[str | None, Header(alias=SESSION_ID_HEADER)] = None,
) -> SessionState:
    """依 header 取出 state，並把三種失敗轉成契約定義的錯誤。

    缺少 header 回 401，因為那等同於沒有出示憑證。過期回 410，讓前端能明確告知
    「進度已過期」而不是含糊的錯誤。
    """
    if not session_id:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.SESSION_NOT_FOUND,
        )

    try:
        return store.get(session_id)
    except SessionNotFoundError as error:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.SESSION_NOT_FOUND,
        ) from error
    except SessionExpiredError as error:
        raise ApiError(
            status.HTTP_410_GONE,
            ErrorCode.SESSION_EXPIRED,
        ) from error


def _snapshot(state: SessionState) -> SessionSnapshot:
    """組出對外快照，附上問題卡與「哪些能力還沒實作」的說明。

    問題卡只在需要追問欄位的狀態才計算 —— 其他狀態算出來也沒有用，前端不會顯示。
    """
    question_groups: tuple[QuestionGroupView, ...] = ()
    if state.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS:
        question_groups = compute_question_groups(
            state, state_machine.default_registry()
        )

    return SessionSnapshot.from_state(
        state,
        question_groups=question_groups,
        implementation=implementation_notice(),
    )


@router.post("", response_model=SessionSnapshot, status_code=status.HTTP_201_CREATED)
def create_session(
    store: Annotated[InMemorySessionStore, Depends(get_store)],
) -> SessionSnapshot:
    """開始一次諮詢。

    回應裡帶 `sessionId`，前端之後每次呼叫都要用 header 帶回來。這是唯一會把
    `session_id` 放在回應本體裡的端點。
    """
    state = store.create()

    log_event(
        "session_created",
        session_id=state.session_id,
        state=state.workflow_state.value,
    )
    return _snapshot(state)


@router.post("/advance", response_model=SessionSnapshot)
def advance_session(
    payload: AdvanceRequest,
    store: Annotated[InMemorySessionStore, Depends(get_store)],
    state: Annotated[SessionState, Depends(require_session_state)],
    deps: Annotated[ApplicationDependencies, Depends(get_dependencies)],
) -> SessionSnapshot:
    """送一筆輸入，推進一步。"""
    try:
        advanced = state_machine.advance(
            state,
            payload.input,
            registry=state_machine.default_registry(),
            entitlement_repository=deps.graph_repository,
            eligibility_service=deps.eligibility_service,
            evidence_repository=deps.evidence_repository,
            source_refresh_service=deps.source_refresh_service,
            coverage_scope=CoverageScope(source_ids=(), domain_tags=()),
        )
    except state_machine.InvalidTransitionError as error:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.INVALID_TRANSITION,
            current_state=state.workflow_state,
        ) from error
    except state_machine.UnknownFieldError as error:
        # 只帶欄位代號。使用者填的值不會離開後端（Req 16.5）。
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.UNKNOWN_FIELD,
            field_ids=error.field_ids,
            current_state=state.workflow_state,
        ) from error
    except state_machine.UnknownItemError as error:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.UNKNOWN_ITEM,
            current_state=state.workflow_state,
        ) from error

    saved = store.save(advanced)

    log_event(
        "session_advanced",
        session_id=saved.session_id,
        state=state.workflow_state.value,
        next_state=saved.workflow_state.value,
        life_event=saved.life_event,
        candidate_count=len(saved.items),
    )
    return _snapshot(saved)


@router.get("/current", response_model=SessionSnapshot)
def read_current_session(
    state: Annotated[SessionState, Depends(require_session_state)],
) -> SessionSnapshot:
    """查目前狀態。前端輪詢時用這個。"""
    return _snapshot(state)


@router.delete("/current", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_session(
    store: Annotated[InMemorySessionStore, Depends(get_store)],
    session_id: Annotated[str | None, Header(alias=SESSION_ID_HEADER)] = None,
) -> Response:
    """立刻清除這次諮詢。

    對應畫面上的「現在就清除」。刻意不使用 `require_session_state`：已經過期或不存在
    時仍然回成功，因為呼叫端的目的是「確保它不在了」，而那個目的已經達成。
    """
    if session_id:
        store.delete(session_id)
        log_event("session_deleted", session_id=session_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
