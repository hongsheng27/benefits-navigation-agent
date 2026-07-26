import type { ReactNode } from "react";

import styles from "./alt.module.css";

type ThreadStepProps = {
  /** Decorative CJK numeral shown on the rail. */
  marker: string;
  title: string;
  titleId: string;
  /** `pending` steps are visibly not yet reachable. */
  tone: "active" | "pending";
  /** Small qualifier next to the title, e.g. 尚未實作. */
  note?: string;
  children: ReactNode;
};

export function ThreadStep({
  marker,
  title,
  titleId,
  tone,
  note,
  children,
}: ThreadStepProps) {
  const isActive = tone === "active";

  return (
    <section
      aria-labelledby={titleId}
      className="relative pb-12 pl-6 last:pb-0 sm:pl-9"
    >
      <span
        aria-hidden="true"
        className={[
          "absolute top-0 left-0 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border text-[0.9rem] leading-none",
          styles.serif,
          isActive
            ? "border-[#2f4f45] bg-[#2f4f45] text-[#f7f4ee]"
            : "border-[#ddd4c5] bg-[#faf8f4] text-[#8b8377]",
        ].join(" ")}
      >
        {marker}
      </span>

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 pt-1">
        <h2
          id={titleId}
          className={[
            styles.serif,
            "text-[1.15rem] leading-[1.6] tracking-[0.01em] sm:text-[1.3rem]",
            isActive ? "text-[#171513]" : "text-[#6b6459]",
          ].join(" ")}
        >
          {title}
        </h2>
        {note ? (
          <span className="rounded-full border border-[#ddd4c5] bg-[#f2ede3] px-2.5 py-0.5 text-[0.7rem] leading-[1.8] tracking-[0.08em] text-[#6b6459]">
            {note}
          </span>
        ) : null}
      </div>

      <div className="mt-4">{children}</div>
    </section>
  );
}
