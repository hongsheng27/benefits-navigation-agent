import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HomePageAlt } from "./HomePageAlt";

afterEach(() => {
  cleanup();
});

describe("HomePageAlt demo mode", () => {
  it("walks the scripted scenes without enabling form actions", () => {
    const onExitDemo = vi.fn();
    render(<HomePageAlt mode="demo" onExitDemo={onExitDemo} />);

    expect(screen.getByText(/這是示範流程/)).toBeInTheDocument();
    expect(screen.getByText(/接下來用「配偶過世」/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(screen.getByLabelText("發生了什麼事？")).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "下一步" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(screen.getByRole("button", { name: "對，就是這些" })).toBeDisabled();

    const backButtons = screen.getAllByRole("button", { name: "← 上一步" });
    fireEvent.click(backButtons[0]);
    expect(screen.getByLabelText("發生了什麼事？")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    fireEvent.click(screen.getByRole("button", { name: "看下一步" }));
    expect(screen.getByRole("button", { name: "繼續" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "勞工保險" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "跳過示範" }));
    expect(onExitDemo).toHaveBeenCalledTimes(1);
  });
});
