import type { BenefitItem } from "../../types/navigator";
import { noReason } from "./benefitEngine";

type IneligibleItemCardProps = {
  item: BenefitItem;
  answers: Record<string, string>;
  compact?: boolean;
};

export function IneligibleItemCard({
  item,
  answers,
  compact,
}: IneligibleItemCardProps) {
  const reason = noReason(item, answers);

  if (compact) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3">
        <span className="text-sm font-bold text-slate-700">{item.name}</span>
        <span className="text-xs text-slate-400">
          差在：{reason?.condition ?? "〈條件名稱〉"}
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-base font-bold text-slate-700">{item.name}</span>
        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-bold text-slate-500">
          不符合
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-400">{item.org}</p>
      <div className="mt-3 rounded-xl border border-slate-200 bg-white px-4 py-3">
        <p className="text-[11px] font-bold text-slate-400">差在這個條件</p>
        <p className="mt-1 text-sm font-bold text-slate-900">
          {reason?.condition ?? "〈條件名稱〉"}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          你的情況：
          <strong className="text-slate-700">{reason?.mine ?? "〈值〉"}</strong>
          　／　需要：
          <strong className="text-slate-700">{reason?.need ?? "〈值〉"}</strong>
        </p>
      </div>
      <p className="mt-3 text-xs text-slate-400">
        依據：<span className="italic text-slate-300">{item.basis}</span>
      </p>
      <p className="mt-2 text-xs leading-5 text-slate-400">
        情況之後有變化的話，回到上方重新回答問題，判定會即時更新。
      </p>
    </div>
  );
}
