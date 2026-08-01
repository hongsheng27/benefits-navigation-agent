import type { Ref } from "react";

import styles from "./alt.module.css";

type SkeletonResultProps = {
  /** Length of what the user typed, used only to confirm it stayed local. */
  characterCount: number;
  onReset: () => void;
  ref?: Ref<HTMLDivElement>;
};

const PLACEHOLDER_ROWS = [
  { marker: "步驟一", label: "行政程序占位" },
  { marker: "步驟二", label: "行政程序占位" },
  { marker: "步驟三", label: "行政程序占位" },
] as const;

const PLACEHOLDER_FIELDS = [
  { term: "承辦機關", value: "待實作" },
  { term: "資格判定", value: "尚未評估" },
  { term: "官方依據", value: "尚未串接" },
] as const;

export function SkeletonResult({ characterCount, onReset, ref }: SkeletonResultProps) {
  return (
    <div
      ref={ref}
      tabIndex={-1}
      className="border border-[#d8cfc0] bg-[#fdfbf7] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
    >
      <div className="border-b border-[#e6dfd2] px-4 py-5 sm:px-6">
        <p className="text-[0.72rem] leading-[1.8] font-semibold tracking-[0.16em] text-[#8a5a1a]">
          前端骨架
        </p>
        <h3
          className={`${styles.serif} mt-2 text-[1.1rem] leading-[1.7] text-[#171513] sm:text-[1.2rem]`}
        >
          這裡沒有判定結果，只有版面示意
        </h3>
        <p className="mt-3 text-[0.9rem] leading-[2] text-[#4a453d]">
          {`目前只有前端畫面。你剛才寫的 ${characterCount} 個字沒有離開這個瀏覽器分頁，沒有送出到任何伺服器，系統也沒有做任何資格判斷。下方是未來結果的排版示意，全部是占位文字，不是給你的建議。`}
        </p>
      </div>

      <ol className="divide-y divide-[#eee7db]">
        {PLACEHOLDER_ROWS.map((row) => (
          <li key={row.marker} className="px-4 py-4 sm:px-6">
            <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-[0.72rem] leading-[1.9] tracking-[0.12em] text-[#6b6459]">
                {row.marker}
              </span>
              <span className="rounded-xs border border-dashed border-[#cfc5b4] px-2 py-0.5 text-[0.85rem] leading-[1.9] text-[#7a7266]">
                {row.label}
              </span>
            </p>
            <dl className="mt-2.5 flex flex-col gap-1 text-[0.82rem] leading-[1.9] text-[#6b6459] sm:flex-row sm:flex-wrap sm:gap-x-6">
              {PLACEHOLDER_FIELDS.map((field) => (
                <div key={field.term} className="flex gap-2">
                  <dt>{field.term}</dt>
                  <dd className="text-[#7a7266]">{field.value}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ol>

      <div className="border-t border-[#e6dfd2] px-4 py-4 sm:px-6">
        <button
          type="button"
          onClick={onReset}
          className="rounded-sm border border-[#c9c0b0] bg-[#f7f4ee] px-4 py-2.5 text-[0.9rem] leading-[1.8] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
        >
          重新描述
        </button>
      </div>
    </div>
  );
}
