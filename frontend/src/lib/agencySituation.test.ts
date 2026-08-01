import { describe, expect, it } from "vitest";

import { MOCK_AGENCIES } from "../mocks/agencies";
import { MOCK_TRACKED_CASES } from "../mocks/trackedCases";
import {
  focusFromCase,
  focusFromOpenCases,
  rankAgenciesForSituation,
} from "./agencySituation";

describe("agencySituation", () => {
  it("ranks agencies that match an open spouse-death case", () => {
    const focus = focusFromCase(MOCK_TRACKED_CASES[0]);
    const ranked = rankAgenciesForSituation(MOCK_AGENCIES, focus);

    expect(ranked.map((item) => item.agency.agencyId)).toEqual(
      expect.arrayContaining(["bli", "nhi", "household"]),
    );
    expect(ranked[0].reasons.length).toBeGreaterThan(0);
  });

  it("builds focus from open cases and skips completed ones", () => {
    const focus = focusFromOpenCases(MOCK_TRACKED_CASES);
    expect(focus).not.toBeNull();
    expect(focus?.lifeEventLabel).toContain("配偶過世");
    expect(focus?.lifeEventLabel).toContain("失業");
    expect(focus?.lifeEventLabel).not.toContain("長照需求");
  });
});
