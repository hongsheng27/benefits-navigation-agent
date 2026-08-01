/**
 * 補助／行政機關目錄的前端形狀。
 *
 * 對齊 `data/source_registry` 與未來 `GET /agencies` 回應。
 * 後端尚未實作時，由 `agencyClient` 回傳 mock。
 */

export type AgencyOfficialStatus =
  | "verified_official"
  | "likely_official"
  | "unverified";

export type AgencyConnectionStatus =
  | "active"
  | "pending"
  | "error"
  | "disabled";

export type AgencySourceType =
  | "agency_site"
  | "benefit_index"
  | "reference_dataset"
  | "other";

/** 單一機關（或官方資料來源）在總覽頁的一筆資料。 */
export type AgencyDirectoryItem = {
  agencyId: string;
  /** 目錄顯示名稱。 */
  name: string;
  organizationName: string;
  jurisdictionCode: string;
  /** 前端顯示用行政層級／地區，例如「中央」「臺北市」。 */
  jurisdictionLabel: string;
  sourceType: AgencySourceType;
  officialStatus: AgencyOfficialStatus;
  connectionStatus: AgencyConnectionStatus;
  websiteUrl: string;
  entryUrl: string | null;
  summary: string;
  phone: string | null;
  relatedBenefitCount: number;
  relatedBenefitNames: string[];
  lastReviewedAt: string | null;
};

export type AgencyListResponse = {
  agencies: AgencyDirectoryItem[];
  /** true 表示目前為前端假資料，尚未來自資料庫。 */
  isMock: boolean;
};
