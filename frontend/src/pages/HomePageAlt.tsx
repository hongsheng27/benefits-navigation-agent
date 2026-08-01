import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { getBackendHealth } from "../api/client";
import styles from "../components/alt/alt.module.css";
import {
  BackendStatusLine,
  type BackendConnectionState,
} from "../components/alt/BackendStatusLine";
import {
  EVENT_NOT_RECOGNIZED_MESSAGE,
  errorMessage,
  lifeEventName,
} from "../components/alt/copy";
import { EventConfirmation } from "../components/alt/EventConfirmation";
import { ExamplePrompts } from "../components/alt/ExamplePrompts";
import { PrivacyNotice } from "../components/alt/PrivacyNotice";
import { QuestionGroupList } from "../components/alt/QuestionGroupList";
import { ResultList } from "../components/alt/ResultList";
import { useBackendSession } from "../hooks/useBackendSession";
import type { SessionSnapshot } from "../types/session";
import { MAX_LIFE_EVENT_TEXT_LENGTH } from "../types/session";

const LEDE =
  "用你自己的話說發生了什麼事就好。系統會自動判斷是哪一種生活變故，再整理可能相關的補助與行政程序。";

/** 不知道怎麼開頭時的少量例句（不是選單；送出後仍由 LLM 辨識）。 */
const EXAMPLE_PROMPTS = [
  "配偶過世一個月了，想確認還有哪些給付來得及申請。",
  "公司裁員被資遣了，想知道失業給付或其他協助怎麼申請。",
  "爸媽需要長期照顧，想知道長照服務與補助怎麼開始申請。",
] as const;

const BOUNDARIES = [
  {
    title: "只問需要的",
    body: "問到足以判定就停。不會問你的姓名，也不會問身分證字號。",
  },
  {
    title: "說得出不符合",
    body: "不符合的時候會指出差在哪個條件，不必白跑一趟。",
  },
  {
    title: "只做導航",
    body: "告訴你該辦什麼、什麼順序、去哪裡。不代你送件。",
  },
] as const;

/** 後端串接版的畫面步驟（後端 session 仍是權威來源）。 */
export type IntakeUiStep = "landing" | "describe" | "confirm" | "questions" | "result";

const STEP_META: Record<
  Exclude<IntakeUiStep, "landing">,
  { index: number; total: number; label: string }
> = {
  describe: { index: 1, total: 4, label: "描述發生的事" },
  confirm: { index: 2, total: 4, label: "確認事件" },
  questions: { index: 3, total: 4, label: "回答必要條件" },
  result: { index: 4, total: 4, label: "查看結果" },
};

/**
 * 依後端快照決定目前要顯示哪一屏。
 *
 * `hasStarted` 是前端自己的「是否離開說明頁」；一旦已有 session／事件，就以快照為準。
 */
export function deriveUiStep(
  snapshot: SessionSnapshot | null,
  hasStarted: boolean,
): IntakeUiStep {
  if (snapshot === null) {
    return hasStarted ? "describe" : "landing";
  }

  const { workflowState, lifeEvent, questionGroups } = snapshot;

  if (workflowState === "understand_event") {
    if (lifeEvent !== null) {
      return "confirm";
    }
    return "describe";
  }

  if (workflowState === "collect_missing_fields" && questionGroups.length > 0) {
    return "questions";
  }

  // 含：確認後無題可問、判定中／結果／完成等。
  return "result";
}

function StepProgress({ step }: { step: Exclude<IntakeUiStep, "landing"> }) {
  const meta = STEP_META[step];
  return (
    <p
      className="text-[0.82rem] leading-[1.9] tracking-[0.06em] text-[#6b6459]"
      aria-live="polite"
    >
      第 {meta.index}／{meta.total} 步 · {meta.label}
    </p>
  );
}

