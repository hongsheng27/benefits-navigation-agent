import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NavigatorFlow } from "./NavigatorFlow";

function sendViaTextarea(text: string) {
  fireEvent.change(screen.getByLabelText("輸入訊息"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByLabelText("送出"));
}

async function reachMatchScreen() {
  render(<NavigatorFlow />);

  sendViaTextarea("家人剛過世，不知道接下來要辦什麼");
  fireEvent.click(await screen.findByRole("button", { name: "有兩個小孩要養" }));
  fireEvent.click(await screen.findByRole("button", { name: "最近也失業了" }));
  fireEvent.click(await screen.findByRole("button", { name: "對，這樣理解沒錯" }));
  fireEvent.click(await screen.findByRole("button", { name: "正確，開始媒合評估 →" }));

  expect(await screen.findByText("過世者生前的投保身分是？")).toBeInTheDocument();
}

describe("MatchScreen", () => {
  it("walks through the questions and opens a matched benefit's detail page", async () => {
    await reachMatchScreen();

    fireEvent.click(screen.getByRole("button", { name: "勞工保險" }));
    fireEvent.click(await screen.findByRole("button", { name: "配偶" }));
    fireEvent.click(await screen.findByRole("button", { name: "15 年以上" }));

    expect(await screen.findByText("家中有幾位未滿 18 歲的子女？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "2 位" }));

    expect(await screen.findByText("你目前的就業狀況是？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "非自願離職" }));

    expect(await screen.findByText("同一戶籍內目前有幾人？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "3 人" }));

    expect(await screen.findByText("問題都回答完了")).toBeInTheDocument();
    expect(screen.getByText("喪葬給付")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /喪葬給付/ }));

    expect(await screen.findByRole("heading", { name: "喪葬給付" })).toBeInTheDocument();
    expect(screen.getByText("應備文件")).toBeInTheDocument();
  });

  it("lets the user skip a question and still reach the results", async () => {
    await reachMatchScreen();

    fireEvent.click(screen.getByRole("button", { name: "先跳過這題" }));
    expect(await screen.findByText("你與過世者的關係是？")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "← 回上一題" }));
    expect(await screen.findByText("過世者生前的投保身分是？")).toBeInTheDocument();
  });
});
