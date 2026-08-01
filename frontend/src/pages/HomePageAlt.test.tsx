import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionSnapshot } from "../types/session";
import { HomePageAlt } from "./HomePageAlt";

const SESSION_ID = "sess_test_1234";

function snapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return {
    sessionId: SESSION_ID,
    workflowState: "understand_event",
    stepIndex: 1,
    stepTotal: 8,
    lifeEvent: null,
    attributes: {},
    items: [],
    questionGroups: [],
    exitReason: null,
    referralRequested: false,
    isProcessing: false,
    createdAt: "2026-07-31T00:00:00Z",
    expiresAt: "2026-07-31T02:00:00Z",
    implementation: {
      isMock: true,
      pending: ["rule_evaluation"],
      placeholderNotice: "（此為後端傳來的暫時資料）",
    },
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

/**
 * Routes fetch by URL + method so each test only declares the advance
 * responses it cares about, in order.
 */
function stubBackend(advanceResponses: ReturnType<typeof jsonResponse>[]) {
  const advanceQueue = [...advanceResponses];
  const calls: { url: string; init?: RequestInit }[] = [];

  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init });

    if (url.endsWith("/health")) {
      return Promise.resolve(jsonResponse({ status: "ok" }));
    }
    if (url.endsWith("/sessions")) {
      return Promise.resolve(jsonResponse(snapshot(), 201));
    }
    if (url.endsWith("/sessions/advance")) {
      const next = advanceQueue.shift();
      if (!next) {
        throw new Error(`unexpected extra advance call: ${JSON.stringify(init?.body)}`);
      }
      return Promise.resolve(next);
    }
    if (url.endsWith("/sessions/current")) {
      return Promise.resolve(jsonResponse({ errorCode: "session_not_found" }, 404));
    }
    throw new Error(`unexpected fetch: ${url}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function describeSituation(text: string) {
  fireEvent.change(screen.getByLabelText("發生了什麼事？"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByRole("button", { name: "整理我的下一步" }));
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("HomePageAlt", () => {
  it("walks the real session flow from description through questions to results", async () => {
    const calls = stubBackend([
      // life_event_text → event recognised, still awaiting confirmation
      jsonResponse(snapshot({ lifeEvent: "spouse_death" })),
      // event_confirmation → moves on to collecting fields
      jsonResponse(
        snapshot({
          lifeEvent: "spouse_death",
          workflowState: "collect_missing_fields",
          stepIndex: 3,
          questionGroups: [
            {
              topicId: "family_situation",
              groupIndex: 1,
              groupTotal: 1,
              questions: [
                {
                  fieldId: "has_dependent_children",
                  valueKind: "boolean",
                  optionIds: [],
                  required: true,
                  purposeId: "has_dependent_children.purpose",
                  unlocksItemIds: ["survivor_pension"],
                },
              ],
            },
          ],
        }),
      ),
      // attribute_answers → a determination comes back
      jsonResponse(
        snapshot({
          lifeEvent: "spouse_death",
          workflowState: "explain_result",
          stepIndex: 6,
          attributes: { has_dependent_children: true },
          items: [
            {
              itemId: "funeral_benefit",
              kind: "benefit",
              status: "needs_human_review",
              missingFieldIds: [],
              decisiveConditions: [],
              citations: [],
              amountMin: null,
              amountMax: null,
              amountPeriod: null,
              amountCurrency: null,
              explanation: null,
            },
          ],
        }),
      ),
    ]);

    render(<HomePageAlt />);
    expect(await screen.findByText("後端已連線")).toBeInTheDocument();

    describeSituation("我先生上個月過世了。");

    // Step 1 turns into a confirmation prompt using the recognised event.
    // Prefer the confirm control: the catalog also shows the label as a chip.
    expect(
      await screen.findByRole("button", { name: "對，就是這件事" }),
    ).toBeInTheDocument();
    expect(screen.getByText("我讀到的是")).toBeInTheDocument();
    expect(screen.getByText("配偶過世")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "對，就是這件事" }));

    // Step 2 renders the backend's question with the frontend's own wording.
    expect(await screen.findByText("家中是否有未成年子女？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "是" }));
    fireEvent.click(screen.getByRole("button", { name: "送出這組答案" }));

    // Step 3 groups the item under the status section the backend returned.
    expect(await screen.findByText("需要人工協助確認")).toBeInTheDocument();
    expect(screen.getByText("喪葬給付")).toBeInTheDocument();
    expect(screen.getByText("（此為後端傳來的暫時資料）")).toBeInTheDocument();

    // The session id travels in a header, never in the path.
    const advanceCalls = calls.filter((call) => call.url.endsWith("/sessions/advance"));
    expect(advanceCalls).toHaveLength(3);
    for (const call of advanceCalls) {
      const headers = call.init?.headers as Record<string, string>;
      expect(headers["X-Session-Id"]).toBe(SESSION_ID);
    }
    expect(JSON.parse(String(advanceCalls[2].init?.body))).toEqual({
      input: { kind: "attribute_answers", answers: { has_dependent_children: true } },
    });
  });

  it("lets the user retry when the backend cannot recognise the event", async () => {
    stubBackend([
      jsonResponse(
        {
          errorCode: "event_not_recognized",
          fieldIds: [],
          currentState: "understand_event",
        },
        422,
      ),
    ]);

    render(<HomePageAlt />);
    await screen.findByText("後端已連線");

    describeSituation("今天天氣真好。");

    // Not an error: the input stays, and the copy invites another attempt.
    expect(await screen.findByText(/我們沒有看懂剛才的描述/)).toBeInTheDocument();
    expect(screen.getByLabelText("發生了什麼事？")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a plain error message when the session has expired", async () => {
    // describeEvent retries once after a stale/expired session; both attempts fail.
    stubBackend([
      jsonResponse(
        { errorCode: "session_expired", fieldIds: [], currentState: null },
        410,
      ),
      jsonResponse(
        { errorCode: "session_expired", fieldIds: [], currentState: null },
        410,
      ),
    ]);

    render(<HomePageAlt />);
    await screen.findByText("後端已連線");

    describeSituation("我先生上個月過世了。");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "這次諮詢已經超過保存時間",
    );
  });

  it("starts a fresh session when the old one rejects life_event_text", async () => {
    stubBackend([
      jsonResponse(
        {
          errorCode: "invalid_transition",
          fieldIds: [],
          currentState: "collect_missing_fields",
        },
        409,
      ),
      jsonResponse(snapshot({ lifeEvent: "serious_illness" })),
    ]);

    render(<HomePageAlt />);
    await screen.findByText("後端已連線");

    describeSituation("我生病了");

    expect(
      await screen.findByRole("button", { name: "對，就是這件事" }),
    ).toBeInTheDocument();
    expect(screen.getByText("重大傷病")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
