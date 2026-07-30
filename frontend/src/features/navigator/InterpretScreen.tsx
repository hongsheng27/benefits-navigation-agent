import { useNavigator } from "./NavigatorContext";

const NEXT_STEPS = [
  {
    title: "媒合可能相關的福利與行政事項",
    body: "依你目前描述的情況，篩選出可能相關、且可能跨機關的福利與待辦事項。",
  },
  {
    title: "只追問還缺的資格資訊",
    body: "只會問判斷資格所必要、且你還沒提供過的問題，其他的不會重複問。",
  },
  {
    title: "附上官方來源與申請順序",
    body: "每一項都會標示負責機關、法規依據與建議的辦理順序，重要步驟仍會請你確認。",
  },
];

export function InterpretScreen() {
  const { state, reviseUnderstanding, goToMatch } = useNavigator();
  const primaryTag = state.detectedDims[0]?.tag ?? "你的情況";

  return (
    <div className="space-y-6">
      <section className="rounded-3xl bg-[#153f3b] px-8 py-9 text-white shadow-lg shadow-emerald-950/20">
        <p className="text-xs font-bold uppercase tracking-widest text-white/70">
          狀況解讀
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">
          我們理解到：{primaryTag}
        </h1>
        {state.detectedDims.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {state.detectedDims.map((dim) => (
              <span
                className="rounded-full bg-white/15 px-3 py-1 text-sm font-bold"
                key={dim.key}
              >
                {dim.tag}
              </span>
            ))}
          </div>
        )}
        <p className="mt-5 max-w-2xl text-[15px] leading-7 text-white/85">
          這是根據你剛才描述的內容整理出的理解，尚未送出任何個人資料，也還沒有進行
          任何資格判斷。
        </p>
      </section>

      <section className="space-y-3">
        {NEXT_STEPS.map((step, index) => (
          <div
            className="flex gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            key={step.title}
          >
            <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-[#e6f2ef] text-sm font-bold text-[#27756c]">
              {index + 1}
            </span>
            <div>
              <h3 className="text-base font-bold text-slate-900">
                {step.title}
              </h3>
              <p className="mt-1 text-sm leading-6 text-slate-500">
                {step.body}
              </p>
            </div>
          </div>
        ))}
      </section>

      <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white px-6 py-5 shadow-sm">
        <div>
          <p className="text-sm font-bold text-slate-700">
            以上的解讀正確嗎？
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            確認後才會開始判斷你可能符合哪些補助；理解有誤可以回去補充。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-600 transition hover:border-[#74a9a3] hover:text-[#27756c]"
            onClick={reviseUnderstanding}
            type="button"
          >
            回去補充說明
          </button>
          <button
            className="rounded-xl bg-[#153f3b] px-4 py-2 text-sm font-bold text-white transition hover:bg-[#1c504b]"
            onClick={goToMatch}
            type="button"
          >
            正確，開始媒合評估 →
          </button>
        </div>
      </section>
    </div>
  );
}
