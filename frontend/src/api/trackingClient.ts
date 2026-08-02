/**
 * 追蹤進度 API client。
 *
 * 預定契約：`GET /cases` → `{ cases: TrackedCase[], isMock?: boolean }`
 * 後端尚未實作時回空列表；使用者從結果頁「加入追蹤」的項目改由
 * `trackingStore`（localStorage）提供，不再注入假案件。
 *
 * 完整假案件仍留在 `mocks/trackedCases.ts`，供單元測試或手動示範引用。
 */

import { apiBaseUrl } from "./client";
import type { TrackedCase } from "../types/tracking";

export type TrackedCaseListResponse = {
  cases: TrackedCase[];
  isMock: boolean;
};

const EMPTY_MOCK: TrackedCaseListResponse = { cases: [], isMock: true };

/**
 * 取得使用者的追蹤案件列表。
 *
 * 若設定 `VITE_CASES_API_PATH`（預設 `/cases`）且後端回 2xx，使用真實資料；
 * 否則回空（`isMock: true`）。強制 mock 旗標同樣回空，避免追蹤頁混入示範案件。
 */
export async function listTrackedCases(
  signal?: AbortSignal,
): Promise<TrackedCaseListResponse> {
  const path = import.meta.env.VITE_CASES_API_PATH ?? "/cases";
  const forceMock = import.meta.env.VITE_USE_CASE_TRACKING_MOCK === "true";

  if (forceMock) {
    return EMPTY_MOCK;
  }

  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) {
      return EMPTY_MOCK;
    }
    const body = (await response.json()) as {
      cases?: TrackedCase[];
      isMock?: boolean;
    };
    if (!Array.isArray(body.cases)) {
      return EMPTY_MOCK;
    }
    return { cases: body.cases, isMock: body.isMock ?? false };
  } catch {
    return EMPTY_MOCK;
  }
}
