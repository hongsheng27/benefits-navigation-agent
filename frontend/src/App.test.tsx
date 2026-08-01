import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubSessionHealth() {
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
      // Agency / cases clients may probe the API; allow failure → mock fallback.
      return Promise.resolve({
        ok: false,
        status: 404,
        json: async () => ({}),
      });
    }),
  );
}

describe("App", () => {
  it("renders the live intake by default and walks the same UI in demo mode", async () => {
    stubSessionHealth();

    render(<App />);

    expect(
      await screen.findByRole("button", { name: "開始說明我的情況" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "切換到示範完整流程" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "主要功能" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "切換到示範完整流程" }));

    expect(await screen.findByText(/這是示範流程/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "看下一步" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "回到正式諮詢" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(await screen.findByText("最近發生了什麼事？")).toBeInTheDocument();
    expect(screen.getByDisplayValue(/配偶過世一個月了/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "回到正式諮詢" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "切換到示範完整流程" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(await screen.findByText("我們這樣理解，對嗎？")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(await screen.findByText("再請你回答幾個問題")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(await screen.findByText("目前整理出的方向")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "結束示範，開始正式諮詢" }));
    expect(
      await screen.findByRole("button", { name: "開始說明我的情況" }),
    ).toBeInTheDocument();
  });

  it("navigates to tracking and agency overview pages", async () => {
    stubSessionHealth();
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "追蹤進度" }));
    expect(await screen.findByText("你正在處理的事")).toBeInTheDocument();
    expect(await screen.findByText(/配偶過世 — 補助與手續/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "補助機關總覽" }));
    expect(await screen.findByText("相關機關與官方網站")).toBeInTheDocument();
    expect(await screen.findByText(/與你目前的/)).toBeInTheDocument();
    expect(await screen.findByText("勞動部勞工保險局")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "新諮詢" }));
    expect(
      await screen.findByRole("button", { name: "開始說明我的情況" }),
    ).toBeInTheDocument();
  });

  it("opens agencies focused on a tracked case", async () => {
    stubSessionHealth();
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "追蹤進度" }));
    const openAgencyButtons = await screen.findAllByRole("button", {
      name: "查看此情況相關機關",
    });
    fireEvent.click(openAgencyButtons[0]);

    expect(
      await screen.findByText(/與「配偶過世 — 補助與手續」相關/),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/案件相關機關/).length).toBeGreaterThan(0);
  });
});
