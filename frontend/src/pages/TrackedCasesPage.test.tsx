import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as trackingClient from "../api/trackingClient";
import { TrackedCasesPage } from "./TrackedCasesPage";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TrackedCasesPage", () => {
  it("shows a clear empty state with a path back to consult", async () => {
    vi.spyOn(trackingClient, "listTrackedCases").mockResolvedValue({
      cases: [],
      isMock: false,
    });
    const onStartConsult = vi.fn();

    render(<TrackedCasesPage onStartConsult={onStartConsult} />);

    expect(await screen.findByText("還沒有可追蹤的案件")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "開始新諮詢" }));
    expect(onStartConsult).toHaveBeenCalledTimes(1);
  });
});
