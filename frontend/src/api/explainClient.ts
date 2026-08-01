/**
 * 諮詢後 grounded 說明 API。
 *
 * 對應 `POST /sessions/current/explain`：把問題與參考摘錄送給後端 LLM。
 */

import type { CopilotReference, PostConsultPanelKind } from "../types/postConsult";
import type { ErrorCode, ErrorResponse, WorkflowState } from "../types/session";
import { apiBaseUrl } from "./client";
import { SessionApiError } from "./sessionClient";

const SESSION_HEADER = "X-Session-Id";

export type ExplainRequestBody = {
  question: string;
  panelKind: PostConsultPanelKind;
  references: CopilotReference[];
};

export type ExplainResponseBody = {
  answer: string;
};

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { errorCode?: unknown }).errorCode === "string"
  );
}

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
    {
      errorCode: "internal_error" satisfies ErrorCode,
      fieldIds: [],
      currentState: null as WorkflowState | null,
    },
    response.status,
  );
}

/**
 * 依參考資料請後端 LLM 回答。
 *
 * 需要有效 session。失敗時拋 `SessionApiError`（常見 `explanation_unavailable`）。
 */
export async function explainWithReferences(
  sessionId: string,
  body: ExplainRequestBody,
  signal?: AbortSignal,
): Promise<ExplainResponseBody> {
  const response = await fetch(`${apiBaseUrl}/sessions/current/explain`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      [SESSION_HEADER]: sessionId,
    },
    body: JSON.stringify({
      question: body.question,
      panelKind: body.panelKind,
      references: body.references.map((item) => ({
        title: item.title,
        body: item.body,
        sourceUrl: item.sourceUrl ?? null,
      })),
    }),
    signal,
  });

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as ExplainResponseBody;
}

/** 設為 "true" 時強制走本機 stub，不打 explain API。 */
export function usePostConsultCopilotMock(): boolean {
  return import.meta.env.VITE_USE_POST_CONSULT_COPILOT_MOCK === "true";
}
