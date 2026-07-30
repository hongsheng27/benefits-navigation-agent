import { formatMoney, type BenefitTotals } from "./benefitEngine";

type MoneySummaryProps = {
  variant: "compact" | "full";
  totals: BenefitTotals;
};

export function MoneySummary({ variant, totals }: MoneySummaryProps) {
  const firstYearLabel = totals.hasAnyEstimate
    ? formatMoney(totals.firstYear)
    : "—";

  if (variant === "compact") {
    return (
      <div className="mb-5 flex flex-wrap items-center gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm">
        <span className="text-xs font-bold text-slate-400">預估可領金額</span>
        <span className="text-2xl font-bold tracking-tight text-[#27756c]">
          {firstYearLabel}
          <span className="ml-1 text-xs font-medium text-slate-400">
            ／首年（估算中）
          </span>
        </span>
        <span className="ml-auto text-xs text-slate-400">
          已納入 {totals.estimatedCount} 項 · 回答問題後會更精確
        </span>
      </div>
    );
  }

  return (
    <div className="mb-5 rounded-2xl border border-[#c3e2d9] bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold text-slate-400">
            若下列補助全數核准，預估可領
          </p>
          <p className="mt-1 text-3xl font-bold tracking-tight text-[#27756c]">
            {firstYearLabel}
            <span className="ml-1 text-sm font-medium text-slate-400">
              ／首年合計
            </span>
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-bold ${
            totals.hasAnyEstimate
              ? totals.allExact
                ? "bg-[#e6f2ef] text-[#27756c]"
                : "bg-[#eaf0f5] text-[#3f5b73]"
              : "bg-slate-100 text-slate-400"
          }`}
        >
          {totals.hasAnyEstimate
            ? `${totals.allExact ? "已用 MyData 實際資料估算" : "以平均值估算，授權 MyData 更準"} · ${totals.estimatedCount} 項`
            : "回答問題後開始估算"}
        </span>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs text-slate-400">每月可領</p>
          <p className="mt-1 text-xl font-bold text-slate-900">
            {totals.monthly ? formatMoney(totals.monthly) : "—"}
          </p>
          <p className="text-[11px] text-slate-400">持續性給付合計</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs text-slate-400">一次性給付</p>
          <p className="mt-1 text-xl font-bold text-slate-900">
            {totals.once ? formatMoney(totals.once) : "—"}
          </p>
          <p className="text-[11px] text-slate-400">單次核發合計</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs text-slate-400">首年合計</p>
          <p className="mt-1 text-xl font-bold text-[#27756c]">
            {firstYearLabel}
          </p>
          <p className="text-[11px] text-slate-400">
            月領 × 給付月數 ＋ 一次性
          </p>
        </div>
      </div>
      <p className="mt-4 rounded-xl bg-[#fbf1de] px-4 py-3 text-xs leading-6 text-[#96660f]">
        ⚠️ 以上為<strong>示範估算值</strong>
        ，依你目前填答的條件推算，非核定金額。實際給付以主管機關審查結果為準；
        正式版金額須以官方公告數字計算。
      </p>
    </div>
  );
}
