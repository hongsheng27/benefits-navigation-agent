/**
 * 把 App 區塊與諮詢步驟寫進瀏覽器 history，讓上一頁／下一頁可在站內移動。
 */

export type HistorySection = "home" | "consult" | "tracking" | "agencies";
export type HistoryIntakeMode = "live" | "demo";
export type HistoryConsultStep =
  | "landing"
  | "describe"
  | "confirm"
  | "questions"
  | "ready"
  | "result";

export type AppHistoryState = {
  v: 1;
  section: HistorySection;
  mode: HistoryIntakeMode;
  /** live 諮詢步驟；demo 時可忽略 */
  consultStep: HistoryConsultStep;
  /** demo 場景索引 */
  demoSceneIndex: number;
};

export const DEFAULT_HISTORY_STATE: AppHistoryState = {
  v: 1,
  section: "home",
  mode: "live",
  consultStep: "landing",
  demoSceneIndex: 0,
};

function isConsultStep(value: unknown): value is HistoryConsultStep {
  return (
    value === "landing" ||
    value === "describe" ||
    value === "confirm" ||
    value === "questions" ||
    value === "ready" ||
    value === "result"
  );
}

function isSection(value: unknown): value is HistorySection {
  return (
    value === "home" ||
    value === "consult" ||
    value === "tracking" ||
    value === "agencies"
  );
}

export function normalizeHistoryState(
  raw: unknown,
): AppHistoryState {
  if (!raw || typeof raw !== "object") {
    return { ...DEFAULT_HISTORY_STATE };
  }
  const record = raw as Record<string, unknown>;
  return {
    v: 1,
    section: isSection(record.section) ? record.section : "home",
    mode: record.mode === "demo" ? "demo" : "live",
    consultStep: isConsultStep(record.consultStep)
      ? record.consultStep
      : "landing",
    demoSceneIndex:
      typeof record.demoSceneIndex === "number" && record.demoSceneIndex >= 0
        ? Math.floor(record.demoSceneIndex)
        : 0,
  };
}

/** 把狀態編成可分享／可重新整理的 query（仍相容 SPA）。 */
export function historyStateToUrl(state: AppHistoryState): string {
  const params = new URLSearchParams();
  if (state.section !== "home") {
    params.set("s", state.section);
  }
  if (state.section === "consult") {
    if (state.mode === "demo") {
      params.set("mode", "demo");
      if (state.demoSceneIndex > 0) {
        params.set("scene", String(state.demoSceneIndex));
      }
    } else if (state.consultStep !== "landing") {
      params.set("step", state.consultStep);
    }
  }
  const query = params.toString();
  return query ? `/?${query}` : "/";
}

export function historyStateFromLocation(
  search: string = typeof window !== "undefined" ? window.location.search : "",
): AppHistoryState {
  const params = new URLSearchParams(search.startsWith("?") ? search : `?${search}`);
  const sectionRaw = params.get("s") ?? "home";
  const section = isSection(sectionRaw) ? sectionRaw : "home";
  const mode = params.get("mode") === "demo" ? "demo" : "live";
  const stepRaw = params.get("step");
  const consultStep = isConsultStep(stepRaw) ? stepRaw : "landing";
  const sceneRaw = params.get("scene");
  const demoSceneIndex = sceneRaw && /^\d+$/.test(sceneRaw) ? Number(sceneRaw) : 0;
  return {
    v: 1,
    section,
    mode: section === "consult" ? mode : "live",
    consultStep: section === "consult" ? consultStep : "landing",
    demoSceneIndex: section === "consult" && mode === "demo" ? demoSceneIndex : 0,
  };
}

export function sameHistoryState(
  a: AppHistoryState,
  b: AppHistoryState,
): boolean {
  return (
    a.section === b.section &&
    a.mode === b.mode &&
    a.consultStep === b.consultStep &&
    a.demoSceneIndex === b.demoSceneIndex
  );
}

export function replaceAppHistory(state: AppHistoryState): void {
  if (typeof window === "undefined") {
    return;
  }
  window.history.replaceState(state, "", historyStateToUrl(state));
}

export function pushAppHistory(state: AppHistoryState): void {
  if (typeof window === "undefined") {
    return;
  }
  const current = normalizeHistoryState(window.history.state);
  if (sameHistoryState(current, state)) {
    return;
  }
  window.history.pushState(state, "", historyStateToUrl(state));
}
