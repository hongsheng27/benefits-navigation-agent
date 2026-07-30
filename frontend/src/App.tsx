import { useState } from "react";

import { NavigatorFlow } from "./features/navigator/NavigatorFlow";
import { HomePage } from "./pages/HomePage";

type AppView = "legacy" | "navigator";

export default function App() {
  // Temporary side-by-side toggle so both flows stay reachable while the
  // navigator prototype is built out in batches; not a final routing decision.
  const [view, setView] = useState<AppView>("legacy");

  return (
    <div className="relative">
      <button
        className="fixed right-4 top-4 z-50 rounded-full border border-slate-300 bg-white/90 px-4 py-2 text-xs font-bold text-slate-600 shadow-sm backdrop-blur transition hover:border-[#27756c] hover:text-[#27756c]"
        onClick={() => setView(view === "legacy" ? "navigator" : "legacy")}
        type="button"
      >
        {view === "legacy" ? "體驗新版對話原型" : "回到目前首頁"}
      </button>
      {view === "legacy" ? <HomePage /> : <NavigatorFlow />}
    </div>
  );
}
