import { useState } from "react";

import { NavigatorFlow } from "./features/navigator/NavigatorFlow";
import { HomePageAlt } from "./pages/HomePageAlt";

type AppView = "navigator" | "backend";

const VIEW_LABELS: Record<AppView, string> = {
  navigator: "完整流程原型（假資料）",
  backend: "後端串接版",
};

export default function App() {
  // Temporary toggle: the navigator prototype covers all five screens on mock
  // data, while the backend-connected page exercises the real session API but
  // can only show what the backend currently returns. Both stay reachable
  // until the team decides which one ships.
  const [view, setView] = useState<AppView>("navigator");
  const otherView: AppView = view === "navigator" ? "backend" : "navigator";

  return (
    <div className="relative">
      <button
        className="fixed right-4 top-4 z-[60] rounded-full border border-slate-300 bg-white/90 px-4 py-2 text-xs font-bold text-slate-600 shadow-sm backdrop-blur transition hover:border-[#27756c] hover:text-[#27756c]"
        onClick={() => setView(otherView)}
        type="button"
      >
        切換到{VIEW_LABELS[otherView]}
      </button>
      {view === "navigator" ? <NavigatorFlow /> : <HomePageAlt />}
    </div>
  );
}
