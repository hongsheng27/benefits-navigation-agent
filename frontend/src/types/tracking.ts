/**
 * 使用者「追蹤進度」案件的前端形狀。
 *
 * 目前由 mock 提供；之後若後端有案件 API，請對齊此契約或同步更新。
 */

export type CaseOverallStatus = "in_progress" | "paused" | "completed";

export type FlowStepStatus = "done" | "current" | "pending" | "skipped";

export type DocumentPrepStatus =
  | "not_started"
  | "preparing"
  | "ready"
  | "submitted";

export type TrackedFlowStep = {
  stepId: string;
  label: string;
  status: FlowStepStatus;
  /** 簡短說明這一步在做什麼。 */
  detail?: string;
};

export type TrackedDocument = {
  documentId: string;
  name: string;
  status: DocumentPrepStatus;
  note?: string;
};

export type TrackedCase = {
  caseId: string;
  /** 顯示用標題，例如「配偶過世 — 補助與手續」。 */
  title: string;
  lifeEventId: string;
  lifeEventLabel: string;
  overallStatus: CaseOverallStatus;
  startedAt: string;
  updatedAt: string;
  /** 諮詢／辦理流程步驟。 */
  flowSteps: TrackedFlowStep[];
  /** 文件準備清單。 */
  documents: TrackedDocument[];
  /** 相關補助或行政事項名稱。 */
  relatedItems: string[];
  /** 建議使用者下一步做什麼。 */
  nextAction: string;
  /** 受理或相關機關（顯示用）。 */
  agencies: string[];
};

/**
 * 結果頁「加入追蹤」的單一補助／手續項目。
 * 存在 localStorage；與案件級 TrackedCase 並存。
 */
export type TrackedBenefitItem = {
  itemId: string;
  name: string;
  categoryLabel: string;
  lifeEventId: string;
  lifeEventLabel: string;
  agency?: string;
  nextAction?: string;
  addedAt: string;
};
