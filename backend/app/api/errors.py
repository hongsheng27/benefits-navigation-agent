"""把錯誤轉成契約定義的形狀，並確保不外洩使用者輸入。

## 為什麼需要這一層

FastAPI 預設的錯誤回應有兩個問題：

1. 形狀不是我們的 `ErrorResponse`，而是把內容包在 `detail` 底下。
2. **Pydantic 的驗證錯誤會把不合法的值原文放進訊息裡。** 如果那個值是使用者打的
   一段話，預設的回應就等於把它送回去，而且任何記錄這個回應的地方都會留下它。

第 2 點是隱私問題，不是美觀問題。ADR-0007 規定自由文字抽取後即丟棄，
`app.observability.logging` 也刻意只記錄例外的類別名稱而不記錄訊息。這個模組把同樣
的原則套用到 HTTP 回應上：**只回代號與欄位名稱，永不回值。**
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.observability.logging import log_event
from app.orchestration.state import WorkflowState
from app.schemas.session import ErrorCode, ErrorResponse


class ApiError(Exception):
    """可以直接對外回應的錯誤。

    帶著 HTTP 狀態碼與契約形狀，所以路由只要 raise 它，不必自己組回應。
    """

    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        field_ids: tuple[str, ...] = (),
        current_state: WorkflowState | None = None,
    ) -> None:
        super().__init__(error_code.value)
        self.status_code = status_code
        self.payload = ErrorResponse(
            error_code=error_code,
            field_ids=field_ids,
            current_state=current_state,
        )


def _respond(status_code: int, payload: ErrorResponse) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(by_alias=True, mode="json"),
    )


async def _handle_api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)

    log_event(
        "request_rejected",
        error_type=exc.payload.error_code.value,
        state=exc.payload.current_state.value if exc.payload.current_state else None,
        extracted_field_names=list(exc.payload.field_ids) or None,
    )
    return _respond(exc.status_code, exc.payload)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    """把 Pydantic 的驗證錯誤縮減成欄位名稱。

    `exc.errors()` 的每一筆都有 `loc`（欄位位置）與 `input`（不合法的原值）。
    這裡只取 `loc`，`input` 與 `msg` 一律丟棄，因為它們可能包含使用者打的字。
    """
    assert isinstance(exc, RequestValidationError)

    field_ids = tuple(
        ".".join(str(part) for part in error.get("loc", ()) if part != "body")
        for error in exc.errors()
    )
    payload = ErrorResponse(
        error_code=ErrorCode.INVALID_FIELD_VALUE,
        field_ids=tuple(name for name in field_ids if name),
    )

    log_event(
        "request_validation_failed",
        error_type=ErrorCode.INVALID_FIELD_VALUE.value,
        extracted_field_names=list(payload.field_ids) or None,
    )
    return _respond(422, payload)


def install_error_handlers(app: FastAPI) -> None:
    """把上面兩個處理器掛到應用程式上。"""
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
