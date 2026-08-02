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
        itemIds={["funeral_benefit", "death_registration"]}
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

  it("does not show funeral content for job loss results", () => {
    render(
      <RelatedProvisionsPanel
        lifeEventId="job_loss"
        itemIds={["unemployment_benefit", "employment_service"]}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("就業保險失業給付申請說明")).toBeInTheDocument();
    expect(screen.queryByText(/環保葬/)).not.toBeInTheDocument();
    expect(screen.queryByText(/喪葬/)).not.toBeInTheDocument();
    expect(screen.queryByText(/聯合奠祭/)).not.toBeInTheDocument();
  });

  it("does not show funeral content for occupational injury results", () => {
    render(
      <RelatedProvisionsPanel
        lifeEventId="occupational_injury"
        itemIds={[
          "occupational_injury_recognition_follow_up",
          "long_term_care_assessment",
          "caregiver_support_services",
        ]}
        onClose={() => {}}
      />,
    );

    expect(screen.getByText("職業災害認定與職災保險說明")).toBeInTheDocument();
    expect(screen.getAllByText(/1966/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/環保葬/)).not.toBeInTheDocument();
    expect(screen.queryByText(/聯合奠祭/)).not.toBeInTheDocument();
  });

  it("uses backend citations and disables fixture fallback in live mode", () => {
    render(
      <RelatedProvisionsPanel
        lifeEventId="occupational_injury"
        itemIds={["database-program-id"]}
        citations={[
          {
            documentId: "database-document-id",
            title: "資料庫回傳的職災資料",
            publisherName: "測試主管機關",
            publishedAt: null,
            url: "https://example.gov.tw/database-document",
            excerpt: "這段摘錄由 backend session snapshot 回傳。",
            effectiveAt: null,
            retrievedAt: null,
          },
        ]}
        allowFixtureFallback={false}
        onClose={() => {}}
      />,
    );

    expect(screen.getAllByText("資料庫回傳的職災資料").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("這段摘錄由 backend session snapshot 回傳。").length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("職業災害認定與職災保險說明")).not.toBeInTheDocument();
  });

  it("shows empty guide state instead of spouse-death fallback", () => {
    render(<ApplicationGuidePanel lifeEventId="serious_illness" onClose={() => {}} />);

    expect(screen.getAllByText(/還沒有對應的申請步驟說明/).length).toBeGreaterThan(0);
    expect(screen.queryByText("辦理死亡登記")).not.toBeInTheDocument();
    expect(screen.queryByText(/配偶過世/)).not.toBeInTheDocument();
  });

  it("shows job-loss application guide without funeral steps", () => {
    render(<ApplicationGuidePanel lifeEventId="job_loss" onClose={() => {}} />);

    expect(screen.getByText("失業／被資遣後常見申請與辦理順序")).toBeInTheDocument();
    expect(screen.getByText("向公立就業服務機構辦理求職登記")).toBeInTheDocument();
    expect(screen.queryByText("辦理死亡登記")).not.toBeInTheDocument();
  });
});
