import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  addTrackedBenefitItem,
  advanceTrackedBenefitStep,
  buildFlowStepsForItem,
  listTrackedBenefitItems,
} from "./trackingStore";

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("trackingStore progress", () => {
  it("builds flow steps from item details", () => {
    const steps = buildFlowStepsForItem("unemployment_benefit");
    expect(steps.length).toBeGreaterThan(0);
    expect(steps[0]?.label).toContain("非自願離職");
  });

  it("advances the current step and persists progress", () => {
    addTrackedBenefitItem({
      itemId: "unemployment_benefit",
      name: "失業給付",
      categoryLabel: "補助／給付",
      lifeEventId: "job_loss",
      lifeEventLabel: "失業／被資遣",
      agency: "勞動部勞工保險局",
    });

    const initial = listTrackedBenefitItems()[0];
    expect(initial.completedStepCount).toBe(0);
    expect(initial.flowSteps.length).toBeGreaterThan(1);

    advanceTrackedBenefitStep("unemployment_benefit");
    const afterOne = listTrackedBenefitItems()[0];
    expect(afterOne.completedStepCount).toBe(1);
    expect(afterOne.nextAction).toContain(afterOne.flowSteps[1].label);

    for (let i = 1; i < afterOne.flowSteps.length; i += 1) {
      advanceTrackedBenefitStep("unemployment_benefit");
    }
    const done = listTrackedBenefitItems()[0];
    expect(done.completedStepCount).toBe(done.flowSteps.length);
    expect(done.nextAction).toContain("已走完");
  });

  it("backfills flow steps for legacy tracked items without progress fields", () => {
    window.localStorage.setItem(
      "jiezhu.trackedBenefitItems.v1",
      JSON.stringify([
        {
          itemId: "employment_service",
          name: "就業服務／職訓諮詢",
          categoryLabel: "諮詢／服務",
          lifeEventId: "job_loss",
          lifeEventLabel: "失業／被資遣",
          addedAt: "2026-08-01T00:00:00.000Z",
        },
      ]),
    );

    const item = listTrackedBenefitItems()[0];
    expect(item.flowSteps.length).toBeGreaterThan(0);
    expect(item.completedStepCount).toBe(0);
  });
});
