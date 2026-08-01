/**
 * 代號 → 中文文案的對照表。
 *
 * 後端只給代號，所有給人看的文字由前端提供（見 `docs/front_back_doc/README.md`
 * 第七節）。代號清單會變長（例如新增生命事件只會改後端的一份 JSON），所以每個查詢
 * 都有 fallback：查不到就顯示代號本身，畫面不會壞掉，也看得出少了哪一筆文案。
 */

import type { ErrorCode, ItemKind, ItemStatus } from "../../types/session";

/** 生命事件。目前後端只認得三個，清單會變長。 */
const LIFE_EVENT_NAMES: Record<string, string> = {
  spouse_death: "配偶過世",
  parent_death: "父母過世",
  child_death: "子女過世",
};

/** 候選項目。目前是離線示範資料的四筆。 */
const ITEM_NAMES: Record<string, string> = {
  death_registration: "死亡登記",
  funeral_benefit: "喪葬給付",
  survivor_pension: "遺屬年金",
  health_insurance_change: "全民健保身分變更",
};

/** 資格欄位的題目文字。目前是三筆 draft 種子資料。 */
const FIELD_LABELS: Record<string, string> = {
  deceased_insurance_type: "過世者生前的投保身分是？",
  has_dependent_children: "家中是否有未成年子女？",
  applicant_age_band: "你目前的年齡大約在哪個範圍？",
};

/** 「為什麼問這個？」的說明。後端的 purposeId 形狀是 `<fieldId>.purpose`。 */
const PURPOSE_TEXTS: Record<string, string> = {
  "deceased_insurance_type.purpose":
    "投保身分決定由哪個機關受理，以及適用哪一套給付規則。",
  "has_dependent_children.purpose": "遺屬年金有加給條件，依據是否有未成年子女。",
  "applicant_age_band.purpose": "遺屬年金有年齡條件，不同年齡區間適用不同規定。",
};

/** 選項文字。boolean 欄位沒有 optionIds，由畫面自己給「是／否」。 */
const OPTION_LABELS: Record<string, string> = {
  labor_insurance: "勞工保險",
  national_pension: "國民年金",
  farmers_insurance: "農民保險",
  civil_service_insurance: "公教人員保險",
  none_or_unsure: "沒有保險或不確定",
  under_25: "未滿 25 歲",
  "25_to_55": "25 至 55 歲",
  "55_to_65": "55 至 65 歲",
  "65_or_above": "65 歲以上",
};

/** 問題分組的標題。 */
const TOPIC_TITLES: Record<string, string> = {
  deceased_insurance: "過世者的投保狀況",
  family_situation: "家庭狀況",
  applicant_situation: "你的狀況",
};

/** 結果分區的標題。 */
const STATUS_SECTION_TITLES: Record<ItemStatus, string> = {
  eligible: "你可能符合",
  needs_information: "需要補充資訊",
  ineligible: "不符合",
  needs_human_review: "需要人工協助確認",
  pending: "待確認",
  declined_by_user: "你選擇不辦理",
};

/** 項目是義務還是權利，畫面上要分得出來。 */
const ITEM_KIND_LABELS: Record<ItemKind, string> = {
  benefit: "可申請的福利",
  administrative: "應辦理的行政事項",
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
  unknown_field: "系統送出的欄位有誤，請回報這個問題。",
  invalid_field_value: "系統送出的答案格式有誤，請回報這個問題。",
  unknown_item: "系統指定的項目有誤，請回報這個問題。",
  invalid_transition: "這個步驟現在不能執行，請重新載入後再試。",
  event_not_recognized: "我們沒有看懂剛才的描述，可以換個說法再說一次嗎？",
  internal_error: "系統暫時無法處理，請稍後再試。",
};

/** 使用者的描述無法對應到已知事件時顯示的提示。這不是錯誤。 */
export const EVENT_NOT_RECOGNIZED_MESSAGE =
  "我們沒有看懂剛才的描述，可以換個說法再說一次嗎？例如直接說發生了什麼事，以及是誰。";

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

export function errorMessage(code: ErrorCode): string {
  return ERROR_MESSAGES[code] ?? ERROR_MESSAGES.internal_error;
}
