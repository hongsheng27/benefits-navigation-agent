/**
 * Session API 的呼叫程式，對應 `docs/front_back_doc/README.md` 第三節的四個端點。
 *
 * 契約定義在 `../types/session.ts`（與後端 `app/schemas/session.py` 手動同步）。
 */

import type {
  AdvanceInput,
  AdvanceRequest,
  ErrorCode,
  ErrorResponse,
  SessionSnapshot,
  WorkflowState,
} from "../types/session";
import { apiBaseUrl } from "./client";

/** session id 走 header，不走網址：它是持有即通行的憑證。 */
const SESSION_HEADER = "X-Session-Id";

/**
 * 後端回傳的錯誤。錯誤本體就是 ErrorResponse，沒有包在 `detail` 底下。
 *
 * `fieldIds` 只帶代號，永遠不會包含使用者輸入的值。
 */
export class SessionApiError extends Error {
  readonly errorCode: ErrorCode;
  readonly fieldIds: string[];
  readonly currentState: WorkflowState | null;
  readonly httpStatus: number;

  constructor(body: ErrorResponse, httpStatus: number) {
    super(`Session API error: ${body.errorCode}`);
    this.name = "SessionApiError";
    this.errorCode = body.errorCode;
    this.fieldIds = body.fieldIds;
    this.currentState = body.currentState;
    this.httpStatus = httpStatus;
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { errorCode?: unknown }).errorCode === "string"
  );
}

/**
 * 把非 2xx 的回應轉成 SessionApiError。
 *
 * 後端保證所有錯誤共用 ErrorResponse 形狀，但網路層或代理伺服器仍可能回別的東西，
 * 那種情況一律當成 internal_error，讓呼叫端只需要處理一種例外型別。
 */
async function toApiError(response: Response): Promise<SessionApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (isErrorResponse(body)) {
    return new SessionApiError(body, response.status);
  }

  return new SessionApiError(
    { errorCode: "internal_error", fieldIds: [], currentState: null },
    response.status,
  );
}

async function readSnapshot(response: Response): Promise<SessionSnapshot> {
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as SessionSnapshot;
}

/** 建立一次諮詢。這是唯一不需要帶 session header 的呼叫。 */
export async function createSession(signal?: AbortSignal): Promise<SessionSnapshot> {
  const response = await fetch(`${apiBaseUrl}/sessions`, {
    method: "POST",
    headers: { Accept: "application/json" },
    signal,
  });
  return readSnapshot(response);
}

/** 送一筆輸入，推進一步。回傳的是完整快照，不是只有變動的部分。 */
export async function advanceSession(
  sessionId: string,
  input: AdvanceInput,
  signal?: AbortSignal,
): Promise<SessionSnapshot> {
  const requestBody: AdvanceRequest = { input };
  const response = await fetch(`${apiBaseUrl}/sessions/advance`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      [SESSION_HEADER]: sessionId,
    },
    body: JSON.stringify(requestBody),
    signal,
  });
  return readSnapshot(response);
}

/** 查目前狀態，供需要取得最新快照的呼叫端使用。 */
export async function getCurrentSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionSnapshot> {
  const response = await fetch(`${apiBaseUrl}/sessions/current`, {
    headers: {
      Accept: "application/json",
      [SESSION_HEADER]: sessionId,
    },
    signal,
  });
  return readSnapshot(response);
}

/**
 * 立刻清除這次諮詢。
 *
 * session 已經不存在或已過期時後端仍然回 204，因為呼叫端的目的是「確保它不在了」。
 */
export async function deleteSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/sessions/current`, {
    method: "DELETE",
    headers: { [SESSION_HEADER]: sessionId },
    signal,
  });

  if (!response.ok) {
    throw await toApiError(response);
  }
}
