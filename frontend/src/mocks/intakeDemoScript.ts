/**
 * 正式諮詢 UI 的唯讀示範腳本。
 *
 * 每個案例都走完 landing → 描述 → 確認 → 問題 → 結果，
 * 不呼叫後端，也不讓使用者改答案。這些結果只是前端示範資料，
 * 不代表 deterministic eligibility rules 已完成判定。
 */

import type { AttributeValue, SessionSnapshot } from "../types/session";

/** 與正式諮詢 HomePageAlt 的步驟一致。 */
export type IntakeDemoStep =
  "landing" | "describe" | "confirm" | "questions" | "result";

export type IntakeDemoScene = {
  step: IntakeDemoStep;
  /** 旁白：說明這一步在正式流程裡會發生什麼。 */
  narration: string;
  description?: string;
  snapshot?: SessionSnapshot | null;
  /** 問題步驟預先選好的答案（僅示範用）。 */
  answers?: Record<string, AttributeValue>;
};

export type IntakeDemoCaseId = "spouse_death" | "occupational_injury_care";

export type IntakeDemoCase = {
  id: IntakeDemoCaseId;
  title: string;
  summary: string;
  scenes: readonly IntakeDemoScene[];
};

function createDemoBase(
  sessionId: string,
): Omit<
  SessionSnapshot,
  | "workflowState"
  | "lifeEvent"
  | "attributes"
  | "items"
  | "questionGroups"
  | "stepIndex"
> {
  return {
    sessionId,
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
}

const SPOUSE_DEMO_BASE = createDemoBase("sess_demo_spouse_death");

const SPOUSE_QUESTION_GROUPS: SessionSnapshot["questionGroups"] = [
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

const SPOUSE_RESULT_ITEMS: SessionSnapshot["items"] = [
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
    sourceLifeEvents: ["spouse_death"],
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
    sourceLifeEvents: ["spouse_death"],
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
    sourceLifeEvents: ["spouse_death"],
  },
];

export const DEMO_DESCRIPTION = "配偶過世一個月了，想確認還有哪些給付來得及申請。";

export const DEMO_ANSWERS: Record<string, AttributeValue> = {
  applicant_jurisdiction: "TPE",
  deceased_insurance_type: "labor_insurance",
  has_dependent_children: true,
};

const SPOUSE_DEMO_SCENES: readonly IntakeDemoScene[] = [
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
      ...SPOUSE_DEMO_BASE,
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
    narration:
      "確認後只會問判斷資格真正需要的問題。示範已選好答案，正式時由你自己回答。",
    answers: DEMO_ANSWERS,
    snapshot: {
      ...SPOUSE_DEMO_BASE,
      workflowState: "collect_missing_fields",
      stepIndex: 3,
      lifeEvent: "spouse_death",
      lifeEvents: ["spouse_death"],
      attributes: DEMO_ANSWERS,
      items: [],
      questionGroups: SPOUSE_QUESTION_GROUPS,
    },
  },
  {
    step: "result",
    narration: "最後會整理可能相關的補助與手續。正式結果仍需向承辦單位確認。",
    snapshot: {
      ...SPOUSE_DEMO_BASE,
      workflowState: "explain_result",
      stepIndex: 6,
      lifeEvent: "spouse_death",
      lifeEvents: ["spouse_death"],
      attributes: DEMO_ANSWERS,
      items: SPOUSE_RESULT_ITEMS,
      questionGroups: [],
    },
  },
] as const;

const CARE_DEMO_BASE: Omit<
  SessionSnapshot,
  | "workflowState"
  | "lifeEvent"
  | "attributes"
  | "items"
  | "questionGroups"
  | "stepIndex"
> = {
  ...createDemoBase("sess_demo_occupational_injury_care"),
  implementation: {
    isMock: true,
    pending: ["rule_evaluation", "official_citations", "action_plan"],
    placeholderNotice: "示範資料",
  },
};

