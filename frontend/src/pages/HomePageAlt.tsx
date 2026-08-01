import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode, RefObject } from "react";

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
import { INTAKE_DEMO_SCENES } from "../mocks/intakeDemoScript";
import type { SessionSnapshot } from "../types/session";
import { MAX_LIFE_EVENT_TEXT_LENGTH } from "../types/session";

const LEDE =
  "你只要用平常說話的方式，說說最近發生了什麼。我們會幫你找出可能相關的補助與要辦的手續，以及大概該用什麼順序、去哪個單位。";

const EXAMPLE_PROMPTS = [
  "配偶過世一個月了，想確認還有哪些給付來得及申請。",
  "公司裁員，我被資遣了，想知道失業給付怎麼申請。",
  "爸媽需要長期照顧，不知道長照可以從哪裡開始。",
] as const;

const BOUNDARIES = [
  {
    title: "只問必要的",
    body: "不會要你的姓名或身分證字號。問到夠判斷就停。",
  },
  {
    title: "說得清楚",
    body: "若看起來不符合，會盡量說明差在哪裡，減少白跑一趟。",
  },
  {
    title: "協助你準備",
    body: "告訴你可能要辦什麼、什麼順序、去哪裡。不會代你送件。",
  },
] as const;

/** 後端串接版的畫面步驟（後端 session 仍是權威來源）。 */
export type IntakeUiStep = "landing" | "describe" | "confirm" | "questions" | "result";

export type IntakeMode = "live" | "demo";

type HomePageAltProps = {
  mode?: IntakeMode;
  /** 示範結束或跳過時回到正式諮詢。 */
  onExitDemo?: () => void;
};

const STEP_META: Record<
  Exclude<IntakeUiStep, "landing">,
  { index: number; total: number; label: string }
> = {
  describe: { index: 1, total: 4, label: "說說發生的事" },
  confirm: { index: 2, total: 4, label: "確認我們理解對不對" },
  questions: { index: 3, total: 4, label: "回答幾個問題" },
  result: { index: 4, total: 4, label: "查看可做的事" },
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

  return "result";
}

function StepProgress({ step }: { step: Exclude<IntakeUiStep, "landing"> }) {
  const meta = STEP_META[step];
  return (
    <div className="mb-6" aria-live="polite">
      <p className="text-[0.8rem] leading-[1.8] text-[#6b6459]">
        步驟 {meta.index}／{meta.total}
        <span className="mx-2 text-[#c9c0b0]">·</span>
        {meta.label}
      </p>
      <div
        className="mt-3 flex gap-1.5"
        role="progressbar"
        aria-valuemin={1}
        aria-valuemax={meta.total}
        aria-valuenow={meta.index}
        aria-label={`目前第 ${meta.index} 步，共 ${meta.total} 步`}
      >
        {Array.from({ length: meta.total }, (_, i) => {
          const done = i + 1 <= meta.index;
          return (
            <span
              key={i}
              className={`h-1 flex-1 rounded-full transition-colors ${
                done ? "bg-[#2f4f45]" : "bg-[#e0d8ca]"
              }`}
            />
          );
        })}
      </div>
    </div>
  );
}

