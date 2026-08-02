/**
 * 管理一次諮詢的 session 狀態：建立、推進、復原、清除。
 *
 * 後端擁有權威狀態，每次呼叫都回完整快照，所以這裡不自己推算流程 —— 畫面一律看
 * `snapshot.workflowState` 決定顯示什麼。
 */

import { useCallback, useRef, useState } from "react";

import {
  SessionApiError,
  advanceSession,
  createSession,
  deleteSession,
} from "../api/sessionClient";
import type { AttributeValue, SessionSnapshot } from "../types/session";

/** 這兩種錯誤代表本機存的 id 已經沒用了，清掉重新開始。 */
function isStaleSessionError(error: unknown): boolean {
  return (
    error instanceof SessionApiError &&
    (error.errorCode === "session_not_found" || error.errorCode === "session_expired")
  );
}

export type BackendSessionStatus = "idle" | "working" | "error";

export type BackendSession = {
  snapshot: SessionSnapshot | null;
  status: BackendSessionStatus;
  /** 一般錯誤的顯示文字。event_not_recognized 不會出現在這裡。 */
  errorCode: SessionApiError["errorCode"] | null;
  /**
   * 後端看不懂使用者的描述。
   *
   * 這不是錯誤：狀態維持在 understand_event，使用者可以直接再送一次。
   */
  eventNotRecognized: boolean;
  describeEvent: (text: string) => Promise<void>;
  confirmEvent: (confirmed: boolean, eventIds?: string[]) => Promise<void>;
  answerFields: (answers: Record<string, AttributeValue>) => Promise<void>;
  answerChatTurn: (text: string) => Promise<void>;
  resetSession: () => Promise<void>;
};

export function useBackendSession(): BackendSession {
  const [snapshot, setSnapshot] = useState<SessionSnapshot | null>(null);
  const [status, setStatus] = useState<BackendSessionStatus>("idle");
  const [errorCode, setErrorCode] = useState<SessionApiError["errorCode"] | null>(null);
  const [eventNotRecognized, setEventNotRecognized] = useState(false);

  // 讓 action 讀得到最新的 session id，又不用把它放進 useCallback 的依賴。
  const sessionIdRef = useRef<string | null>(null);

  const applySnapshot = useCallback((next: SessionSnapshot) => {
    sessionIdRef.current = next.sessionId;
    setSnapshot(next);
    setStatus("idle");
    setErrorCode(null);
    setEventNotRecognized(false);
  }, []);

  const forgetSession = useCallback(() => {
    sessionIdRef.current = null;
    setSnapshot(null);
  }, []);

  /**
   * 包住一次 API 呼叫：設定進行中狀態、成功就套用快照、失敗就分類處理。
   *
   * `event_not_recognized` 在這裡被攔下來 —— 它不進 errorCode，也不清 session。
   */
  const run = useCallback(
    async (call: () => Promise<SessionSnapshot>) => {
      setStatus("working");
      setErrorCode(null);
      setEventNotRecognized(false);

      try {
        applySnapshot(await call());
      } catch (error: unknown) {
        if (error instanceof SessionApiError) {
          if (error.errorCode === "event_not_recognized") {
            setEventNotRecognized(true);
            setStatus("idle");
            return;
          }
          if (isStaleSessionError(error)) {
            forgetSession();
          }
          setErrorCode(error.errorCode);
          setStatus("error");
          return;
        }
        setErrorCode("internal_error");
        setStatus("error");
      }
    },
    [applySnapshot, forgetSession],
  );

  const describeEvent = useCallback(
    async (text: string) => {
      const advanceLifeEventText = async () => {
        let sessionId = sessionIdRef.current;
        if (!sessionId) {
          const created = await createSession();
          sessionId = created.sessionId;
          sessionIdRef.current = sessionId;
        }
        return advanceSession(sessionId, { kind: "life_event_text", text });
      };

      setStatus("working");
      setErrorCode(null);
      setEventNotRecognized(false);

      try {
        applySnapshot(await advanceLifeEventText());
      } catch (error: unknown) {
        if (error instanceof SessionApiError) {
          if (error.errorCode === "event_not_recognized") {
            setEventNotRecognized(true);
            setStatus("idle");
            return;
          }
          // 常見於：後端重啟後記憶體 session 已沒了，或本機還握著已往下走的舊諮詢，
          // 卻又在第一步送 life_event_text → invalid_transition。清掉後開新的再送一次。
          if (isStaleSessionError(error) || error.errorCode === "invalid_transition") {
            forgetSession();
            try {
              applySnapshot(await advanceLifeEventText());
              return;
            } catch (retryError: unknown) {
              if (retryError instanceof SessionApiError) {
                if (retryError.errorCode === "event_not_recognized") {
                  setEventNotRecognized(true);
                  setStatus("idle");
                  return;
                }
                setErrorCode(retryError.errorCode);
                setStatus("error");
                return;
              }
              setErrorCode("internal_error");
              setStatus("error");
              return;
            }
          }
          setErrorCode(error.errorCode);
          setStatus("error");
          return;
        }
        setErrorCode("internal_error");
        setStatus("error");
      }
    },
    [applySnapshot, forgetSession],
  );

  const confirmEvent = useCallback(
    async (confirmed: boolean, eventIds?: string[]) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId) {
        return;
      }
      await run(() =>
        advanceSession(sessionId, {
          kind: "event_confirmation",
          confirmed,
          ...(confirmed && eventIds && eventIds.length > 0 ? { eventIds } : {}),
        }),
      );
    },
    [run],
  );

  const answerFields = useCallback(
    async (answers: Record<string, AttributeValue>) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId) {
        return;
      }
      await run(() =>
        advanceSession(sessionId, { kind: "attribute_answers", answers }),
      );
    },
    [run],
  );

  const answerChatTurn = useCallback(
    async (text: string) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId) {
        return;
      }
      await run(() => advanceSession(sessionId, { kind: "attribute_chat_turn", text }));
    },
    [run],
  );

  const resetSession = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    forgetSession();
    setStatus("idle");
    setErrorCode(null);
    setEventNotRecognized(false);

    if (!sessionId) {
      return;
    }
    try {
      await deleteSession(sessionId);
    } catch {
      // 呼叫端的目的是「這次諮詢不要再出現」，本機已經清掉就算達成。
    }
  }, [forgetSession]);

  return {
    snapshot,
    status,
    errorCode,
    eventNotRecognized,
    describeEvent,
    confirmEvent,
    answerFields,
    answerChatTurn,
    resetSession,
  };
}
