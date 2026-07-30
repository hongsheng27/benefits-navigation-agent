import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NavigatorFlow } from "./NavigatorFlow";

describe("ProfileScreen", () => {
  it("opens from the top bar, edits a field, and shows the updated value", async () => {
    render(<NavigatorFlow />);

    fireEvent.click(screen.getByRole("button", { name: "我的資料" }));
    expect(
      await screen.findByRole("heading", { name: "基本資料" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("李○芳").length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole("button", { name: "修改" })[0]);
    const input = await screen.findByRole("textbox");
    fireEvent.change(input, { target: { value: "王小明" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    expect(await screen.findByText("王小明")).toBeInTheDocument();
  });

  it("simulates a MyData authorization and revoke round-trip", async () => {
    render(<NavigatorFlow />);

    fireEvent.click(screen.getByRole("button", { name: "我的資料" }));
    fireEvent.click(await screen.findByRole("button", { name: "MyData 授權" }));
    expect(await screen.findByText("尚未授權")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "前往 MyData 授權" }));
    expect(await screen.findByText("已授權")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "撤回授權並刪除帶入資料" }));
    expect(await screen.findByText("尚未授權")).toBeInTheDocument();
  });

  it("wipes all data through the confirmation dialog and returns to the chat step", async () => {
    render(<NavigatorFlow />);

    fireEvent.click(screen.getByRole("button", { name: "我的資料" }));
    fireEvent.click(await screen.findByRole("button", { name: "隱私與資料管理" }));

    fireEvent.click(await screen.findByRole("button", { name: "永久刪除我的資料" }));
    expect(
      await screen.findByText("確定要永久刪除我的資料嗎？"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "永久刪除" }));

    expect(
      await screen.findByPlaceholderText("請描述目前的狀況……"),
    ).toBeInTheDocument();
  });
});