function PageChrome({
  children,
  footerExtra,
  demoBanner,
}: {
  children: ReactNode;
  footerExtra?: ReactNode;
  demoBanner?: ReactNode;
}) {
  return (
    <div
      className={`${styles.page} flex min-h-screen flex-col text-[#171513] antialiased`}
    >
      <header className="mx-auto w-full max-w-[40rem] px-5 pt-8 sm:px-8 sm:pt-12">
        <div className="flex items-baseline gap-3">
          <span
            className={`${styles.serif} text-[1.35rem] leading-none tracking-[0.18em] text-[#2f4f45]`}
          >
            接住
          </span>
          <span className="text-[0.78rem] leading-[1.6] text-[#8b8377]">
            生活變故時，幫你理出下一步
          </span>
        </div>
      </header>

      {demoBanner}

      <main className="mx-auto w-full max-w-[40rem] grow px-5 pt-10 pb-28 sm:px-8 sm:pt-14">
        {children}
      </main>

      <footer className="border-t border-[#e0d8ca]/30">
        <div className="mx-auto flex w-full max-w-[40rem] flex-col gap-2 px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p className="text-[0.78rem] leading-[1.7] text-[#8b8377]">
            接住 · 生活突然改變時，先有人陪你理出下一步
          </p>
          {footerExtra}
        </div>
      </footer>
    </div>
  );
}

type IntakeStepsProps = {
  uiStep: IntakeUiStep;
  snapshot: SessionSnapshot | null;
  description: string;
  setDescription?: (value: string) => void;
  eventNotRecognized?: boolean;
  busy?: boolean;
  readOnly: boolean;
  demoAnswers?: Record<string, boolean | number | string>;
  onStart?: () => void;
  onSubmitDescribe?: (event: FormEvent<HTMLFormElement>) => void;
  onExampleSelect?: (prompt: string) => void;
  onConfirm?: () => void;
  onRedescribe?: () => void;
  onAnswerFields?: (answers: Record<string, boolean | number | string>) => void;
  onReset?: () => void;
  inputRef?: RefObject<HTMLTextAreaElement | null>;
  stepHeadingRef?: RefObject<HTMLHeadingElement | null>;
};

function IntakeSteps({
  uiStep,
  snapshot,
  description,
  setDescription,
  eventNotRecognized = false,
  busy = false,
  readOnly,
  demoAnswers,
  onStart,
  onSubmitDescribe,
  onExampleSelect,
  onConfirm,
  onRedescribe,
  onAnswerFields,
  onReset,
  inputRef,
  stepHeadingRef,
}: IntakeStepsProps) {
  const trimmed = description.trim();
  const canSubmit =
    !readOnly &&
    trimmed.length > 0 &&
    trimmed.length <= MAX_LIFE_EVENT_TEXT_LENGTH &&
    !busy;

  const questionGroups = snapshot?.questionGroups ?? [];
  const hasNoQuestionsYet =
    uiStep === "result" &&
    (snapshot?.items.length ?? 0) === 0 &&
    questionGroups.length === 0;

  return (
    <>
      {uiStep === "landing" ? (
        <section>
          <p
            className={`${styles.serif} text-[2.4rem] leading-[1.15] tracking-[0.12em] text-[#2f4f45] sm:text-[2.8rem]`}
          >
            接住
          </p>
          <h1 className="mt-5 text-[1.35rem] leading-[1.65] font-semibold text-[#171513] sm:text-[1.5rem]">
            突然發生大事時，
            <br />
            先不用自己查完所有規定。
          </h1>
          <p className="mt-5 max-w-[32rem] text-[0.98rem] leading-[1.95] text-[#4a453d]">
            {LEDE}
          </p>
          <ul className="mt-10 space-y-5 border-t border-[#e0d8ca] pt-8">
            {BOUNDARIES.map((item) => (
              <li key={item.title}>
                <h2 className="text-[0.92rem] font-semibold tracking-[0.02em] text-[#2f4f45]">
                  {item.title}
                </h2>
                <p className="mt-1 text-[0.9rem] leading-[1.85] text-[#5c564e]">
                  {item.body}
                </p>
              </li>
            ))}
          </ul>
          {!readOnly && onStart ? (
            <button
              type="button"
              onClick={onStart}
              className="mt-10 w-full rounded-sm bg-[#2f4f45] px-6 py-3.5 text-[1rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] sm:w-auto"
            >
              開始說明我的情況
            </button>
          ) : null}
        </section>
      ) : null}

      {uiStep === "describe" ? (
        <section>
          <StepProgress step="describe" />
          <h1
            ref={stepHeadingRef}
            tabIndex={-1}
            className="text-[1.35rem] leading-[1.55] font-semibold text-[#171513] outline-none sm:text-[1.5rem]"
          >
            最近發生了什麼事？
          </h1>
          <p className="mt-2 text-[0.92rem] leading-[1.9] text-[#6b6459]">
            用你平常說話的方式寫就好，句子不通順也沒關係。
          </p>
          <form
            onSubmit={(event) => {
              if (readOnly) {
                event.preventDefault();
                return;
              }
              onSubmitDescribe?.(event);
            }}
            noValidate
            className="mt-6"
          >
            <label htmlFor="intake-description" className="sr-only">
              發生了什麼事？
            </label>

            <textarea
              id="intake-description"
              ref={inputRef}
              value={description}
              readOnly={readOnly}
              onChange={(event) => setDescription?.(event.target.value)}
              aria-describedby="intake-hint intake-privacy"
              maxLength={MAX_LIFE_EVENT_TEXT_LENGTH}
              rows={6}
              placeholder="例如：家人剛過世、被資遣、需要長照……"
              className="block w-full resize-y rounded-sm border border-[#cfc5b4] bg-[#fffdfa] px-4 py-3.5 text-[1rem] leading-[1.9] text-[#171513] placeholder:text-[#a89f90] focus-visible:border-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[#2f4f45] read-only:bg-[#f7f4ee] read-only:text-[#3a352e]"
            />
            <p id="intake-hint" className="sr-only">
              幾句話就好，不通順也沒關係。
            </p>

            {eventNotRecognized ? (
              <p
                aria-live="polite"
                className="mt-4 rounded-sm border border-[#e2d3b5] bg-[#f8f3ea] px-4 py-3.5 text-[0.92rem] leading-[1.9] text-[#4a453d]"
              >
                {EVENT_NOT_RECOGNIZED_MESSAGE}
              </p>
            ) : null}

            <PrivacyNotice id="intake-privacy" />

            {!readOnly && onExampleSelect ? (
              <ExamplePrompts
                labelId="intake-examples"
                prompts={EXAMPLE_PROMPTS}
                onSelect={onExampleSelect}
              />
            ) : null}

            <div className="mt-8">
              <button
                type="submit"
                disabled={!canSubmit}
                className="w-full rounded-sm bg-[#2f4f45] px-6 py-3.5 text-[1rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459] sm:w-auto"
              >
                {busy ? "正在了解你的情況…" : "下一步"}
              </button>
              <p className="mt-3 text-[0.82rem] leading-[1.8] text-[#8b8377]">
                {readOnly
                  ? "示範中無法送出。正式使用時，寫下一點內容就可以繼續。"
                  : canSubmit
                    ? "送出後我們只留下「發生哪一類事」，你寫的原文不會保存。"
                    : "寫下一點內容後，就可以繼續。"}
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
            className="text-[1.35rem] leading-[1.55] font-semibold text-[#171513] outline-none sm:text-[1.5rem]"
          >
            我們這樣理解，對嗎？
          </h1>
          <p className="mt-2 text-[0.92rem] leading-[1.9] text-[#6b6459]">
            先確認這一步，後面才不會問到不相干的問題。
          </p>
          <EventConfirmation
            disabled={busy || readOnly}
            lifeEvent={snapshot.lifeEvent}
            onConfirm={() => onConfirm?.()}
            onRedescribe={() => onRedescribe?.()}
          />
        </section>
      ) : null}

      {uiStep === "questions" ? (
        <section>
          <StepProgress step="questions" />
          <h1
            ref={stepHeadingRef}
            tabIndex={-1}
            className="text-[1.35rem] leading-[1.55] font-semibold text-[#171513] outline-none sm:text-[1.5rem]"
          >
            再請你回答幾個問題
          </h1>
          <p className="mt-2 text-[0.92rem] leading-[1.9] text-[#6b6459]">
            與「
            {snapshot?.lifeEvent ? lifeEventName(snapshot.lifeEvent) : "你的情況"}
            」有關。答完這組就可以繼續。
          </p>
          <div className="mt-6">
            <QuestionGroupList
              disabled={busy || readOnly}
              groups={questionGroups}
              initialAnswers={demoAnswers}
              readOnly={readOnly}
              onSubmit={(answers) => onAnswerFields?.(answers)}
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
            className="text-[1.35rem] leading-[1.55] font-semibold text-[#171513] outline-none sm:text-[1.5rem]"
          >
            目前整理出的方向
          </h1>
          <p className="mt-2 text-[0.92rem] leading-[1.9] text-[#6b6459]">
            關於「
            {snapshot.lifeEvent ? lifeEventName(snapshot.lifeEvent) : "你的情況"}」
          </p>

          {hasNoQuestionsYet ? (
            <div className="mt-6 rounded-sm border border-[#e0d8ca] bg-[#fdfbf7] px-4 py-6 text-[0.95rem] leading-[1.95] text-[#4a453d]">
              <p>
                我們已記下這是「
                {snapshot.lifeEvent
                  ? lifeEventName(snapshot.lifeEvent)
                  : "相關情況"}
                」。
              </p>
              <p className="mt-3">
                這類情況的詳細問題與可辦項目，資料還在補齊中。你可以重新開始，改用「配偶過世」相關說法，目前示範內容較完整。
              </p>
            </div>
          ) : (
            <div className="mt-6">
              <ResultList snapshot={snapshot} />
            </div>
          )}

          {!readOnly && onReset ? (
            <div className="mt-10">
              <button
                type="button"
                onClick={() => onReset()}
                className="rounded-sm border border-[#c9c0b0] bg-transparent px-5 py-2.5 text-[0.92rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
              >
                重新開始
              </button>
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  );
}

function DemoNavBar({
  sceneIndex,
  total,
  narration,
  isLast,
  onNext,
  onSkip,
  onFinish,
}: {
  sceneIndex: number;
  total: number;
  narration: string;
  isLast: boolean;
  onNext: () => void;
  onSkip: () => void;
  onFinish: () => void;
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t border-[#d8cfc0] bg-[#f7f4ee]/97 backdrop-blur">
      <div className="mx-auto flex w-full max-w-[40rem] flex-col gap-3 px-5 py-4 sm:px-8">
        <p className="text-[0.88rem] leading-[1.8] text-[#4a453d]" aria-live="polite">
          <span className="font-semibold text-[#2f4f45]">
            示範 {sceneIndex + 1}／{total}
          </span>
          <span className="mx-2 text-[#c9c0b0]">·</span>
          {narration}
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onSkip}
            className="rounded-sm border border-[#c9c0b0] bg-transparent px-4 py-2.5 text-[0.88rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
          >
            跳過示範
          </button>
          {isLast ? (
            <button
              type="button"
              onClick={onFinish}
              className="rounded-sm bg-[#2f4f45] px-5 py-2.5 text-[0.92rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
            >
              結束示範，開始正式諮詢
            </button>
          ) : (
            <button
              type="button"
              onClick={onNext}
              className="rounded-sm bg-[#2f4f45] px-5 py-2.5 text-[0.92rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
            >
              看下一步
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function HomePageDemo({ onExitDemo }: { onExitDemo?: () => void }) {
  const [sceneIndex, setSceneIndex] = useState(0);
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);
  const scene = INTAKE_DEMO_SCENES[sceneIndex];
  const isLast = sceneIndex >= INTAKE_DEMO_SCENES.length - 1;

  useEffect(() => {
    if (scene.step !== "landing") {
      stepHeadingRef.current?.focus();
    }
  }, [scene.step, sceneIndex]);

  function exit() {
    onExitDemo?.();
  }

  return (
    <PageChrome
      demoBanner={
        <div className="mx-auto w-full max-w-[40rem] px-5 pt-4 sm:px-8">
          <p className="rounded-sm border border-[#e2d3b5] bg-[#f8f3ea] px-4 py-3 text-[0.88rem] leading-[1.85] text-[#4a453d]">
            這是示範流程，畫面無法操作。正式使用時會請你自己填寫與選擇。
          </p>
        </div>
      }
      footerExtra={
        <p className="text-[0.78rem] leading-[1.7] text-[#8b8377]">示範模式 · 不連線服務</p>
      }
    >
      <IntakeSteps
        uiStep={scene.step}
        snapshot={scene.snapshot ?? null}
        description={scene.description ?? ""}
        readOnly
        demoAnswers={scene.answers}
        stepHeadingRef={stepHeadingRef}
      />
      <DemoNavBar
        sceneIndex={sceneIndex}
        total={INTAKE_DEMO_SCENES.length}
        narration={scene.narration}
        isLast={isLast}
        onNext={() => setSceneIndex((i) => Math.min(i + 1, INTAKE_DEMO_SCENES.length - 1))}
        onSkip={exit}
        onFinish={exit}
      />
    </PageChrome>
  );
}

function HomePageLive() {
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = description.trim();
    if (
      trimmed.length === 0 ||
      trimmed.length > MAX_LIFE_EVENT_TEXT_LENGTH ||
      busy
    ) {
      return;
    }
    await describeEvent(trimmed);
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
    <PageChrome footerExtra={<BackendStatusLine state={connection} />}>
      {errorCode ? (
        <div
          role="alert"
          className="mb-8 rounded-sm border border-[#e4c4c4] bg-[#faf2f2] px-4 py-4 text-[0.92rem] leading-[1.9] text-[#5c2323]"
        >
          <p>{errorMessage(errorCode)}</p>
          <button
            type="button"
            onClick={() => void handleReset()}
            className="mt-3 text-[0.88rem] font-semibold text-[#2f4f45] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
          >
            重新開始
          </button>
        </div>
      ) : null}

      <IntakeSteps
        uiStep={uiStep}
        snapshot={snapshot}
        description={description}
        setDescription={setDescription}
        eventNotRecognized={eventNotRecognized}
        busy={busy}
        readOnly={false}
        onStart={() => setHasStarted(true)}
        onSubmitDescribe={(event) => void handleSubmit(event)}
        onExampleSelect={(prompt) => {
          setDescription(prompt);
          inputRef.current?.focus();
        }}
        onConfirm={() => void confirmEvent(true)}
        onRedescribe={() => void handleRedescribe()}
        onAnswerFields={(answers) => void answerFields(answers)}
        onReset={() => void handleReset()}
        inputRef={inputRef}
        stepHeadingRef={stepHeadingRef}
      />
    </PageChrome>
  );
}

export function HomePageAlt({ mode = "live", onExitDemo }: HomePageAltProps) {
  if (mode === "demo") {
    return <HomePageDemo onExitDemo={onExitDemo} />;
  }
  return <HomePageLive />;
}
