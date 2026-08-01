import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApplicationGuidePanel } from "./ApplicationGuidePanel";
import { RelatedProvisionsPanel } from "./RelatedProvisionsPanel";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("post-consult panels", () => {
  it("shows related provision excerpts and answers via grounded LLM", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/sessions/current/explain") && init?.method === "POST") {
          const body = JSON.parse(String(init.body)) as {
            question: string;
            references: { title: string }[];
          };
          expect(body.question).toBe("金額大概多少？");
          expect(body.references.length).toBeGreaterThan(0);
          expect(body.references.some((item) => item.title.includes("環保葬"))).toBe(
            true,
          );
          return {
            ok: true,
            status: 200,
            json: async () => ({
              answer: "依參考資料，金額常見為 1 萬或 2 萬元。",
            }),
          };
        }
        return {
          ok: false,
          status: 404,
          json: async () => ({ errorCode: "session_not_found" }),
        };
      }),
    );

    render(
      <RelatedProvisionsPanel
        lifeEventId="spouse_death"
        sessionId="sess_test"
        onClose={() => {}}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "相關法條與官方依據" }),
    ).toBeInTheDocument();
    expect(screen.getByText("新北市環保葬鼓勵金")).toBeInTheDocument();
    expect(screen.getAllByText("白話摘要").length).toBeGreaterThan(0);

    const input = screen.getByLabelText("向說明助理提問");
    fireEvent.change(input, { target: { value: "金額大概多少？" } });
    fireEvent.submit(input.closest("form")!);

    expect(
      await screen.findByText("依參考資料，金額常見為 1 萬或 2 萬元。"),
    ).toBeInTheDocument();
    expect(screen.getByText("金額大概多少？")).toBeInTheDocument();
  });

  it("shows application steps and keeps eligibility out of stub fallback", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 503,
        json: async () => ({
          errorCode: "explanation_unavailable",
          fieldIds: [],
          currentState: null,
        }),
      })),
    );

    render(
      <ApplicationGuidePanel
        lifeEventId="spouse_death"
        sessionId="sess_test"
        onClose={() => {}}
      />,
    );

    expect(screen.getByRole("heading", { name: "申請解說" })).toBeInTheDocument();
    expect(screen.getByText("辦理死亡登記")).toBeInTheDocument();

    const input = screen.getByLabelText("向說明助理提問");
    fireEvent.change(input, { target: { value: "我符不符合資格？" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() => {
      expect(screen.getByText(/不能代替資格判定/)).toBeInTheDocument();
    });
    expect(screen.getByText("我符不符合資格？")).toBeInTheDocument();
  });
});
