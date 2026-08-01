import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the live intake by default and walks the same UI in demo mode", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).endsWith("/health")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ status: "ok" }),
          });
        }
        if (String(url).endsWith("/sessions/current")) {
          return Promise.resolve({
            ok: false,
            status: 404,
            json: async () => ({ errorCode: "session_not_found" }),
          });
        }
        throw new Error(`unexpected fetch: ${url}`);
      }),
    );

    render(<App />);

    expect(
      await screen.findByRole("button", { name: "開始說明我的情況" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "切換到示範完整流程" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "切換到示範完整流程" }));

    expect(await screen.findByText(/這是示範流程/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "看下一步" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "我的資料" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "開始說明我的情況" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(await screen.findByText("最近發生了什麼事？")).toBeInTheDocument();
    expect(screen.getByDisplayValue(/配偶過世一個月了/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(await screen.findByText("我們這樣理解，對嗎？")).toBeInTheDocument();
    expect(screen.getByText("配偶過世")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(await screen.findByText("再請你回答幾個問題")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "繼續" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(await screen.findByText("目前整理出的方向")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "結束示範，開始正式諮詢" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "結束示範，開始正式諮詢" }));
    expect(
      await screen.findByRole("button", { name: "開始說明我的情況" }),
    ).toBeInTheDocument();
  });
});
