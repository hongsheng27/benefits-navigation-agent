# ADR-0013: 在 Repository 邊界後使用 SQLite 作為 Runtime 真相來源

- Status: Accepted
- Date: 2026-07-27
- Supersedes: [ADR-0008: Curate in SQL, Serve from JSON](0008-curate-in-sql-serve-from-json.md)

## 背景

ADR-0008 在 MVP 只有個位數到低十位數方案、runtime 唯讀、資料更新頻率低的 demo 階段是合理選擇。把人工審查後的 SQL 資料匯出成 JSON，能讓現場展示不依賴網路、credentials 或外部服務，也能用 Git diff 審查小型資料集。

目前資料層範圍已擴大為動態 Entitlement Graph、來源更新、coverage 狀態、規則版本與審查狀態。若 runtime 仍只讀 JSON，資料庫與 JSON 會形成延遲同步的雙重真相，且難以一致處理 graph 查詢、refresh、`candidate`／`under_review`／`stale` 狀態與證據版本。因此 ADR-0008 的前提已不再符合目標架構。

本決策由專案 reviewer 與 owner 共同接受。它核准的是架構與文件對齊，**不表示 repository、schema migration、Rule DSL、privacy sanitizer、refresh worker 或 composition root 已完成實作**。

## 決定

### 1. 目前本機真相來源

在另有 owner-approved storage migration ADR 與替代 adapter 前，SQLite 同時是本機資料策展與 runtime 的單一真相來源。Runtime 只讀最近一次成功 commit 的完整狀態；SQLite 開啟或查詢失敗時回報安全錯誤，不切換到 JSON。

Catalog 不保存 raw user text、direct identifiers、session 對話、credentials 或其他使用者私密資料。

### 2. Storage-neutral 邊界與組裝位置

Runtime 只透過四個 storage-neutral 介面取用資料：

- `EntitlementGraphRepository`：事件展開、前置需求、產出與體系反查。
- `EligibilityService`：必要欄位、單筆與批次確定性資格判斷，以及方案狀態安全閘門。
- `EvidenceRepository`：依方案與規則來源參照取得官方證據。
- `SourceRefreshService`：coverage 狀態與非阻塞 on-demand refresh。

Owner 核准的 mixed API 以 `CoverageScope(source_ids, domain_tags)` 查詢
`CoverageSnapshot`；refresh request 保留 batch
`RefreshRequest(event_id, source_ids, requested_at)`，receipt 為
`RefreshReceipt(job_id, accepted, deduplicated)`。Coverage scope 必須由 caller 明確提供，
不得從 event ID 隱式推定。

FastAPI application composition root 建立並注入具體實作。Workflow 與 state machine 只依賴共同 domain contracts，不接觸 SQL、SQLite connection、`sqlite3.Row`、SQL tuple、資料表名稱或 SQLite 欄位名稱。未來若更換儲存技術，應替換 adapter，而不是改寫 workflow。

### 3. Canonical 規則與相容投影

SQLite 中 versioned、可遞迴巢狀 `all_of`／`any_of` 的 Rule DSL 是唯一 canonical 資格規則。規則版本保留必要欄位、condition、operator、expected value、label 與 source references。

`program_rule_fields` 只能是由 canonical Rule DSL deterministic、lossless 產生的唯讀 compatibility projection。不得人工分別維護 Rule DSL 與 `program_rule_fields`，也不得讓兩者成為並列真相。

### 4. 方案狀態與排序

Runtime 行為如下：

| 狀態 | 可見性與判斷 |
| --- | --- |
| `verified` | 規則與證據完整時可做確定性完整判斷；不完整時降級為 `needs_human_review`。 |
| `candidate`／`under_review` | 可見，但必須顯示尚未二次確認的警告；不做完整判斷，回 `needs_human_review`。 |
| `stale` | 可見並顯示 stale 警告；一律回 `needs_human_review`。 |
| `rejected`／`inactive` | 隱藏且不可評估。 |

`relevance_score` 只供 backend deterministic 排序，不代表資格機率或符合程度，API 與 frontend 不得接收該欄位、數值、區間、百分比或衍生值。

### 5. 隱私與可觀測性

`StructuredReason.actual` 只可回傳給當次請求的 Requesting User，用來解釋實際情況與規則要求的差異。Raw user text 與所有 `actual` 值必須在 serialization 與 emission 前，從 logs、traces、metrics、exceptions 與 audit payload 遞迴移除。

若 sanitizer 失敗或無法確認完整 payload 已安全處理，observability 必須 fail closed：不輸出原 payload，只能產生不含原內容衍生資訊的固定安全失敗指示。

### 6. Refresh 與 coverage

On-demand refresh 必須先用 request 開始時已 commit 的 SQLite 狀態建立回應，再排入本機背景工作；不得等待 crawler、附件處理或 LLM。Refresh 以來源、`event_id` 與 application timezone 的日期做同日去重；receipt 以 `accepted` 表示是否至少排入一個來源，以 `deduplicated` 表示是否被同日工作去重。