export function HomePageAlt() {
  const [description, setDescription] = useState("");
  const [hasStarted, setHasStarted] = useState(false);
  const [connection, setConnection] = useState<BackendConnectionState>("checking");

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);

  const {
    snapshot,
    status,
    errorCode,
    eventNotRecognized,
    describeEvent,
    confirmEvent,
    answerFields,
    resetSession,
  } = useBackendSession();

  useEffect(() => {
    const controller = new AbortController();

    getBackendHealth(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) {
          setConnection("connected");
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setConnection("unavailable");
      });

    return () => {
      controller.abort();
    };
  }, []);

  // 復原到進行中的諮詢時，跳過說明頁。
  useEffect(() => {
    if (snapshot !== null) {
      setHasStarted(true);
    }
  }, [snapshot]);

  const uiStep = deriveUiStep(snapshot, hasStarted);

  useEffect(() => {
    if (uiStep !== "landing") {
      stepHeadingRef.current?.focus();
    }
  }, [uiStep]);

  const busy = status === "working" || status === "restoring";
  const trimmed = description.trim();
  const canSubmit =
    trimmed.length > 0 && trimmed.length <= MAX_LIFE_EVENT_TEXT_LENGTH && !busy;

  const questionGroups = snapshot?.questionGroups ?? [];
  const hasNoQuestionsYet =
    uiStep === "result" &&
    (snapshot?.items.length ?? 0) === 0 &&
    questionGroups.length === 0;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    await describeEvent(trimmed);
  }

  function handleExampleSelect(prompt: string) {
    setDescription(prompt);
    inputRef.current?.focus();
  }

  async function handleReset() {
    setDescription("");
    setHasStarted(false);
    await resetSession();
  }

  async function handleRedescribe() {
    await confirmEvent(false);
    setDescription("");
    inputRef.current?.focus();
  }

  return (
    <div
      className={`${styles.page} flex min-h-screen flex-col text-[#171513] antialiased`}
    >
      <header className="mx-auto w-full max-w-[46rem] px-5 pt-8 sm:px-8 sm:pt-12">
        <div className="flex items-center gap-2.5">
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            className="h-5 w-5 text-[#2f4f45]"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
          >
            <path d="M2.6 8.4a7.4 7.4 0 0 0 14.8 0" />
            <path d="M10 2.4v3.2" />
          </svg>
          <span
            className={`${styles.serif} text-[1.05rem] leading-none tracking-[0.22em]`}
          >
            接住
          </span>
          <span className="text-[0.75rem] leading-[1.8] tracking-[0.08em] text-[#6b6459]">
            福利與行政程序導航
          </span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[46rem] grow px-5 pt-10 pb-16 sm:px-8 sm:pt-16">
        {errorCode ? (
          <div
            role="alert"
            className="mb-8 border-l-2 border-[#8a2a2a] bg-[#f7ecec] px-4 py-4 text-[0.9rem] leading-[2] text-[#5c2323] sm:px-5"
          >
            <p>{errorMessage(errorCode)}</p>
            <button
              type="button"
              onClick={() => void handleReset()}
              className="mt-3 rounded-sm border border-[#c9a0a0] bg-[#faf3f3] px-4 py-2 text-[0.88rem] leading-[1.8] text-[#5c2323] transition-colors hover:border-[#8a2a2a] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8a2a2a]"
            >
              清除這次諮詢，重新開始
            </button>
          </div>
        ) : null}

        {uiStep === "landing" ? (
          <section>
            <h1
              className={`${styles.serif} text-[1.65rem] leading-[1.55] tracking-[0.01em] sm:text-[2.15rem] sm:leading-[1.5]`}
            >
              不用先弄懂制度。
              <br />
              先說發生了什麼事。
            </h1>
            <p className="mt-6 max-w-[34rem] text-[0.98rem] leading-[2.1] text-[#4a453d] sm:text-[1.02rem]">
              {LEDE}
            </p>
            <ul className="mt-10 grid gap-px border-y border-[#e0d8ca] bg-[#e0d8ca] sm:grid-cols-3">
              {BOUNDARIES.map((item) => (
                <li key={item.title} className="bg-[#faf8f4] px-1 py-5 sm:px-4">
                  <h2 className="text-[0.88rem] leading-[1.9] font-semibold tracking-[0.06em] text-[#2f4f45]">
                    {item.title}
                  </h2>
                  <p className="mt-1.5 text-[0.85rem] leading-[2] text-[#5c564e]">
                    {item.body}
                  </p>
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => setHasStarted(true)}
              className="mt-10 rounded-sm bg-[#2f4f45] px-6 py-3 text-[0.95rem] leading-[1.8] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
            >
              開始
            </button>
          </section>
        ) : null}

        {uiStep === "describe" ? (
          <section>
            <StepProgress step="describe" />
            <h1
              ref={stepHeadingRef}
              tabIndex={-1}
              className={`${styles.serif} mt-3 text-[1.45rem] leading-[1.55] tracking-[0.01em] sm:text-[1.85rem] outline-none`}
            >
              用你自己的話說一次
            </h1>
            <form
              onSubmit={(event) => void handleSubmit(event)}
              noValidate
              className="mt-6"
            >
              <label
                htmlFor="intake-description"
                className="block text-[0.95rem] leading-[1.9] font-semibold tracking-[0.02em]"
              >
                發生了什麼事？
              </label>
              <p
                id="intake-hint"
                className="mt-1.5 text-[0.85rem] leading-[2] text-[#6b6459]"
              >
                幾句話就好，不通順、想到哪寫到哪都沒關係。
              </p>

              <textarea
                id="intake-description"
                ref={inputRef}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                aria-describedby="intake-hint intake-privacy"
                maxLength={MAX_LIFE_EVENT_TEXT_LENGTH}
                rows={5}
                placeholder="從最近發生的事開始寫就可以。"
                className="mt-3 block w-full resize-y rounded-sm border border-[#cfc5b4] bg-[#fffdfa] px-4 py-3.5 text-[0.98rem] leading-[2] text-[#171513] placeholder:text-[#8b8377] focus-visible:border-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#2f4f45]"
              />

              {eventNotRecognized ? (
                <p
                  aria-live="polite"
                  className="mt-4 border-l-2 border-[#8a5a1a] bg-[#f6f1e6] px-4 py-3.5 text-[0.88rem] leading-[2] text-[#4a453d] sm:px-5"
                >
                  {EVENT_NOT_RECOGNIZED_MESSAGE}
                </p>
              ) : null}

              <PrivacyNotice id="intake-privacy" />

              <ExamplePrompts
                labelId="intake-examples"
                prompts={EXAMPLE_PROMPTS}
                onSelect={handleExampleSelect}
              />

              <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3">
                <button
                  type="submit"
                  disabled={!canSubmit}
                  className="rounded-sm bg-[#2f4f45] px-6 py-3 text-[0.95rem] leading-[1.8] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
                >
                  {busy ? "正在辨識…" : "整理我的下一步"}
                </button>
                <p className="text-[0.82rem] leading-[1.9] text-[#6b6459]">
                  {canSubmit
                    ? "這段文字會送到後端辨識事件，辨識完成後原文即被丟棄。"
                    : "先寫下發生的事，才能送出。"}
                </p>
              </div>
            </form>
          </section>
        ) : null}

        {uiStep === "confirm" && snapshot?.lifeEvent ? (
          <section>
            <StepProgress step="confirm" />
            <h1
              ref={stepHeadingRef}
              tabIndex={-1}
              className={`${styles.serif} mt-3 text-[1.45rem] leading-[1.55] tracking-[0.01em] sm:text-[1.85rem] outline-none`}
            >
              請確認我們的理解
            </h1>
            <EventConfirmation
              disabled={busy}
              lifeEvent={snapshot.lifeEvent}
              onConfirm={() => void confirmEvent(true)}
              onRedescribe={() => void handleRedescribe()}
            />
          </section>
        ) : null}

        {uiStep === "questions" ? (
          <section>
            <StepProgress step="questions" />
            <h1
              ref={stepHeadingRef}
              tabIndex={-1}
              className={`${styles.serif} mt-3 text-[1.45rem] leading-[1.55] tracking-[0.01em] sm:text-[1.85rem] outline-none`}
            >
              回答幾個必要的條件
            </h1>
            <p className="mt-3 text-[0.9rem] leading-[2] text-[#5c564e]">
              問到能判定就停。事件：
              {snapshot?.lifeEvent ? lifeEventName(snapshot.lifeEvent) : "—"}
            </p>
            <div className="mt-6">
              <QuestionGroupList
                disabled={busy}
                groups={questionGroups}
                onSubmit={(answers) => void answerFields(answers)}
              />
            </div>
          </section>
        ) : null}

        {uiStep === "result" && snapshot ? (
          <section>
            <StepProgress step="result" />
            <h1
              ref={stepHeadingRef}
              tabIndex={-1}
              className={`${styles.serif} mt-3 text-[1.45rem] leading-[1.55] tracking-[0.01em] sm:text-[1.85rem] outline-none`}
            >
              你的下一步
            </h1>
            <p className="mt-3 text-[0.85rem] leading-[1.9] tracking-[0.04em] text-[#6b6459]">
              事件：{snapshot.lifeEvent ? lifeEventName(snapshot.lifeEvent) : "—"}
              <span className="ml-3">
                進度 {snapshot.stepIndex} / {snapshot.stepTotal}
              </span>
            </p>

            {hasNoQuestionsYet ? (
              <p className="mt-6 border border-dashed border-[#d8cfc0] bg-[#f7f4ee] px-4 py-6 text-[0.9rem] leading-[2] text-[#5c564e]">
                這個事件目前還沒有可追問的條件或可展開的項目（示範資料多半只涵蓋配偶過世）。辨識結果仍保留在上方，之後補上福利圖譜就會出現題目與清單。
              </p>
            ) : (
              <div className="mt-6">
                <ResultList snapshot={snapshot} />
              </div>
            )}

            <div className="mt-8">
              <button
                type="button"
                onClick={() => void handleReset()}
                className="rounded-sm border border-[#c9c0b0] bg-[#f7f4ee] px-4 py-2.5 text-[0.9rem] leading-[1.8] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
              >
                清除這次諮詢，重新開始
              </button>
            </div>
          </section>
        ) : null}
      </main>

      <footer className="border-t border-[#e0d8ca] bg-[#f4f0e8]">
        <div className="mx-auto flex w-full max-w-[46rem] flex-col gap-3 px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p className="text-[0.8rem] leading-[1.9] text-[#6b6459]">
            接住 · 已串接後端 session API。本頁不載入任何第三方服務。
          </p>
          <BackendStatusLine state={connection} />
        </div>
      </footer>
    </div>
  );
}
