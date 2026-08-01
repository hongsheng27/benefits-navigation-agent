/**
 * 代號 → 中文文案的對照表。
 *
 * 後端只給代號，所有給人看的文字由前端提供（見 `docs/front_back_doc/README.md`
 * 第七節）。代號清單會變長（例如新增生命事件只會改後端的一份 JSON），所以每個查詢
 * 都有 fallback：查不到就顯示代號本身，畫面不會壞掉，也看得出少了哪一筆文案。
 */

import type { ErrorCode, ItemKind, ItemStatus } from "../../types/session";

/** 一個生命事件在前端的完整顯示資料。 */
export type LifeEventCopy = {
  eventId: string;
  label: string;
  /** 首頁情境分類標題。 */
  category: string;
  /** 點選情境時帶入輸入框的例句。 */
  examplePrompt: string;
};

/**
 * 台灣常見、可能需要補助／福利／行政協助的生活變故文案。
 *
 * `eventId` 須與後端 `data/life_events/events.v0.1.json` 對齊。
 * 使用者用自然語言描述，由後端 LLM 對應到這些代號；前端只負責顯示中文名。
 * 多數事件目前只有「辨識＋確認」；福利項目展開仍多半只有配偶過世有示範資料。
 */
export const LIFE_EVENT_CATALOG: readonly LifeEventCopy[] = [
  // —— 喪親 ——
  {
    eventId: "spouse_death",
    label: "配偶過世",
    category: "喪親",
    examplePrompt: "配偶過世一個月了，想確認還有哪些給付來得及申請。",
  },
  {
    eventId: "parent_death",
    label: "父母過世",
    category: "喪親",
    examplePrompt: "我媽媽前天在醫院過世，不知道接下來要辦什麼。",
  },
  {
    eventId: "child_death",
    label: "子女過世",
    category: "喪親",
    examplePrompt: "小孩過世了，想知道有哪些補助或要先辦的手續。",
  },
  {
    eventId: "sibling_death",
    label: "兄弟姊妹過世",
    category: "喪親",
    examplePrompt: "我哥哥剛過世，不確定身為手足可以申請什麼、要辦什麼。",
  },
  {
    eventId: "other_relative_death",
    label: "親人過世",
    category: "喪親",
    examplePrompt: "親人過世了，不知道接下來要辦什麼。",
  },

  // —— 就業與收入 ——
  {
    eventId: "job_loss",
    label: "失業／被資遣",
    category: "就業與收入",
    examplePrompt: "公司裁員被資遣了，想知道失業給付或其他協助怎麼申請。",
  },
  {
    eventId: "unpaid_leave",
    label: "無薪假／收入驟減",
    category: "就業與收入",
    examplePrompt: "被放無薪假，收入突然少很多，想問有沒有可以申請的補助。",
  },
  {
    eventId: "occupational_injury",
    label: "職業災害",
    category: "就業與收入",
    examplePrompt: "上班時受傷，想了解職災給付、醫療與休養期間可以申請什麼。",
  },
  {
    eventId: "youth_employment_hardship",
    label: "青年就業困難",
    category: "就業與收入",
    examplePrompt: "剛畢業一直找不到穩定工作，想知道青年就業或職訓相關協助。",
  },
  {
    eventId: "low_income_hardship",
    label: "低收入／生活困頓",
    category: "就業與收入",
    examplePrompt: "家裡收入很低、開銷快撐不住，想確認是否符合生活扶助。",
  },

  // —— 健康與照顧 ——
  {
    eventId: "serious_illness",
    label: "重大傷病",
    category: "健康與照顧",
    examplePrompt: "被診斷重大傷病，醫療費壓力很大，想知道有哪些補助或減免。",
  },
  {
    eventId: "disability_onset",
    label: "身心障礙／失能",
    category: "健康與照顧",
    examplePrompt: "家人剛取得身心障礙證明，想了解可以申請哪些福利與服務。",
  },
  {
    eventId: "long_term_care_need",
    label: "長照需求",
    category: "健康與照顧",
    examplePrompt: "爸媽需要長期照顧，想知道長照服務與補助怎麼開始申請。",
  },
  {
    eventId: "caregiver_burden",
    label: "家庭照顧負擔",
    category: "健康與照顧",
    examplePrompt: "我幾乎全職照顧失能家人，自己快撐不住，想找照顧者支持資源。",
  },
  {
    eventId: "mental_health_crisis",
    label: "精神健康危機",
    category: "健康與照顧",
    examplePrompt: "自己或家人有嚴重情緒／精神困擾，想知道就醫與社會扶助管道。",
  },
  {
    eventId: "elderly_living_hardship",
    label: "老人生活困難",
    category: "健康與照顧",
    examplePrompt: "家裡有獨居長輩，生活與就醫都吃力，想問老人福利或關懷資源。",
  },

  // —— 生育與家庭 ——
  {
    eventId: "pregnancy",
    label: "懷孕",
    category: "生育與家庭",
    examplePrompt: "剛確認懷孕，想了解產檢、津貼或懷孕期間可以申請的協助。",
  },
  {
    eventId: "childbirth",
    label: "生育／生產",
    category: "生育與家庭",
    examplePrompt: "剛生完小孩，想確認生育給付、育兒津貼要怎麼申請。",
  },
  {
    eventId: "childcare_hardship",
    label: "育兒生活困難",
    category: "生育與家庭",
    examplePrompt: "帶小孩開銷太高，想知道托育、育兒相關補助有哪些。",
  },
  {
    eventId: "school_expense_hardship",
    label: "就學費用困難",
    category: "生育與家庭",
    examplePrompt: "小孩學費與生活費負擔很重，想問就學貸款或助學金相關協助。",
  },
  {
    eventId: "divorce",
    label: "離婚／分居",
    category: "生育與家庭",
    examplePrompt: "剛離婚，一個人帶小孩，想了解單親或特殊境遇可以申請什麼。",
  },
  {
    eventId: "single_parent_hardship",
    label: "單親家庭困境",
    category: "生育與家庭",
    examplePrompt: "我是單親，收入不夠支應孩子生活，想確認有哪些扶助。",
  },
  {
    eventId: "domestic_violence",
    label: "家庭暴力",
    category: "生育與家庭",
    examplePrompt: "遭受家暴需要離開不安全的環境，想知道保護與急難協助管道。",
  },
  {
    eventId: "special_family_circumstances",
    label: "特殊境遇家庭",
    category: "生育與家庭",
    examplePrompt: "家庭遇到喪偶、離婚或配偶入獄等特殊情況，想確認特殊境遇家庭扶助。",
  },

  // —— 居住與災害 ——
  {
    eventId: "housing_insecurity",
    label: "居住不穩／迫遷",
    category: "居住與災害",
    examplePrompt: "快繳不出房租、可能被迫搬家，想知道租金補貼或居住協助。",
  },
  {
    eventId: "natural_disaster",
    label: "天然災害受災",
    category: "居住與災害",
    examplePrompt: "家裡被颱風／水災影響，想了解災害救助金或後續協助。",
  },
  {
    eventId: "fire_or_accident",
    label: "火災或重大意外",
    category: "居住與災害",
    examplePrompt: "家裡遇到火災，暫時沒地方住，想問急難救助怎麼申請。",
  },

  // —— 特定身分與處境 ——
  {
    eventId: "new_immigrant_hardship",
    label: "新住民生活困難",
    category: "特定身分與處境",
    examplePrompt: "我是新住民，在生活或工作上遇到困難，想知道可申請的協助。",
  },
  {
    eventId: "indigenous_welfare_need",
    label: "原住民福利諮詢",
    category: "特定身分與處境",
    examplePrompt: "想了解原住民身分可以申請的生活、就學或就業相關福利。",
  },
  {
    eventId: "incarceration_family",
    label: "家屬入監",
    category: "特定身分與處境",
    examplePrompt: "家人入監後家計出問題，想知道受刑人家庭可以申請什麼扶助。",
  },
  {
    eventId: "missing_family_member",
    label: "家屬失蹤",
    category: "特定身分與處境",
    examplePrompt: "家人失蹤一段時間了，家裡經濟受影響，想問相關協助管道。",
  },
  {
    eventId: "veteran_support_need",
    label: "榮民／榮眷協助",
    category: "特定身分與處境",
    examplePrompt: "家裡有榮民或榮眷身分，想確認可以申請哪些生活或就養協助。",
  },
  {
    eventId: "youth_independence_hardship",
    label: "少年自立困難",
    category: "特定身分與處境",
    examplePrompt: "離開安置或家庭後要自立生活，想知道少年生涯發展或生活協助。",
  },
] as const;

