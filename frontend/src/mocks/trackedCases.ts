import type { TrackedCase } from "../types/tracking";

/** 追蹤進度頁的示範案件（離線假資料）。 */
export const MOCK_TRACKED_CASES: TrackedCase[] = [
  {
    caseId: "case_spouse_20260728",
    title: "配偶過世 — 補助與手續",
    lifeEventId: "spouse_death",
    lifeEventLabel: "配偶過世",
    overallStatus: "in_progress",
    startedAt: "2026-07-28T09:20:00Z",
    updatedAt: "2026-08-01T08:15:00Z",
    nextAction: "準備死亡證明文件影本，並確認勞保喪葬給付線上申請入口。",
    agencies: ["勞動部勞工保險局", "戶政事務所", "衛生福利部中央健康保險署"],
    relatedItems: ["死亡登記", "喪葬給付", "遺屬年金", "健保身分變更"],
    flowSteps: [
      {
        stepId: "describe",
        label: "說明發生的事",
        status: "done",
        detail: "已確認為配偶過世",
      },
      {
        stepId: "questions",
        label: "回答必要條件",
        status: "done",
        detail: "投保身分、未成年子女等已填",
      },
      {
        stepId: "review_results",
        label: "查看可辦項目",
        status: "done",
      },
      {
        stepId: "prepare_docs",
        label: "準備申請文件",
        status: "current",
        detail: "尚有 2 份文件未備妥",
      },
      {
        stepId: "apply",
        label: "向機關送件／申請",
        status: "pending",
      },
      {
        stepId: "follow_up",
        label: "追蹤審查結果",
        status: "pending",
      },
    ],
    documents: [
      {
        documentId: "doc_death_cert",
        name: "死亡證明文件",
        status: "ready",
        note: "已向醫院取得",
      },
      {
        documentId: "doc_household",
        name: "戶口名簿或戶籍謄本",
        status: "preparing",
        note: "預計本週至戶政申請",
      },
      {
        documentId: "doc_bank",
        name: "申請人金融帳戶資料",
        status: "not_started",
      },
      {
        documentId: "doc_relationship",
        name: "親屬關係證明（如需要）",
        status: "not_started",
      },
    ],
  },
  {
    caseId: "case_jobloss_20260715",
    title: "被資遣 — 失業相關協助",
    lifeEventId: "job_loss",
    lifeEventLabel: "失業／被資遣",
    overallStatus: "paused",
    startedAt: "2026-07-15T14:00:00Z",
    updatedAt: "2026-07-20T11:30:00Z",
    nextAction: "確認非自願離職證明是否齊全後，再繼續失業給付諮詢。",
    agencies: ["勞動部勞動力發展署", "公立就業服務機構"],
    relatedItems: ["失業給付", "職業訓練生活津貼"],
    flowSteps: [
      {
        stepId: "describe",
        label: "說明發生的事",
        status: "done",
      },
      {
        stepId: "questions",
        label: "回答必要條件",
        status: "current",
        detail: "尚缺離職原因相關說明",
      },
      {
        stepId: "review_results",
        label: "查看可辦項目",
        status: "pending",
      },
      {
        stepId: "prepare_docs",
        label: "準備申請文件",
        status: "pending",
      },
      {
        stepId: "apply",
        label: "向機關送件／申請",
        status: "pending",
      },
    ],
    documents: [
      {
        documentId: "doc_severance",
        name: "非自願離職證明",
        status: "preparing",
      },
      {
        documentId: "doc_labor_insurance",
        name: "勞保投保資料",
        status: "not_started",
      },
    ],
  },
  {
    caseId: "case_ltc_20260601",
    title: "長照需求 — 服務與補助",
    lifeEventId: "long_term_care_need",
    lifeEventLabel: "長照需求",
    overallStatus: "completed",
    startedAt: "2026-06-01T10:00:00Z",
    updatedAt: "2026-06-28T16:45:00Z",
    nextAction: "此案諮詢流程已結束。若情況有變，可再開始新的諮詢。",
    agencies: ["衛生福利部", "縣市長照管理中心"],
    relatedItems: ["長照服務給付及支付", "照顧服務"],
    flowSteps: [
      { stepId: "describe", label: "說明發生的事", status: "done" },
      { stepId: "questions", label: "回答必要條件", status: "done" },
      { stepId: "review_results", label: "查看可辦項目", status: "done" },
      { stepId: "prepare_docs", label: "準備申請文件", status: "done" },
      { stepId: "apply", label: "向機關聯繫／申請", status: "done" },
      { stepId: "follow_up", label: "追蹤服務安排", status: "done" },
    ],
    documents: [
      {
        documentId: "doc_id",
        name: "身分證明文件",
        status: "submitted",
      },
      {
        documentId: "doc_assessment",
        name: "長照需要評估相關資料",
        status: "submitted",
      },
    ],
  },
];
