# 後端 ↔ 資料層交接

這份文件記錄 backend workflow 與資料層（catalog、Entitlement Graph、Rule Engine、evidence、refresh／coverage）的交界、目前實作與 accepted target。

- 架構依據：[ADR-0013: Use SQLite Runtime Behind Repositories](../decisions/0013-use-sqlite-runtime-behind-repositories.md)
- 高階資料模型：[data-model.md](../data-model.md)
- 詳細目標 schema 與 contracts：[data-layer-rule-engine design](../../.kiro/specs/data-layer-rule-engine/design.md)
- Workflow 實作說明：[backend overview](../backend/backend-overview.html)
- 最後更新：2026-08-02

> **main × databaseV3 整合狀態**：FastAPI composition root 已把 SQLite／PostgreSQL
> repositories 注入最新 main 的多事件與 LLM workflow；主流程不改由資料庫控制。
> Workflow 測試仍可明確注入 fixture。SQLite migration 0008 已把 Case 2 七個候選項目、
> relevance graph 與候選來源寫入本機資料庫；沒有建立正式 Rule DSL 或 verified citation。
> PostgreSQL adapters 已有 legacy event alias，但 RDS 實際 graph／evidence rows 仍須在取得
> 私網連線與 database credentials 後驗證。候選資料不能標成 `verified`，只有人工審查過的
> 規則與依據才能進入完整資格判定。

> 程式碼描述目前實作；Accepted ADR 與 finalized spec 描述目標行為。兩者不一致時必須記錄 implementation gap，不能把目標文件當成已完成程式，也不能因 legacy code 存在而忽略 accepted architecture。

## 一、目前實作快照

| 能力 | 目前位置 | 狀態 |
| --- | --- | --- |
| 政府機關 OID、來源、文件與方案 catalog | `backend/app/services/benefit_catalog.py` 與 SQLite | 已有基礎；方案多為候選狀態 |
| Legacy 結構化規則欄位 | `program_rule_fields`、`backend/app/rules/engine.py` | 可運作，但不是 accepted canonical Rule DSL |
| Shared data contracts | `backend/app/orchestration/data_contracts.py` | 已對齊，候選項目包含 database summary |
| Storage-neutral interfaces 與離線實作 | `backend/app/orchestration/protocols.py` | 已落地；SQLite／PostgreSQL implementations 已接入 composition root |
| 規則引擎轉接 | `backend/app/orchestration/rule_adapter.py` | 已有 mapping 與安全降級，完整結構化資料仍待資料層提供 |
| 來源刷新組裝 | `backend/app/orchestration/source_refresh.py` | 本機 queue；不阻塞 request |
| 逐項判定組裝 | `backend/app/orchestration/determination.py` | 狀態閘門、單項失敗隔離與 SQLite EligibilityService 已接入；Case 2 尚無 approved rules |
| 欄位登記與缺漏計算 | `field_registry.py`、`missing_fields.py` | 已落地，資料內容仍是有限 draft |
| SQLite migration runner | `backend/app/adapters/sqlite/migrations.py` | migrations 0001–0008 已實作，0008 提供 Case 2 candidate vertical slice |

目前 workflow 測試仍可使用不連 SQLite 的 fixture implementations；正式本機 runtime 預設已使用 SQLite repositories。

## 二、責任邊界

| 層 | 負責 | 不負責 |
| --- | --- | --- |
| Data layer | SQLite canonical catalog、graph、rules、evidence、statuses、coverage、refresh adapters | Session 流程、API 呈現、以自然語言猜資格 |
| Rule Engine／EligibilityService | 狀態閘門、必要欄位與人工核准 Rule DSL 的確定性判斷 | Crawl、LLM 判定、資料自動驗證 |
| Workflow／state machine | Session、提問順序、停止／轉介條件、呼叫 storage-neutral ports | SQL、SQLite rows、個別福利門檻、重做 eligibility 判斷 |
| FastAPI composition root | 建立並注入具體 implementations 或 test fakes | 在 route 內臨時建立 adapter |
| API mapper／privacy | Requesting User response、score omission、敏感值清除 | 更改 eligibility 結論 |

LLM、crawler、importer、converter 與 exporter 都不能自動 verify 資料或決定 eligibility。

