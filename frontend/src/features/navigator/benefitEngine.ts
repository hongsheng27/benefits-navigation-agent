import type {
  BenefitItem,
  DocumentRequirement,
  DocumentSourceInfo,
  EstimateResult,
  NoReasonInfo,
  QuestionCode,
  VerdictKind,
} from "../../types/navigator";

// 示範投保薪資，用來讓「預估可領金額」有具體數字可看；正式版須以官方公告數字為準。
const WAGE_DEFAULT = 34800;
const WAGE_MYDATA = 36300;

const CHILDREN_COUNTS: Record<string, number> = {
  沒有: 0,
  "1 位": 1,
  "2 位": 2,
  "3 位以上": 3,
};

const HOUSEHOLD_COUNTS: Record<string, number> = {
  "1 人": 1,
  "2 人": 2,
  "3 人": 3,
  "4 人以上": 4,
};

export function formatMoney(amount: number): string {
  return `NT$ ${Math.round(amount).toLocaleString("en-US")}`;
}

export function isDocumentReady(
  doc: DocumentRequirement,
  answers: Record<string, string>,
  mydataAuthorized: boolean,
): boolean {
  if (doc.sourceType === "mydata") {
    return mydataAuthorized;
  }
  if (doc.sourceType === "self") {
    return false;
  }
  return doc.needs.every((code) => Boolean(answers[code]));
}

export function readiness(
  item: BenefitItem,
  answers: Record<string, string>,
  mydataAuthorized: boolean,
): { got: number; total: number; percent: number } {
  const got = item.documents.filter((doc) =>
    isDocumentReady(doc, answers, mydataAuthorized),
  ).length;
  const total = item.documents.length;
  return { got, total, percent: total ? Math.round((got / total) * 100) : 0 };
}

function missingRequirements(
  item: BenefitItem,
  answers: Record<string, string>,
): QuestionCode[] {
  return item.requires.filter(
    (code) => !answers[code] || answers[code] === "不確定",
  );
}

export function getMissingRequirementCodes(
  item: BenefitItem,
  answers: Record<string, string>,
): QuestionCode[] {
  return missingRequirements(item, answers);
}

export function verdict(
  item: BenefitItem,
  answers: Record<string, string>,
): VerdictKind {
  const missing = missingRequirements(item, answers);
  if (missing.length === item.requires.length) {
    return "pending";
  }
  if (missing.length) {
    return "info";
  }
  if (item.id === "special" && answers.children === "沒有") {
    return "no";
  }
  if (item.id === "unemploy" && answers.employment !== "非自願離職") {
    return "no";
  }
  return "ok";
}

export function noReason(
  item: BenefitItem,
  answers: Record<string, string>,
): NoReasonInfo | null {
  if (item.id === "special") {
    return {
      condition: "家中有未成年子女",
      mine: "沒有未成年子女",
      need: "至少 1 名未滿 18 歲子女",
    };
  }
  if (item.id === "unemploy") {
    return {
      condition: "離職原因",
      mine: answers.employment || "—",
      need: "非自願離職",
    };
  }
  return null;
}

export function estimate(
  item: BenefitItem,
  answers: Record<string, string>,
  mydataAuthorized: boolean,
): EstimateResult {
  const missing = missingRequirements(item, answers);
  if (missing.length) {
    return { ok: false, reason: "資料不足，尚無法估算" };
  }

  const exact = mydataAuthorized;
  const wage = exact ? WAGE_MYDATA : WAGE_DEFAULT;
  const kids = CHILDREN_COUNTS[answers.children] ?? 0;
  const household = HOUSEHOLD_COUNTS[answers.household] ?? 0;

  switch (item.id) {
    case "funeral": {
      if (answers.insured_type === "國民年金") {
        return {
          ok: true,
          kind: "once",
          amount: wage * 3,
          note: "國保喪葬給付，示範以 3 個月計",
          exact,
        };
      }
      return {
        ok: true,
        kind: "once",
        amount: wage * 5,
        note: `投保薪資 ${formatMoney(wage)} × 5 個月`,
        exact,
      };
    }
    case "survivor": {
      const years = answers.insured_years;
      const base =
        years === "15 年以上" ? wage * 0.3 : years === "5 – 15 年" ? wage * 0.22 : wage * 0.15;
      const add = Math.min(kids, 2) * 0.25;
      return {
        ok: true,
        kind: "monthly",
        amount: base * (1 + add),
        note: `年資 ${years}${kids ? `　·　含 ${Math.min(kids, 2)} 名子女加給` : "　·　無加給"}`,
        exact,
      };
    }
    case "special": {
      if (kids <= 0) {
        return { ok: false, reason: "無未成年子女，無子女生活津貼" };
      }
      return {
        ok: true,
        kind: "monthly",
        amount: 5600 * kids,
        note: `${kids} 名子女 × ${formatMoney(5600)}`,
        exact: true,
      };
    }
    case "unemploy": {
      if (answers.employment !== "非自願離職") {
        return { ok: false, reason: "須為非自願離職才可請領" };
      }
      return {
        ok: true,
        kind: "monthly",
        amount: wage * 0.6 * (1 + Math.min(kids, 2) * 0.1),
        months: 6,
        note: `投保薪資 60%${kids ? `　·　含眷屬加給 ${Math.min(kids, 2) * 10}%` : ""}　·　最長 6 個月`,
        exact,
      };
    }
    case "relief": {
      const amount = household >= 4 ? 40000 : household === 3 ? 30000 : household === 2 ? 20000 : 10000;
      return {
        ok: true,
        kind: "once",
        amount,
        note: `依家戶 ${household || "—"} 人核算，一次性核發`,
        exact: true,
      };
    }
    default:
      return { ok: false, reason: "尚未設定估算規則" };
  }
}

