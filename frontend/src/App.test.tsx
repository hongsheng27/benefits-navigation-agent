import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("checks backend health and renders the mock result", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok" }),
      }),
    );

    render(<App />);

    expect(await screen.findByText("後端已連線")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("最近發生了什麼事？"), {
      target: { value: "家人剛過世，不知道接下來要辦什麼" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "開始整理下一步" }),
    );

    expect(
      screen.getByRole("heading", { name: "我們先從這裡接住你" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/這是前端骨架的示意結果/),
    ).toBeInTheDocument();
  });
});
