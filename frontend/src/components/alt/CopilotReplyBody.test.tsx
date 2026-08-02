import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  CopilotReplyBody,
  normalizeCopilotReplyText,
  parseCopilotReplyBlocks,
} from "./CopilotReplyBody";

describe("normalizeCopilotReplyText", () => {
  it("splits glued steps and bullet points onto new lines", () => {
    const raw =
      "有順序性。常見順序是： **步驟 1：追蹤認定** 先確認進度。 **步驟 2：確認給付** 再向勞保局確認。 **重點提醒：** - 這是示範 - 可並行了解";
    const normalized = normalizeCopilotReplyText(raw);
    expect(normalized).toContain("**步驟 1：追蹤認定**");
    expect(normalized).toContain("**步驟 2：確認給付**");
    expect(normalized).toContain("**重點提醒：**");
    expect(normalized).toMatch(/\n- 這是示範/);
  });
});

describe("parseCopilotReplyBlocks", () => {
  it("builds headings, paragraphs, and lists", () => {
    const blocks = parseCopilotReplyBlocks(
      [
        "根據參考資料，常見順序如下。",
        "",
        "**步驟 1：追蹤認定**",
        "先確認案件進度。",
        "",
        "**重點提醒：**",
        "- 這是示範用整理",
        "- 窗口各自獨立",
      ].join("\n"),
    );
    expect(blocks[0]).toEqual({
      type: "paragraph",
      text: "根據參考資料，常見順序如下。",
    });
    expect(blocks.some((block) => block.type === "heading")).toBe(true);
    expect(blocks.some((block) => block.type === "list")).toBe(true);
  });
});

describe("CopilotReplyBody", () => {
  it("renders formatted assistant reply instead of raw markdown markers", () => {
    render(
      <CopilotReplyBody
        content={
          "常見順序： **步驟 1：追蹤職業災害認定進度** 先確認進度。 **重點提醒：** - 這是示範用整理"
        }
      />,
    );
    expect(screen.getByText("步驟 1：追蹤職業災害認定進度")).toBeInTheDocument();
    expect(screen.getByText(/先確認進度/)).toBeInTheDocument();
    expect(screen.getByText("這是示範用整理")).toBeInTheDocument();
    expect(screen.queryByText(/\*\*步驟/)).not.toBeInTheDocument();
  });
});
