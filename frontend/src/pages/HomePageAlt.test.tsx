import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HomePageAlt } from "./HomePageAlt";

function stubHealthyBackend() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ status: "ok" }),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("HomePageAlt", () => {
  it("shows the backend connection and a clearly-labelled mock result", async () => {
    stubHealthyBackend();

    render(<HomePageAlt />);

    expect(await screen.findByText("後端已連線")).toBeInTheDocument();

    const input = screen.getByLabelText("發生了什麼事？");
    const submit = screen.getByRole("button", { name: "整理我的下一步" });
    expect(submit).toBeDisabled();

    fireEvent.change(input, {
      target: { value: "家人剛過世，不知道接下來要辦什麼。" },
    });
    expect(submit).toBeEnabled();

    fireEvent.click(submit);

    expect(
      screen.getByRole("heading", { name: "這裡沒有判定結果，只有版面示意" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/沒有做任何資格判斷/)).toBeInTheDocument();
  });
});
