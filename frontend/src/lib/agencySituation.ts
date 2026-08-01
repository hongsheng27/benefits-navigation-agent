/**
 * 把機關目錄與使用者追蹤案件對起來。
 *
 * 匹配規則（任一成立即視為相關）：
 * 1. 案件列出的機關名稱，與目錄機關名稱／組織名互相包含
 * 2. 案件相關項目名稱，與機關 relatedBenefitNames 重疊
 */

import type { AgencyDirectoryItem } from "../types/agency";
import type { TrackedCase } from "../types/tracking";

/** 從追蹤頁帶過來、或由進行中案件自動彙總的情境。 */
export type AgencySituationFocus = {
  caseId?: string;
  caseTitle?: string;
  lifeEventLabel?: string;
  agencyNames: string[];
  relatedItemNames: string[];
};

export type RankedAgency = {
  agency: AgencyDirectoryItem;
  /** 為什麼跟使用者情況有關（給畫面顯示）。 */
  reasons: string[];
};

function normalize(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, "");
}

function namesOverlap(a: string, b: string): boolean {
  const left = normalize(a);
  const right = normalize(b);
  if (!left || !right) {
    return false;
  }
  return left.includes(right) || right.includes(left);
}

/** 從單一案件建立機關總覽的聚焦情境。 */
export function focusFromCase(trackedCase: TrackedCase): AgencySituationFocus {
  return {
    caseId: trackedCase.caseId,
    caseTitle: trackedCase.title,
    lifeEventLabel: trackedCase.lifeEventLabel,
    agencyNames: trackedCase.agencies,
    relatedItemNames: trackedCase.relatedItems,
  };
}

/**
 * 從多筆追蹤案件彙總（預設只用進行中／暫停，略過已完成）。
 */
export function focusFromOpenCases(cases: TrackedCase[]): AgencySituationFocus | null {
  const open = cases.filter(
    (item) => item.overallStatus === "in_progress" || item.overallStatus === "paused",
  );
  if (open.length === 0) {
    return null;
  }

  const agencyNames = [...new Set(open.flatMap((item) => item.agencies))];
  const relatedItemNames = [...new Set(open.flatMap((item) => item.relatedItems))];
  const labels = [...new Set(open.map((item) => item.lifeEventLabel))];

  return {
    lifeEventLabel: labels.join("、"),
    agencyNames,
    relatedItemNames,
  };
}

/** 依使用者情境排序／篩出相關機關。 */
export function rankAgenciesForSituation(
  agencies: AgencyDirectoryItem[],
  focus: AgencySituationFocus | null,
): RankedAgency[] {
  if (focus === null) {
    return [];
  }

  const ranked: RankedAgency[] = [];

  for (const agency of agencies) {
    const reasons: string[] = [];

    for (const name of focus.agencyNames) {
      if (
        namesOverlap(agency.name, name) ||
        namesOverlap(agency.organizationName, name)
      ) {
        reasons.push(`案件相關機關：${name}`);
        break;
      }
    }

    for (const itemName of focus.relatedItemNames) {
      const hit = agency.relatedBenefitNames.find((benefit) =>
        namesOverlap(benefit, itemName),
      );
      if (hit) {
        reasons.push(`對應你可能辦理的「${itemName}」`);
        break;
      }
    }

    if (reasons.length > 0) {
      ranked.push({ agency, reasons });
    }
  }

  return ranked.sort((a, b) => b.reasons.length - a.reasons.length);
}