const LIFE_EVENT_NAMES: Record<string, string> = Object.fromEntries(
  LIFE_EVENT_CATALOG.map((entry) => [entry.eventId, entry.label]),
);

/** 候選項目的前端顯示名稱。 */
const ITEM_NAMES: Record<string, string> = {
  death_registration: "死亡登記",
  funeral_benefit: "喪葬給付",
  survivor_pension: "遺屬年金",
  health_insurance_change: "全民健保身分變更",
  occupational_injury_recognition: "職業災害認定申請",
  occupational_disability_benefit: "職災失能／傷病給付（示意）",
  disability_assessment: "身心障礙鑑定",
  unemployment_benefit: "失業給付",
  employment_service: "就業服務／職訓諮詢",
  taipei_green_funeral_incentive: "臺北市多元環保葬鼓勵金",
  taipei_joint_funeral_service: "臺北市聯合奠祭",
  new_taipei_green_funeral_incentive: "新北市環保葬鼓勵金",
  taoyuan_green_funeral_incentive: "桃園市環保葬鼓勵金",
  penghu_green_funeral_subsidy: "澎湖縣多元環保葬補助",
  occupational_injury_recognition_follow_up: "追蹤職業災害認定",
  occupational_accident_disability_benefit: "職災保險失能給付",
  long_term_care_assessment: "長照需求評估",
  caregiver_support_services: "家庭照顧者支持與喘息服務",
  caregiver_employment_support: "照顧者就業支持",
  caregiver_support_contact: "支持專線與人工協助",
};