const CARE_QUESTION_GROUPS: SessionSnapshot["questionGroups"] = [
  {
    topicId: "care_relationship",
    groupIndex: 1,
    groupTotal: 4,
    questions: [
      {
        fieldId: "caregiver_relationship",
        valueKind: "code",
        optionIds: [
          "relationship_spouse",
          "relationship_child",
          "relationship_parent",
          "relationship_other_relative",
        ],
        required: true,
        purposeId: "caregiver_relationship.purpose",
        unlocksItemIds: ["caregiver_support_services"],
      },
    ],
  },
  {
    topicId: "occupational_injury_and_insurance",
    groupIndex: 2,
    groupTotal: 4,
    questions: [
      {
        fieldId: "disability_cause",
        valueKind: "code",
        optionIds: [
          "cause_occupational_injury",
          "cause_general_accident",
          "cause_illness",
          "unsure",
        ],
        required: true,
        purposeId: "disability_cause.purpose",
        unlocksItemIds: [
          "occupational_injury_recognition_follow_up",
          "occupational_accident_disability_benefit",
        ],
      },
      {
        fieldId: "occupational_injury_recognition",
        valueKind: "code",
        optionIds: [
          "injury_recognized",
          "recognition_processing",
          "recognition_not_applied",
          "unsure",
        ],
        required: true,
        purposeId: "occupational_injury_recognition.purpose",
        unlocksItemIds: [
          "occupational_injury_recognition_follow_up",
          "occupational_accident_disability_benefit",
        ],
      },
      {
        fieldId: "care_recipient_insurance_type",
        valueKind: "code",
        optionIds: [
          "labor_insurance",
          "occupational_accident_insurance",
          "no_insurance",
          "unsure",
        ],
        required: true,
        purposeId: "care_recipient_insurance_type.purpose",
        unlocksItemIds: ["occupational_accident_disability_benefit"],
      },
    ],
  },
  {
    topicId: "disability_and_long_term_care",
    groupIndex: 3,
    groupTotal: 4,
    questions: [
      {
        fieldId: "disability_assessment_status",
        valueKind: "code",
        optionIds: [
          "disability_certificate_obtained",
          "disability_assessment_in_progress",
          "disability_assessment_not_applied",
          "unsure",
        ],
        required: true,
        purposeId: "disability_assessment_status.purpose",
        unlocksItemIds: ["disability_assessment", "long_term_care_assessment"],
      },
    ],
  },
  {
    topicId: "caregiver_situation",
    groupIndex: 4,
    groupTotal: 4,
    questions: [
      {
        fieldId: "current_care_arrangement",
        valueKind: "code",
        optionIds: [
          "care_mostly_solo",
          "care_shared_by_family",
          "hired_caregiver",
          "care_not_arranged",
        ],
        required: true,
        purposeId: "current_care_arrangement.purpose",
        unlocksItemIds: ["caregiver_support_services", "caregiver_support_contact"],
      },
      {
        fieldId: "caregiver_employment_impact",
        valueKind: "code",
        optionIds: [
          "left_job",
          "reduced_hours",
          "no_employment_change",
          "considering_employment_change",
        ],
        required: true,
        purposeId: "caregiver_employment_impact.purpose",
        unlocksItemIds: ["caregiver_employment_support"],
      },
    ],
  },
];

const CARE_RESULT_ITEMS: SessionSnapshot["items"] = [
  {
    itemId: "occupational_injury_recognition_follow_up",
    kind: "administrative",
    status: "needs_human_review",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    sourceLifeEvents: ["occupational_injury"],
    explanation:
      "職災認定仍在申請中，可先確認案件進度與後續需要補交的資料；app 不收公司或事故細節。",
  },
  {
    itemId: "occupational_accident_disability_benefit",
    kind: "benefit",
    status: "needs_human_review",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    sourceLifeEvents: ["occupational_injury"],
    explanation:
      "父親有職災保險，但是否符合失能給付仍須依職災認定、診斷與失能程度由承辦機關確認。",
  },
  {
    itemId: "disability_assessment",
    kind: "administrative",
    status: "needs_human_review",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    sourceLifeEvents: ["occupational_injury"],
    explanation:
      "目前還沒申請身心障礙鑑定，可先向所在地公所或醫療院所確認辦理流程；app 只列文件，不收證件。",
  },
  {
    itemId: "long_term_care_assessment",
    kind: "administrative",
    status: "needs_human_review",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    sourceLifeEvents: ["occupational_injury"],
    explanation:
      "可聯絡 1966 詢問長照需求評估；實際適用服務仍需由照管單位依最新政策與評估結果確認。",
  },
  {
    itemId: "caregiver_support_services",
    kind: "benefit",
    status: "needs_human_review",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    sourceLifeEvents: ["occupational_injury"],
    explanation:
      "你目前幾乎獨力照顧，可進一步詢問喘息服務與家庭照顧者支持；是否適用仍需依照顧安排評估。",
  },
  {
    itemId: "caregiver_employment_support",
    kind: "benefit",
    status: "needs_human_review",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    sourceLifeEvents: ["occupational_injury"],
    explanation:
      "你已因照顧減少工時，可再確認工作安排、就業服務或其他照顧者就業支持方向。",
  },
  {
    itemId: "caregiver_support_contact",
    kind: "administrative",
    status: "needs_human_review",
    missingFieldIds: [],
    decisiveConditions: [],
    citations: [],
    amountMin: null,
    amountMax: null,
    amountPeriod: null,
    amountCurrency: null,
    sourceLifeEvents: ["occupational_injury"],
    explanation:
      "不必等所有資格確認完才求助；需要有人一起釐清時，可先聯絡 1966 或所在地家庭照顧者支持窗口。",
  },
];

