import type { EligibilityQuestion } from "../types/navigator";

export const ELIGIBILITY_QUESTIONS: EligibilityQuestion[] = [
  {
    code: "insured_type",
    label: "過世者的投保身分",
    prompt: "過世者生前的投保身分是？",
    options: ["勞工保險", "國民年金", "農民保險", "公教人員保險", "不確定"],
    why: "投保身分決定由哪個機關受理，以及適用哪一套給付規則。",
  },
  {
    code: "relation",
    label: "你與過世者的關係",
    prompt: "你與過世者的關係是？",
    options: ["配偶", "子女", "父母", "其他親屬"],
    why: "請領資格與順位依親屬關係認定。",
    profileField: "relation",
  },
  {
    code: "insured_years",
    label: "過世者的投保年資",
    prompt: "過世者的投保年資大約多久？",
    options: ["未滿 1 年", "1 – 5 年", "5 – 15 年", "15 年以上", "不確定"],
    why: "年資是遺屬年金的門檻條件之一。",
    mydataPrefill: true,
  },
  {
    code: "children",
    label: "未成年子女",
    prompt: "家中有幾位未滿 18 歲的子女？",
    options: ["沒有", "1 位", "2 位", "3 位以上"],
    why: "影響遺屬給付加給與育兒相關項目。",
    profileField: "children",
  },
  {
    code: "employment",
    label: "你目前的就業狀況",
    prompt: "你目前的就業狀況是？",
    options: ["未就業", "非自願離職", "有工作", "退休"],
    why: "部分給付排除同時領取性質相同的補助。",
    profileField: "employment",
  },
  {
    code: "household",
    label: "同戶籍人數",
    prompt: "同一戶籍內目前有幾人？",
    options: ["1 人", "2 人", "3 人", "4 人以上"],
    why: "家戶人數是計算每人每月平均收入的分母。",
    profileField: "household",
  },
];
