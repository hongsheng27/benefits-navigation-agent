import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ApplicationGuidePanel } from "./ApplicationGuidePanel";
import { RelatedProvisionsPanel } from "./RelatedProvisionsPanel";

afterEach(() => {
  cleanup();
});

describe("post-consult panels", () => {
  it("shows related provision excerpts and answers a Copilot question", () => {
    render(
      <RelatedProvisionsPanel lifeEventId="spouse_death" onClose={() => {}} />,
    );

    expect(
      screen.getByRole("heading", { name: "相關法條與官方依據" }),
    ).toBeInTheDocument();
    expect(screen.getByText("新北市環保葬鼓勵金")).toBeInTheDocument();
    expect(screen.getAllByText("白話摘要").length).toBeGreaterThan(0);
    expect(screen.getAllByText("候選摘錄").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("向說明助理提問"), {
      target: { value: "金額大概多少？" },
    });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));

    expect(screen.getByText("金額大概多少？")).toBeInTheDocument();
    expect(
      screen.getByText(/金額也依來源與骨灰／骨骸而不同/),
    ).toBeInTheDocument();
  });

  it("shows application steps and keeps eligibility out of Copilot answers", () => {
    render(
      <ApplicationGuidePanel lifeEventId="spouse_death" onClose={() => {}} />,
    );

    expect(screen.getByRole("heading", { name: "申請解說" })).toBeInTheDocument();
    expect(screen.getByText("辦理死亡登記")).toBeInTheDocument();
    expect(screen.getAllByText("這一步常要準備").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("向說明助理提問"), {
      target: { value: "我符不符合資格？" },
    });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));

    expect(screen.getByText("我符不符合資格？")).toBeInTheDocument();
    expect(screen.getByText(/不能代替資格判定/)).toBeInTheDocument();
  });
});
