import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NavigatorFlow } from "./NavigatorFlow";

function sendViaTextarea(text: string) {
  fireEvent.change(screen.getByLabelText("輸入訊息"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByLabelText("送出"));
}

describe("NavigatorFlow", () => {
  it("shows the intro hero before the conversation starts, then hides it", async () => {
    render(<NavigatorFlow />);

    expect(
      screen.getByRole("heading", {
        name: "突然發生大事時，先不用自己查完所有規定",
      }),
    ).toBeInTheDocument();

    sendViaTextarea("家人剛過世，不知道接下來要辦什麼");

    expect(await screen.findByText("喪偶")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", {
        name: "突然發生大事時，先不用自己查完所有規定",
      }),
    ).not.toBeInTheDocument();
  });

  it("collects a few turns of chat, then confirms into the interpretation screen", async () => {
    render(<NavigatorFlow />);

    sendViaTextarea("家人剛過世，不知道接下來要辦什麼");
    expect(await screen.findByText("喪偶")).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: "有兩個小孩要養" }));
    fireEvent.click(await screen.findByRole("button", { name: "最近也失業了" }));

    fireEvent.click(await screen.findByRole("button", { name: "對，就是這件事" }));

    expect(
      await screen.findByRole("heading", { name: "我們理解到：喪偶" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("喪偶").length).toBeGreaterThan(0);
  });

  it("lets the user revise before confirming, extending the conversation", async () => {
    render(<NavigatorFlow />);

    sendViaTextarea("家裡最近生活很困難，錢快不夠用了");
    await screen.findByText("生活困難");

    fireEvent.click(await screen.findByRole("button", { name: "只有我自己" }));
    fireEvent.click(await screen.findByRole("button", { name: "還在工作" }));

    fireEvent.click(await screen.findByRole("button", { name: "不太對，我再說明一次" }));

    expect(
      await screen.findByText("好的，那我們再多聊一點，還有什麼想補充的嗎？"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("輸入訊息")).toBeInTheDocument();
  });

  it('does not treat "還在工作" (still employed) as a jobless signal', async () => {
    render(<NavigatorFlow />);

    sendViaTextarea("家裡最近生活很困難，錢快不夠用了");
    await screen.findByText("生活困難");

    fireEvent.click(await screen.findByRole("button", { name: "只有我自己" }));
    fireEvent.click(await screen.findByRole("button", { name: "還在工作" }));

    await screen.findByRole("button", { name: "對，就是這件事" });
    expect(screen.queryByText("收入中斷")).not.toBeInTheDocument();
  });

  it("does not repeat a follow-up question about a dimension already mentioned in the user's message", async () => {
    render(<NavigatorFlow />);

    sendViaTextarea("我先生上週過世了，我們還有兩個小孩");

    expect(await screen.findByText("喪偶")).toBeInTheDocument();
    expect(screen.getByText("育兒")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "最近也失業了" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("家裡還有其他人需要你照顧嗎？例如小孩或長輩。"),
    ).not.toBeInTheDocument();
  });
});
