import { describe, expect, it } from "vitest";

import {
  buildCopilotGreeting,
  createUserMessage,
  replyToCopilot,
} from "./copilotStub";
import type { CopilotContext } from "../types/postConsult";

const PROVISION_CONTEXT: CopilotContext = {
  kind: "related_provisions",
  lifeEventId: "spouse_death",
  lifeEventLabel: "配偶過世",
  provisionTitles: ["新北市環保葬鼓勵金", "臺北市聯合奠祭家屬須知"],
  guideTitle: null,
  references: [
    {
      title: "新北市環保葬鼓勵金",
      body: "完成環保葬次日起1個月內臨櫃申辦",
    },
  ],
};

const GUIDE_CONTEXT: CopilotContext = {
  kind: "application_guide",
  lifeEventId: "spouse_death",
  lifeEventLabel: "配偶過世",
  provisionTitles: [],
  guideTitle: "配偶過世後常見申請與辦理順序",
  references: [
    {
      title: "辦理死亡登記",
      body: "向戶政事務所完成死亡登記",
    },
  ],
};

describe("copilotStub", () => {
  it("greets with a plain-language summary of related provisions", () => {
    const greeting = buildCopilotGreeting(PROVISION_CONTEXT);
    expect(greeting.role).toBe("assistant");
    expect(greeting.content).toContain("配偶過世");
    expect(greeting.content).toContain("新北市環保葬鼓勵金");
    expect(greeting.content).toContain("不能由我判定");
  });

  it("answers deadline questions from provision context", () => {
    const reply = replyToCopilot("申請期限大概多久？", PROVISION_CONTEXT);
    expect(reply.role).toBe("assistant");
    expect(reply.content).toMatch(/個月|期限/);
  });

  it("refuses to judge eligibility and steers back to rules or agencies", () => {
    const reply = replyToCopilot("我可不可以領？", GUIDE_CONTEXT);
    expect(reply.content).toMatch(/不能代替資格判定|不能替你下結論/);
    expect(reply.content).not.toMatch(/你符合資格|一定可以領/);
  });

  it("creates trimmed user messages", () => {
    const message = createUserMessage("  要帶哪些文件？  ");
    expect(message.role).toBe("user");
    expect(message.content).toBe("要帶哪些文件？");
  });
});
