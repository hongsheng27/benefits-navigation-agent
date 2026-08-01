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
- [ADR-0008: Curate in SQL, Serve from JSON](0008-curate-in-sql-serve-from-json.md) — **Superseded**
- [ADR-0009: Use Generated SQLite for the Local Government OID Registry](0009-use-generated-sqlite-for-government-oid.md)
- [ADR-0010: Use a Provenance-First Local Benefit Catalog](0010-use-local-provenance-first-benefit-catalog.md)
- [ADR-0011: Use Frozen Pydantic Models for Session Workflow State](0011-frozen-pydantic-session-workflow-state.md)
- [ADR-0012: Deterministic State Machine with Loop Guardrails](0012-deterministic-state-machine-with-guardrails.md)
- [ADR-0013: Use SQLite Runtime Behind Repositories](0013-use-sqlite-runtime-behind-repositories.md) — supersedes ADR-0008
- [ADR-0014: Keep Fixture Data Out of the Verified Governance Status](0014-keep-fixture-data-out-of-verified-status.md)
- [ADR-0015: Use a Narrow LLM Port Instead of an Agent Loop](0015-narrow-llm-port-instead-of-agent-loop.md)
- [ADR-0016: Use Bedrock as the Only Live LLM Provider](0016-use-bedrock-only-live-llm-provider.md)
- [ADR-0017: Target RDS PostgreSQL and S3 for the Hackathon Data Layer](0017-target-rds-postgresql-and-s3.md)
- [ADR-0018: Preserve Legacy Rule Fields Through a Read-only Bridge](0018-preserve-legacy-rules-through-read-only-bridge.md)

新 ADR 至少記錄背景、決定、理由與後果。候選方案不必逐一列出，除非那個比較本身是
決策的重點。

`origin/feat/databaseV3` 合併時發現它新增的 ADR-0014／0015 與 main 已使用的編號
重複，因此資料層的兩份決策在整合分支改編為 ADR-0017／0018；決策內容不變。

## 新增 ADR 前先確認編號

編號撞過一次：兩個分支各自新增 ADR-0008，合併時才發現，最後要改檔名、改標題，
還要更新四個檔案裡的引用。

查其他分支的可靠做法（不必逐一 checkout）：

```
git fetch
git log --all --name-only --pretty=format: -- 'docs/decisions/*' | Sort-Object -Unique
```

這會列出**所有分支歷史上曾經存在**的 ADR 檔名，包含還沒合併進 `main` 的。
ADR-0014 就是這樣發現 0013 已經被佔用的。

所以新增之前：

1. 看 `docs/decisions/` 目前最大的編號。
2. 用 `git branch -a` 檢查其他未合併的分支有沒有也在寫 ADR。本目錄的最大編號**不代表**
   全專案的最大編號。
3. 若無法確認，在分支上先用一個明顯的暫定名稱，合併前再定編號。

改編號時要一併更新：檔名、檔案第一行的標題、本索引、根目錄 `README.md`，
以及任何引用它的文件或程式註解。
