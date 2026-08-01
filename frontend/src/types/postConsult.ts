/**
 * 諮詢結束後的「相關法條／申請解說」面板資料形狀。
 *
 * 第一版以前端 fixture 為主；之後可對到官方 citations／action_plan API。
 * Copilot 只負責說明，不做資格判定。
 */

export type PostConsultPanelKind = "related_provisions" | "application_guide";

/** 一則可展示的法條／官方依據摘錄。 */
export type RelatedProvision = {
  provisionId: string;
  title: string;
  /** 法規或計畫名稱（若與 title 相同可重複）。 */
  lawName: string;
  /** 例如「三、申請條件」；沒有條號時為 null。 */
  articleLabel: string | null;
  publisherName: string;
  sourceUrl: string;
  excerpt: string;
  /** 預先寫好的白話摘要，供 Copilot 開場使用。 */
  plainLanguageSummary: string;
  /** 目前來源為 discovery candidate，尚未人工核對。 */
  reviewStatus: "candidate";
  relatedItemIds: string[];
  lifeEventIds: string[];
};

export type ApplicationStep = {
  stepId: string;
  title: string;
  description: string;
  requiredDocuments: string[];
  agencyName: string | null;
  deadlineNote: string | null;
  tips: string[];
};

export type ApplicationGuide = {
  guideId: string;
  lifeEventId: string;
  title: string;
  overview: string;
  steps: ApplicationStep[];
  disclaimer: string;
};

export type CopilotRole = "assistant" | "user";

export type CopilotMessage = {
  id: string;
  role: CopilotRole;
  content: string;
};

/** 送給後端／模型的一筆參考資料。 */
export type CopilotReference = {
  title: string;
  body: string;
  sourceUrl?: string | null;
};

export type CopilotContext = {
  kind: PostConsultPanelKind;
  lifeEventId: string | null;
  lifeEventLabel: string;
  provisionTitles: string[];
  guideTitle: string | null;
  /** 提問時一併送給 LLM 的參考摘錄或步驟內容。 */
  references: CopilotReference[];
};
