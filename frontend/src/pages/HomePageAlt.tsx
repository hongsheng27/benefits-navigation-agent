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
import { ThreadStep } from "../components/alt/ThreadStep";
import { useBackendSession } from "../hooks/useBackendSession";
import { MAX_LIFE_EVENT_TEXT_LENGTH } from "../types/session";

const LEDE =
  "用你自己的話說發生了什麼事就好。系統會自動判斷是哪一種生活變故，再整理可能相關的補助與行政程序、辦理順序與機關，並附上可帶去問承辦人的官方依據。部分情境的福利圖譜仍在建置中。";

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
    body: "不符合的時候會指出差在哪一個條件，不必白跑一趟。",
  },
  {
    title: "只做導航",
    body: "告訴你該辦什麼、什麼順序、去哪裡。不代你送件，也不取代承辦人員。",
  },
] as const;

export function HomePageAlt() {
  const [description, setDescription] = useState("");
  const [connection, setConnection] = useState<BackendConnectionState>("checking");

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

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
        // StrictMode mounts twice in development; the aborted first run is
        // not a failure.
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

  const workflowState = snapshot?.workflowState ?? null;
  const hasResult = workflowState !== null && workflowState !== "understand_event";

  useEffect(() => {
    if (hasResult) {
      resultRef.current?.focus();
    }
  }, [hasResult]);

  const busy = status === "working" || status === "restoring";
  const trimmed = description.trim();
  const canSubmit =
    trimmed.length > 0 && trimmed.length <= MAX_LIFE_EVENT_TEXT_LENGTH && !busy;

  // 事件已辨識但還沒確認：後端維持在 understand_event，並且已經給出 lifeEvent。
  const awaitingConfirmation =
    workflowState === "understand_event" && (snapshot?.lifeEvent ?? null) !== null;

  // 只有「尚未確認事件」時才能送描述。中途若仍顯示表單，再送會拿到 invalid_transition。
  const canDescribeEvent =
    snapshot === null ||
    (workflowState === "understand_event" && snapshot.lifeEvent === null);

  const questionGroups = snapshot?.questionGroups ?? [];
  const showQuestions =
    workflowState === "collect_missing_fields" && questionGroups.length > 0;

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
    await resetSession();
    inputRef.current?.focus();
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

        {errorCode ? (
          <div
            role="alert"
            className="mt-10 border-l-2 border-[#8a2a2a] bg-[#f7ecec] px-4 py-4 text-[0.9rem] leading-[2] text-[#5c2323] sm:px-5"
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

        <div className="mt-14 ml-[1.15rem] border-l border-[#e0d8ca] sm:ml-6">
          <ThreadStep
            marker="一"
            title="用你自己的話說一次"
            titleId="step-describe"
            tone="active"
          >
            {awaitingConfirmation && snapshot?.lifeEvent ? (
              <EventConfirmation
                disabled={busy}
                lifeEvent={snapshot.lifeEvent}
                onConfirm={() => void confirmEvent(true)}
                onRedescribe={() => void handleRedescribe()}
              />
            ) : !canDescribeEvent ? (
              <div className="mt-2">
                <p className="text-[0.9rem] leading-[2] text-[#5c564e]">
                  這次諮詢已經過了描述事件的步驟。若要說另一件事，請重新開始。
                </p>
                <button
                  type="button"
                  onClick={() => void handleReset()}
                  className="mt-4 rounded-sm border border-[#c9c0b0] bg-[#f7f4ee] px-4 py-2.5 text-[0.9rem] leading-[1.8] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
                >
                  清除這次諮詢，重新開始
                </button>
              </div>
            ) : (
              <form onSubmit={(event) => void handleSubmit(event)} noValidate>
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
            )}
          </ThreadStep>

          <ThreadStep
            marker="二"
            title="回答幾個必要的條件"
            titleId="step-questions"
            tone={showQuestions ? "active" : "pending"}
            note={showQuestions ? undefined : "等待上一步完成"}
          >
            {showQuestions ? (
              <QuestionGroupList
                disabled={busy}
                groups={questionGroups}
                onSubmit={(answers) => void answerFields(answers)}
              />
            ) : (
              <p className="text-[0.9rem] leading-[2] text-[#5c564e]">
                確認事件之後，後端會依這個事件展開需要確認的條件，問到能判定為止就停。
              </p>
            )}
          </ThreadStep>

          <ThreadStep
            marker="三"
            title="拿到一張有順序的行動清單"
            titleId="step-result"
            tone={hasResult ? "active" : "pending"}
          >
            <div aria-live="polite" ref={resultRef} tabIndex={-1}>
              {snapshot && hasResult ? (
                <>
                  <p className="text-[0.85rem] leading-[1.9] tracking-[0.04em] text-[#6b6459]">
                    事件：{snapshot.lifeEvent ? lifeEventName(snapshot.lifeEvent) : "—"}
                    <span className="ml-3">
                      進度 {snapshot.stepIndex} / {snapshot.stepTotal}
                    </span>
                  </p>
                  <ResultList snapshot={snapshot} />
                  <div className="mt-6">
                    <button
                      type="button"
                      onClick={() => void handleReset()}
                      className="rounded-sm border border-[#c9c0b0] bg-[#f7f4ee] px-4 py-2.5 text-[0.9rem] leading-[1.8] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
                    >
                      清除這次諮詢，重新開始
                    </button>
                  </div>
                </>
              ) : (
                <p className="border border-dashed border-[#d8cfc0] bg-[#f7f4ee] px-4 py-6 text-[0.88rem] leading-[2] text-[#6b6459]">
                  確認事件之後，後端評估出的項目會出現在這裡。
                </p>
              )}
            </div>
          </ThreadStep>
        </div>
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
