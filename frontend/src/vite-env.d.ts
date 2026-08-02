/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** 預設 true；設為 "false" 才打真實 GET /agencies */
  readonly VITE_USE_AGENCY_MOCK?: string;
  readonly VITE_AGENCIES_API_PATH?: string;
  /** 設為 "true" 強制案件追蹤使用 mock */
  readonly VITE_USE_CASE_TRACKING_MOCK?: string;
  readonly VITE_CASES_API_PATH?: string;
  /** 設為 "true" 強制諮詢後 Copilot 使用本機 stub，不打 explain API */
  readonly VITE_USE_POST_CONSULT_COPILOT_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
