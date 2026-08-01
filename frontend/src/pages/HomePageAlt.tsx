import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { getBackendHealth } from "../api/client";
import styles from "../components/alt/alt.module.css";
import {
  BackendStatusLine,
  type BackendConnectionState,
} from "../components/alt/BackendStatusLine";
import { ExamplePrompts } from "../components/alt/ExamplePrompts";
import { PrivacyNotice } from "../components/alt/PrivacyNotice";
import { SkeletonResult } from "../components/alt/SkeletonResult";
import { ThreadStep } from "../components/alt/ThreadStep";

const LEDE =
  "接住會判斷哪些補助與行政程序和你有關、要用什麼順序辦、去哪個機關，並附上可以帶去問承辦人的官方依據。目前開放的情境是配偶過世。";

const EXAMPLE_PROMPTS = [
  "家人剛過世，不知道接下來要辦什麼。",
  "配偶過世一個月了，想確認還有哪些給付來得及申請。",
  "我在幫媽媽處理爸爸的後事，她沒有工作。",
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

const UPCOMING_QUESTIONS = [
  "與過世者的關係",
  "過世者的投保身分與年資",
  "你目前是否在工作、有無投保",
  "家中是否有未成年子女",
] as const;

export function HomePageAlt() {
  const [description, setDescription] = useState("");
  const [submittedLength, setSubmittedLength] = useState<number | null>(null);
  const [connection, setConnection] = useState<BackendConnectionState>("checking");

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    if (submittedLength !== null) {
      resultRef.current?.focus();
    }
  }, [submittedLength]);

  const trimmed = description.trim();
  const canSubmit = trimmed.length > 0;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    setSubmittedLength(trimmed.length);
  }

  function handleExampleSelect(prompt: string) {
    setDescription(prompt);
    setSubmittedLength(null);
    inputRef.current?.focus();
  }

  function handleReset() {
    setDescription("");
    setSubmittedLength(null);
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

        <div className="mt-14 ml-[1.15rem] border-l border-[#e0d8ca] sm:ml-6">
          <ThreadStep
            marker="一"
            title="用你自己的話說一次"
            titleId="step-describe"
            tone="active"
          >
            <form onSubmit={handleSubmit} noValidate>
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
                rows={5}
                placeholder="從最近發生的事開始寫就可以。"
                className="mt-3 block w-full resize-y rounded-sm border border-[#cfc5b4] bg-[#fffdfa] px-4 py-3.5 text-[0.98rem] leading-[2] text-[#171513] placeholder:text-[#8b8377] focus-visible:border-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#2f4f45]"
              />

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
                  整理我的下一步
                </button>
                <p className="text-[0.82rem] leading-[1.9] text-[#6b6459]">
                  {canSubmit
                    ? "送出不會離開這個頁面，也不會傳送任何資料。"
                    : "先寫下發生的事，才能送出。"}
                </p>
              </div>
            </form>
          </ThreadStep>

          <ThreadStep
            marker="二"
            title="回答幾個必要的條件"
            titleId="step-questions"
            tone="pending"
            note="尚未實作"
          >
            <p className="text-[0.9rem] leading-[2] text-[#5c564e]">
              資格是由條件的組合決定的，所以接住會反問，例如：
            </p>
            <ul className="mt-3 flex flex-wrap gap-x-2 gap-y-2">
              {UPCOMING_QUESTIONS.map((question) => (
                <li
                  key={question}
                  className="border border-dashed border-[#d8cfc0] px-3 py-1.5 text-[0.85rem] leading-[1.9] text-[#6b6459]"
                >
                  {question}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[0.85rem] leading-[2] text-[#6b6459]">
              問到能判定為止就停下來，不會多問。
            </p>
          </ThreadStep>

          <ThreadStep
            marker="三"
            title="拿到一張有順序的行動清單"
            titleId="step-result"
            tone={submittedLength === null ? "pending" : "active"}
          >
            <div aria-live="polite">
              {submittedLength === null ? (
                <p className="border border-dashed border-[#d8cfc0] bg-[#f7f4ee] px-4 py-6 text-[0.88rem] leading-[2] text-[#6b6459]">
                  送出之後，示意結果會出現在這裡。
                </p>
              ) : (
                <SkeletonResult
                  ref={resultRef}
                  characterCount={submittedLength}
                  onReset={handleReset}
                />
              )}
            </div>
          </ThreadStep>
        </div>
      </main>

      <footer className="border-t border-[#e0d8ca] bg-[#f4f0e8]">
        <div className="mx-auto flex w-full max-w-[46rem] flex-col gap-3 px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p className="text-[0.8rem] leading-[1.9] text-[#6b6459]">
            接住 · 前端骨架。本頁不載入任何第三方服務。
          </p>
          <BackendStatusLine state={connection} />
        </div>
      </footer>
    </div>
  );
}
