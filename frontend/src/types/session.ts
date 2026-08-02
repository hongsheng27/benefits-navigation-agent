/**
 * Session API 的資料形狀，對應後端的 `backend/app/schemas/session.py`。
 *
 * 兩邊手寫維護，並由 `backend/tests/unit/test_session_schemas.py` 檢查是否走鐘。
 * 改動任何一邊時請同步另一邊。
 *
 * 這裡只放形狀，不放給人看的文字。畫面上的題目文案、選項文字、錯誤訊息都由前端
 * 提供，後端只給代號 —— 這樣新增一個資格欄位時不需要動後端邏輯，也讓文案由負責
 * 使用體驗的人掌握。
 */

/** 八個 workflow state。順序即正常路徑，中間三個會形成迴圈。 */
export type WorkflowState =
  | "understand_event"
  | "resolve_entitlements"
  | "collect_missing_fields"
  | "retrieve_rules"
  | "evaluate_eligibility"
  | "explain_result"
  | "confirm"
  | "complete";

/** 項目是可以申請的福利，還是必須辦理的行政事項。 */
export type ItemKind = "benefit" | "administrative";

/**
 * 單一項目的狀態。每個項目各自帶一個，所以同時有多項符合是正常情況。
 *
 * 其中四個由規則引擎產生：eligible、ineligible、needs_information、
 * needs_human_review。pending 是初始值，declined_by_user 來自使用者選擇。
 */
export type ItemStatus =
  | "pending"
  | "eligible"
  | "ineligible"
  | "needs_information"
  | "needs_human_review"
  | "declined_by_user";

/** 金額的發放性質。「5,000」與「每月 5,000」無法只從數字分辨。 */
export type AmountPeriod = "one_time" | "monthly" | "annual";

/** 整次諮詢提前結束的原因。項目層級的人工協助不在這裡，看 ItemStatus。 */
export type ExitReason =
  | "event_not_recognized"
  | "event_retry_limit_reached"
  | "loop_limit_reached"
  | "no_progress"
  | "user_requested_help";

/** 一個資格欄位接受哪一種值。之後由欄位登記表宣告。 */
export type AttributeValueKind = "code" | "boolean" | "band" | "integer";

/** 一筆去識別化的答案。 */
export type AttributeValue = boolean | number | string;

/**
 * 後端還沒實作、因此回應中相關內容為佔位資料的能力。
 *
 * 實作完成就會從回應的清單裡消失，前端不需要改程式。
 */
export type PendingCapability =
  | "life_event_extraction"
  | "entitlement_graph"
  | "state_machine"
  | "field_registry"
  | "rule_evaluation"
  | "official_citations"
  | "plain_language_explanation"
  | "action_plan"
  | "privacy_gate";

/**
 * 這份回應有多少是真的。
 *
 * `placeholderNotice` 是唯一由後端提供中文文字的欄位，違反「後端給代號、前端給文案」
 * 的分界。這是刻意的臨時例外，會在佔位資料移除時連同整個物件一起刪除。
 * 只有 `isMock` 為 true 時才有值。
 */
export type ImplementationNotice = {
  isMock: boolean;
  pending: PendingCapability[];
  placeholderNotice: string;
};

/** 錯誤代號。顯示文字由前端決定。 */
export type ErrorCode =
  | "session_not_found"
  | "session_expired"
  | "unknown_field"
  | "invalid_field_value"
  | "unknown_item"
  | "invalid_transition"
  /**
   * 無法把使用者的描述對應到已登記的事件。
   *
   * **這不是程式錯誤，不要顯示「系統發生錯誤」。** 請顯示「我們沒有看懂，
   * 可以換個說法嗎」之類的訊息，並讓使用者重新送一次 `life_event_text`。
   *
   * 後端刻意不區分「模型壞掉」與「描述看不懂」—— 對使用者而言下一步都一樣。
   */
  | "event_not_recognized"
  /** 諮詢後 grounded 說明暫時無法產生；前端可退回 stub。 */
  | "explanation_unavailable"
  | "internal_error";

/** 自由文字的長度上限，與後端的 MAX_LIFE_EVENT_TEXT_LENGTH 相同。 */
export const MAX_LIFE_EVENT_TEXT_LENGTH = 2000;

// ---------------------------------------------------------------------------
// 請求
// ---------------------------------------------------------------------------

/**
 * 畫面 1：描述發生了什麼事。
 *
 * 這是唯一帶自由文字的請求形狀。送出前應先在本機遮罩明顯的個資；後端抽出屬性後
 * 會丟棄原文，不存也不回傳。
 */
export type LifeEventTextInput = {
  kind: "life_event_text";
  text: string;
};

/** 畫面 2：確認或否認系統理解的事件。false 表示要重新描述。 */
export type EventConfirmationInput = {
  kind: "event_confirmation";
  confirmed: boolean;
  /** 確認時勾選的事件（1～5）；省略則沿用後端目前的 lifeEvents。 */
  eventIds?: string[];
};

/** 畫面 4 送出一組答案；畫面 7 修正答案也用這個形狀。鍵是欄位代號。 */
export type AttributeAnswersInput = {
  kind: "attribute_answers";
  answers: Record<string, AttributeValue>;
};