## 三、唯一 shared contracts 與 ports

整合以 `main` 已落地的模組作為唯一接縫：

- `backend/app/orchestration/data_contracts.py`
- `backend/app/orchestration/protocols.py`

Data-layer spec 不再建立 `backend/app/domain/contracts.py` 或 `backend/app/application/ports.py` 第二套定義。SQLite adapters 應直接實作 orchestration ports；資料表欄名、`sqlite3.Row`、SQL tuple 與 encoded metadata 不得跨過 adapter boundary。

| 介面 | Backend 問題 | 主要回傳 |
| --- | --- | --- |
| `EntitlementGraphRepository` | 事件牽動哪些項目？前置需求、產出與體系關係為何？ | `CandidateItem`、`GraphRelation` |
| `EligibilityService` | 需要哪些欄位？這個／這批項目可否做確定性判斷？ | `FieldRegistryEntry`、`EligibilityDecision` |
| `EvidenceRepository` | 哪些候選資料可顯示？實際評估的 source references 對應哪些已核准證據？ | `Citation` |
| `SourceRefreshService` | 目前 coverage 與 gaps 為何？是否已排入同日去重更新？ | coverage contracts、`RefreshReceipt` |

Repository 成功但沒有資料時回 immutable empty collection；open、query 或 mapping 失敗時 raise storage-neutral error，不能用空結果掩蓋失敗。

## 四、Owner 已確認的 contract 方向

- `GraphRelation` 採 `target_id`、`display_name`、`canonical_order`。
- `EligibilityDecision` 包含 stable、去重的 `missing_field_ids`。
- `Citation.published_at`、`effective_at`、`retrieved_at` 使用 timezone-aware `datetime | None`。
- `EvidenceRepository` 除 item lookup 外，提供依實際評估 `source_references` 查詢 citations 的操作。
- `get_candidate_citations` 可回 candidate／under_review／verified 供結果頁查閱；`get_citations` 保持 verified-only，兩者不得混用。
- Collections 使用 immutable tuple；空集合使用 `()`，不用 `None`。
- DB `program_id` 只在 adapter boundary 映射成 `item_id`。

### Owner 已確認的 Refresh／coverage 混合 shape

唯一 shared API 為：

- `get_coverage_status(CoverageScope) -> CoverageSnapshot`
- `CoverageScope(source_ids, domain_tags)` 明確限定觀測範圍；兩個條件都有時取交集。
- `RefreshRequest(event_id, source_ids, requested_at)` 保留 batch source request。
- `RefreshReceipt(job_id, accepted, deduplicated)` 分開表示是否排入與是否同日去重。

Coverage 使用 rich scope／snapshot；refresh 則保留 main 已落地的 batch event request 與
`accepted` flag。`event_id` 是 refresh job／dedup context，不取代 explicit coverage scope；state machine 的
預設空 local service 使用空 scope，但只要顯式注入 refresh service 就必須同時注入 scope，
避免服務看似啟用卻靜默不工作。

## 五、Legacy mapping 與 implementation gaps

| Legacy／目前形狀 | Accepted target／處理 |
| --- | --- |
| Orchestration 與 data-layer 各自規劃 contract 路徑 | 只保留 `app/orchestration/data_contracts.py` 與 `protocols.py` 作整合起點 |
| `GraphRelation.item_id`／`order` | **已對齊** `target_id`／`canonical_order` |
| `EligibilityDecision` 無 missing fields | **已加入** `missing_field_ids`，`needs_information` adapter 使用本次 decision 清單 |
| Citation 日期是 `str` | **已改為** timezone-aware `datetime | None`，naive datetime 會被拒絕 |
| EvidenceRepository 只有 item lookup | **已加入** source-reference exact lookup；完整結論仍待 SQLite adapter 逐一驗證 |
| `EligibilityResult.amount`／`amount_label` | 改為 amount quartet；不得由 label、title 或 excerpt 推定 |
| `reasons: list[str]` | 目標為 `StructuredReason`；legacy text 不能反推 actual 或 canonical condition |
| 單一 `source_url` | 由 EvidenceRepository exact-map 完整 Citation，不推定缺少 metadata |
| `program_rule_fields` 可寫 | 保存 legacy 後，改為 canonical Rule DSL 的 deterministic、lossless、唯讀 projection |
| Workflow `pending`／`declined_by_user` | 保持 workflow state，不寫入 catalog ProgramStatus |

