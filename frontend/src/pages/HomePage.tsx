import { FormEvent, useEffect, useState } from "react";

import { getBackendHealth } from "../api/client";
import { ConnectionStatus, type ConnectionState } from "../components/ConnectionStatus";

const exampleEvents = [
  "家人剛過世，不知道接下來要辦什麼",
  "家人突然重病，需要安排返家照護",
];

export function HomePage() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("checking");
  const [lifeEvent, setLifeEvent] = useState("");
  const [submittedEvent, setSubmittedEvent] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    getBackendHealth(controller.signal)
      .then(() => setConnectionState("connected"))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setConnectionState("unavailable");
      });

    return () => controller.abort();
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const sanitizedInput = lifeEvent.trim();

    if (!sanitizedInput) {
      return;
    }

    setSubmittedEvent(sanitizedInput);
  }

  return (
    <div className="min-h-screen overflow-hidden bg-[#f7f8f2] text-slate-900">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[34rem] bg-[radial-gradient(circle_at_15%_10%,rgba(253,186,116,0.34),transparent_32%),radial-gradient(circle_at_85%_5%,rgba(94,234,212,0.22),transparent_28%)]"
      />

      <header className="relative mx-auto flex max-w-6xl items-center justify-between px-5 py-6 sm:px-8">
        <a className="flex items-center gap-3" href="/" aria-label="接住首頁">
          <span className="grid size-10 place-items-center rounded-2xl bg-[#153f3b] text-lg font-bold text-white shadow-lg shadow-emerald-950/10">
            接
          </span>
          <span>
            <span className="block text-lg font-bold tracking-[0.16em]">接住</span>
            <span className="block text-[0.65rem] tracking-[0.18em] text-slate-500">
              福利導航
            </span>
          </span>
        </a>
        <ConnectionStatus state={connectionState} />
      </header>

      <main className="relative mx-auto max-w-6xl px-5 pb-16 pt-10 sm:px-8 sm:pt-16">
        <section className="grid items-start gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
          <div className="pt-2">
            <p className="mb-5 text-sm font-semibold tracking-[0.2em] text-[#27756c]">
              從人生事件開始
            </p>
            <h1 className="max-w-xl text-5xl font-bold leading-[1.08] tracking-[-0.045em] text-slate-950 sm:text-6xl">
              不確定下一步，
              <span className="mt-2 block text-[#27756c]">我們陪你釐清。</span>
            </h1>
            <p className="mt-7 max-w-lg text-lg leading-8 text-slate-600">
              用自己的話描述正在面對的事情。我們會協助整理可能相關的福利、辦理順序與官方依據。
            </p>

            <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 text-sm text-slate-600">
              <span className="flex items-center gap-2">
                <span className="text-[#27756c]">✓</span> 只詢問必要資訊
              </span>
              <span className="flex items-center gap-2">
                <span className="text-[#27756c]">✓</span> 保留官方來源
              </span>
              <span className="flex items-center gap-2">
                <span className="text-[#27756c]">✓</span> 重要步驟由你確認
              </span>
            </div>
          </div>

          <div className="rounded-[2rem] border border-white/70 bg-white/90 p-5 shadow-[0_28px_80px_-28px_rgba(15,23,42,0.25)] backdrop-blur sm:p-8">
            <form onSubmit={handleSubmit}>
              <label
                className="block text-base font-bold text-slate-900"
                htmlFor="life-event"
              >
                最近發生了什麼事？
              </label>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                請不要輸入姓名、身分證字號、地址、電話或 email。
              </p>
              <textarea
                className="mt-5 min-h-40 w-full resize-y rounded-2xl border border-slate-200 bg-[#fbfcf8] px-5 py-4 text-base leading-7 text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-[#5da79e] focus:ring-4 focus:ring-[#5da79e]/15"
                id="life-event"
                onChange={(event) => setLifeEvent(event.target.value)}
                placeholder="例如：家人剛過世，我不知道有哪些事情需要處理……"
                value={lifeEvent}
              />

              <div className="mt-4">
                <p className="text-xs font-medium text-slate-400">也可以試試</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {exampleEvents.map((example) => (
                    <button
                      className="rounded-full border border-slate-200 px-3 py-2 text-left text-xs leading-5 text-slate-600 transition hover:border-[#74a9a3] hover:bg-[#f1f8f6]"
                      key={example}
                      onClick={() => setLifeEvent(example)}
                      type="button"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>

              <button
                className="mt-6 w-full rounded-2xl bg-[#153f3b] px-5 py-4 text-base font-bold text-white shadow-lg shadow-emerald-950/15 transition hover:-translate-y-0.5 hover:bg-[#1c504b] focus:outline-none focus:ring-4 focus:ring-[#5da79e]/30 disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!lifeEvent.trim()}
                type="submit"
              >
                開始整理下一步
              </button>
            </form>

            {submittedEvent && (
              <section
                aria-live="polite"
                className="mt-6 rounded-2xl border border-[#cde4df] bg-[#eff8f5] p-5"
              >
                <div className="flex items-start gap-3">
                  <span
                    aria-hidden="true"
                    className="grid size-8 shrink-0 place-items-center rounded-full bg-[#27756c] text-sm text-white"
                  >
                    ✓
                  </span>
                  <div>
                    <h2 className="font-bold text-[#153f3b]">我們先從這裡接住你</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                      已收到：「{submittedEvent}」
                    </p>
                    <p className="mt-3 text-xs leading-5 text-slate-500">
                      這是前端骨架的示意結果，尚未送出資料或進行福利資格判斷。
                    </p>
                  </div>
                </div>
              </section>
            )}
          </div>
        </section>
      </main>

      <footer className="relative border-t border-slate-200/70 px-5 py-6 text-center text-xs leading-5 text-slate-500">
        接住提供福利導航，不取代政府承辦人或專業人員的正式判斷。
      </footer>
    </div>
  );
}
