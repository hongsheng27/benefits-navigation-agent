import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as trackingClient from "../api/trackingClient";
import { addTrackedBenefitItem } from "../lib/trackingStore";
import { MOCK_TRACKED_CASES } from "../mocks/trackedCases";
import { TrackedCasesPage } from "./TrackedCasesPage";

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("TrackedCasesPage", () => {
  it("shows a clear empty state with a path back to consult", async () => {
    vi.spyOn(trackingClient, "listTrackedCases").mockResolvedValue({
      cases: [],
      isMock: true,
    });
    const onStartConsult = vi.fn();

    render(<TrackedCasesPage onStartConsult={onStartConsult} />);

    expect(await screen.findByText("還沒有可追蹤的案件")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "開始新諮詢" }));
    expect(onStartConsult).toHaveBeenCalledTimes(1);
  });

  it("hides mock fixture cases and only lists items the user tracked", async () => {
    vi.spyOn(trackingClient, "listTrackedCases").mockResolvedValue({
      cases: MOCK_TRACKED_CASES,
      isMock: true,
    });
    addTrackedBenefitItem({
      itemId: "funeral_benefit",
      name: "喪葬給付",
      categoryLabel: "現金給付",
      lifeEventId: "spouse_death",
      lifeEventLabel: "配偶過世",
      agency: "勞保局",
      nextAction: "準備死亡證明與申請書",
    });

    render(<TrackedCasesPage />);

    expect(await screen.findByText("喪葬給付")).toBeInTheDocument();
    expect(screen.getByText("追蹤中")).toBeInTheDocument();
    expect(screen.queryByText("還沒有可追蹤的案件")).not.toBeInTheDocument();
    // Fixture case titles must not appear while isMock.
    for (const fixture of MOCK_TRACKED_CASES) {
      expect(screen.queryByText(fixture.title)).not.toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: "取消追蹤" }));
    expect(await screen.findByText("還沒有可追蹤的案件")).toBeInTheDocument();
    expect(screen.queryByText("喪葬給付")).not.toBeInTheDocument();
  });
});
