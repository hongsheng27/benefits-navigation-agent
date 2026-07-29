# 資料模型

這份文件說明資料層的高階模型、runtime 邊界與治理語意，不是完整 SQL migration 清單。詳細的 proposed schema、constraints、indexes、migration 與 rollback 設計見 [data-layer-rule-engine design](../.kiro/specs/data-layer-rule-engine/design.md)。架構決策見 [ADR-0013: Use SQLite Runtime Behind Repositories](decisions/0013-use-sqlite-runtime-behind-repositories.md)。

> 目前狀態：requirements、design 與 ADR 已核准；程式碼 migration、repositories、Rule DSL 與 runtime wiring 尚未完成。以下描述目標架構，不代表每個 model 已存在。

## Runtime 真相與存取路徑

本機 SQLite 是目前資料策展與 runtime 的單一真相來源，直到另有 owner-approved storage migration ADR 與替代 adapter。Runtime 讀取最近一次成功 commit 的完整狀態，且不載入 JSON catalog、不使用 JSON fallback。

```text
SQLite canonical catalog
    ↓ SQLite adapters
Storage-neutral repositories / services
    ├── EntitlementGraphRepository
    ├── EligibilityService
    ├── EvidenceRepository
    └── SourceRefreshService
    ↓
Workflow / state machine
    ↓
API response mapper
```

FastAPI application composition root 建立具體 adapters 並注入 workflow。Workflow 與 state machine 只使用 immutable domain contracts，不接觸 SQL、SQLite connections、rows、tuples、table names 或 column names。

## 1. Catalog、方案與治理狀態

方案 model 保存穩定的 `item_id`、顯示名稱、治理狀態、結構化金額（若已核准）、目前資料版本與 review metadata。資料庫內既有 `program_id` 只在 adapter boundary 映射成跨層 `item_id`。

合法治理狀態與 runtime 行為：

| 狀態 | Runtime 行為 |
| --- | --- |
| `verified` | 規則與 citations 完整時可做完整確定性判斷；缺漏時為 `needs_human_review`。 |
| `candidate`／`under_review` | 可見並帶尚未二次確認警告；不做完整判斷。 |
| `stale` | 可見並帶 stale 警告；一律 `needs_human_review`。 |
| `rejected`／`inactive` | 隱藏且不可評估。 |

狀態轉換另存 history 與 reviewer reference。Crawler、importer、converter、exporter 或 LLM 都不能把資料標記為 `verified`。

## 2. Entitlement Graph

Entitlement Graph 以唯一 ID 的 typed nodes 與 directed edges 表示人生事件、體系、方案、機關與文件需求。高階 node types 包含：

- life event
- system
- benefit program／administrative item
- agency
- document requirement

高階 edge types 包含 `triggers`、`belongs_to`、`requires`、`produces` 與 `administered_by`。Edge 可有以 field registry ID 表示的 path conditions。

Graph repository 負責事件展開、前置需求、產出、體系反查與穩定排序。未知的 path condition 欄位會保留仍可能成立的 path 並回報缺漏欄位；已知不符只排除該 path。Graph 只判斷「是否仍可能相關」，不取代 EligibilityService 的資格判斷。

## 3. Field Registry

Field registry 是資料層、workflow 與規則引擎共用的資格欄位詞彙表。每筆至少描述：

- `field_id`
- data type
- allowed values
- prompt label
- why needed
- PII classification
- active/version metadata

Rule DSL、graph conditions 與 workflow 問題卡都引用相同 `field_id`。欄位型別或合法值不能由 frontend 或自由文字臨時推定。

## 4. Canonical versioned Rule DSL

SQLite 中 versioned、可巢狀的 Rule DSL 是唯一 canonical 資格規則。每個 rule version 至少保存：

- `rule_id`、`item_id`、rule version 與 DSL version
- required field IDs
- 唯一 root 的遞迴 `all_of`／`any_of` tree
- leaf condition 的 ID、field、operator、expected value、label 與 source reference
- review／approval metadata

```json
{
  "rule_id": "synthetic-rule",
  "item_id": "synthetic-item",
  "version": "v1",
  "required_field_ids": ["synthetic-field"],
  "logic": {
    "all_of": [
      {
        "condition_id": "synthetic-condition",
        "field_id": "synthetic-field",
        "operator": "==",
        "expected": "synthetic-value",
        "label": "合成測試條件",
        "source_reference": "synthetic-source-ref"
      }
    ]
  }
}
```

以上只有資料形狀示意，不包含福利事實。Rule Engine 只執行目前唯一、有效且人工核准的 canonical version；不得在 Python control flow 硬編碼個別方案門檻。

### 唯讀 compatibility projection

`program_rule_fields` 不再是另一份人工維護的規則。它是由 canonical Rule DSL 透過 deterministic、lossless converter 產生的唯讀 compatibility projection：

- 同一 rule/converter version 產生穩定順序與等價 serialization。
- Canonical → projection → canonical round trip 必須保留 nested boolean semantics、conditions、fields、operators、values、labels 與 source references。
- 無法無損表示時整次拒絕，不產生部分 projection。
- Direct insert、update、delete 必須被拒絕。

