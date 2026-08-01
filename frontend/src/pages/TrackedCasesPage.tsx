import { useEffect, useState } from "react";

import { listTrackedCases } from "../api/trackingClient";
import styles from "../components/alt/alt.module.css";
import type {
  CaseOverallStatus,
  DocumentPrepStatus,
  FlowStepStatus,
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
  onViewAgencies,
}: {
  item: TrackedCase;
  onViewAgencies?: (trackedCase: TrackedCase) => void;
}) {
  const doneCount = item.flowSteps.filter((s) => s.status === "done").length;
  const readyDocs = item.documents.filter(
    (d) => d.status === "ready" || d.status === "submitted",
  ).length;

  return (
    <article className="border border-[#e0d8ca] bg-[#fdfbf7] px-5 py-6 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
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
};

export function TrackedCasesPage({ onViewAgencies }: TrackedCasesPageProps) {
  const [cases, setCases] = useState<TrackedCase[]>([]);
  const [isMock, setIsMock] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
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

  return (
    <div className={`${styles.page} min-h-[calc(100vh-4rem)] text-[#171513]`}>
      <main className="mx-auto w-full max-w-3xl px-5 py-10 sm:px-8 sm:py-14">
        <p className="text-[0.8rem] tracking-[0.08em] text-[#8b8377]">追蹤進度</p>
        <h1 className="mt-2 text-[1.6rem] font-semibold leading-[1.4] text-[#171513]">
          你正在處理的事
        </h1>
        <p className="mt-3 max-w-xl text-[0.95rem] leading-[1.9] text-[#5c564e]">
          這裡會留下每次諮詢對應的事件、流程走到哪、文件準備得如何，以及建議的下一步。
        </p>

        {isMock ? (
          <p className="mt-5 border-l-2 border-[#8a5a1a] bg-[#f6f1e6] px-4 py-3 text-[0.85rem] leading-[1.85] text-[#4a453d]">
            目前為示範資料。之後會改為讀取你真實的諮詢紀錄。
          </p>
        ) : null}

        {loading ? (
          <p className="mt-10 text-[0.9rem] text-[#8b8377]">正在載入……</p>
        ) : cases.length === 0 ? (
          <p className="mt-10 border border-dashed border-[#d8cfc0] px-4 py-8 text-[0.92rem] leading-[1.9] text-[#6b6459]">
            還沒有可追蹤的案件。可先到「新諮詢」說明你的情況。
          </p>
        ) : (
          <div className="mt-8 space-y-6">
            {cases.map((item) => (
              <CaseCard
                key={item.caseId}
                item={item}
                onViewAgencies={onViewAgencies}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
