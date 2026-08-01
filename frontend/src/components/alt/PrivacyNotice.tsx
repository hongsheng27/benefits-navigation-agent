type PrivacyNoticeProps = {
  /** Referenced by the textarea through aria-describedby. */
  id: string;
};

const FORBIDDEN = ["姓名", "身分證字號", "地址", "電話", "電子郵件"];

export function PrivacyNotice({ id }: PrivacyNoticeProps) {
  const headingId = `${id}-heading`;

  return (
    <aside
      aria-labelledby={headingId}
      className="mt-5 border-l-2 border-[#8a5a1a] bg-[#f6f1e6] px-4 py-4 sm:px-5"
    >
      <div className="flex items-start gap-3">
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="mt-[0.35rem] h-4 w-4 shrink-0 text-[#8a5a1a]"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M10 2.2 3.6 4.6v5c0 3.6 2.6 6.7 6.4 8.2 3.8-1.5 6.4-4.6 6.4-8.2v-5L10 2.2Z" />
          <path d="M10 8v3.4" />
          <path d="M10 13.6h.01" />
        </svg>

        <div id={id} className="min-w-0">
          <h3
            id={headingId}
            className="text-[0.95rem] leading-[1.9] font-semibold tracking-[0.02em] text-[#171513]"
          >
            請不要寫進來的資訊
          </h3>
          <p className="mt-1 text-[0.9rem] leading-[2] text-[#4a453d]">
            {`${FORBIDDEN.join("、")}都不要輸入。判斷資格靠的是關係、年齡區間、投保狀況這類條件，不需要知道你是誰。`}
          </p>
        </div>
      </div>
    </aside>
  );
}
