/**
 * 補助機關總覽 API client。
 *
 * 預定契約：`GET /agencies` → {@link AgencyListResponse}
 * 後端尚未實作時回傳前端 mock（對齊 source_registry 形狀）。
 */

import { apiBaseUrl } from "./client";
import { MOCK_AGENCY_LIST_RESPONSE } from "../mocks/agencies";
import type { AgencyListResponse } from "../types/agency";

/**
 * 取得機關／官方來源目錄。
 *
 * - `VITE_USE_AGENCY_MOCK=true`：強制 mock
 * - 否則嘗試 `VITE_AGENCIES_API_PATH`（預設 `/agencies`），失敗則退回 mock
 */
export async function listAgencies(
  signal?: AbortSignal,
): Promise<AgencyListResponse> {
  const path = import.meta.env.VITE_AGENCIES_API_PATH ?? "/agencies";
  const forceMock = import.meta.env.VITE_USE_AGENCY_MOCK !== "false";

  // 預設強制 mock，直到後端提供穩定 endpoint；設為 false 才打真實 API。
  if (forceMock) {
    return MOCK_AGENCY_LIST_RESPONSE;
  }

  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      headers: { Accept: "application/json" },
      signal,
    });
    if (!response.ok) {
      return MOCK_AGENCY_LIST_RESPONSE;
    }
    const body = (await response.json()) as AgencyListResponse;
    if (!Array.isArray(body.agencies)) {
      return MOCK_AGENCY_LIST_RESPONSE;
    }
    return {
      agencies: body.agencies,
      isMock: body.isMock ?? false,
    };
  } catch {
    return MOCK_AGENCY_LIST_RESPONSE;
  }
}
