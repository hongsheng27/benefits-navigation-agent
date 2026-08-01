import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode, RefObject } from "react";

import { getBackendHealth } from "../api/client";
import styles from "../components/alt/alt.module.css";
import { ApplicationGuidePanel } from "../components/alt/ApplicationGuidePanel";
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
import { AttributeChatPanel } from "../components/alt/AttributeChatPanel";
import { QuestionGroupList } from "../components/alt/QuestionGroupList";
import { RelatedProvisionsPanel } from "../components/alt/RelatedProvisionsPanel";
import { ResultGateBlock } from "../components/alt/ResultGateBlock";
import { ResultList } from "../components/alt/ResultList";
import { useBackendSession } from "../hooks/useBackendSession";
import {
  DEFAULT_INTAKE_DEMO_CASE_ID,
  INTAKE_DEMO_CASES,
  type IntakeDemoCase,
  type IntakeDemoCaseId,
} from "../mocks/intakeDemoScript";
import type { PostConsultPanelKind } from "../types/postConsult";
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
export type IntakeUiStep =
  "landing" | "describe" | "confirm" | "questions" | "ready" | "result";

export type IntakeMode = "live" | "demo";

const STEP_ORDER: IntakeUiStep[] = [
  "landing",
  "describe",
  "confirm",
  "questions",
  "ready",
  "result",
];

/** 線性精靈的上一步；已在第一屏則回 null。 */
export function previousUiStep(step: IntakeUiStep): IntakeUiStep | null {
  const index = STEP_ORDER.indexOf(step);
  if (index <= 0) {
    return null;
  }
  return STEP_ORDER[index - 1] ?? null;
}

type HomePageAltProps = {
  mode?: IntakeMode;
  /** 示範結束或跳過時回到正式諮詢。 */
  onExitDemo?: () => void;
  /** 在諮詢頁內切換正式／示範。 */
  onToggleMode?: () => void;
  /** 結果頁前往追蹤進度；參數為 lifeEventId（若有）。 */
  onGoToTracking?: (lifeEventId: string | null) => void;
  /** 外層已有 AppNav 時隱藏頁內品牌列，避免重複。 */
  hideBrandHeader?: boolean;
  /** 瀏覽器上一頁／下一頁還原到的諮詢步驟（live）。 */
  historyConsultStep?: IntakeUiStep | null;
  /** 瀏覽器上一頁／下一頁還原到的示範場景索引。 */
  historyDemoSceneIndex?: number | null;
  /** live 步驟變更時通知外層寫入 history。 */
  onConsultStepChange?: (step: IntakeUiStep) => void;
  /** demo 場景索引變更時通知外層寫入 history。 */
  onDemoSceneIndexChange?: (index: number) => void;
};

const STEP_META: Record<
  Exclude<IntakeUiStep, "landing">,
  { index: number; total: number; label: string }
> = {
  describe: { index: 1, total: 5, label: "說說發生的事" },
  confirm: { index: 2, total: 5, label: "確認我們理解對不對" },
  questions: { index: 3, total: 5, label: "回答幾個問題" },
  ready: { index: 4, total: 5, label: "差不多了" },
  result: { index: 5, total: 5, label: "查看可做的事" },
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

  const { workflowState, lifeEvent, lifeEvents, questionGroups } = snapshot;

  if (workflowState === "understand_event") {
    if (lifeEvents.length > 0 || lifeEvent !== null) {
      return "confirm";
    }
    return "describe";
  }

  if (workflowState === "collect_missing_fields" && questionGroups.length > 0) {
    return "questions";
  }

  return "result";
}

function snapshotLifeEvents(snapshot: SessionSnapshot | null): string[] {
  if (snapshot?.lifeEvents.length) {
    return snapshot.lifeEvents;
  }
  return snapshot?.lifeEvent ? [snapshot.lifeEvent] : [];
}