Crawler、importer 與 LLM 只能產生 `candidate` 或 `under_review` 資料，永遠不能自動標記為 `verified`。Coverage 只陳述指定 scope 與時間點的可量測狀態、數量與 gaps，不宣稱零遺漏、法律內容完整或所有福利均已索引。

### 7. JSON 的角色

JSON 不是 runtime input、startup prerequisite 或 fallback，也不能回寫 canonical SQLite。若 tests 或 release 流程需要 snapshot，只能由 SQLite 單向、deterministic、atomic 地產生帶版本 metadata 的選配 JSON。

### 8. AWS development strategy 與 SQLite lifecycle

依團隊規範，owner 核准後可使用 live AWS 進行準備與驗證；credentials、tokens、`.env` 與 account-specific secrets 永遠不得提交。Data-layer 目前仍使用本機 SQLite、本機檔案與本機背景工作，任何 production database、queue、object storage、LLM hosting 或 deployment service 都需要另立決策，並在同一變更中更新 `docs/aws_migration_guide.md`。Local tests 不得依賴 live AWS 才能執行。

所有 SQLite connections 必須使用 `contextlib.closing` 或等價的明確 close guarantee；不能只依賴 `with sqlite3.connect(...)`，因為它管理 transaction 但不保證關閉 connection。

## 理由

- 單一 committed SQLite 狀態消除 SQL 與 runtime JSON 的同步落差。
- 四個 storage-neutral 介面讓 workflow、規則與儲存技術可分開測試與演進。
- 唯一 canonical Rule DSL 加唯讀相容投影避免規則雙寫與語意漂移。
- 狀態閘門、證據完整性與 human review 保留保守、安全且可稽核的資格行為。
- Current-data-first refresh 保持請求延遲可預測，並把 crawler／LLM 限制在候選資料階段。
- 本機實作保留賽前可離線、無 credentials 的優點，而不再以 JSON 作 runtime 真相。

## 後果

### 正面

- Curation、graph、rules、evidence、coverage 與 runtime 查詢共享同一 committed truth。
- Workflow 不綁定 SQLite，未來 adapter 替換不需要重寫 state machine。
- API 不暴露容易被誤解的 relevance score；未審查或 stale 資料不會產生完整資格結論。
- 隱私與 connection lifecycle 成為跨 adapter 的明確驗證要求。

### 負面與成本

- SQLite schema、migration、repositories、Rule DSL converter、composition root 與 validation suite 都需要新增或重構；目前尚未完成。
- Runtime 現在依賴本機 SQLite 可用性；資料庫失敗時不再有 JSON fallback。
- Legacy `program_rule_fields` 需要保留、人工核對並逐步轉為 canonical Rule DSL，不能自動假定為已驗證規則。
- 單機 SQLite 與本機 worker 不處理未來多實例 shared-write 需求；該需求留給之後獨立決策。

## 遷移與回滾

1. 先盤點並備份現有 schema、legacy rule rows 與 checksums，不修改 `data/local/*.db` 的未備份共享副本。
2. 以 ordered、transactional migrations 加入 schema metadata、domain tables、graph、Rule DSL、evidence、coverage、refresh 與 review records。
3. 將既有可寫 `program_rule_fields` 原樣保存為 legacy artifact；轉換結果只能先成為 `candidate`／`under_review`，不得自動 verify。
4. 經人工核對 canonical Rule DSL、citations 與版本後，產生 deterministic、lossless、唯讀 compatibility projection。
5. 建立並驗證四個 SQLite adapters、FastAPI composition root、workflow fakes、privacy filters 與 connection closure，再切換 runtime reader。
6. 切換失敗時，回滾該次 transaction／migration，恢復上一個已支援 schema 與最後成功 committed SQLite 狀態；不得回退成 JSON runtime。
7. Legacy table 只在另一次 owner 核准、consumer inventory 與 rollback window 完成後移除。

## 考慮過的替代方案

### 維持 ADR-0008：SQL 策展、JSON runtime

對低十位數、唯讀 demo 仍簡單可靠，但無法避免動態 graph、refresh、coverage 與審查狀態的雙重真相，因此不採用。

### SQLite 與 JSON 都可作 runtime fallback

表面上提高可用性，實際上會產生兩個可能不同版本的真相，且難以說明查詢與審查狀態來自哪一份資料，因此不採用。

### Workflow 直接查 SQL

短期程式碼較少，但會把 schema、row shape 與 transaction 細節帶進 state machine，阻礙測試與未來 adapter 替換，因此不採用。

### 現在選定 production AWS service

目前沒有 live AWS 權限與足夠的容量、成本、部署或一致性證據；提前選型會增加不必要承諾，因此延後到獨立 ADR。

## 相關文件

- [資料模型高階說明](../data-model.md)
- [SQLite runtime alignment proposal](../back_database_doc/sqlite-runtime-alignment-proposal.md)
- [AWS migration guide](../aws_migration_guide.md)
- [Data-layer rule-engine requirements](../../.kiro/specs/data-layer-rule-engine/requirements.md)
- [Data-layer rule-engine design](../../.kiro/specs/data-layer-rule-engine/design.md)
