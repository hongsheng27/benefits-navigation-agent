import type { NavigatorStep } from "../../types/navigator";
import { ChatScreen } from "./ChatScreen";
import { DetailScreen } from "./DetailScreen";
import { InterpretScreen } from "./InterpretScreen";
import { MatchScreen } from "./MatchScreen";
import { NavigatorProvider, useNavigator } from "./NavigatorContext";
import { ProfileScreen } from "./ProfileScreen";
import { ToastBanner } from "./ToastBanner";

const MAIN_STEPS: { key: NavigatorStep; label: string }[] = [
  { key: "chat", label: "描述狀況" },
  { key: "interpret", label: "狀況解讀" },
  { key: "match", label: "媒合與評估" },
  { key: "detail", label: "準備清單" },
];

function TopBar() {
  const { state, openProfile, goToStep } = useNavigator();
  const currentIndex = MAIN_STEPS.findIndex((s) => s.key === state.step);

  return (
    <div className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center gap-4 px-5 py-3 sm:px-8">
        <span className="grid size-9 place-items-center rounded-xl bg-[#153f3b] text-sm font-bold text-white">
          接
        </span>
        <nav className="flex flex-1 flex-wrap items-center gap-1 text-xs">
          {MAIN_STEPS.map((step, index) => {
            const isActive = state.step === step.key;
            const isDone = currentIndex > -1 && index < currentIndex;
            return (
              <button
                className={`rounded-full px-3 py-1.5 font-bold transition ${
                  isActive
                    ? "bg-[#e6f2ef] text-[#27756c]"
                    : isDone
                      ? "text-slate-500 hover:bg-slate-50"
                      : "cursor-default text-slate-300"
                }`}
                disabled={!isDone}
                key={step.key}
                onClick={() => goToStep(step.key)}
                type="button"
              >
                {step.label}
              </button>
            );
          })}
        </nav>
        <button
          className={`rounded-full border px-4 py-2 text-xs font-bold transition ${
            state.step === "profile"
              ? "border-[#c3e2d9] bg-[#e6f2ef] text-[#27756c]"
              : "border-slate-200 text-slate-600 hover:border-[#74a9a3] hover:text-[#27756c]"
          }`}
          onClick={openProfile}
          type="button"
        >
          我的資料
        </button>
      </div>
    </div>
  );
}

function NavigatorScreens() {
  const { state } = useNavigator();
  switch (state.step) {
    case "chat":
      return <ChatScreen />;
    case "interpret":
      return <InterpretScreen />;
    case "match":
      return <MatchScreen />;
    case "detail":
      return <DetailScreen />;
    case "profile":
      return <ProfileScreen />;
    default:
      return null;
  }
}

export function NavigatorFlow() {
  return (
    <NavigatorProvider>
      <div className="min-h-screen bg-[#f7f8f2]">
        <TopBar />
        <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8">
          <NavigatorScreens />
        </div>
        <ToastBanner />
      </div>
    </NavigatorProvider>
  );
}
