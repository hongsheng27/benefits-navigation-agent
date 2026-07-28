export type ConnectionState = "checking" | "connected" | "unavailable";

const statusContent: Record<ConnectionState, { label: string; dotClassName: string }> =
  {
    checking: {
      label: "正在確認後端",
      dotClassName: "bg-amber-400",
    },
    connected: {
      label: "後端已連線",
      dotClassName: "bg-emerald-500",
    },
    unavailable: {
      label: "後端尚未啟動",
      dotClassName: "bg-slate-400",
    },
  };

type ConnectionStatusProps = {
  state: ConnectionState;
};

export function ConnectionStatus({ state }: ConnectionStatusProps) {
  const content = statusContent[state];

  return (
    <div
      aria-live="polite"
      className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm backdrop-blur"
    >
      <span
        aria-hidden="true"
        className={`size-2 rounded-full ${content.dotClassName}`}
      />
      {content.label}
    </div>
  );
}
