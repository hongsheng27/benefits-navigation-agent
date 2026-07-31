# Frontend

使用 React、Vite、TypeScript 與 Tailwind CSS，負責：

- 人生事件輸入與對話介面
- 缺漏資格欄位問題
- 福利結果、判斷依據與官方來源
- 申請順序與 checklist

## Local development

```bash
npm install
npm run dev
```

## Checks

Commit 前請先跑 `npm run format`，再跑其餘檢查：

```bash
npm run format
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

排版由 Prettier 決定（設定見 `.prettierrc.json`），請安裝 EditorConfig 外掛以套用
根目錄的 `.editorconfig`。

目前 `src/features/navigator/` 下是可執行的五畫面導覽原型（描述狀況、狀況解讀、
媒合與評估、準備清單/詳情、我的資料），資料與資格判斷邏輯全部是明確標示的 mock，
不會呼叫任何後端 API，也不會傳送使用者資料。正式 API、session、PII 與 eligibility
contracts 仍需由專案負責人實作或密切審查；資格判定只能由 deterministic rule engine
（`src/features/navigator/benefitEngine.ts`）產生，不得改由 LLM 決定或覆寫。
