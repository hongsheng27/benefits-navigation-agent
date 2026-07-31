import { useEffect, useRef, useState, type FormEvent } from "react";

import { EXAMPLE_EVENTS } from "../../mocks/navigatorChatData";
import { IntroHero } from "./IntroHero";
import { useNavigator } from "./NavigatorContext";

export function ChatScreen() {
  const { state, sendMessage, confirmUnderstanding, reviseUnderstanding } =
    useNavigator();
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [state.messages.length, state.isTyping]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.trim() || state.isTyping) {
      return;
    }
    sendMessage(draft);
    setDraft("");
  }

  function handleChipClick(chip: string) {
    if (state.isTyping) {
      return;
    }
    sendMessage(chip);
  }

  const awaitingConfirmation = state.summaryShown && !state.confirmed;
  const lastMessage = state.messages[state.messages.length - 1];
  const quickChips =
    !state.isTyping && lastMessage?.role === "ai" ? lastMessage.chips : undefined;
  const showIntro = state.messages.length <= 1 && !state.confirmed;

  return (
    <div>
      {showIntro && <IntroHero />}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-3 border-b border-slate-200 px-6 py-4">
            <span className="grid size-9 place-items-center rounded-full bg-[#153f3b] text-sm font-bold text-white">
              接
            </span>
            <div>
              <p className="text-sm font-bold text-slate-900">接住小幫手</p>
              <p className="text-xs text-slate-400">用你自己的話描述目前的狀況</p>
            </div>
          </div>

          <div
            aria-live="polite"
            className="flex min-h-[22rem] flex-col gap-4 px-6 py-6"
          >
            {state.messages.map((message) => (
              <div
                key={message.id}
                className={`flex max-w-[88%] gap-3 ${
                  message.role === "user"
                    ? "self-end flex-row-reverse"
                    : "self-start"
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`mt-0.5 grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold ${
                    message.role === "user"
                      ? "bg-slate-100 text-slate-600"
                      : "bg-[#e6f2ef] text-[#27756c]"
                  }`}
                >
                  {message.role === "user" ? "你" : "接"}
                </span>
                <p
                  className={`rounded-2xl px-4 py-3 text-[15px] leading-7 ${
                    message.role === "user"
                      ? "rounded-tr-md bg-[#153f3b] text-white"
                      : "rounded-tl-md bg-slate-100 text-slate-800"
                  }`}
                >
                  {message.text}
                </p>
              </div>
            ))}

            {state.isTyping && (
              <div className="flex items-center gap-1 self-start rounded-2xl rounded-tl-md bg-slate-100 px-4 py-3">
                <span className="size-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.2s]" />
                <span className="size-1.5 animate-bounce rounded-full bg-slate-400" />
                <span className="size-1.5 animate-bounce rounded-full bg-slate-400 [animation-delay:0.2s]" />
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {quickChips && quickChips.length > 0 && (
            <div className="flex flex-wrap gap-2 px-6 pb-4">
              {quickChips.map((chip) => (
                <button
                  className="rounded-full border border-slate-200 px-3 py-2 text-xs text-slate-600 transition hover:border-[#74a9a3] hover:bg-[#f1f8f6]"
                  key={chip}
                  onClick={() => handleChipClick(chip)}
                  type="button"
                >
                  {chip}
                </button>
              ))}
            </div>
          )}

          {awaitingConfirmation && (
            <div className="mx-6 mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-[#153f3b] px-6 py-5">
              <p className="text-sm font-bold text-white">
                這樣理解你的狀況對嗎？
              </p>
              <div className="flex gap-2">
                <button
                  className="rounded-xl bg-white px-4 py-2 text-sm font-bold text-[#153f3b] transition hover:bg-[#f0faf7]"
                  onClick={confirmUnderstanding}
                  type="button"
                >
                  對，這樣理解沒錯
                </button>
                <button
                  className="rounded-xl border border-white/50 px-4 py-2 text-sm font-bold text-white transition hover:bg-white/10"
                  onClick={reviseUnderstanding}
                  type="button"
                >
                  不太對，我想再說明
                </button>
              </div>
            </div>
          )}

          <p className="border-t border-slate-200 bg-slate-50/60 px-6 pt-3 text-xs text-slate-400">
            請不要輸入姓名、身分證字號、地址、電話或 email。
          </p>
          <form
            className="flex items-end gap-3 bg-slate-50/60 px-6 pb-4 pt-2"
            onSubmit={handleSubmit}
          >
            <textarea
              aria-label="輸入訊息"
              className="min-h-12 flex-1 resize-none rounded-xl border border-slate-200 bg-white px-4 py-3 text-[15px] leading-6 outline-none focus:border-[#5da79e] focus:ring-4 focus:ring-[#5da79e]/15"
              disabled={state.isTyping}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="請描述目前的狀況……"
              value={draft}
            />
            <button
              aria-label="送出"
              className="grid size-12 shrink-0 place-items-center rounded-xl bg-[#153f3b] text-white transition hover:bg-[#1c504b] disabled:cursor-not-allowed disabled:opacity-40"
              disabled={state.isTyping || !draft.trim()}
              type="submit"
            >
              ➤
            </button>
          </form>
        </div>

        <aside className="sticky top-6 h-fit rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400">
            理解摘要
          </h2>
          {state.detectedDims.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {state.detectedDims.map((dim) => (
                <span
                  className="rounded-full bg-[#eeecf8] px-3 py-1 text-xs font-bold text-[#54479c]"
                  key={dim.key}
                >
                  {dim.tag}
                </span>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm italic text-slate-400">
              還沒有偵測到明確的情境標籤
            </p>
          )}
          <p className="mt-4 border-t border-slate-200 pt-3 text-xs leading-6 text-slate-400">
            也可以試試：
          </p>
          <div className="mt-2 flex flex-col gap-2">
            {EXAMPLE_EVENTS.map((example) => (
              <button
                className="rounded-xl border border-slate-200 px-3 py-2 text-left text-xs leading-5 text-slate-600 transition hover:border-[#74a9a3] hover:bg-[#f1f8f6] disabled:cursor-not-allowed disabled:opacity-40"
                disabled={state.isTyping}
                key={example}
                onClick={() => handleChipClick(example)}
                type="button"
              >
                {example}
              </button>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