/** 資格欄位的題目文字。 */
const FIELD_LABELS: Record<string, string> = {
  applicant_jurisdiction: "你主要在哪個縣市辦理或居住？",
  care_relationship: "你和需要照顧的人是什麼關係？",
  caregiver_relationship: "你和需要照顧的人是什麼關係？",
  disability_cause: "造成失能的原因是？",
  occupational_recognition_status: "是否已經取得職業災害認定？",
  occupational_injury_recognition: "是否已經取得職業災害認定？",
  involuntary_job_loss: "這次是否屬於非自願離職？",
  deceased_insurance_type: "過世者生前的投保身分是？",
  has_dependent_children: "家中是否有未成年子女？",
  applicant_age_band: "你目前的年齡大約在哪個範圍？",
  care_recipient_insurance_type: "父親受傷前的投保身分是？",
  disability_assessment_status: "是否已經完成身心障礙鑑定？",
  current_care_arrangement: "目前主要由誰照顧？",
  caregiver_employment_impact: "你是否因照顧而請假、減少工時或離職？",
};

/** 「為什麼問這個？」的說明。後端的 purposeId 形狀是 `<fieldId>.purpose`。 */
const PURPOSE_TEXTS: Record<string, string> = {
  "applicant_jurisdiction.purpose":
    "所在縣市決定有哪些地方型補助與受理窗口可以對照。",
  "care_relationship.purpose": "代辦與請領資格依親屬關係認定。",
  "caregiver_relationship.purpose": "代辦與部分請領資格會依親屬關係認定。",
  "disability_cause.purpose":
    "職業災害與一般意外或疾病的受理機關、申請路徑及給付不同。",
  "occupational_recognition_status.purpose":
    "職災給付以認定為前提；還沒認定的話，第一步就是先申請認定。",
  "occupational_injury_recognition.purpose":
    "職災相關給付通常需要確認認定狀態；這裡不詢問公司或事故經過。",
  "involuntary_job_loss.purpose": "非自願離職才是失業給付常見門檻之一。",
  "deceased_insurance_type.purpose":
    "不同投保身分，受理機關與可申請的給付不一樣。",
  "has_dependent_children.purpose": "有沒有未成年子女，會影響遺屬年金是否加給。",
  "applicant_age_band.purpose":
    "遺屬年金依年齡有不同規定，我們需要大致了解你的年齡區間。",
  "care_recipient_insurance_type.purpose": "投保身分會影響可能的給付與受理機關。",
  "disability_assessment_status.purpose":
    "鑑定進度會影響身障服務與部分照顧資源接續時的辦理順序。",
  "current_care_arrangement.purpose":
    "目前的分工會影響喘息服務與家庭照顧者支持的評估方向。",
  "caregiver_employment_impact.purpose":
    "工作是否已受影響，會決定是否同時整理照顧者就業支持方向。",
};

