import type { ReactNode } from "react";

import styles from "../alt/alt.module.css";

export type AppSection = "home" | "consult" | "tracking" | "agencies";

const NAV_ITEMS: { id: Exclude<AppSection, "home">; label: string; hint: string }[] =
  [
    { id: "consult", label: "新諮詢", hint: "開始說明新的情況" },
    { id: "tracking", label: "追蹤進度", hint: "查看進行中的案件" },
    { id: "agencies", label: "補助機關總覽", hint: "查機關與官方網站" },
  ];

type AppNavProps = {
  active: AppSection;
  onNavigate: (section: AppSection) => void;
  trailing?: ReactNode;
};

export function AppNav({ active, onNavigate, trailing }: AppNavProps) {
  const brandActive = active === "home";

  return (
    <header className="sticky top-0 z-50 border-b border-[#e0d8ca]/80 bg-[#faf8f4]/92 backdrop-blur">
      <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-6 gap-y-3 px-5 py-3.5 sm:px-8">
        <div className="flex min-w-0 items-baseline gap-3">
          <button
            type="button"
            onClick={() => onNavigate("home")}
            aria-current={brandActive ? "page" : undefined}
            aria-label="回到接住主頁"
            className={`${styles.serif} -ml-1 rounded-sm px-1.5 py-1 text-[1.2rem] leading-none tracking-[0.16em] text-[#2f4f45] underline-offset-[0.28em] transition-[color,background-color,text-decoration-color,transform] duration-150 hover:bg-[#e8efe9] hover:text-[#1f3a32] hover:underline hover:decoration-[#2f4f45]/70 hover:decoration-2 active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]`}
          >
            接住
          </button>
          <span className="hidden text-[0.75rem] text-[#8b8377] sm:inline">
            理清補助與手續
          </span>
        </div>

        <nav
          aria-label="主要功能"
          className="flex min-w-0 flex-1 flex-wrap items-center gap-1"
        >
          {NAV_ITEMS.map((item) => {
            const isActive = item.id === active;
            return (
              <button
                key={item.id}
                type="button"
                title={item.hint}
                aria-current={isActive ? "page" : undefined}
                onClick={() => onNavigate(item.id)}
                className={`rounded-sm px-3 py-2 text-[0.88rem] tracking-[0.02em] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] ${
                  isActive
                    ? "bg-[#2f4f45] font-semibold text-[#f7f4ee]"
                    : "text-[#4a453d] hover:bg-[#efe8dc] hover:text-[#2f4f45]"
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        {trailing ? <div className="shrink-0">{trailing}</div> : null}
      </div>
    </header>
  );
}
