export type BackendConnectionState = "checking" | "connected" | "unavailable";

type BackendStatusLineProps = {
  state: BackendConnectionState;
};

const ICON_PROPS = {
  "aria-hidden": true,
  viewBox: "0 0 16 16",
  className: "h-3.5 w-3.5 shrink-0",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

/**
 * Status is carried by glyph + wording as well as colour, so the three
 * states stay distinguishable without colour vision.
 */
export function BackendStatusLine({ state }: BackendStatusLineProps) {
  return (
    <p
      aria-live="polite"
      className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.8rem] leading-[1.9] tracking-[0.03em]"
    >
      {state === "checking" ? (
        <span className="flex items-center gap-2 text-[#6b6459]">
          <svg {...ICON_PROPS}>
            <circle cx="8" cy="8" r="5.4" strokeDasharray="2.6 2.6" />
          </svg>
          正在確認後端連線
        </span>
      ) : null}

      {state === "connected" ? (
        <span className="flex items-center gap-2 text-[#2f4f45]">
          <svg {...ICON_PROPS}>
            <circle cx="8" cy="8" r="5.4" />
            <path d="M5.6 8.2 7.3 9.9l3.1-3.6" />
          </svg>
          後端已連線
        </span>
      ) : null}

      {state === "unavailable" ? (
        <>
          <span className="flex items-center gap-2 text-[#8a5a1a]">
            <svg {...ICON_PROPS}>
              <circle cx="8" cy="8" r="5.4" />
              <path d="M5.4 10.6 10.6 5.4" />
            </svg>
            後端未連線
          </span>
          <span className="text-[#6b6459]">本機服務可能尚未啟動，畫面仍可瀏覽。</span>
        </>
      ) : null}
    </p>
  );
}
