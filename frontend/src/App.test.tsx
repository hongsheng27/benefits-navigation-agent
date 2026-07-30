import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the navigator flow's chat step by default", async () => {
    render(<App />);

    expect(
      await screen.findByPlaceholderText("請描述目前的狀況……"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "我的資料" })).toBeInTheDocument();
  });
});