export const CARE_DEMO_DESCRIPTION =
  "爸爸在工作中發生重大事故後失能，現在需要長期照顧。我一邊工作、一邊照顧兩歲的小孩，最近也因為照顧爸爸減少工時，不知道職災、身障和長照該先辦哪一個。";

export const CARE_DEMO_ANSWERS: Record<string, AttributeValue> = {
  caregiver_relationship: "relationship_child",
  disability_cause: "cause_occupational_injury",
  occupational_injury_recognition: "recognition_processing",
  care_recipient_insurance_type: "occupational_accident_insurance",
  disability_assessment_status: "disability_assessment_not_applied",
  current_care_arrangement: "care_mostly_solo",
  caregiver_employment_impact: "reduced_hours",
};

const CARE_DEMO_SCENES: readonly IntakeDemoScene[] = [
  {
    step: "landing",
    narration:
      "接下來用「父親職災失能」這個例子，看系統如何同時整理被照顧者與照顧者的方向。",
    snapshot: null,
  },
  {
    step: "describe",
    narration:
      "正式使用時，只要描述照顧處境；不需要填公司、確切日期或事故經過。示範已預先填好。",
    description: CARE_DEMO_DESCRIPTION,
    snapshot: null,
  },
  {
    step: "confirm",
    narration:
      "系統先確認主要事件是職業災害；確認後，後續問題會同時涵蓋父親與照顧者本人。",
    snapshot: {
      ...CARE_DEMO_BASE,
      workflowState: "understand_event",
      stepIndex: 2,
      lifeEvent: "occupational_injury",
      lifeEvents: ["occupational_injury"],
      extraCandidateLifeEvents: [
        "serious_illness",
        "job_loss",
        "low_income_hardship",
      ],
      attributes: {},
      items: [],
      questionGroups: [],
    },
  },
  {
    step: "questions",
    narration:
      "只追問資格與服務方向真正需要的七個去識別化欄位，不詢問公司、姓名或受傷細節。",
    answers: CARE_DEMO_ANSWERS,
    snapshot: {
      ...CARE_DEMO_BASE,
      workflowState: "collect_missing_fields",
      stepIndex: 3,
      lifeEvent: "occupational_injury",
      lifeEvents: ["occupational_injury"],
      attributes: CARE_DEMO_ANSWERS,
      items: [],
      questionGroups: CARE_QUESTION_GROUPS,
    },
  },
  {
    step: "result",
    narration:
      "最後分成父親與照顧者兩條線整理方向；這仍是示範，不代表資格規則已完成判定。",
    snapshot: {
      ...CARE_DEMO_BASE,
      workflowState: "explain_result",
      stepIndex: 6,
      lifeEvent: "occupational_injury",
      lifeEvents: ["occupational_injury"],
      attributes: CARE_DEMO_ANSWERS,
      items: CARE_RESULT_ITEMS,
      questionGroups: [],
    },
  },
] as const;

export const DEFAULT_INTAKE_DEMO_CASE_ID: IntakeDemoCaseId = "spouse_death";

export const INTAKE_DEMO_CASES: readonly IntakeDemoCase[] = [
  {
    id: "spouse_death",
    title: "配偶過世",
    summary: "查看喪親後可能要辦的手續與給付。",
    scenes: SPOUSE_DEMO_SCENES,
  },
  {
    id: "occupational_injury_care",
    title: "父親職災失能",
    summary: "同時整理父親的申請方向與照顧者本人的支持。",
    scenes: CARE_DEMO_SCENES,
  },
] as const;

/** 保留既有 export，讓原本只使用第一案例的程式與測試繼續運作。 */
export const INTAKE_DEMO_SCENES = SPOUSE_DEMO_SCENES;
