/**
 * 正式諮詢 UI 的唯讀示範腳本。
 *
 * 用「配偶過世」走完 landing → 描述 → 確認 → 問題 → 結果，
 * 不呼叫後端，也不讓使用者改答案。
 */

import type { AttributeValue, SessionSnapshot } from "../types/session";

/** 與正式諮詢 HomePageAlt 的步驟一致。 */
export type IntakeDemoStep =
  | "landing"
  | "describe"
  | "confirm"
  | "questions"
  | "result";

export type IntakeDemoScene = {
  step: IntakeDemoStep;
  /** 旁白：說明這一步在正式流程裡會發生什麼。 */
  narration: string;
  description?: string;
  snapshot?: SessionSnapshot | null;
  /** 問題步驟預先選好的答案（僅示範用）。 */
  answers?: Record<string, AttributeValue>;
};

const DEMO_BASE: Omit<
  SessionSnapshot,
  "workflowState" | "lifeEvent" | "attributes" | "items" | "questionGroups" | "stepIndex"
> = {
  sessionId: "sess_demo_walkthrough",
  stepTotal: 8,
  lifeEvents: [],
  extraCandidateLifeEvents: [],
  exitReason: null,
  referralRequested: false,
  isProcessing: false,
  collectorQuestion: null,
  createdAt: "2026-08-01T00:00:00Z",
  expiresAt: "2026-08-01T02:00:00Z",
  implementation: {
    isMock: true,
    pending: ["rule_evaluation"],
    placeholderNotice: "示範資料",
  },
};

const QUESTION_GROUPS: SessionSnapshot["questionGroups"] = [
  {
    topicId: "location",
    groupIndex: 1,
    groupTotal: 3,
    questions: [
      {
        fieldId: "applicant_jurisdiction",
        valueKind: "code",
        optionIds: ["TPE", "NWT", "TAO", "PEN", "OTHER_TW", "unsure"],
        required: true,
        purposeId: "applicant_jurisdiction.purpose",
        unlocksItemIds: [
          "death_registration",
          "funeral_benefit",
          "survivor_pension",
          "health_insurance_change",
        ],
      },
    ],
  },
  {
    topicId: "deceased_insurance",
    groupIndex: 2,
    groupTotal: 3,
    questions: [
      {
        fieldId: "deceased_insurance_type",
        valueKind: "code",
        optionIds: [
          "labor_insurance",
          "national_pension",
          "farmers_insurance",
          "civil_service_insurance",
          "none_or_unsure",
        ],
        required: true,
        purposeId: "deceased_insurance_type.purpose",
        unlocksItemIds: ["funeral_benefit", "survivor_pension"],
      },
    ],
  },
  {
    topicId: "family_situation",
    groupIndex: 3,
    groupTotal: 3,
    questions: [
      {
        fieldId: "has_dependent_children",
        valueKind: "boolean",
        optionIds: [],
        required: true,
        purposeId: "has_dependent_children.purpose",
        unlocksItemIds: ["survivor_pension"],
      },
    ],
  },
];

const RESULT_ITEMS: SessionSnapshot["items"] = [
  {
    itemId: "death_registration",
    kind: "administrative",
    status: "eligible",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    explanation: "戶政死亡登記通常要先辦，後面許多給付才接得上。",
  },
  {
    itemId: "funeral_benefit",
    kind: "benefit",
    status: "needs_human_review",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    explanation: "依過世者投保身分，可能可向對應機關申請喪葬給付。",
  },
  {
    itemId: "survivor_pension",
    kind: "benefit",
    status: "needs_information",
    missingFieldIds: ["applicant_age_band"],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    explanation: "有未成年子女時，遺屬年金條件可能不同，送件前建議再確認。",
  },
];

export const DEMO_DESCRIPTION =
  "配偶過世一個月了，想確認還有哪些給付來得及申請。";

export const DEMO_ANSWERS: Record<string, AttributeValue> = {
  applicant_jurisdiction: "TPE",
  deceased_insurance_type: "labor_insurance",
  has_dependent_children: true,
};

export const INTAKE_DEMO_SCENES: readonly IntakeDemoScene[] = [
  {
    step: "landing",
    narration: "接下來用「配偶過世」這個例子，帶你看正式諮詢會經過哪些畫面。",
    snapshot: null,
  },
  {
    step: "describe",
    narration: "正式使用時，會請你用自己的話描述發生的事。示範已預先填好一句話。",
    description: DEMO_DESCRIPTION,
    snapshot: null,
  },
  {
    step: "confirm",
    narration: "系統會先說出它理解的情況，請你確認對不對，避免後面問到不相干的問題。",
    snapshot: {
      ...DEMO_BASE,
      workflowState: "understand_event",
      stepIndex: 2,
      lifeEvent: "spouse_death",
      lifeEvents: ["spouse_death"],
      extraCandidateLifeEvents: ["job_loss", "low_income_hardship", "mental_health_crisis"],
      attributes: {},
      items: [],
      questionGroups: [],
    },
  },
  {
    step: "questions",
    narration: "確認後只會問判斷資格真正需要的問題。示範已選好答案，正式時由你自己回答。",
    answers: DEMO_ANSWERS,
    snapshot: {
      ...DEMO_BASE,
      workflowState: "collect_missing_fields",
      stepIndex: 3,
      lifeEvent: "spouse_death",
      lifeEvents: ["spouse_death"],
      attributes: DEMO_ANSWERS,
      items: [],
      questionGroups: QUESTION_GROUPS,
    },
  },
  {
    step: "result",
    narration: "最後會整理可能相關的補助與手續。正式結果仍需向承辦單位確認。",
    snapshot: {
      ...DEMO_BASE,
      workflowState: "explain_result",
      stepIndex: 6,
      lifeEvent: "spouse_death",
      lifeEvents: ["spouse_death"],
      attributes: DEMO_ANSWERS,
      items: RESULT_ITEMS,
      questionGroups: [],
    },
  },
] as const;