/** 選項文字。boolean 欄位沒有 optionIds，由畫面自己給「是／否」。 */
const OPTION_LABELS: Record<string, string> = {
  TPE: "臺北市",
  NWT: "新北市",
  TAO: "桃園市",
  PEN: "澎湖縣",
  OTHER_TW: "其他縣市",
  unsure: "不確定",
  spouse: "配偶",
  child: "子女",
  parent: "父母",
  other_relative: "其他親屬",
  occupational_injury: "職業災害（工作中發生）",
  accident: "一般意外",
  illness: "疾病（如中風）",
  recognized: "已認定",
  applying: "申請中",
  not_started: "還沒申請",
  labor_insurance: "勞工保險",
  national_pension: "國民年金",
  farmers_insurance: "農民保險",
  civil_service_insurance: "公教人員保險",
  none_or_unsure: "沒有保險或不確定",
  under_25: "未滿 25 歲",
  "25_to_55": "25 至 55 歲",
  "55_to_65": "55 至 65 歲",
  "65_or_above": "65 歲以上",
  relationship_spouse: "配偶",
  relationship_child: "子女",
  relationship_parent: "父母",
  relationship_other_relative: "其他親屬",
  cause_occupational_injury: "職業災害（工作中發生）",
  cause_general_accident: "一般意外",
  cause_illness: "疾病（如中風）",
  injury_recognized: "已認定",
  recognition_processing: "申請中",
  recognition_not_applied: "還沒申請",
  occupational_accident_insurance: "職災保險",
  no_insurance: "無",
  disability_certificate_obtained: "已取得身障證明",
  disability_assessment_in_progress: "鑑定中",
  disability_assessment_not_applied: "還沒申請",
  care_mostly_solo: "我幾乎全天獨力照顧",
  care_shared_by_family: "家人輪流分擔",
  hired_caregiver: "已聘僱看護",
  care_not_arranged: "還沒安排",
  left_job: "已離職",
  reduced_hours: "減少工時",
  no_employment_change: "沒有",
  considering_employment_change: "還在考慮",
};

/** 問題分組的標題。 */
const TOPIC_TITLES: Record<string, string> = {
  location: "所在地",
  care_relationship: "你與被照顧者",
  injury_context: "失能與職災",
  employment_status: "就業狀況",
  deceased_insurance: "過世者的投保狀況",
  family_situation: "家庭狀況",
  applicant_situation: "你的狀況",
  occupational_injury_and_insurance: "職災與投保狀況",
  disability_and_long_term_care: "失能與長照銜接",
  caregiver_situation: "照顧者本人的狀況",
};

/** 第二個 demo 用前端映射呈現雙線，不改動後端 ItemView contract。 */
export type ResultAudience = "care_recipient" | "caregiver";

const ITEM_AUDIENCES: Partial<Record<string, ResultAudience>> = {
  occupational_injury_recognition_follow_up: "care_recipient",
  occupational_accident_disability_benefit: "care_recipient",
  disability_assessment: "care_recipient",
  long_term_care_assessment: "care_recipient",
  caregiver_support_services: "caregiver",
  caregiver_employment_support: "caregiver",
  caregiver_support_contact: "caregiver",
};

export function itemAudience(itemId: string): ResultAudience | null {
  return ITEM_AUDIENCES[itemId] ?? null;
}

export function resultAudienceTitle(audience: ResultAudience): string {
  return audience === "care_recipient" ? "給父親（被照顧者）" : "給你（照顧者）";
}

export function resultAudienceDescription(audience: ResultAudience): string {
  return audience === "care_recipient"
    ? "先把職災、失能與長照的辦理順序接起來。"
    : "照顧者也可以使用支持、喘息與就業協助，不必一個人扛。";
}

/** 結果分區的標題。 */
const STATUS_SECTION_TITLES: Record<ItemStatus, string> = {
  eligible: "這些，你或許可以辦理",
  needs_information: "還差一點資訊才能更確定",
  ineligible: "目前看起來比較難符合",
  needs_human_review: "這幾項，建議再跟承辦聊聊",
  pending: "我們還需要再核對一下",
  declined_by_user: "你選擇先不辦理",
};

/** 項目是義務還是權利，畫面上要分得出來。 */
const ITEM_KIND_LABELS: Record<ItemKind, string> = {
  benefit: "補助／給付",
  administrative: "行政手續",
};

