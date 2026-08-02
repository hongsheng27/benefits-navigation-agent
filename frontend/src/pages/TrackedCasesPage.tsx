import { useEffect, useMemo, useRef, useState } from "react";

import { listTrackedCases } from "../api/trackingClient";
import styles from "../components/alt/alt.module.css";
import {
  addTrackedBenefitItem,
  advanceTrackedBenefitStep,
  clearTrackedBenefitItems,
  listPendingBenefitItems,
  listTrackedBenefitItems,
  removeTrackedBenefitItem,
  type PendingBenefitItem,
} from "../lib/trackingStore";
import type {
  CaseOverallStatus,
  DocumentPrepStatus,
  FlowStepStatus,
  TrackedBenefitItem,
  TrackedCase,
} from "../types/tracking";

const OVERALL_LABEL: Record<CaseOverallStatus, string> = {
  in_progress: "進行中",
  paused: "暫停",
  completed: "已完成",
};

const FLOW_LABEL: Record<FlowStepStatus, string> = {
  done: "已完成",
  current: "進行中",
  pending: "尚未開始",
  skipped: "已略過",
};

const DOC_LABEL: Record<DocumentPrepStatus, string> = {
  not_started: "尚未準備",
  preparing: "準備中",
  ready: "已備妥",
  submitted: "已送出",
};

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleDateString("zh-TW", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function OverallBadge({ status }: { status: CaseOverallStatus }) {
  const tone =
    status === "completed"
      ? "border-[#b7cfc4] bg-[#eef5f1] text-[#2f4f45]"
      : status === "paused"
        ? "border-[#e2d3b5] bg-[#f8f3ea] text-[#8a5a1a]"
        : "border-[#c9d6d0] bg-[#f1f4f0] text-[#2f4f45]";
  return (
    <span
      className={`rounded-sm border px-2.5 py-0.5 text-[0.78rem] font-semibold tracking-[0.04em] ${tone}`}
    >
      {OVERALL_LABEL[status]}
    </span>
  );
}

function CaseCard({
  item,
  highlighted,
  onViewAgencies,
}: {
  item: TrackedCase;
  highlighted?: boolean;
  onViewAgencies?: (trackedCase: TrackedCase) => void;
}) {
  const cardRef = useRef<HTMLElement>(null);
  const doneCount = item.flowSteps.filter((s) => s.status === "done").length;
  const readyDocs = item.documents.filter(
    (d) => d.status === "ready" || d.status === "submitted",
  ).length;

  useEffect(() => {
    if (highlighted && typeof cardRef.current?.scrollIntoView === "function") {
      cardRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [highlighted]);

  return (
    <article
      ref={cardRef}
      className={`border bg-[#fdfbf7] px-4 py-5 sm:px-6 sm:py-6 ${
        highlighted
          ? "border-[#2f4f45] shadow-[inset_3px_0_0_0_#2f4f45]"
          : "border-[#e0d8ca]"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {highlighted ? (
            <p className="mb-1 text-[0.78rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
              剛從諮詢過來的這筆
            </p>
          ) : null}
          <p className="text-[0.78rem] tracking-[0.06em] text-[#8b8377]">
            {item.lifeEventLabel}
          </p>
          <h2 className="mt-1 text-[1.15rem] font-semibold leading-[1.5] text-[#171513]">
            {item.title}
          </h2>
        </div>
        <OverallBadge status={item.overallStatus} />
      </div>

      <p className="mt-3 text-[0.9rem] leading-[1.9] text-[#4a453d]">
        <span className="font-semibold text-[#2f4f45]">下一步：</span>
        {item.nextAction}
      </p>

      <dl className="mt-4 grid gap-2 text-[0.82rem] leading-[1.8] text-[#6b6459] sm:grid-cols-2">
        <div>
          <dt className="inline text-[#8b8377]">開始於　</dt>
          <dd className="inline">{formatDate(item.startedAt)}</dd>
        </div>
        <div>
          <dt className="inline text-[#8b8377]">最近更新　</dt>
          <dd className="inline">{formatDate(item.updatedAt)}</dd>
        </div>
        <div>
          <dt className="inline text-[#8b8377]">流程進度　</dt>
          <dd className="inline">
            {doneCount}／{item.flowSteps.length} 步完成
          </dd>
        </div>
        <div>
          <dt className="inline text-[#8b8377]">文件備妥　</dt>
          <dd className="inline">
            {readyDocs}／{item.documents.length} 份
          </dd>
        </div>
      </dl>

      <section className="mt-6">
        <h3 className="text-[0.88rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
          辦理流程
        </h3>
        <ol className="mt-3 space-y-2">
          {item.flowSteps.map((step, index) => {
            const marker =
              step.status === "done"
                ? "bg-[#2f4f45] text-[#f7f4ee]"
                : step.status === "current"
                  ? "border border-[#2f4f45] bg-[#f1f4f0] text-[#2f4f45]"
                  : "border border-[#d8cfc0] bg-[#f7f4ee] text-[#8b8377]";
            return (
              <li key={step.stepId} className="flex gap-3">
                <span
                  className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-[0.72rem] font-semibold ${marker}`}
                >
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <p className="text-[0.92rem] font-semibold text-[#171513]">
                    {step.label}
                    <span className="ml-2 text-[0.78rem] font-normal text-[#8b8377]">
                      {FLOW_LABEL[step.status]}
                    </span>
                  </p>
                  {step.detail ? (
                    <p className="mt-0.5 text-[0.82rem] leading-[1.8] text-[#6b6459]">
                      {step.detail}
                    </p>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      </section>

      <section className="mt-6">
        <h3 className="text-[0.88rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
          文件準備
        </h3>
        <ul className="mt-3 divide-y divide-[#eee7db] border border-[#e8e0d2]">
          {item.documents.map((doc) => (
            <li
              key={doc.documentId}
              className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-3"
            >
              <div>
                <p className="text-[0.9rem] text-[#171513]">{doc.name}</p>
                {doc.note ? (
                  <p className="mt-0.5 text-[0.8rem] text-[#8b8377]">{doc.note}</p>
                ) : null}
              </div>
              <span className="text-[0.78rem] tracking-[0.04em] text-[#6b6459]">
                {DOC_LABEL[doc.status]}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-6 grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="text-[0.88rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
            相關項目
          </h3>
          <ul className="mt-2 flex flex-wrap gap-2">
            {item.relatedItems.map((name) => (
              <li
                key={name}
                className="rounded-sm border border-[#d8cfc0] px-2.5 py-1 text-[0.8rem] text-[#4a453d]"
              >
                {name}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-[0.88rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
            相關機關
          </h3>
          <ul className="mt-2 space-y-1 text-[0.88rem] leading-[1.8] text-[#4a453d]">
            {item.agencies.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </div>
      </section>

      {onViewAgencies ? (
        <div className="mt-6">
          <button
            type="button"
            onClick={() => onViewAgencies(item)}
            className="rounded-sm border border-[#2f4f45] bg-transparent px-4 py-2.5 text-[0.88rem] font-semibold text-[#2f4f45] transition-colors hover:bg-[#2f4f45] hover:text-[#f7f4ee] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
          >
            查看此情況相關機關
          </button>
        </div>
      ) : null}
    </article>
  );
}

type TrackedCasesPageProps = {
  onViewAgencies?: (trackedCase: TrackedCase) => void;
  /** 從諮詢結果帶過來時，高亮對應 lifeEvent 的案件。 */
  highlightLifeEventId?: string | null;
  onStartConsult?: () => void;
};

function BenefitItemCard({
  item,
  mode,
  onAdd,
  onRemove,
  onAdvanceStep,
}: {
  item: TrackedBenefitItem | PendingBenefitItem;
  mode: "tracked" | "pending";
  onAdd?: () => void;
  onRemove?: () => void;
  onAdvanceStep?: () => void;
}) {
  const isTracked = mode === "tracked" && "flowSteps" in item;
  const flowSteps = isTracked ? item.flowSteps : [];
  const completedStepCount = isTracked ? item.completedStepCount : 0;
  const totalSteps = flowSteps.length;
  const progressRatio = totalSteps > 0 ? completedStepCount / totalSteps : 0;
  const allDone = isTracked && totalSteps > 0 && completedStepCount >= totalSteps;
  const currentStep = isTracked ? flowSteps[completedStepCount] : null;

  return (
    <article className="border border-[#e0d8ca] bg-[#fdfbf7] px-4 py-5 sm:px-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[1.05rem] font-semibold text-[#171513]">{item.name}</h3>
        <span className="rounded-sm border border-[#d8cfc0] px-2 py-0.5 text-[0.75rem] text-[#6b6459]">
          {item.categoryLabel}
        </span>
      </div>
      <p className="mt-2 text-[0.88rem] leading-[1.85] text-[#5c564e]">
        相關情況：{item.lifeEventLabel}
        {item.agency ? ` · ${item.agency}` : ""}
      </p>
      {"nextAction" in item && item.nextAction ? (
        <p className="mt-2 text-[0.88rem] leading-[1.85] text-[#4a453d]">
          {item.nextAction}
        </p>
      ) : null}

      {isTracked && totalSteps > 0 ? (
        <section className="mt-4" aria-label="辦理進度">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h4 className="text-[0.88rem] font-semibold tracking-[0.04em] text-[#2f4f45]">
              辦理進度
            </h4>
            <p className="text-[0.78rem] text-[#6b6459]">
              {allDone
                ? `全部 ${totalSteps} 步已完成`
                : `第 ${completedStepCount + 1}／${totalSteps} 步`}
            </p>
          </div>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-[#e8e0d2]"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={totalSteps}
            aria-valuenow={completedStepCount}
            aria-label={`${item.name} 進度 ${completedStepCount}／${totalSteps}`}
          >
            <div
              className="h-full rounded-full bg-[#2f4f45] transition-[width] duration-500 ease-out"
              style={{ width: `${Math.round(progressRatio * 100)}%` }}
            />
          </div>
          <ol className="mt-4 space-y-2">
            {flowSteps.map((step, index) => {
              const done = index < completedStepCount;
              const current = index === completedStepCount && !allDone;
              const marker = done
                ? "bg-[#2f4f45] text-[#f7f4ee]"
                : current
                  ? "border-2 border-[#2f4f45] bg-[#f1f4f0] text-[#2f4f45] shadow-[0_0_0_3px_rgba(47,79,69,0.12)]"
                  : "border border-[#d8cfc0] bg-[#f7f4ee] text-[#8b8377]";
              return (
                <li
                  key={step.stepId}
                  className={`flex gap-3 rounded-sm px-2 py-2 transition-colors duration-300 ${
                    current ? "bg-[#f1f4f0]" : ""
                  }`}
                >
                  <span
                    className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-[0.72rem] font-semibold transition-all duration-300 ${marker}`}
                  >
                    {done ? "✓" : index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className={`text-[0.9rem] font-semibold ${
                        current
                          ? "text-[#2f4f45]"
                          : done
                            ? "text-[#5c564e]"
                            : "text-[#8b8377]"
                      }`}
                    >
                      {step.label}
                      <span className="ml-2 text-[0.75rem] font-normal text-[#8b8377]">
                        {done ? "已完成" : current ? "進行中" : "待辦"}
                      </span>
                    </p>
                    {current && onAdvanceStep ? (
                      <button
                        type="button"
                        onClick={onAdvanceStep}
                        className="mt-2 rounded-sm bg-[#2f4f45] px-3.5 py-1.5 text-[0.82rem] font-semibold text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
                      >
                        已完成
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
          {allDone ? (
            <p className="mt-3 text-[0.85rem] leading-[1.8] text-[#2f4f45]">
              這項已走完目前整理的步驟。若還要辦別的，可繼續看其他追蹤項目。
            </p>
          ) : currentStep ? (
            <p className="sr-only">目前步驟：{currentStep.label}</p>
          ) : null}
        </section>
      ) : null}

      {mode === "pending" && onAdd ? (
        <button
          type="button"
          onClick={onAdd}
          className="mt-4 rounded-sm border border-[#2f4f45] bg-transparent px-4 py-2 text-[0.85rem] font-semibold text-[#2f4f45] transition-colors hover:bg-[#2f4f45] hover:text-[#f7f4ee]"
        >
          加入追蹤
        </button>
      ) : null}
      {mode === "tracked" ? (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          {"addedAt" in item ? (
            <p className="text-[0.78rem] text-[#8b8377]">
              加入於 {formatDate(item.addedAt)}
            </p>
          ) : null}
          {onRemove ? (
            <button
              type="button"
              onClick={onRemove}
              className="text-[0.82rem] font-semibold text-[#6b6459] underline decoration-[#cfc5b4] underline-offset-2 hover:text-[#2f4f45] hover:decoration-[#2f4f45]"
            >
              取消追蹤
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export function TrackedCasesPage({
  onViewAgencies,
  highlightLifeEventId = null,
  onStartConsult,
}: TrackedCasesPageProps) {
  const [cases, setCases] = useState<TrackedCase[]>([]);
  const [trackedItems, setTrackedItems] = useState<TrackedBenefitItem[]>([]);
  const [pendingItems, setPendingItems] = useState<PendingBenefitItem[]>([]);
  const [isMock, setIsMock] = useState(true);
  const [loading, setLoading] = useState(true);

  function refreshLocalTracking() {
    setTrackedItems(listTrackedBenefitItems());
    setPendingItems(listPendingBenefitItems());
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    refreshLocalTracking();
    listTrackedCases(controller.signal)
      .then((response) => {
        if (!controller.signal.aborted) {
          setCases(response.cases);
          setIsMock(response.isMock);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setCases([]);
          setIsMock(true);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  // 後端案件 API 未就緒（isMock）時不渲染假案件；只顯示本機「加入追蹤」項目。
  const sortedCases = useMemo(() => {
    if (isMock) {
      return [];
    }
    return [...cases].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
  }, [cases, isMock]);

  const hasTracked = trackedItems.length > 0 || sortedCases.length > 0;
  const hasPending = pendingItems.length > 0;
  const isEmpty = !loading && !hasTracked && !hasPending;

  return (
    <div className={`${styles.page} min-h-[calc(100vh-4rem)] text-[#171513]`}>
      <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-8 sm:py-14">
        <p className="text-[0.8rem] tracking-[0.08em] text-[#8b8377]">追蹤進度</p>
        <h1 className="mt-2 text-[1.45rem] font-semibold leading-[1.4] text-[#171513] sm:text-[1.6rem]">
          你正在處理的事
        </h1>
        <p className="mt-3 max-w-xl text-[0.92rem] leading-[1.9] text-[#5c564e] sm:text-[0.95rem]">
          這裡只顯示你從結果頁「加入追蹤」的項目；本輪諮詢還沒加入的，會出現在「待追蹤」。
        </p>

        {loading ? (
          <p className="mt-10 text-[0.9rem] text-[#8b8377]">正在載入……</p>
        ) : isEmpty ? (
          <div className="mt-8 border border-dashed border-[#d8cfc0] bg-[#fdfbf7] px-4 py-8 sm:px-6">
            <h2 className="text-[1.05rem] font-semibold text-[#171513]">
              還沒有可追蹤的案件
            </h2>
            <p className="mt-3 text-[0.92rem] leading-[1.9] text-[#5c564e]">
              完成一次「新諮詢」後，可在結果頁把項目加入追蹤，之後回來接著辦。
            </p>
            {onStartConsult ? (
              <button
                type="button"
                onClick={onStartConsult}
                className="mt-6 rounded-sm bg-[#2f4f45] px-5 py-2.5 text-[0.92rem] font-semibold tracking-[0.04em] text-[#f7f4ee] transition-colors hover:bg-[#254038] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f4f45]"
              >
                開始新諮詢
              </button>
            ) : (
              <p className="mt-4 text-[0.88rem] text-[#6b6459]">
                請先到上方的「新諮詢」說明你的情況。
              </p>
            )}
          </div>
        ) : (
          <div className="mt-8 space-y-10">
            {hasTracked ? (
              <section>
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <h2 className="text-[1.1rem] font-semibold text-[#2f4f45]">
                      追蹤中
                    </h2>
                    <p className="mt-1 text-[0.85rem] text-[#6b6459]">
                      只會顯示你曾按過「加入追蹤」的項目（存在這個瀏覽器裡）。
                    </p>
                  </div>
                  {trackedItems.length > 0 ? (
                    <button
                      type="button"
                      onClick={() => {
                        clearTrackedBenefitItems();
                        refreshLocalTracking();
                      }}
                      className="text-[0.82rem] font-semibold text-[#6b6459] underline decoration-[#cfc5b4] underline-offset-2 hover:text-[#2f4f45] hover:decoration-[#2f4f45]"
                    >
                      清空全部追蹤
                    </button>
                  ) : null}
                </div>
                <div className="mt-4 space-y-4">
                  {trackedItems.map((item) => (
                    <BenefitItemCard
                      key={`tracked-${item.itemId}`}
                      item={item}
                      mode="tracked"
                      onAdvanceStep={() => {
                        advanceTrackedBenefitStep(item.itemId);
                        refreshLocalTracking();
                      }}
                      onRemove={() => {
                        removeTrackedBenefitItem(item.itemId);
                        refreshLocalTracking();
                      }}
                    />
                  ))}
                  {sortedCases.map((item) => (
                    <CaseCard
                      key={item.caseId}
                      item={item}
                      highlighted={
                        highlightLifeEventId !== null &&
                        item.lifeEventId === highlightLifeEventId
                      }
                      onViewAgencies={onViewAgencies}
                    />
                  ))}
                </div>
              </section>
            ) : null}

            {hasPending ? (
              <section>
                <h2 className="text-[1.1rem] font-semibold text-[#8a5a1a]">
                  待追蹤
                </h2>
                <p className="mt-1 text-[0.85rem] text-[#6b6459]">
                  本輪諮詢整理出的項目，尚未加入追蹤。
                </p>
                <div className="mt-4 space-y-4">
                  {pendingItems.map((item) => (
                    <BenefitItemCard
                      key={`pending-${item.itemId}`}
                      item={item}
                      mode="pending"
                      onAdd={() => {
                        addTrackedBenefitItem({
                          itemId: item.itemId,
                          name: item.name,
                          categoryLabel: item.categoryLabel,
                          lifeEventId: item.lifeEventId,
                          lifeEventLabel: item.lifeEventLabel,
                          agency: item.agency,
                        });
                        refreshLocalTracking();
                      }}
                    />
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        )}
      </main>
    </div>
  );
}
