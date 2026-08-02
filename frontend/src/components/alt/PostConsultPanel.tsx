import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { askCopilot } from "../../lib/askCopilot";
import { buildCopilotGreeting } from "../../lib/copilotStub";
import type {
  CopilotContext,
  CopilotMessage,
  PostConsultPanelKind,
} from "../../types/postConsult";
import { CopilotReplyBody } from "./CopilotReplyBody";

type PostConsultPanelProps = {
  kind: PostConsultPanelKind;
  title: string;
  subtitle: string;
  context: CopilotContext;
  /** 正式諮詢的 session；缺省時會嘗試建一個臨時 session 再問 LLM。 */
  sessionId?: string | null;
  onClose: () => void;
  children: ReactNode;
};

export function PostConsultPanel({
  kind,
  title,
  subtitle,
  context,
  sessionId = null,
  onClose,
  children,
}: PostConsultPanelProps) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const [messages, setMessages] = useState<CopilotMessage[]>(() => [
    buildCopilotGreeting(context),
  ]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) {
      return;
    }
    setBusy(true);
    setDraft("");
    setMessages((current) => [
      ...current,
      {
        id: `pending_user_${Date.now()}`,
        role: "user",
        content: text,
      },
    ]);
    try {
      const result = await askCopilot(text, context, {
        sessionId,
        ensureSession: !sessionId,
      });
      setMessages((current) => {
        const withoutPending = current.filter(
          (message) => !message.id.startsWith("pending_user_"),
        );
        return [
          ...withoutPending,
          result.userMessage,
          result.assistantMessage,
        ];
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-stretch justify-center bg-[#171513]/45 p-3 sm:p-6"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) {
          onClose();
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[min(920px,100%)] w-full max-w-6xl flex-col overflow-hidden rounded-sm border border-[#d9d0c0] bg-[#faf8f4] shadow-[0_20px_60px_rgba(23,21,19,0.28)]"
      >
        <header className="flex items-start justify-between gap-4 border-b border-[#e0d8ca] px-4 py-4 sm:px-6">
          <div className="min-w-0">
            <p className="text-[0.75rem] tracking-[0.08em] text-[#8b8377]">
              諮詢後說明
            </p>
            <h2
              id={titleId}
              className="mt-1 text-[1.2rem] font-semibold tracking-[0.02em] text-[#2f4f45]"
            >
              {title}
            </h2>
            <p className="mt-1.5 text-[0.88rem] leading-[1.7] text-[#5c564e]">
              {subtitle}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            disabled={busy}
            className="shrink-0 rounded-sm border border-[#c9c0b0] px-3 py-2 text-[0.88rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:opacity-60"
          >
            關閉
          </button>
        </header>

        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)]">
          <section
            aria-label="主要內容"
            className="min-h-0 overflow-y-auto border-b border-[#e0d8ca] px-4 py-5 sm:px-6 lg:border-b-0 lg:border-r"
          >
            {children}
          </section>

          <section
            aria-label="說明助理"
            className="flex min-h-[18rem] flex-col bg-[#f4f0e8] lg:min-h-0"
          >
            <div className="border-b border-[#e0d8ca] px-4 py-3 sm:px-5">
              <h3 className="text-[0.95rem] font-semibold text-[#2f4f45]">
                Copilot 說明
              </h3>
              <p className="mt-1 text-[0.78rem] leading-[1.7] text-[#6b6459]">
                提問時會把左側參考資料一併送進說明服務。不做資格判定、不代為送件。
              </p>
            </div>

            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4 sm:px-5">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`max-w-[95%] rounded-sm px-3 py-2.5 text-[0.86rem] leading-[1.75] ${
                    message.role === "assistant"
                      ? "self-start bg-[#faf8f4] text-[#3a352e] ring-1 ring-[#e0d8ca]"
                      : "self-end bg-[#2f4f45] text-[#f7f4ee]"
                  }`}
                >
                  <CopilotReplyBody
                    content={message.content}
                    tone={message.role === "assistant" ? "assistant" : "user"}
                  />
                </div>
              ))}
              {busy ? (
                <p className="text-[0.82rem] text-[#8b8377]">正在依參考資料整理回答…</p>
              ) : null}
            </div>

            <form
              onSubmit={(event) => {
                void handleAsk(event);
              }}
              className="border-t border-[#e0d8ca] px-4 py-3 sm:px-5"
            >
              <label className="sr-only" htmlFor={`copilot-input-${kind}`}>
                向說明助理提問
              </label>
              <div className="flex gap-2">
                <input
                  id={`copilot-input-${kind}`}
                  type="text"
                  value={draft}
                  disabled={busy}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="例如：期限多久？要帶哪些文件？"
                  className="min-w-0 flex-1 rounded-sm border border-[#c9c0b0] bg-[#faf8f4] px-3 py-2.5 text-[0.88rem] text-[#171513] outline-none focus:border-[#2f4f45] disabled:opacity-60"
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="shrink-0 rounded-sm bg-[#2f4f45] px-4 py-2.5 text-[0.88rem] font-semibold text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
                >
                  {busy ? "送出中" : "送出"}
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
