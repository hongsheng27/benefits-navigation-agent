/**
 * 追蹤進度 API client。
 *
 * 預定契約：`GET /cases` → `{ cases: TrackedCase[], isMock?: boolean }`
 * 後端尚未實作時回傳前端 mock，方便頁面先接好資料流。
 */

import { apiBaseUrl } from "./client";
import { MOCK_TRACKED_CASES } from "../mocks/trackedCases";
import type { TrackedCase } from "../types/tracking";

export type TrackedCaseListResponse = {
  cases: TrackedCase[];
  isMock: boolean;
};

/**
 * 取得使用者的追蹤案件列表。
 *
 * 若設定 `VITE_CASES_API_PATH`（預設 `/cases`）且後端回 2xx，使用真實資料；
 * 否則退回 mock。
 */
export async function listTrackedCases(
  signal?: AbortSignal,
): Promise<TrackedCaseListResponse> {
  const path = import.meta.env.VITE_CASES_API_PATH ?? "/cases";
  const forceMock = import.meta.env.VITE_USE_CASE_TRACKING_MOCK === "true";

  if (forceMock) {
    return { cases: MOCK_TRACKED_CASES, isMock: true };
  }

  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) {
      return { cases: MOCK_TRACKED_CASES, isMock: true };
    }
    const body = (await response.json()) as {
      cases?: TrackedCase[];
      isMock?: boolean;
    };
    if (!Array.isArray(body.cases)) {
      return { cases: MOCK_TRACKED_CASES, isMock: true };
    }
    return { cases: body.cases, isMock: body.isMock ?? false };
  } catch {
    return { cases: MOCK_TRACKED_CASES, isMock: true };
  }
}
