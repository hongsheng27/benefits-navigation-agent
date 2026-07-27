# Architecture Decision Records

每項已定案的關鍵技術選擇新增一份 ADR。

## Current decisions

- [ADR-0001: Use a Modular Monolith for the Backend](0001-backend-modular-monolith.md)
- [ADR-0002: Use FastAPI for the HTTP API](0002-use-fastapi-for-http-api.md)
- [ADR-0003: Use Policy-Governed Hybrid Orchestration](0003-policy-governed-hybrid-orchestration.md)
- [ADR-0004: Trial Strands for the Bounded Agent Runner](0004-trial-strands-agent-runner.md)
- [ADR-0005: Split Client and Server Session State](0005-split-client-server-session-state.md)
- [ADR-0006: Use React, Vite, TypeScript, and Tailwind CSS](0006-use-react-vite-typescript-tailwind.md)
- [ADR-0007: Limit Data Retention and Egress](0007-limit-data-retention-and-egress.md)
- [ADR-0008: Curate in SQL, Serve from JSON](0008-curate-in-sql-serve-from-json.md)
- [ADR-0009: Use Generated SQLite for the Local Government OID Registry](0009-use-generated-sqlite-for-government-oid.md)
- [ADR-0010: Use a Provenance-First Local Benefit Catalog](0010-use-local-provenance-first-benefit-catalog.md)
- [ADR-0011: Use Frozen Pydantic Models for Session Workflow State](0011-frozen-pydantic-session-workflow-state.md)

新 ADR 至少記錄背景、決定、理由與後果。候選方案不必逐一列出，除非那個比較本身是
決策的重點。

## 新增 ADR 前先確認編號

編號撞過一次：兩個分支各自新增 ADR-0008，合併時才發現，最後要改檔名、改標題，
還要更新四個檔案裡的引用。

所以新增之前：

1. 看 `docs/decisions/` 目前最大的編號。
2. 用 `git branch -a` 檢查其他未合併的分支有沒有也在寫 ADR。本目錄的最大編號**不代表**
   全專案的最大編號。
3. 若無法確認，在分支上先用一個明顯的暫定名稱，合併前再定編號。

改編號時要一併更新：檔名、檔案第一行的標題、本索引、根目錄 `README.md`，
以及任何引用它的文件或程式註解。