export type BenefitTotals = {
  monthly: number;
  once: number;
  firstYear: number;
  estimatedCount: number;
  hasAnyEstimate: boolean;
  allExact: boolean;
};

export function totals(
  items: BenefitItem[],
  answers: Record<string, string>,
  mydataAuthorized: boolean,
): BenefitTotals {
  let monthly = 0;
  let once = 0;
  let firstYear = 0;
  let estimatedCount = 0;
  let hasAnyEstimate = false;
  let allExact = true;

  items.forEach((item) => {
    if (verdict(item, answers) === "no") {
      return;
    }
    const result = estimate(item, answers, mydataAuthorized);
    if (!result.ok) {
      return;
    }
    hasAnyEstimate = true;
    estimatedCount += 1;
    if (!result.exact) {
      allExact = false;
    }
    if (result.kind === "monthly") {
      monthly += result.amount;
      firstYear += result.amount * Math.min(12, result.months ?? 12);
    } else {
      once += result.amount;
      firstYear += result.amount;
    }
  });

  return { monthly, once, firstYear, estimatedCount, hasAnyEstimate, allExact };
}

export function resolveDocumentSource(documentName: string): DocumentSourceInfo {
  const n = documentName;
  if (/戶籍|戶口|除戶|關係證明|眷屬/.test(n)) {
    return { org: "內政部戶政司", linkLabel: "戶政司 · 戶籍謄本申請" };
  }
  if (/身分證/.test(n)) {
    return { org: "內政部戶政司", linkLabel: "戶政司 · 國民身分證資料" };
  }
  if (/所得/.test(n)) {
    return { org: "財政部財政資訊中心", linkLabel: "財政部 · 所得資料查詢" };
  }
  if (/財產|不動產/.test(n)) {
    return { org: "財政部財政資訊中心", linkLabel: "財政部 · 財產歸屬清單" };
  }
  if (/勞保|投保|年資/.test(n)) {
    return { org: "勞動部勞工保險局", linkLabel: "勞保局 · 被保險人投保資料" };
  }
  if (/死亡證明/.test(n)) {
    return { org: "開立死亡證明的醫院或衛生所", linkLabel: "衛福部 · 死亡證明書開立規定" };
  }
  if (/離職證明/.test(n)) {
    return { org: "原任職單位（雇主）", linkLabel: "勞動部 · 非自願離職證明說明" };
  }
  if (/在學/.test(n)) {
    return { org: "子女就讀學校", linkLabel: "教育部 · 在學證明申請說明" };
  }
  if (/存摺|帳戶/.test(n)) {
    return { org: "你的往來金融機構", linkLabel: "—" };
  }
  if (/存款餘額/.test(n)) {
    return { org: "各往來金融機構", linkLabel: "—" };
  }
  if (/收據/.test(n)) {
    return { org: "開立收據的禮儀公司或業者", linkLabel: "—" };
  }
  if (/申請書|申報|調查表|說明/.test(n)) {
    return { org: "受理機關表單", linkLabel: "機關網站 · 表單下載" };
  }
  return { org: "—", linkLabel: "—" };
}
