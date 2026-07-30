import type { BenefitItem, EligibilityQuestion } from "../../types/navigator";
import { getMissingRequirementCodes } from "./benefitEngine";

type InfoNeedsRowProps = {
  item: BenefitItem;
  answers: Record<string, string>;
  questions: EligibilityQuestion[];
  onBackToMatch: () => void;
};

export function InfoNeedsRow({
  item,
  answers,
  questions,
  onBackToMatch,
}: InfoNeedsRowProps) {
  const missingLabels = getMissingRequirementCodes(item, answers).map(
    (code) => questions.find((q) => q.code === code)?.label ?? code,
  );

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-1 py-3 last:border-none">
      <div className="min-w-[140px] flex-1">
        <p className="text-sm font-bold text-slate-800">{item.name}</p>
        <p className="text-xs text-slate-400">{item.org}</p>
      </div>
      <span className="rounded-lg bg-[#eaf0f5] px-3 py-1 text-xs text-[#3f5b73]">
        還缺：{missingLabels.join("、") || "—"}
      </span>
      <button
        className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-500 transition hover:border-[#74a9a3] hover:text-[#27756c]"
        onClick={onBackToMatch}
        type="button"
      >
        回去補答
      </button>
    </div>
  );
}
