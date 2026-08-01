import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SessionSnapshot } from "../types/session";
import { deriveUiStep, HomePageAlt, previousUiStep } from "./HomePageAlt";

const SESSION_ID = "sess_test_1234";

function snapshot(overrides: Partial<SessionSnapshot> = {}): SessionSnapshot {
  return {
    sessionId: SESSION_ID,
    workflowState: "understand_event",
    stepIndex: 1,
    stepTotal: 8,
    lifeEvent: null,
    lifeEvents: [],
    extraCandidateLifeEvents: [],
    attributes: {},
    items: [],
    questionGroups: [],
    exitReason: null,
    referralRequested: false,
    isProcessing: false,
    collectorQuestion: null,
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

async function startIntake() {
  expect(
    await screen.findByRole("button", { name: "開始說明我的情況" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "開始說明我的情況" }));
  expect(await screen.findByLabelText("發生了什麼事？")).toBeInTheDocument();
}

function describeSituation(text: string) {
  fireEvent.change(screen.getByLabelText("發生了什麼事？"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByRole("button", { name: "下一步" }));
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("previousUiStep", () => {
  it("walks the wizard backwards", () => {
    expect(previousUiStep("landing")).toBeNull();
    expect(previousUiStep("describe")).toBe("landing");
    expect(previousUiStep("confirm")).toBe("describe");
    expect(previousUiStep("questions")).toBe("confirm");
    expect(previousUiStep("result")).toBe("questions");
  });
});

describe("deriveUiStep", () => {
  it("maps session snapshots to a single UI step", () => {
    expect(deriveUiStep(null, false)).toBe("landing");
    expect(deriveUiStep(null, true)).toBe("describe");
    expect(deriveUiStep(snapshot({ lifeEvent: null }), true)).toBe("describe");
    expect(deriveUiStep(snapshot({ lifeEvent: "spouse_death" }), true)).toBe(
      "confirm",
    );
    expect(
      deriveUiStep(
        snapshot({
          lifeEvent: "spouse_death",
          workflowState: "collect_missing_fields",
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
        true,
      ),
    ).toBe("questions");
    expect(
      deriveUiStep(
        snapshot({
          lifeEvent: "job_loss",
          workflowState: "collect_missing_fields",
          questionGroups: [],
        }),
        true,
      ),
    ).toBe("result");
  });
});

describe("HomePageAlt", () => {
  it("walks the real session flow from description through questions to results", async () => {
    const calls = stubBackend([
      jsonResponse(snapshot({ lifeEvent: "spouse_death" })),
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
    expect(await screen.findByText("服務已就緒")).toBeInTheDocument();

    await startIntake();
    // Only the current step is on screen.
    expect(screen.queryByText("再請你回答幾個問題")).not.toBeInTheDocument();
    expect(screen.queryByText("目前整理出的方向")).not.toBeInTheDocument();

    describeSituation("我先生上個月過世了。");

    expect(
      await screen.findByRole("button", { name: "對，就是這件事" }),
    ).toBeInTheDocument();
    expect(screen.getByText("我們這樣理解，對嗎？")).toBeInTheDocument();
    expect(screen.queryByLabelText("發生了什麼事？")).not.toBeInTheDocument();
    expect(screen.getByText("配偶過世")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "對，就是這件事" }));

    expect(await screen.findByText("再請你回答幾個問題")).toBeInTheDocument();
    expect(screen.queryByText("我們這樣理解，對嗎？")).not.toBeInTheDocument();
    expect(screen.getByText("家中是否有未成年子女？")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "一次回答多題" })).toBeInTheDocument();
    // 有選項時可直接點 chips，不必先切到整頁選擇題。
    fireEvent.click(screen.getByRole("button", { name: "是" }));

    expect(await screen.findByText("目前整理出的方向")).toBeInTheDocument();
    expect(screen.queryByText("再請你回答幾個問題")).not.toBeInTheDocument();
    expect(screen.getByText("建議再向承辦確認")).toBeInTheDocument();
    expect(screen.getByText("喪葬給付")).toBeInTheDocument();
    expect(screen.getByText(/目前結果仍是示範資料/)).toBeInTheDocument();

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

  it("sends attribute_chat_turn when the user answers in dialog mode", async () => {
    const calls = stubBackend([
      jsonResponse(snapshot({ lifeEvent: "spouse_death" })),
      jsonResponse(
        snapshot({
          lifeEvent: "spouse_death",
          workflowState: "collect_missing_fields",
          stepIndex: 3,
          collectorQuestion: "你主要在哪個縣市辦理或居住？",
          questionGroups: [
            {
              topicId: "location",
              groupIndex: 1,
              groupTotal: 1,
              questions: [
                {
                  fieldId: "applicant_jurisdiction",
                  valueKind: "code",
                  optionIds: ["TPE", "NWT", "TAO", "PEN", "OTHER_TW", "unsure"],
                  required: true,
                  purposeId: "applicant_jurisdiction.purpose",
                  unlocksItemIds: ["funeral_benefit"],
                },
              ],
            },
          ],
        }),
      ),
      jsonResponse(
        snapshot({
          lifeEvent: "spouse_death",
          workflowState: "explain_result",
          stepIndex: 6,
          attributes: { applicant_jurisdiction: "TPE" },
          collectorQuestion: null,
          questionGroups: [],
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
    await screen.findByText("服務已就緒");
    await startIntake();
    describeSituation("我先生上個月過世了。");
    fireEvent.click(await screen.findByRole("button", { name: "對，就是這件事" }));

    expect(await screen.findByText("再請你回答幾個問題")).toBeInTheDocument();
    expect(screen.getByText("你主要在哪個縣市辦理或居住？")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "臺北市" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("用文字回答，或上方點選選項"), {
      target: { value: "我住臺北市" },
    });
    fireEvent.click(screen.getByRole("button", { name: "送出" }));

    expect(await screen.findByText("目前整理出的方向")).toBeInTheDocument();
    const advanceCalls = calls.filter((call) => call.url.endsWith("/sessions/advance"));
    expect(JSON.parse(String(advanceCalls[2].init?.body))).toEqual({
      input: { kind: "attribute_chat_turn", text: "我住臺北市" },
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
    await screen.findByText("服務已就緒");
    await startIntake();

    describeSituation("今天天氣真好。");

    expect(await screen.findByText(/我們沒有完全看懂/)).toBeInTheDocument();
    expect(screen.getByLabelText("發生了什麼事？")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a plain error message when the session has expired", async () => {
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
    await screen.findByText("服務已就緒");
    await startIntake();

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
    await screen.findByText("服務已就緒");
    await startIntake();

    describeSituation("我生病了");

    expect(
      await screen.findByRole("button", { name: "對，就是這件事" }),
    ).toBeInTheDocument();
    expect(screen.getByText("重大傷病")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("skips the questions step when the backend returns no question groups", async () => {
    stubBackend([
      jsonResponse(snapshot({ lifeEvent: "job_loss" })),
      jsonResponse(
        snapshot({
          lifeEvent: "job_loss",
          workflowState: "collect_missing_fields",
          questionGroups: [],
          items: [],
        }),
      ),
    ]);

    render(<HomePageAlt />);
    await screen.findByText("服務已就緒");
    await startIntake();
    describeSituation("我失業了");

    fireEvent.click(await screen.findByRole("button", { name: "對，就是這件事" }));

    expect(await screen.findByText("目前整理出的方向")).toBeInTheDocument();
    expect(screen.queryByText("再請你回答幾個問題")).not.toBeInTheDocument();
    expect(screen.getByText(/資料還在補齊中/)).toBeInTheDocument();
  });
});
