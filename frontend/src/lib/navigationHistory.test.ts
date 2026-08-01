import { describe, expect, it } from "vitest";

import {
  historyStateFromLocation,
  historyStateToUrl,
  normalizeHistoryState,
  sameHistoryState,
} from "./navigationHistory";

describe("navigationHistory", () => {
  it("round-trips consult step into the URL", () => {
    const state = {
      v: 1 as const,
      section: "consult" as const,
      mode: "live" as const,
      consultStep: "questions" as const,
      demoSceneIndex: 0,
    };
    expect(historyStateToUrl(state)).toBe("/?s=consult&step=questions");
    expect(historyStateFromLocation("?s=consult&step=questions")).toEqual(
      state,
    );
  });

  it("round-trips the ready consult step", () => {
    const state = {
      v: 1 as const,
      section: "consult" as const,
      mode: "live" as const,
      consultStep: "ready" as const,
      demoSceneIndex: 0,
    };
    expect(historyStateToUrl(state)).toBe("/?s=consult&step=ready");
    expect(historyStateFromLocation("?s=consult&step=ready")).toEqual(state);
  });

  it("round-trips demo scene index", () => {
    const state = {
      v: 1 as const,
      section: "consult" as const,
      mode: "demo" as const,
      consultStep: "landing" as const,
      demoSceneIndex: 2,
    };
    expect(historyStateToUrl(state)).toBe("/?s=consult&mode=demo&scene=2");
    expect(historyStateFromLocation("?s=consult&mode=demo&scene=2")).toEqual(
      state,
    );
  });

  it("normalizes unknown history payloads", () => {
    expect(normalizeHistoryState(null).section).toBe("home");
    expect(
      sameHistoryState(
        normalizeHistoryState({ section: "tracking" }),
        normalizeHistoryState({ section: "tracking", mode: "live" }),
      ),
    ).toBe(true);
  });
});