/** 畫面 4 對話模式：一句話補資格欄位（抽取後丟棄原文）。 */
export type AttributeChatTurnInput = {
  kind: "attribute_chat_turn";
  text: string;
};

/** 使用者選「這一項我不想辦」。 */
export type ItemDeclineInput = {
  kind: "item_decline";
  itemId: string;
};

/** 畫面 7：複查答案後確認，進入產生辦理清單。 */
export type ReviewConfirmationInput = {
  kind: "review_confirmation";
  confirmed: boolean;
};

/** 畫面 7：決定要不要轉介人工協助。 */
export type ReferralChoiceInput = {
  kind: "referral_choice";
  requested: boolean;
};

/** 使用者主動要求人工協助，隨時可送。 */
export type HelpRequestInput = {
  kind: "help_request";
};

/**
 * 推進一步時可以送的輸入。
 *
 * 自由文字只在 `life_event_text` 與 `attribute_chat_turn`；其餘為結構化輸入。
 */
export type AdvanceInput =
  | LifeEventTextInput
  | EventConfirmationInput
  | AttributeAnswersInput
  | AttributeChatTurnInput
  | ItemDeclineInput
  | ReviewConfirmationInput
  | ReferralChoiceInput
  | HelpRequestInput;

export type AdvanceRequest = {
  input: AdvanceInput;
};

// ---------------------------------------------------------------------------
// 回應
// ---------------------------------------------------------------------------

/** 畫面 5 顯示「差在這個條件：你的情況 X ／ 需要 Y」所需的三段。 */
export type DecisiveConditionView = {
  fieldId: string;
  expected: AttributeValue;
  actual: AttributeValue;
};

/** 完整結構化原因，與 DecisiveConditionView 並存 (additive compatibility)。 */
export type StructuredReasonView = {
  conditionId: string;
  fieldId: string;
  operator: string;
  expected: string;
  actual: string | null;
  label: string;
  sourceReference: string;
};

/** 官方依據。 */
export type CitationView = {
  documentId: string;
  title: string;
  publisherName: string;
  publishedAt: string | null;
  url: string;
  excerpt: string;
  effectiveAt: string | null;
  retrievedAt: string | null;
};

/** 一個候選項目對前端露出的部分。金額只有結構，文字由前端組。 */
export type ItemView = {
  itemId: string;
  kind: ItemKind;
  status: ItemStatus;

  programStatus: string | null;

  missingFieldIds: string[];
  decisiveConditions: DecisiveConditionView[];
  structuredReasons: StructuredReasonView[];
  citations: CitationView[];

  amountMin: number | null;
  amountMax: number | null;
  amountPeriod: AmountPeriod | null;
  amountCurrency: string | null;

  explanation: string | null;
  /** 複合情境時，此項目來自哪些 life event。 */
  sourceLifeEvents: string[];
};

/**
 * 一個問題的結構。
 *
 * purposeId 對應「為什麼問這個？」那段說明的代號，文字由前端提供。
 * optionIds 只在 valueKind 為 code 或 band 時有值。
 */
export type QuestionView = {
  fieldId: string;
  valueKind: AttributeValueKind;
  optionIds: string[];
  required: boolean;
  purposeId: string;
  unlocksItemIds: string[];
};

/** 一組同主題的問題。分組按主題而非按項目，避免同一題被問兩次。 */
export type QuestionGroupView = {
  topicId: string;
  questions: QuestionView[];
  groupIndex: number;
  groupTotal: number;
};

/** 一次諮詢在某個時間點的完整對外狀態。三個端點都回這個形狀。 */
export type SessionSnapshot = {
  sessionId: string;
  workflowState: WorkflowState;

  /** 進度顯示用。因為中間有迴圈，這個數字可能往回走。 */
  stepIndex: number;
  stepTotal: number;

  lifeEvent: string | null;
  /** 複合情境：建議或已確認的事件（最多 5）。lifeEvent 為第一筆相容欄位。 */
  lifeEvents: string[];
  /** 確認頁額外候補（最多 3），預設未勾選。 */
  extraCandidateLifeEvents: string[];

  /** 使用者答過的答案，畫面 7 複查時要顯示。 */
  attributes: Record<string, AttributeValue>;

  items: ItemView[];

  /** 欄位登記表完成前，後端會回空陣列。 */
  questionGroups: QuestionGroupView[];

  exitReason: ExitReason | null;
  referralRequested: boolean;

  /** 為 true 時輪詢應該繼續。 */
  isProcessing: boolean;

  /** 對話式補欄位的下一問（系統產生）。 */
  collectorQuestion: string | null;

  createdAt: string;
  expiresAt: string;

  /** 這份回應有多少是真的。實作完成後 pending 清單會逐項變短。 */
  implementation: ImplementationNotice;
};

/** 所有錯誤共用的形狀。三個欄位都不會包含使用者輸入的值。 */
export type ErrorResponse = {
  errorCode: ErrorCode;
  fieldIds: string[];
  currentState: WorkflowState | null;
};
