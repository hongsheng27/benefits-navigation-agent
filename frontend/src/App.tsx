import { useState } from "react";

import { HomePageAlt, type IntakeMode } from "./pages/HomePageAlt";

const TOGGLE_LABEL: Record<IntakeMode, string> = {
  live: "正式諮詢",
  demo: "示範完整流程",
};

export default function App() {
  const [mode, setMode] = useState<IntakeMode>("live");
  const otherMode: IntakeMode = mode === "live" ? "demo" : "live";

  return (
    <div className="relative">
      <button
        className="fixed right-4 top-4 z-[60] rounded-sm border border-[#c9c0b0] bg-[#f7f4ee]/95 px-3.5 py-2 text-[0.75rem] font-semibold tracking-[0.02em] text-[#4a453d] shadow-sm backdrop-blur transition hover:border-[#2f4f45] hover:text-[#2f4f45]"
        onClick={() => setMode(otherMode)}
        type="button"
      >
        {mode === "live" ? `切換到${TOGGLE_LABEL.demo}` : `回到${TOGGLE_LABEL.live}`}
      </button>
      <HomePageAlt
        mode={mode}
        onExitDemo={() => setMode("live")}
      />
    </div>
  );
}