/**
 * 結果列用的細項類型（前端對照，不擴充後端 ItemKind）。
 * 比 benefit／administrative 更贴近使用者理解的「補助、資格認定」等。
 */
export type ItemCategory =
  | "benefit"
  | "recognition"
  | "administrative"
  | "consultation";

const ITEM_CATEGORY_LABELS: Record<ItemCategory, string> = {
  benefit: "補助／給付",
  recognition: "資格認定",
  administrative: "行政手續",
  consultation: "諮詢／服務",
};

const ITEM_CATEGORIES: Record<string, ItemCategory> = {
  funeral_benefit: "benefit",
  survivor_pension: "benefit",
  unemployment_benefit: "benefit",
  occupational_disability_benefit: "benefit",
  occupational_accident_disability_benefit: "benefit",
  taipei_green_funeral_incentive: "benefit",
  new_taipei_green_funeral_incentive: "benefit",
  taoyuan_green_funeral_incentive: "benefit",
  penghu_green_funeral_subsidy: "benefit",
  caregiver_support_services: "benefit",
  caregiver_employment_support: "benefit",
  occupational_injury_recognition: "recognition",
  occupational_injury_recognition_follow_up: "recognition",
  disability_assessment: "recognition",
  long_term_care_assessment: "recognition",
  death_registration: "administrative",
  health_insurance_change: "administrative",
  taipei_joint_funeral_service: "administrative",
  caregiver_support_contact: "consultation",
  employment_service: "consultation",
};

/**
 * 錯誤訊息。
 *
 * `event_not_recognized` 刻意不在這裡 —— 它不是程式錯誤，不能顯示成「系統發生錯誤」，
 * 由 `EVENT_NOT_RECOGNIZED_MESSAGE` 單獨提供，並且在畫面上是可重試的提示而非錯誤。
 */
const ERROR_MESSAGES: Record<ErrorCode, string> = {
  session_not_found: "這次諮詢已經找不到了，請重新開始。",
  session_expired: "這次諮詢已經超過保存時間，請重新開始。",
  unknown_field: "送出的內容有一點問題，請重新開始再試一次。",
  invalid_field_value: "有些答案格式不對，請重新開始再試一次。",
  unknown_item: "整理結果時出了一點問題，請重新開始再試一次。",
  invalid_transition: "這個步驟現在無法繼續，請重新開始再試一次。",
  event_not_recognized: "我們沒有完全看懂，可以換個說法再說一次嗎？",
  explanation_unavailable: "說明服務暫時無法回答，請稍後再試，或先閱讀左側資料。",
  internal_error: "服務暫時無法處理，請稍後再試。",
};

/** 使用者的描述無法對應到已知事件時顯示的提示。這不是錯誤。 */
export const EVENT_NOT_RECOGNIZED_MESSAGE =
  "我們沒有完全看懂剛才的描述。可以再說一次發生了什麼、以及是誰嗎？例如「先生上個月過世了」。";

export function lifeEventName(code: string): string {
  return LIFE_EVENT_NAMES[code] ?? code;
}

export function itemName(itemId: string): string {
  return ITEM_NAMES[itemId] ?? itemId;
}

export function fieldLabel(fieldId: string): string {
  return FIELD_LABELS[fieldId] ?? fieldId;
}

export function purposeText(purposeId: string): string | null {
  return PURPOSE_TEXTS[purposeId] ?? null;
}

export function optionLabel(optionId: string): string {
  return OPTION_LABELS[optionId] ?? optionId;
}

export function topicTitle(topicId: string): string {
  return TOPIC_TITLES[topicId] ?? topicId;
}

export function statusSectionTitle(status: ItemStatus): string {
  return STATUS_SECTION_TITLES[status] ?? status;
}

export function itemKindLabel(kind: ItemKind): string {
  return ITEM_KIND_LABELS[kind] ?? kind;
}

export function itemCategory(itemId: string): ItemCategory | null {
  return ITEM_CATEGORIES[itemId] ?? null;
}

/** 結果列「項目類型」文案；未知 id 時退回後端 kind 標籤。 */
export function itemCategoryLabel(itemId: string, kind: ItemKind): string {
  const category = itemCategory(itemId);
  if (category) {
    return ITEM_CATEGORY_LABELS[category];
  }
  return itemKindLabel(kind);
}

export function errorMessage(code: ErrorCode): string {
  return ERROR_MESSAGES[code] ?? ERROR_MESSAGES.internal_error;
}