function lifeEventSummary(snapshot: SessionSnapshot | null): string {
  const labels = snapshotLifeEvents(snapshot).map(lifeEventName);
  return labels.length > 0 ? labels.join("、") : "你的情況";
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

function ModeToggle({ mode, onToggle }: { mode: IntakeMode; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="absolute right-4 top-3 z-20 rounded-sm border border-[#c9c0b0] bg-[#f7f4ee]/95 px-3 py-1.5 text-[0.72rem] font-semibold tracking-[0.02em] text-[#4a453d] shadow-sm backdrop-blur transition hover:border-[#2f4f45] hover:text-[#2f4f45] sm:right-6 sm:top-4"
    >
      {mode === "live" ? "切換到示範完整流程" : "回到正式諮詢"}
    </button>
  );
}

function BackLink({ disabled, onBack }: { disabled?: boolean; onBack: () => void }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onBack}
      className="text-[0.88rem] font-semibold text-[#2f4f45] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:text-[#a89f90] disabled:no-underline"
    >
      ← 上一步
    </button>
  );
}

function PageChrome({
  children,
  footerExtra,
  demoBanner,
  hideBrandHeader = false,
  modeToggle,
}: {
  children: ReactNode;
  footerExtra?: ReactNode;
  demoBanner?: ReactNode;
  hideBrandHeader?: boolean;
  modeToggle?: ReactNode;
}) {
  return (
    <div
      className={`${styles.page} relative flex min-h-[calc(100vh-4rem)] flex-col text-[#171513] antialiased`}
    >
      {modeToggle}

      {hideBrandHeader ? null : (
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
      )}

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
  /** 回看稍早步驟時，禁止再送出以免打亂後端狀態。 */
  isReviewing?: boolean;
  demoAnswers?: Record<string, boolean | number | string>;
  /** 純前端 demo 可選擇用服務對象分組結果，不會改動 API contract。 */
  groupResultsByAudience?: boolean;
  /** 結果頁回看問題時使用（後端結果快照可能已清空 questionGroups）。 */
  cachedQuestionGroups?: SessionSnapshot["questionGroups"];
  onStart?: () => void;
  onSubmitDescribe?: (event: FormEvent<HTMLFormElement>) => void;
  onExampleSelect?: (prompt: string) => void;
  onConfirm?: (eventIds: string[]) => void;
  onRedescribe?: () => void;
  onAnswerFields?: (answers: Record<string, boolean | number | string>) => void;
  onAnswerChatTurn?: (text: string) => void | Promise<void>;
  onReset?: () => void;
  /** 通過結果前閘門，進入結果頁。 */
  onViewResults?: () => void;
  /** 在問題對話窗內顯示結果前確認（不另開一頁）。 */
  showResultGate?: boolean;
  onGoToTracking?: (lifeEventId: string | null) => void;
  onBack?: () => void;
  onReturnToCurrent?: () => void;
  /** 正式諮詢 session，供結果頁 Copilot 呼叫 grounded LLM。 */
  sessionId?: string | null;
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
  isReviewing = false,
  demoAnswers,
  groupResultsByAudience = false,
  cachedQuestionGroups = [],
  onStart,
  onSubmitDescribe,
  onExampleSelect,
  onConfirm,
  onRedescribe,
  onAnswerFields,
  onAnswerChatTurn,
  onReset,
  onViewResults,
  showResultGate = false,
  onGoToTracking,
  onBack,
  onReturnToCurrent,
  sessionId = null,
  inputRef,
  stepHeadingRef,
}: IntakeStepsProps) {
  const [openPanel, setOpenPanel] = useState<PostConsultPanelKind | null>(null);
  const trimmed = description.trim();
  const actionsLocked = readOnly || isReviewing;
  const hideDemoResultActions = readOnly && groupResultsByAudience;
  const canSubmit =
    !actionsLocked &&
    trimmed.length > 0 &&
    trimmed.length <= MAX_LIFE_EVENT_TEXT_LENGTH &&
    !busy;

  const questionGroups =
    (snapshot?.questionGroups?.length ?? 0) > 0
      ? (snapshot?.questionGroups ?? [])
      : cachedQuestionGroups;
  const hasNoQuestionsYet =
    uiStep === "result" &&
    (snapshot?.items.length ?? 0) === 0 &&
    questionGroups.length === 0;
  const situationLabel = snapshot?.lifeEvent
    ? lifeEventName(snapshot.lifeEvent)
    : "你剛才說的情況";
  const resultGate =
    showResultGate && onViewResults && onReset
      ? {
          situationLabel,
          onViewResults,
          onConfirmRestart: onReset,
        }
      : null;

  const showBack = uiStep !== "landing" && onBack !== undefined;

  return (
    <>
      {showBack || isReviewing ? (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
          {showBack ? <BackLink disabled={busy} onBack={onBack} /> : null}
          {isReviewing && onReturnToCurrent ? (
            <button
              type="button"
              disabled={busy}
              onClick={onReturnToCurrent}
              className="text-[0.88rem] font-semibold text-[#2f4f45] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:text-[#a89f90]"
            >
              回到目前進度 →
            </button>
          ) : null}
        </div>
      ) : null}

      {isReviewing ? (
        <div className="mb-6 rounded-sm border border-[#e2d3b5] bg-[#f8f3ea] px-4 py-3.5 text-[0.88rem] leading-[1.85] text-[#4a453d]">
          <p>你正在回看稍早的步驟，這裡不能重新送出。</p>
          {onReturnToCurrent ? (
            <button
              type="button"
              disabled={busy}
              onClick={onReturnToCurrent}
              className="mt-3 rounded-sm bg-[#2f4f45] px-4 py-2 text-[0.88rem] font-semibold tracking-[0.02em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
            >
              回到目前進度
            </button>
          ) : null}
        </div>
      ) : null}

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
          {!actionsLocked && onStart ? (
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
              if (actionsLocked) {
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
              readOnly={actionsLocked}
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

            {!actionsLocked && onExampleSelect ? (
              <ExamplePrompts
                labelId="intake-examples"
                prompts={EXAMPLE_PROMPTS}
                onSelect={onExampleSelect}
              />
            ) : null}

            <div className="mt-8">
              {isReviewing && onReturnToCurrent ? (
                <>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={onReturnToCurrent}
                    className="w-full rounded-sm bg-[#2f4f45] px-6 py-3.5 text-[1rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459] sm:w-auto"
                  >
                    回到目前進度
                  </button>
                  <p className="mt-3 text-[0.82rem] leading-[1.8] text-[#8b8377]">
                    回看中無法重新送出；按上面按鈕可回到你剛才進行到的步驟。
                  </p>
                </>
              ) : (
                <>
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
                </>
              )}
            </div>
          </form>
        </section>
      ) : null}

      {uiStep === "confirm" && snapshotLifeEvents(snapshot).length > 0 ? (
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
            disabled={busy || actionsLocked}
            lifeEvent={snapshot?.lifeEvent}
            lifeEvents={snapshot?.lifeEvents ?? []}
            extraCandidateLifeEvents={snapshot?.extraCandidateLifeEvents ?? []}
            onConfirm={(eventIds) => onConfirm?.(eventIds)}
            onRedescribe={() => onRedescribe?.()}
          />
          {isReviewing && onReturnToCurrent ? (
            <div className="mt-6">
              <button
                type="button"
                disabled={busy}
                onClick={onReturnToCurrent}
                className="rounded-sm bg-[#2f4f45] px-5 py-2.5 text-[0.92rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
              >
                回到目前進度
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {uiStep === "questions" ? (
        <section>
          <StepProgress step={showResultGate ? "ready" : "questions"} />
          <h1
            ref={stepHeadingRef}
            tabIndex={-1}
            className="text-[1.35rem] leading-[1.55] font-semibold text-[#171513] outline-none sm:text-[1.5rem]"
          >
            {showResultGate ? "再確認一下就可以了" : "再請你回答幾個問題"}
          </h1>
          <p className="mt-2 text-[0.92rem] leading-[1.9] text-[#6b6459]">
            {showResultGate
              ? `關於「${situationLabel}」，我們先在對話裡問你要不要看整理結果。`
              : `與「${situationLabel}」有關。答完這組就可以繼續。`}
          </p>
          <div className="mt-6">
            {readOnly ||
            isReviewing ||
            !onAnswerChatTurn ||
            snapshotLifeEvents(snapshot).includes("occupational_injury") ? (
              <div>
                {questionGroups.length > 0 ? (
                  <QuestionGroupList
                    key={`${uiStep}-${isReviewing ? "review" : "live"}`}
                    disabled={busy || actionsLocked}
                    groups={questionGroups}
                    initialAnswers={demoAnswers ?? snapshot?.attributes}
                    readOnly={readOnly || isReviewing || showResultGate}
                    onSubmit={(answers) => onAnswerFields?.(answers)}
                    submitLabel={
                      !readOnly &&
                      !showResultGate &&
                      snapshotLifeEvents(snapshot).includes("occupational_injury")
                        ? "送出答案"
                        : undefined
                    }
                  />
                ) : null}
                {resultGate ? (
                  <div
                    className={
                      questionGroups.length > 0
                        ? "mt-6 rounded-sm border border-[#e0d8ca] bg-[#f4f0e8] px-4 py-4"
                        : "rounded-sm border border-[#e0d8ca] bg-[#f4f0e8] px-4 py-4"
                    }
                  >
                    <div className="max-w-[95%] rounded-sm bg-[#faf8f4] px-3 py-2.5 text-[0.88rem] leading-[1.75] text-[#3a352e] ring-1 ring-[#e0d8ca]">
                      我們好像已經掌握夠多了。要先看看整理結果嗎？若你還有別的情況想說，也可以從頭再說明一次。
                    </div>
                    <div className="mt-3">
                      <ResultGateBlock
                        embeddedInChat
                        situationLabel={resultGate.situationLabel}
                        disabled={busy || isReviewing}
                        onViewResults={resultGate.onViewResults}
                        onConfirmRestart={resultGate.onConfirmRestart}
                      />
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <AttributeChatPanel
                key="questions-chat"
                groups={questionGroups}
                collectorQuestion={snapshot?.collectorQuestion ?? null}
                disabled={busy || actionsLocked}
                answeredCount={Object.keys(snapshot?.attributes ?? {}).length}
                initialChoiceAnswers={snapshot?.attributes}
                onChatTurn={(text) => onAnswerChatTurn(text)}
                onSubmitChoices={(answers) => onAnswerFields?.(answers)}
                resultGate={resultGate}
              />
            )}
          </div>
          {isReviewing && onReturnToCurrent ? (
            <div className="mt-6">
              <button
                type="button"
                disabled={busy}
                onClick={onReturnToCurrent}
                className="rounded-sm bg-[#2f4f45] px-5 py-2.5 text-[0.92rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] disabled:cursor-not-allowed disabled:bg-[#ddd5c7] disabled:text-[#6b6459]"
              >
                回到目前進度
              </button>
            </div>
          ) : null}
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
            我們先幫你整理到這裡
          </h1>
          <p className="mt-3 max-w-[36rem] text-[0.95rem] leading-[2] text-[#4a453d]">
            關於「{situationLabel}
            」。下面是依你目前提供的資訊整理出的方向，可以慢慢看；這不是最後裁定，不確定的地方再向承辦單位確認就好。
          </p>

          {hasNoQuestionsYet ? (
            <div className="mt-8 rounded-sm border border-[#e0d8ca] bg-[#fdfbf7] px-4 py-6 text-[0.95rem] leading-[2] text-[#4a453d]">
              <p>
                我們已記下這是「
                {lifeEventSummary(snapshot)}
                」。
              </p>
              <p className="mt-3">
                這類情況的詳細問題與可辦項目，資料還在補齊中。你可以重新開始，改用「配偶過世」相關說法，目前示範內容較完整。
              </p>
            </div>
          ) : (
            <div className="mt-8">
              <p className="mb-5 text-[0.92rem] leading-[2] text-[#6b6459]">
                我們依你說的內容，先把可能相關的補助與手續排在下面。覺得有幫助的，可以加入追蹤，之後再慢慢辦理。
              </p>
              <ResultList
                snapshot={snapshot}
                groupByAudience={groupResultsByAudience}
                enableItemTracking={!hideDemoResultActions}
                onGoToTracking={onGoToTracking}
              />
            </div>
          )}

          <div className="mt-12">
            <p className="text-[0.88rem] leading-[1.9] text-[#6b6459]">
              若想再多了解依據或怎麼申請，可以從這裡繼續：
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3">
              {!isReviewing && !hideDemoResultActions ? (
                <>
                  <button
                    type="button"
                    onClick={() => setOpenPanel("related_provisions")}
                    className="w-full rounded-sm bg-[#2f4f45] px-4 py-2.5 text-center text-[0.92rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
                  >
                    一起看相關法條
                  </button>
                  <button
                    type="button"
                    onClick={() => setOpenPanel("application_guide")}
                    className="w-full rounded-sm bg-[#2f4f45] px-4 py-2.5 text-center text-[0.92rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
                  >
                    一起看申請解說
                  </button>
                </>
              ) : null}
              {onGoToTracking && !isReviewing && !hideDemoResultActions ? (
                <button
                  type="button"
                  onClick={() => onGoToTracking(snapshot.lifeEvent)}
                  className="w-full rounded-sm border border-[#c9c0b0] bg-transparent px-4 py-2.5 text-center text-[0.92rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
                >
                  去追蹤進度看這筆
                </button>
              ) : null}
              {!actionsLocked && onReset ? (
                <button
                  type="button"
                  onClick={() => onReset()}
                  className="w-full rounded-sm border border-[#c9c0b0] bg-transparent px-4 py-2.5 text-center text-[0.92rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
                >
                  重新開始
                </button>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      {openPanel === "related_provisions" ? (
        <RelatedProvisionsPanel
          lifeEventId={snapshot?.lifeEvent ?? null}
          jurisdiction={
            typeof snapshot?.attributes.applicant_jurisdiction === "string"
              ? snapshot.attributes.applicant_jurisdiction
              : null
          }
          sessionId={sessionId ?? snapshot?.sessionId ?? null}
          onClose={() => setOpenPanel(null)}
        />
      ) : null}
      {openPanel === "application_guide" ? (
        <ApplicationGuidePanel
          lifeEventId={snapshot?.lifeEvent ?? null}
          sessionId={sessionId ?? snapshot?.sessionId ?? null}
          onClose={() => setOpenPanel(null)}
        />
      ) : null}
    </>
  );
}

function DemoNavBar({
  sceneIndex,
  total,
  narration,
  isLast,
  canGoBack,
  onBack,
  onNext,
  onSkip,
  onFinish,
}: {
  sceneIndex: number;
  total: number;
  narration: string;
  isLast: boolean;
  canGoBack: boolean;
  onBack: () => void;
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
          {canGoBack ? (
            <button
              type="button"
              onClick={onBack}
              className="rounded-sm border border-[#c9c0b0] bg-transparent px-4 py-2.5 text-[0.88rem] text-[#3a352e] transition-colors hover:border-[#2f4f45] hover:text-[#2f4f45] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
            >
              ← 上一步
            </button>
          ) : null}
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

function DemoCaseSelector({
  cases,
  selectedId,
  onSelect,
}: {
  cases: readonly IntakeDemoCase[];
  selectedId: IntakeDemoCaseId;
  onSelect: (caseId: IntakeDemoCaseId) => void;
}) {
  return (
    <section
      className="mb-10 border-b border-[#e0d8ca] pb-8"
      aria-labelledby="demo-case-selector-title"
    >
      <h2
        id="demo-case-selector-title"
        className="text-[0.92rem] font-semibold tracking-[0.02em] text-[#2f4f45]"
      >
        選擇示範案例
      </h2>
      <p className="mt-1 text-[0.85rem] leading-[1.8] text-[#6b6459]">
        兩個案例使用相同流程；切換後會從示範第一幕開始。
      </p>
      <div
        className="mt-4 grid gap-3 sm:grid-cols-2"
        role="group"
        aria-label="示範案例"
      >
        {cases.map((demoCase, index) => {
          const selected = demoCase.id === selectedId;
          return (
            <button
              key={demoCase.id}
              type="button"
              aria-pressed={selected}
              onClick={() => onSelect(demoCase.id)}
              className={`rounded-sm border px-4 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45] ${
                selected
                  ? "border-[#2f4f45] bg-[#eef2ef]"
                  : "border-[#d8cfc0] bg-[#fffdfa] hover:border-[#8fa79c]"
              }`}
            >
              <span className="block text-[0.76rem] tracking-[0.08em] text-[#6b6459]">
                案例 {index + 1}
              </span>
              <span className="mt-1 block text-[0.95rem] font-semibold text-[#171513]">
                {demoCase.title}
              </span>
              <span className="mt-1 block text-[0.82rem] leading-[1.7] text-[#6b6459]">
                {demoCase.summary}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function HomePageDemo({
  onExitDemo,
  onToggleMode,
  onGoToTracking,
  hideBrandHeader,
  historyDemoSceneIndex = null,
  onDemoSceneIndexChange,
}: {
  onExitDemo?: () => void;
  onToggleMode?: () => void;
  onGoToTracking?: (lifeEventId: string | null) => void;
  hideBrandHeader?: boolean;
  historyDemoSceneIndex?: number | null;
  onDemoSceneIndexChange?: (index: number) => void;
}) {
  const [selectedCaseId, setSelectedCaseId] = useState<IntakeDemoCaseId>(
    DEFAULT_INTAKE_DEMO_CASE_ID,
  );
  const [sceneIndex, setSceneIndex] = useState(0);
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);
  const selectedCase =
    INTAKE_DEMO_CASES.find((demoCase) => demoCase.id === selectedCaseId) ??
    INTAKE_DEMO_CASES[0];
  const scenes = selectedCase.scenes;
  const scene = scenes[sceneIndex];
  const isLast = sceneIndex >= scenes.length - 1;

  useEffect(() => {
    if (scene.step !== "landing") {
      stepHeadingRef.current?.focus();
    }
  }, [scene.step, sceneIndex, selectedCaseId]);

  useEffect(() => {
    onDemoSceneIndexChange?.(sceneIndex);
  }, [sceneIndex, onDemoSceneIndexChange]);

  useEffect(() => {
    if (historyDemoSceneIndex == null) {
      return;
    }
    const clamped = Math.min(Math.max(historyDemoSceneIndex, 0), scenes.length - 1);
    setSceneIndex(clamped);
  }, [historyDemoSceneIndex, scenes.length]);

  function selectCase(caseId: IntakeDemoCaseId) {
    setSelectedCaseId(caseId);
    setSceneIndex(0);
  }

  function exit() {
    onExitDemo?.();
  }

  return (
    <PageChrome
      hideBrandHeader={hideBrandHeader}
      modeToggle={
        onToggleMode && sceneIndex === 0 ? (
          <ModeToggle mode="demo" onToggle={onToggleMode} />
        ) : null
      }
      demoBanner={
        <div className="mx-auto w-full max-w-[40rem] px-5 pt-4 sm:px-8">
          <p className="rounded-sm border border-[#e2d3b5] bg-[#f8f3ea] px-4 py-3 text-[0.88rem] leading-[1.85] text-[#4a453d]">
            這是示範流程，畫面無法操作。正式使用時會請你自己填寫與選擇。
          </p>
        </div>
      }
      footerExtra={
        <p className="text-[0.78rem] leading-[1.7] text-[#8b8377]">
          示範模式 · 不連線服務
        </p>
      }
    >
      {sceneIndex === 0 ? (
        <DemoCaseSelector
          cases={INTAKE_DEMO_CASES}
          selectedId={selectedCaseId}
          onSelect={selectCase}
        />
      ) : null}
      <IntakeSteps
        key={selectedCase.id}
        uiStep={scene.step === "ready" ? "questions" : scene.step}
        snapshot={scene.snapshot ?? null}
        description={scene.description ?? ""}
        readOnly
        demoAnswers={scene.answers}
        groupResultsByAudience={selectedCaseId === "occupational_injury_care"}
        stepHeadingRef={stepHeadingRef}
        onGoToTracking={onGoToTracking}
        showResultGate={scene.step === "ready"}
        onViewResults={
          scene.step === "ready"
            ? () => setSceneIndex((i) => Math.min(i + 1, scenes.length - 1))
            : undefined
        }
        onReset={
          scene.step === "ready"
            ? () => {
                setSceneIndex(0);
              }
            : undefined
        }
        onBack={
          sceneIndex > 0 ? () => setSceneIndex((i) => Math.max(0, i - 1)) : undefined
        }
      />
      <DemoNavBar
        sceneIndex={sceneIndex}
        total={scenes.length}
        narration={scene.narration}
        isLast={isLast}
        canGoBack={sceneIndex > 0}
        onBack={() => setSceneIndex((i) => Math.max(0, i - 1))}
        onNext={() => setSceneIndex((i) => Math.min(i + 1, scenes.length - 1))}
        onSkip={exit}
        onFinish={exit}
      />
    </PageChrome>
  );
}

function HomePageLive({
  hideBrandHeader,
  onToggleMode,
  onGoToTracking,
  historyConsultStep = null,
  onConsultStepChange,
}: {
  hideBrandHeader?: boolean;
  onToggleMode?: () => void;
  onGoToTracking?: (lifeEventId: string | null) => void;
  historyConsultStep?: IntakeUiStep | null;
  onConsultStepChange?: (step: IntakeUiStep) => void;
}) {
  const [description, setDescription] = useState("");
  const [hasStarted, setHasStarted] = useState(false);
  const [connection, setConnection] = useState<BackendConnectionState>("checking");
  const [reviewStep, setReviewStep] = useState<IntakeUiStep | null>(null);
  const [resultGatePassed, setResultGatePassed] = useState(false);
  const [cachedQuestionGroups, setCachedQuestionGroups] = useState<
    SessionSnapshot["questionGroups"]
  >([]);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);
  const naturalStepRef = useRef<IntakeUiStep>("landing");
  const applyingHistoryRef = useRef(false);

  const {
    snapshot,
    status,
    errorCode,
    eventNotRecognized,
    describeEvent,
    confirmEvent,
    answerFields,
    answerChatTurn,
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

  useEffect(() => {
    if ((snapshot?.questionGroups.length ?? 0) > 0) {
      setCachedQuestionGroups(snapshot!.questionGroups);
    }
  }, [snapshot]);

  const naturalStep = deriveUiStep(snapshot, hasStarted);
  const awaitingResultConfirm = naturalStep === "result" && !resultGatePassed;
  // 進度上的「目前步驟」（history／回看用）；畫面上閘門仍留在 questions。
  const progressStep: IntakeUiStep = awaitingResultConfirm ? "ready" : naturalStep;
  const displayStep: IntakeUiStep = awaitingResultConfirm ? "questions" : naturalStep;
  const uiStep = reviewStep ?? displayStep;
  const isReviewing = reviewStep !== null && reviewStep !== progressStep;
  const showResultGate = awaitingResultConfirm && !isReviewing;
  const historyStep: IntakeUiStep = isReviewing ? uiStep : progressStep;

  useEffect(() => {
    if (naturalStep !== "result") {
      setResultGatePassed(false);
    }
  }, [naturalStep]);

  useEffect(() => {
    if (naturalStep !== naturalStepRef.current) {
      naturalStepRef.current = naturalStep;
      if (!applyingHistoryRef.current) {
        setReviewStep(null);
      }
    }
  }, [naturalStep]);

  useEffect(() => {
    if (uiStep !== "landing" && !showResultGate) {
      stepHeadingRef.current?.focus();
    }
  }, [uiStep, showResultGate]);

  useEffect(() => {
    if (!applyingHistoryRef.current) {
      onConsultStepChange?.(historyStep);
    }
    applyingHistoryRef.current = false;
  }, [historyStep, onConsultStepChange]);

  useEffect(() => {
    if (historyConsultStep == null) {
      return;
    }
    applyingHistoryRef.current = true;
    const target = historyConsultStep;
    const natural = deriveUiStep(snapshot, hasStarted || target !== "landing");
    const gatedNatural: IntakeUiStep =
      natural === "result" && !resultGatePassed ? "ready" : natural;
    const targetIndex = STEP_ORDER.indexOf(target);
    const naturalIndex = STEP_ORDER.indexOf(gatedNatural);

    if (target === "landing") {
      setHasStarted(false);
      setReviewStep(null);
      setResultGatePassed(false);
      return;
    }

    setHasStarted(true);

    if (natural === "result" && target === "ready") {
      setResultGatePassed(false);
      setReviewStep(null);
      return;
    }

    if (natural === "result" && target === "result") {
      setResultGatePassed(true);
      setReviewStep(null);
      return;
    }

    // history 的 ready 對應畫面上的 questions＋閘門
    if (target === "questions" && gatedNatural === "ready") {
      setResultGatePassed(false);
      setReviewStep("questions");
      return;
    }

    if (target === gatedNatural || targetIndex >= naturalIndex) {
      setReviewStep(null);
      return;
    }
    setReviewStep(target);
  }, [historyConsultStep, snapshot, hasStarted, resultGatePassed]);

  const busy = status === "working";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = description.trim();
    if (trimmed.length === 0 || trimmed.length > MAX_LIFE_EVENT_TEXT_LENGTH || busy) {
      return;
    }
    await describeEvent(trimmed);
  }

  async function handleReset() {
    setDescription("");
    setHasStarted(false);
    setReviewStep(null);
    setResultGatePassed(false);
    setCachedQuestionGroups([]);
    await resetSession();
  }

  async function handleRedescribe() {
    setReviewStep(null);
    await confirmEvent(false);
    setDescription("");
    inputRef.current?.focus();
  }

  function handleBack() {
    const prev = previousUiStep(uiStep);
    if (prev === null || busy) {
      return;
    }

    // 仍在後端「確認事件」狀態時，上一步用正式拒絕確認回到描述。
    if (uiStep === "confirm" && naturalStep === "confirm" && !isReviewing) {
      void handleRedescribe();
      return;
    }

    // 尚無 session 的描述頁 → 說明頁
    if (uiStep === "describe" && naturalStep === "describe" && snapshot === null) {
      setHasStarted(false);
      return;
    }

    // 結果頁回到對話閘門：收回「已通過」狀態
    if (uiStep === "result") {
      setResultGatePassed(false);
      setReviewStep(null);
      return;
    }

    // 對話閘門中按上一頁 → 回看問題（或沒有問題時回確認）
    if (showResultGate) {
      if (
        (snapshot?.questionGroups.length ?? 0) === 0 &&
        cachedQuestionGroups.length === 0
      ) {
        setReviewStep("confirm");
        return;
      }
      setReviewStep("questions");
      return;
    }

    setReviewStep(prev);
  }

  return (
    <PageChrome
      hideBrandHeader={hideBrandHeader}
      modeToggle={
        onToggleMode && uiStep === "landing" ? (
          <ModeToggle mode="live" onToggle={onToggleMode} />
        ) : null
      }
      footerExtra={<BackendStatusLine state={connection} />}
    >
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
        isReviewing={isReviewing}
        cachedQuestionGroups={cachedQuestionGroups}
        onStart={() => setHasStarted(true)}
        onSubmitDescribe={(event) => void handleSubmit(event)}
        onExampleSelect={(prompt) => {
          setDescription(prompt);
          inputRef.current?.focus();
        }}
        onConfirm={(eventIds) => void confirmEvent(true, eventIds)}
        onRedescribe={() => void handleRedescribe()}
        onAnswerFields={(answers) => void answerFields(answers)}
        onAnswerChatTurn={(text) => answerChatTurn(text)}
        groupResultsByAudience={snapshotLifeEvents(snapshot).includes(
          "occupational_injury",
        )}
        onReset={() => void handleReset()}
        showResultGate={showResultGate}
        onViewResults={() => {
          setReviewStep(null);
          setResultGatePassed(true);
        }}
        onGoToTracking={onGoToTracking}
        onBack={uiStep === "landing" ? undefined : handleBack}
        onReturnToCurrent={() => setReviewStep(null)}
        sessionId={snapshot?.sessionId ?? null}
        inputRef={inputRef}
        stepHeadingRef={stepHeadingRef}
      />
    </PageChrome>
  );
}

export function HomePageAlt({
  mode = "live",
  onExitDemo,
  onToggleMode,
  onGoToTracking,
  hideBrandHeader = false,
  historyConsultStep = null,
  historyDemoSceneIndex = null,
  onConsultStepChange,
  onDemoSceneIndexChange,
}: HomePageAltProps) {
  if (mode === "demo") {
    return (
      <HomePageDemo
        hideBrandHeader={hideBrandHeader}
        onExitDemo={onExitDemo}
        onToggleMode={onToggleMode}
        onGoToTracking={onGoToTracking}
        historyDemoSceneIndex={historyDemoSceneIndex}
        onDemoSceneIndexChange={onDemoSceneIndexChange}
      />
    );
  }
  return (
    <HomePageLive
      hideBrandHeader={hideBrandHeader}
      onToggleMode={onToggleMode}
      onGoToTracking={onGoToTracking}
      historyConsultStep={historyConsultStep}
      onConsultStepChange={onConsultStepChange}
    />
  );
}
