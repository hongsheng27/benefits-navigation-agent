import type { BenefitItem, EligibilityQuestion } from "../../types/navigator";
import {
  estimate,
  formatMoney,
  getMissingRequirementCodes,
  isDocumentReady,
  readiness,
  verdict,
} from "./benefitEngine";
import { SELF_PROVIDED_LABEL } from "./labels";

const VERDICT_STYLE: Record<
  string,
  { label: string; badgeClass: string; borderClass: string }
> = {
  ok: {
    label: "符合",
    badgeClass: "bg-[#e6f2ef] text-[#27756c]",
    borderClass: "border-[#c3e2d9]",
  },
  info: {
    label: "需補充資訊",
    badgeClass: "bg-[#eaf0f5] text-[#3f5b73]",
    borderClass: "border-[#d7e1ea]",
  },
  pending: {
    label: "待確認",
    badgeClass: "bg-slate-100 text-slate-500",
    borderClass: "border-slate-200",
  },
};

const SOURCE_LABEL: Record<string, string> = {
  auto: "帳戶帶入",
  mydata: "MyData",
  self: SELF_PROVIDED_LABEL,
};

type BenefitCardProps = {
  item: BenefitItem;
  answers: Record<string, string>;
  mydataAuthorized: boolean;
  questions: EligibilityQuestion[];
  onOpen: (id: string) => void;
};

export function BenefitCard({
  item,
  answers,
  mydataAuthorized,
  questions,
  onOpen,
}: BenefitCardProps) {
  const v = verdict(item, answers);
  const style = VERDICT_STYLE[v] ?? VERDICT_STYLE.pending;
  const ready = readiness(item, answers, mydataAuthorized);
  const est = estimate(item, answers, mydataAuthorized);
  const missingLabels = getMissingRequirementCodes(item, answers).map(
    (code) => questions.find((q) => q.code === code)?.label ?? code,
  );
  const barClass =
    ready.percent >= 66
      ? "bg-[#0d7360]"
      : ready.percent >= 33
        ? "bg-[#96660f]"
        : "bg-slate-400";

  const docGroups = (["auto", "mydata", "self"] as const)
    .map((type) => {
      const docs = item.documents.filter((d) => d.sourceType === type);
      if (!docs.length) {
        return null;
      }
      const readyCount = docs.filter((d) =>
        isDocumentReady(d, answers, mydataAuthorized),
      ).length;
      return { type, readyCount, total: docs.length };
    })
    .filter((group): group is NonNullable<typeof group> => group !== null);

  return (
    <button
      className={`flex flex-col rounded-2xl border ${style.borderClass} bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md`}
      onClick={() => onOpen(item.id)}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-bold text-slate-900">{item.name}</h3>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${style.badgeClass}`}
        >
          {style.label}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        {item.org}
        {item.deadline ? `　·　${item.deadline}` : ""}
      </p>

      {v === "ok" ? (
        <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-600">
          {item.reason}
        </p>
      ) : (
        <p className="mt-3 rounded-lg bg-[#eaf0f5] px-3 py-2 text-sm leading-6 text-[#3f5b73]">
          還需要確認：<strong>{missingLabels.join("、") || "—"}</strong>
        </p>
      )}

      <div className="mt-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
        <p className="text-[11px] font-bold text-slate-400">預估可領</p>
        {est.ok ? (
          <p className="text-lg font-bold text-[#27756c]">
            {formatMoney(est.amount)}
            <span className="ml-1 text-xs font-medium text-slate-400">
              {est.kind === "monthly" ? "／月" : "　一次性"}
            </span>
          </p>
        ) : (
          <p className="text-sm italic text-slate-400">尚無法估算</p>
        )}
      </div>

      <div className="mt-4 border-t border-slate-100 pt-3">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>文件備妥率</span>
          <span className="font-bold text-slate-700">
            {ready.percent}%（{ready.got}/{ready.total} 項）
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full ${barClass}`}
            style={{ width: `${ready.percent}%` }}
          />
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {docGroups.map((group) => (
            <span
              className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-500"
              key={group.type}
            >
              {SOURCE_LABEL[group.type]} {group.readyCount}/{group.total}
            </span>
          ))}
        </div>
      </div>
    </button>
  );
}