`data_contracts.CandidateItem` 描述資料層候選與治理狀態；`state.CandidateItem` 描述本次使用者流程的判定狀態。兩者由 mapper 轉換，不能直接互換。

## 六、狀態、安全與隱私

| `program_status` | Runtime 行為 |
| --- | --- |
| `verified` | 規則與 citations 完整時做 deterministic evaluation；缺漏時降級 `needs_human_review` |
| `candidate`／`under_review` | 可見並警告；不做完整 evaluation，回 `needs_human_review` |
| `rejected`／`inactive` | 隱藏且 non-evaluable |
| `stale` | Owner 核准方案 B：可見並警告、不做完整 evaluation，固定回 `needs_human_review` |

`stale` 的 runtime 與文件語意已統一。方案 A（使用最後一次 verified snapshot 產生完整
結論）未採用；refresh 或新 candidate 資料也不能繞過人工審查自動恢復 `verified`。

其他安全邊界：

- `StructuredReason.actual` 只可回給當次 Requesting User，不得進 logs、traces、metrics、exceptions 或 audit。
- Raw user text 只存在 request-local extraction scope，完成、失敗或取消後都要丟棄。
- `relevance_score` 只供 backend deterministic sorting，API／frontend 完全省略。
- 完整 `eligible`／`ineligible` 結論需要實際評估 source references 的 approved citations；缺漏時降級。
- Crawler／LLM 只能產生 `candidate`／`under_review`，不得 auto-verify。

## 七、Runtime truth、refresh 與 AWS

SQLite 是目前 data-layer curation／runtime 的 accepted single source of truth，runtime 不讀 JSON catalog，也沒有 JSON fallback。這是目前 feature architecture，不代表已選定 production database。

依 main 的團隊規範，live AWS 可用於準備與驗證，但必須遵守：

- 不提交 credentials、tokens、`.env` 或 account-specific secrets。
- 新 AWS service 或 deployment choice 先取得 owner 共識並記錄 ADR。
- AWS 使用或遷移資訊集中更新 `docs/aws_migration_guide.md`。
- Local SQLite、files、fakes 與 deterministic tests 保持可用。

Refresh 必須先用 request-start committed state 建立 response，再非阻塞 enqueue；worker 失敗不能改變既有 response 或 last successful committed state。Coverage 只描述 measurable scope、status、counts 與 gaps，不宣稱法律或網站完整、零遺漏。

## 八、SQLite lifecycle

每個 read、transaction、exception、rollback 與 teardown path 都必須使用 `contextlib.closing` 或明確 `close()`。Read path 在 close 前完成 materialize／mapping；只有 commit 與 close 成功後才能回傳結果。錯誤訊息不得包含 SQL、row contents 或使用者值。

## 九、仍待 owner checkpoint 的 sequencing

- migration batch、backup marker、temporary-copy dry run、rollback 與 compatibility window
- legacy rows 人工核對與 canonical Rule DSL approval 的批次順序
- runtime reader 何時從 legacy engine 切到 SQLite-backed EligibilityService
- review tooling 何時停止寫 legacy `program_rule_fields`
- optional property-test dependency 與 JSON tests/release exporter
- future shared-write、production storage 或 AWS service selection

以上不得由單一 contributor 靜默決定。切換失敗時回到上一個受支援 schema與 last successful committed SQLite state，不回退成 JSON runtime。

## 十、整合後的責任邊界

- `main` 擁有使用者流程、LLM 事件萃取、複數事件確認、問答與送出時機。
- database adapters 擁有 graph expansion、deterministic eligibility、evidence 與 coverage／refresh。
- LLM 只萃取輸入或解釋結果，不得執行資格判定，也不得把 fixture 升成 `verified`。
- 下一個資料任務是取得 RDS 私網連線與 database credentials，核對現有 graph／evidence rows；缺資料時再用獨立 PostgreSQL seed 補齊，不覆寫隊友資料。
