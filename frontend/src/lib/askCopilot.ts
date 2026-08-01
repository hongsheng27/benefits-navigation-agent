/**
 * 諮詢後 Copilot：優先打後端 grounded LLM，失敗或無 session 時退回 stub。
 */

import {
  explainWithReferences,
  usePostConsultCopilotMock,
} from "../api/explainClient";
import { createSession } from "../api/sessionClient";
import type { CopilotContext, CopilotMessage } from "../types/postConsult";
import { createUserMessage, replyToCopilot } from "./copilotStub";

function messageId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export type AskCopilotResult = {
  userMessage: CopilotMessage;
  assistantMessage: CopilotMessage;
  usedLlm: boolean;
};

/**
 * 送出一則問題。有 session（或可建立）且未強制 mock 時呼叫 LLM，
 * 並把 context.references 一併帶上。
 */
export async function askCopilot(
  question: string,
  context: CopilotContext,
  options?: {
    sessionId?: string | null;
    ensureSession?: boolean;
  },
): Promise<AskCopilotResult> {
  const userMessage = createUserMessage(question);
  const trimmed = question.trim();

  if (!trimmed) {
    return {
      userMessage,
      assistantMessage: {
        id: messageId("reply"),
        role: "assistant",
        content: "請先輸入你想了解的問題，例如期限、文件或窗口。",
      },
      usedLlm: false,
    };
  }

  if (usePostConsultCopilotMock() || context.references.length === 0) {
    return {
      userMessage,
      assistantMessage: replyToCopilot(trimmed, context),
      usedLlm: false,
    };
  }

  let sessionId = options?.sessionId ?? null;
  if (!sessionId && options?.ensureSession) {
    try {
      const snapshot = await createSession();
      sessionId = snapshot.sessionId;
    } catch {
      sessionId = null;
    }
  }

  if (!sessionId) {
    return {
      userMessage,
      assistantMessage: replyToCopilot(trimmed, context),
      usedLlm: false,
    };
  }

  try {
    const response = await explainWithReferences(sessionId, {
      question: trimmed,
      panelKind: context.kind,
      references: context.references,
    });
    return {
      userMessage,
      assistantMessage: {
        id: messageId("reply"),
        role: "assistant",
        content: response.answer,
      },
      usedLlm: true,
    };
  } catch {
    const fallback = replyToCopilot(trimmed, context);
    return {
      userMessage,
      assistantMessage: {
        ...fallback,
        content: `${fallback.content}\n\n（目前無法連上說明服務，以上是本機備援說明。）`,
      },
      usedLlm: false,
    };
  }
}