Legacy writable rows 只供遷移盤點與人工核對，不能與 canonical Rule DSL 雙寫。

## 5. Evidence 與 Citations

Evidence model 將 registered official source、document metadata、人工核准 excerpt、方案關聯與 rule source reference 分開保存。跨層 `Citation` 至少包含：

- `document_id`
- title、publisher、URL、excerpt
- optional `published_at`、`effective_at`、`retrieved_at`

Optional 日期缺失時維持空值，不推定替代日期；有值時使用 timezone-aware `datetime`，
不得用無時區字串跨越 adapter boundary。完整 `eligible`／`ineligible` 結論必須讓實際評估過的每個 distinct source reference 都可解析到已核准 citation；缺漏時降級為 `needs_human_review`。

## 6. Shared domain contracts

Storage-neutral 邊界使用 immutable contracts，而不是 SQLite rows。高階 contracts 包含：

| Contract | 用途 |
| --- | --- |
| `CandidateItem` | 候選 ID、顯示名稱、治理狀態、backend-only relevance metadata、缺漏欄位與 graph relations。 |
| `EligibilityDecision` | eligibility status、結構化金額、缺漏欄位與 structured reasons。 |
| `StructuredReason` | condition、field、operator、expected、actual、label 與 source reference。 |
| `Citation` | 可追溯的已核准官方證據。 |
| `FieldRegistryEntry` | workflow 提問與資料驗證的共用詞彙。 |
| `CoverageMetadata`／`CoverageSnapshot` | 指定 scope 與觀測時間的來源進度及 gaps。 |
| `RefreshRequest`／`RefreshReceipt` | 非阻塞更新與同日去重結果。 |

`relevance_score` 只留在 backend contract 供 deterministic sorting；API 與 frontend 不得收到該欄位或任何衍生數值。

`StructuredReason.actual` 只可回傳給當次 Requesting User。Raw user text 與 actual values 必須在輸出 logs、traces、metrics、exceptions 或 audit 前遞迴移除；sanitization 無法確認時 observability fail closed。

## 7. Coverage 與 Refresh

Coverage model 保存 registered source scope、crawl status、最近成功時間、已索引文件數、domain tags、觀測時間與 gap categories。`CoverageScope(source_ids, domain_tags)` 明確限定查詢範圍，`CoverageSnapshot` 的所有 per-source metadata 共用同一個 timezone-aware `observed_at`，且 registered/status/indexed aggregate counts 必須與 sources 相等。它只描述可量測進度與已知缺口，不保證法律內容完整、網站完整、零遺漏或所有福利均已索引。

Owner 核准的混合 refresh contract 是
`RefreshRequest(event_id, source_ids, requested_at)` 與
`RefreshReceipt(job_id, accepted, deduplicated)`。`event_id` 作為 job 與同日去重 context；
coverage 範圍仍由 explicit `CoverageScope` 決定，不能以 event ID 隱式猜測。On-demand refresh 的資料模型包含 source、event、application timezone calendar date、dedup key、job status 與安全錯誤碼。請求流程：

1. 先從 request 開始時已 commit 的 SQLite 狀態建立回應。
2. 再以本機背景工作 enqueue 到期來源。
3. 相同 source＋event/topic＋日期只建立一個 job。
4. Worker 失敗不改變已建立的回應或 last successful committed state。
5. 新資料只能進入 `candidate`／`under_review`，等待人工審查。

## 8. JSON Snapshot

JSON 只可由 SQLite 單向、deterministic、atomic 產生，供 tests fixture 或 release snapshot 使用。Snapshot 應包含 schema、data、Rule DSL versions 與 export timestamp。

JSON 不是 runtime input、startup requirement、fallback 或 SQLite import source；不得人工同步維護 SQLite 與 JSON 兩份內容。

## 9. SQLite Lifecycle 與資料邊界

每條 SQLite connection 都要以 `contextlib.closing` 或等價 `finally: close()` 明確關閉。Read path 必須在 close 前 materialize/map 完成；transaction failure 先嘗試 rollback，再 close，最後只回安全錯誤。不能只依賴 `with sqlite3.connect(...)`。

Canonical catalog 明確排除 raw user text、direct identifiers、credentials 與 session 對話。Local SQLite、local files、local jobs 與 local/mock LLM 保持預設且可測試；owner 核准後可加入 live AWS adapter，但本資料模型不選定 production AWS service，且任何 secrets 都不得進入 repository。

## 相關文件

- [ADR-0013: Use SQLite Runtime Behind Repositories](decisions/0013-use-sqlite-runtime-behind-repositories.md)
- [被取代的 ADR-0008](decisions/0008-curate-in-sql-serve-from-json.md)
- [SQLite runtime alignment proposal](back_database_doc/sqlite-runtime-alignment-proposal.md)
- [Requirements](../.kiro/specs/data-layer-rule-engine/requirements.md)
- [Detailed proposed design/schema](../.kiro/specs/data-layer-rule-engine/design.md)
