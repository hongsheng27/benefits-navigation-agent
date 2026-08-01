# ADR-0017: 以 RDS PostgreSQL 與 S3 作為 Hackathon 資料層目標

- Status: Accepted
- Date: 2026-07-29
- Complements: [ADR-0013: 在 Repository 邊界後使用 SQLite 作為 Runtime 真相來源](0013-use-sqlite-runtime-behind-repositories.md)

## 背景

ADR-0013 已決定在本機以 SQLite 作為資料策展與 runtime 的單一真相來源，並以 storage-neutral repositories 隔離 Workflow。Hackathon 的 AWS 環境開放後，owner 希望把共享資料庫與附件移到 AWS，而不是把單機 SQLite 檔案當成 production shared-write database。

Entitlement Graph、versioned Rule DSL、official evidence、review records 與 source-reference mapping 都依賴 foreign keys、unique constraints、partial indexes 與 transaction。把這個關聯模型改成 DynamoDB partition/sort-key 模型會需要重新設計 integrity、joins 與 migration；把 SQLite 檔案上傳到 S3 則不提供 database transaction、locking 或多 instance coordination。

目前日期仍早於 Hackathon AWS 資源開放日。這份決策只固定目標與 adapter 邊界，不授權現在建立資源、連線 AWS 或讀取 credentials。

## 決定

1. 本機開發、migration tests 與離線 fallback-free runtime 繼續使用 SQLite，直到 RDS adapter、PostgreSQL migrations、資料轉移與 cutover 驗證完成。
2. Hackathon shared relational database 的目標服務採用 Amazon RDS for PostgreSQL。
3. 官方 HTML、PDF 與附件物件的目標 storage 採用 Amazon S3；database 保存 metadata、hash、source URL 與 opaque object key/reference。`document_attachments` 另保存 per-row storage backend；`source_documents` 則由 composition root 選定的 object adapter 以整批 local 或 S3 模式解析，不支援同一 deployment mixed backend。
4. Workflow、state machine、Rule Engine 與 domain contracts 不接收 PostgreSQL、RDS、S3 或 AWS SDK types。切換只發生在 FastAPI composition root 與 storage adapters。
5. SQLite schema 保持 relational、stable-ID-first 與 transaction-first；PostgreSQL adapter 保留相同 node、edge、rule version、evidence、review 與 source-reference semantics。
6. SQLite typed JSON 的 `expected_value_type + expected_value_json` 在 PostgreSQL 使用 type tag 加 `JSONB`；timestamps 改為 `TIMESTAMPTZ`；partial unique indexes、foreign keys 與 all-or-none constraints保留等價語意。
7. `source_documents` 與 `source_registry` 維持多對多 provenance，由 association table 保存同一文件從多個已登記來源被發現的紀錄；RDS schema 不將其降級成只能有一個 `source_id`。
8. Attachment `storage_backend` 支援 `local` 與 `s3`，`storage_ref` 對 application 是 opaque reference。`source_documents` 沿用 opaque `storage_ref`，由全域 object adapter 整批選擇 local 或 S3，不允許同一 deployment 混合解析。S3 path validation、bucket policy 與 upload/download implementation 留在未來 S3 adapter，不放進 Workflow 或 Rule DSL。
9. AWS cutover 前必須使用 Git 外 credentials、保留完全不需要 AWS 的 local tests，並依 `docs/aws_migration_guide.md` 執行 migration、verification 與 rollback。

## 理由

- PostgreSQL 最接近現有 relational model，可保留 deterministic integrity，而不需要把 Graph、Rule DSL 和 evidence joins 重寫成 application-level constraints。
- RDS PostgreSQL 比在 Hackathon 期間重新設計 DynamoDB access patterns 更容易驗證、除錯和回滾。
- S3 適合存放文件與附件物件，但不適合承載可寫 SQLite database file。
- Storage-neutral repositories 已提供 adapter replacement seam，使本機 SQLite 與 AWS paths 可以共用 Workflow tests 和 domain semantics。
- 多對多 source-document provenance 保留官方來源追蹤，避免同一 canonical document 被多個入口發現時遺失資訊。

## 後果

### 正面

- Task 1.4 之後的 schema 可以明確維持 PostgreSQL 可移植性。
- Graph、rules、evidence 與 review constraints 可在本機和 RDS 保持同一語意。
- 大型文件不進 Git 或 relational rows；S3 object 與 DB metadata 責任分離。
- Local tests 仍可在無 AWS、無 credentials、無 network 的環境執行。

### 負面與成本

- SQLite 與 PostgreSQL 需要各自的 migration dialect；SQLite SQL 檔不能直接拿到 RDS 執行。
- 需要新增 PostgreSQL connection pool、adapter implementations、schema migration、data copy、verification 與 rollback procedure。
- SQLite `json_valid`／`json_type`、dynamic numeric typing 與部分 DDL introspection 必須改寫為 PostgreSQL `JSONB`、numeric types 與 catalog queries。
- S3 adapter 需要 bucket policy、object-key validation、error mapping 與 local fixture implementation。
- RDS networking、security group、credentials、TLS、backup 與 availability 仍需在 AWS 環境開放後驗證。

## 遷移與回滾

1. 在本機完成 ordered SQLite migrations、repositories、Rule DSL validator 與 integration tests。
2. 建立 PostgreSQL dialect migrations，使用 temporary/local PostgreSQL 或 disposable test environment 驗證，不讓 Workflow 依賴 dialect。
3. AWS 環境開放後建立 RDS PostgreSQL 與 S3，使用 Git 外 credentials 和最小權限。
4. 從 SQLite last successful committed state 匯出 canonical rows，依 dependency order 匯入 RDS，重新計算 counts/checksums，執行 FK、rule/evidence 與 synthetic isolation validation。
5. 上傳全部文件物件到 S3，逐一驗證 hash，transactionally 更新 opaque object keys 後才整批切換 source-document object adapter；不允許 mixed local/S3 source-document mode。附件可逐列更新 `storage_backend='s3'` 與 opaque object key，但同樣必須先通過 hash 驗證。
6. 只在完整 validation 通過後，於 composition root 將 adapters 切到 PostgreSQL/S3。
7. Cutover 失敗時切回未修改的 SQLite adapter 與 local object storage；不得改用 JSON runtime fallback。

## 考慮過的替代方案

### DynamoDB

適合已知 access patterns 的 key-value workload，但目前 Graph、recursive Rule DSL、evidence mapping、human review 與 migration integrity 會需要重新設計，超出 Hackathon 最小風險路徑，因此不採用為本資料層目標。

### Aurora PostgreSQL

能保留 PostgreSQL compatibility，但 Hackathon 階段的 provisioning、成本與操作複雜度高於目前需要。若現場帳號限制或容量需求改變，可另立 ADR 取代 RDS target。

### 將 SQLite database file 放到 S3 或共享檔案系統

S3 不提供 SQLite 所需的 random-write transaction 與 locking；共享檔案系統也保留單機 database 的 concurrency 與故障風險，因此不作為 shared runtime database。

## 相關文件

- [AWS migration guide](../aws_migration_guide.md)
- [Data-layer Rule Engine requirements](../../.kiro/specs/data-layer-rule-engine/requirements.md)
- [Data-layer Rule Engine design](../../.kiro/specs/data-layer-rule-engine/design.md)
