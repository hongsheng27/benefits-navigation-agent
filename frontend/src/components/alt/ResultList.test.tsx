import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { SessionSnapshot } from "../../types/session";
import { ResultList } from "./ResultList";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function snapshotWithItems(): SessionSnapshot {
  return {
    sessionId: "sess_result_cards",
    workflowState: "explain_result",
    stepIndex: 6,
    stepTotal: 8,
    lifeEvent: "job_loss",
    lifeEvents: ["job_loss"],
    extraCandidateLifeEvents: [],
    attributes: {},
    items: [
      {
        itemId: "unemployment_benefit",
        kind: "benefit",
        status: "needs_human_review",
        missingFieldIds: [],
        decisiveConditions: [],
        citations: [],
        amountMin: null,
        amountMax: null,
        amountPeriod: null,
        amountCurrency: null,
        explanation: "示範說明：失業給付可能與你的情況有關。",
        sourceLifeEvents: ["job_loss"],
      },
      {
        itemId: "employment_service",
        kind: "benefit",
        status: "needs_human_review",
        missingFieldIds: [],
        decisiveConditions: [],
        citations: [],
        amountMin: null,
        amountMax: null,
        amountPeriod: null,
        amountCurrency: null,
        explanation: "示範說明：就業服務可協助求職登記。",
        sourceLifeEvents: ["job_loss"],
      },
    ],
    questionGroups: [],
    exitReason: null,
    referralRequested: false,
    isProcessing: false,
    collectorQuestion: null,
    createdAt: "2026-08-02T00:00:00Z",
    expiresAt: "2026-08-02T02:00:00Z",
    implementation: {
      isMock: true,
      pending: [],
      placeholderNotice: "示範資料",
    },
  };
}

describe("ResultList cards", () => {
  it("renders separated cards with a per-item law dialog", () => {
    render(<ResultList snapshot={snapshotWithItems()} enableItemTracking={false} />);

    expect(screen.getByText("失業給付")).toBeInTheDocument();
    expect(screen.getByText("就業服務／職訓諮詢")).toBeInTheDocument();

    const cards = screen.getAllByRole("listitem").filter((node) =>
      node.className.includes("border"),
    );
    expect(cards.length).toBeGreaterThanOrEqual(2);

    const lawButtons = screen.getAllByRole("button", {
      name: /就業保險法／失業給付請領須知/,
    });
    expect(lawButtons.length).toBeGreaterThan(0);
    fireEvent.click(lawButtons[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("就業保險失業給付申請說明")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "關閉" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
