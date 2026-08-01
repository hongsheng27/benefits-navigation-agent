import type { BenefitItem, EligibilityQuestion } from "../../types/navigator";
import { verdict } from "./benefitEngine";
import { IneligibleItemCard } from "./IneligibleItemCard";
import { InfoNeedsRow } from "./InfoNeedsRow";

type NotEligibleAndInfoPanelProps = {
  items: BenefitItem[];
  currentItemId: string;
  answers: Record<string, string>;
  questions: EligibilityQuestion[];
  onBackToMatch: () => void;
};

export function NotEligibleAndInfoPanel({
  items,
  currentItemId,
  answers,
  questions,
  onBackToMatch,
}: NotEligibleAndInfoPanelProps) {
  const others = items.filter((item) => item.id !== currentItemId);
  const noItems = others.filter((item) => verdict(item, answers) === "no");
  const infoItems = others.filter((item) => {
    const v = verdict(item, answers);
    return v === "info" || v === "pending";
  });

  if (!noItems.length && !infoItems.length) {
    return null;
  }

  return (
    <div className="mt-8 border-t-2 border-dashed border-slate-200 pt-6">
      {noItems.length > 0 && (
        <div className="mb-6">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-base font-bold text-slate-900">
              不符合資格的項目{" "}
              <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                {noItems.length} 項
              </span>
            </h3>
            <span className="text-xs text-slate-400">
              這些你不需要準備文件，也不用為它們跑一趟
            </span>
          </div>
          <div className="space-y-3">
            {noItems.map((item) => (
              <IneligibleItemCard answers={answers} item={item} key={item.id} />
            ))}
          </div>
        </div>
      )}
      {infoItems.length > 0 && (
        <div>
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-base font-bold text-slate-900">
              尚未能判定的項目{" "}
              <span className="ml-1 rounded-full bg-[#eaf0f5] px-2 py-0.5 text-xs text-[#3f5b73]">
                {infoItems.length} 項
              </span>
            </h3>
            <span className="text-xs text-slate-400">
              補齊條件後就能確認，先不用準備文件
            </span>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white px-4">
            {infoItems.map((item) => (
              <InfoNeedsRow
                answers={answers}
                item={item}
                key={item.id}
                onBackToMatch={onBackToMatch}
                questions={questions}
              />
            ))}
          </div>
        </div>
      )}
      <div className="mt-5">
        <button
          className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-bold text-slate-600 transition hover:border-[#74a9a3] hover:text-[#27756c]"
          onClick={onBackToMatch}
          type="button"
        >
          ← 回結果列表看全部項目
        </button>
      </div>
    </div>
  );
}
