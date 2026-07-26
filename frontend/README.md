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

可複製根目錄 `.env.example` 所列的 `VITE_API_BASE_URL` 到 frontend 的
`.env.local`。未設定時，開發環境預設連線至 `http://localhost:8000`。

## Checks

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

目前頁面是可執行的 frontend scaffold。輸入後的結果仍是明確標示的 mock，不會傳送
使用者資料或執行資格判斷。正式 API、session、PII 與 eligibility contracts 仍需由
專案負責人實作或密切審查。
