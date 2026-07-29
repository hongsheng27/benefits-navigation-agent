# 實作計畫：資料層與規則引擎補齊

## 概述

本計畫依 finalized `requirements.md` 與 `design.md`，將資料庫遷移、storage-neutral contracts、SQLite adapters、純 Rule DSL evaluator、相容投影、隱私、FastAPI 注入、本機 refresh／curation、選用 JSON exporter 與驗證工作拆成可由 coding agent 逐批執行的 Python 任務。每一批都以前一批產物為基礎，最後完成 runtime wiring 與可執行驗證；不得建立 JSON runtime fallback、硬編碼個別方案規則、加入未核准福利事實，或在未經 owner 核准及未同步 `docs/aws_migration_guide.md` 的情況下新增 live network、AWS resource、credential lookup 或 live LLM path。

## 已滿足的前置條件

架構與文件對齊已完成：owner 已接受 [ADR-0013 SQLite runtime](../../../docs/decisions/0013-use-sqlite-runtime-behind-repositories.md)，且 README、AWS migration guide 與 finalized spec 已對齊 SQLite runtime 單一真相來源、storage-neutral repositories 與無 JSON fallback。此 accepted 決策只核准架構與文件，**不表示 schema migration、repositories、Rule DSL、privacy sanitizer、refresh worker、composition root 或其他 feature code 已實作**；因此本計畫所有 checkbox 仍保持未勾選。

## Tasks

> **Approval Gate — Schema migration（非執行任務）**：在執行 1.1 前，owner 必須核准 migration 順序、legacy preservation、備份／rollback、相容窗口與只在暫存副本執行 dry run 的方式；不得直接變更 `data/local/*.db` 或未備份的共享資料庫。Converted legacy rules 只能是 `candidate`／`under_review`，不得因 migration、converter 或 importer 自動成為 `verified`。

- [ ] 1. 建立 schema、migration 與 legacy preservation 基礎
  - [x] 1.1 建立 ordered migration runner 與 schema metadata
    - 實作 checksum、transaction、supported-version guard、safe error，以及 `schema_metadata`、`schema_migrations`、`catalog_revisions` 的 migration；所有連線啟用 foreign keys。
    - Expected files/modules：`backend/app/adapters/sqlite/migrations.py`、`backend/app/adapters/sqlite/migration_sql/0001_metadata.sql`、`scripts/migrate_catalog.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/adapters/sqlite/test_migrations.py -q -k 'version or checksum'`
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.8, 1.9, 13.2, 13.3_

  - [x] 1.2 建立 programs、status history、review 與 field registry schema
    - 新增 `benefit_programs`、`program_status_history`、`review_approvals`、`field_registry`、`field_allowed_values`；加入 status、amount all-or-none、review metadata、uniqueness 與必要 indexes。
    - Expected files/modules：`backend/app/adapters/sqlite/migration_sql/0002_programs_fields.sql`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_schema_programs.py -q`
    - _Requirements: 1.5, 3.7, 3.13, 3.14, 3.15, 7.1–7.8, 15.4, 16.9–16.13_

  - [ ] 1.3 建立 typed Entitlement Graph schema
    - 新增 nodes、edges、edge conditions、graph versions、endpoint／program／field references、edge-type checks、stable-order indexes 與 batch referential integrity constraints。
    - Expected files/modules：`backend/app/adapters/sqlite/migration_sql/0003_graph.sql`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_schema_graph.py -q`
    - _Requirements: 4.1, 4.2, 4.8, 4.10_

  - [ ] 1.4 建立 canonical Rule DSL、evidence 與 attachment schema
    - 新增 rule definitions／versions／tree／conditions／required fields／source refs／approved amounts，以及 source registry、documents、approved excerpts、program links、source-reference links、attachments 與 review constraints。
    - Expected files/modules：`backend/app/adapters/sqlite/migration_sql/0004_rules_evidence.sql`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_schema_rules_evidence.py -q`
    - _Requirements: 5.1–5.10, 10.1–10.10, 15.3–15.5, 16.7–16.13_

  - [ ] 1.5 建立 coverage、refresh jobs 與 compatibility generations schema
    - 新增 crawl attempts、coverage state／snapshots、refresh jobs 的 same-day unique key，以及 compatibility generations／rows／active pointer／read-only view triggers；補齊 constraints 與 indexes。
    - Expected files/modules：`backend/app/adapters/sqlite/migration_sql/0005_refresh_compatibility.sql`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_schema_refresh_compatibility.py -q`
    - _Requirements: 6.2–6.4, 6.9, 11.4–11.7, 12.1–12.13_

  - [ ] 1.6 實作 legacy `program_rule_fields` preservation 與 candidate conversion migration
    - 先記錄 inventory／checksum，再將 writable legacy table 原樣保存為唯讀 legacy artifact；建立可重跑 conversion draft，但不猜 nested semantics、不補來源、不自動核准，且失敗時整批 rollback。
    - Expected files/modules：`backend/app/adapters/sqlite/migration_sql/0006_preserve_legacy_rules.sql`、`backend/app/adapters/sqlite/legacy_rule_conversion.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_legacy_rule_migration.py -q`
    - _Requirements: 1.2, 5.1, 5.8–5.13, 6.10, 15.2–15.4, 16.7–16.8_

  - [ ] 1.7 建立 migration dry-run、rollback 與 committed-state integration tests
    - 在 temporary SQLite copies 驗證 fresh install、supported／unsupported versions、每步 rollback、legacy row preservation、converted status 非 verified、最後成功 commit 可見性與 failed migration 不改變舊狀態。
    - Expected files/modules：`backend/tests/unit/adapters/sqlite/test_migrations.py`、`backend/tests/integration/adapters/sqlite/test_catalog_migration.py`、`backend/tests/integration/adapters/sqlite/test_legacy_rule_migration.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/adapters/sqlite/test_migrations.py tests/integration/adapters/sqlite/test_catalog_migration.py tests/integration/adapters/sqlite/test_legacy_rule_migration.py -q`
    - _Requirements: 1.2, 1.4, 1.5, 1.8, 1.9, 4.10, 6.9, 15.11, 15.12_

- [ ] 2. 對齊既有 orchestration contracts、errors 與四個 Protocol ports
  - [ ] 2.1 對齊既有 immutable shared contracts 與 storage-neutral errors
    - 以 `app/orchestration/data_contracts.py` 作唯一 shared contract 定義，使用 frozen／slotted dataclasses、tuple／recursive freeze 補齊 design 中的欄位、enum、amount invariants、finite relevance normalization 與 sanitized error hierarchy；不得另建 `app/domain/contracts.py`，contract 不含資料表或 API alias。
    - Expected files/modules：`backend/app/orchestration/data_contracts.py`、`backend/app/orchestration/data_errors.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/test_data_contracts.py tests/unit/test_data_errors.py -q`
    - _Requirements: 2.11, 2.12, 3.1–3.15, 8.1, 12.4, 12.5_

  - [ ] 2.2 對齊既有 exact storage-neutral Protocol ports
    - 以 `app/orchestration/protocols.py` 作唯一 Graph、Eligibility、Evidence、Refresh Protocol 定義，補齊 owner 核准的混合 contract shape：rich `CoverageScope`／`CoverageSnapshot`，搭配 batch `RefreshRequest(event_id, source_ids, requested_at)` 與含 `accepted`／`deduplicated` 的 receipt；不得另建 `app/application/ports.py`，也禁止 connection、row、SQL tuple、table names 或 JSON path 洩漏。
    - Expected files/modules：`backend/app/orchestration/protocols.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/test_protocols.py -q`
    - _Requirements: 2.1–2.4, 2.6, 2.7, 2.11, 2.12, 3.11_

  - [ ] 2.3 擴充既有 required exact unit／contract tests
    - 精確驗證 constructor signatures、immutability、empty tuples、recursive freeze、amount quartet、error sanitization、runtime-checkable fake conformance 與 successful-empty versus failure semantics；沿用 main 已有測試，不建立第二套 domain／port test tree。
    - Expected files/modules：`backend/tests/unit/test_data_contracts.py`、`backend/tests/unit/test_data_errors.py`、`backend/tests/unit/test_protocols.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/test_data_contracts.py tests/unit/test_data_errors.py tests/unit/test_protocols.py -q`
    - _Requirements: 1.7–1.9, 2.1–2.4, 2.11, 2.12, 3.1–3.15_

  > **Approval Gate — Hypothesis dependency（非執行任務）**：在執行 2.4 或任何 PBT task 前，owner 必須決定是否核准以精確版本加入 Hypothesis dev dependency。若未核准，所有標記 `*` 的 PBT 與 dependency task 保持未執行；required unit、contract、integration 與 architecture tests 仍須完成。不得使用未鎖版 dependency；核准後先檢查 package 名稱與 lockfile diff。

  - [ ]* 2.4 加入 owner-approved pinned Hypothesis dev dependency
    - 僅在 approval gate 核准後，以精確版本更新 backend dependency 與 lockfile；不改 runtime dependencies，並記錄可移除範圍。
    - Expected files/modules：`backend/pyproject.toml`、`backend/uv.lock`。
    - Narrow validation：`cd backend && uv lock --check && uv run python -c "import hypothesis; print(hypothesis.__version__)"`
    - _Requirements: 15.5–15.10_

  - [ ]* 2.5 撰寫 Property 1：immutable contracts 與 amount shape
    - **Property 1: Immutable contracts 與 amount shape**；以合法／非法 contract 組合驗證 collection 永不為 `None`、建立後不可變、amount 全空或全有且 min <= max。
    - Expected files/modules：`backend/tests/property/test_property_01_contracts.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_01_contracts.py -q`
    - **Validates: Requirements 3.1–3.9, 3.13–3.15**

- [ ] 3. 建立 SQLite connection／transaction lifecycle helpers
  - [ ] 3.1 實作 `contextlib.closing` connection 與 transaction helpers
    - materialize／map 結果後才 close，成功順序為 operation→commit→close→return；失敗路徑嘗試 rollback／close，close failure 丟棄 result，所有 errors sanitized。
    - Expected files/modules：`backend/app/adapters/sqlite/connection.py`、`backend/app/adapters/sqlite/__init__.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/adapters/sqlite/test_connection.py -q -k 'success or ordering'`
    - _Requirements: 1.8, 1.9, 13.1–13.8, 13.11_

  - [ ] 3.2 撰寫 lifecycle failure-injection tests
    - 以 instrumented fake connection 覆蓋 read、operation、commit、rollback、close 的成功與每個 failure point，驗證 invocation order、connection closure 與錯誤不含 SQL／rows／user values。
    - Expected files/modules：`backend/tests/unit/adapters/sqlite/test_connection.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/adapters/sqlite/test_connection.py -q`
    - _Requirements: 13.2–13.11_

- [ ] 4. 實作 SQLite adapters 與 storage mapping
  - [ ] 4.1 實作 row mapping 與 canonical rule reader
    - 將 `program_id` 僅在 adapter boundary 映射為 `item_id`，解析 typed／timezone values、required fields、唯一 current approved rule；mapping 不得從 citation／文字推定 amount，不能回 partial models。
    - Expected files/modules：`backend/app/adapters/sqlite/mapping.py`、`backend/app/adapters/sqlite/rule_repository.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/adapters/sqlite/test_mapping.py tests/integration/adapters/sqlite/test_rule_repository.py -q`
    - _Requirements: 1.5, 2.12, 3.10–3.15, 5.2, 5.10–5.12_

  - [ ] 4.2 實作 Entitlement Graph adapter path semantics
    - 驗證 life-event ID；未知欄位保留 path、已知不符只排除該 path、all paths excluded 才移除 program；去重、stable ordering、status visibility 與 empty-vs-invalid/error 語意依 design 實作。
    - Expected files/modules：`backend/app/adapters/sqlite/graph_repository.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_graph_repository.py -q`
    - _Requirements: 2.1, 2.11, 2.12, 4.3–4.12, 7.3–7.6_

  - [ ] 4.3 實作 Evidence repository exact mapping
    - 只讀 registered／approved official evidence，逐欄映射 required fields 與 optional dates；提供 item 與 source-reference 查詢，空結果與 query／mapping error 清楚區分。
    - Expected files/modules：`backend/app/adapters/sqlite/evidence_repository.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_evidence_repository.py -q`
    - _Requirements: 2.3, 2.11, 2.12, 10.1–10.4, 10.7–10.10_

  - [ ] 4.4 實作 refresh／coverage SQLite adapter primitives
    - 實作 coverage snapshot reads、共同 observed_at、history-preserving mapping 與 atomic refresh enqueue primitive；此階段不執行 worker、network 或 LLM。
    - Expected files/modules：`backend/app/adapters/sqlite/source_refresh_service.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_source_refresh_repository.py -q`
    - _Requirements: 2.4, 2.11, 2.12, 11.2–11.7, 12.1–12.13_

  - [ ] 4.5 撰寫 required adapter contract／integration tests
    - 對 SQLite implementations 套用共同 contract suite，驗證 program_id↔item_id、empty tuple、invalid ID、unavailable/query/mapping errors、committed-state reads、deterministic ordering 與無 JSON fallback。
    - Expected files/modules：`backend/tests/contract/test_repository_contracts.py`、`backend/tests/integration/adapters/sqlite/test_repository_semantics.py`。
    - Narrow validation：`cd backend && uv run pytest tests/contract/test_repository_contracts.py tests/integration/adapters/sqlite/test_repository_semantics.py -q`
    - _Requirements: 1.2, 1.3, 1.7–1.9, 2.11, 2.12, 3.10–3.12, 4.11, 4.12_

  - [ ]* 4.6 撰寫 Property 2：Graph path 保留與排除語意
    - **Property 2: Graph path 保留與排除語意**；以獨立 reference model 比對有限 typed graph 的 reachable programs 與 missing-field union。
    - Expected files/modules：`backend/tests/property/test_property_02_graph_paths.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_02_graph_paths.py -q`
    - **Validates: Requirements 4.1–4.7, 7.3–7.6**

  - [ ]* 4.7 撰寫 Property 3：Graph deterministic ordering
    - **Property 3: Graph deterministic ordering**；shuffle insertion order 後驗證 candidates、missing IDs、prerequisites 與 produces 完全相同且排序穩定。
    - Expected files/modules：`backend/tests/property/test_property_03_graph_ordering.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_03_graph_ordering.py -q`
    - **Validates: Requirements 4.5, 4.8, 4.9, 8.11**

- [ ] 5. 實作純 recursive Rule DSL validation 與 evaluator
  - [ ] 5.1 建立 canonical immutable DSL tree 與 validator
    - 定義 `AllOf`、`AnyOf`、`Condition`、versioned allowlist；驗證唯一 root、acyclic／reachable tree、group non-empty、condition IDs、field／source references 與 required-field consistency。
    - Expected files/modules：`backend/app/rules/dsl.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/rules/test_dsl.py -q`
    - _Requirements: 5.1–5.3, 5.6–5.10_

  - [ ] 5.2 實作 pure deterministic recursive evaluator
    - 以 explicit operator dispatch 實作 nested all_of／any_of 與 typed leaves；禁止 `eval`、DB access、program ID branches、個別門檻／期限／金額硬編碼。
    - Expected files/modules：`backend/app/rules/evaluator.py`、`backend/app/rules/engine.py`（改為相容 facade 或退役 legacy runtime path）。
    - Narrow validation：`cd backend && uv run pytest tests/unit/rules/test_evaluator.py -q`
    - _Requirements: 5.4, 5.5, 5.7, 5.11, 5.13, 16.3_

  - [ ] 5.3 實作 required fields、StructuredReason 與 amount mapping
    - 欄位不足時在 recursion 前回 stable missing IDs；完整 evaluation 回 structured decisive reasons；只接受 approved structured amount quartet，未知 amount 全為 `None`。
    - Expected files/modules：`backend/app/rules/evaluation.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/rules/test_evaluation.py -q`
    - _Requirements: 3.13–3.15, 7.9, 7.10, 10.5, 10.6, 16.4_

  - [ ] 5.4 撰寫 required DSL／evaluator unit tests
    - 覆蓋 operators、nested boolean examples、invalid types／nodes、missing fields、reason condition IDs、amount boundaries，並用 synthetic identifiers；不得放真實 threshold 或 source excerpt。
    - Expected files/modules：`backend/tests/unit/rules/test_dsl.py`、`backend/tests/unit/rules/test_evaluator.py`、`backend/tests/unit/rules/test_evaluation.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/rules/test_dsl.py tests/unit/rules/test_evaluator.py tests/unit/rules/test_evaluation.py -q`
    - _Requirements: 3.13–3.15, 5.3–5.13, 7.9, 7.10_

  - [ ]* 5.5 撰寫 Property 4：Rule DSL recursive semantics
    - **Property 4: Rule DSL recursive semantics**；任意合法深度 tree 與完整 typed attributes 必須等同獨立 reference evaluator。
    - Expected files/modules：`backend/tests/property/test_property_04_rule_recursion.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_04_rule_recursion.py -q`
    - **Validates: Requirements 5.3–5.7**

  - [ ]* 5.6 撰寫 Property 5：Missing fields 阻止完整 evaluation
    - **Property 5: Missing fields 阻止完整 evaluation**；缺 required field 時回 sorted unique IDs，recursive engine call count 必須為零。
    - Expected files/modules：`backend/tests/property/test_property_05_missing_fields.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_05_missing_fields.py -q`
    - **Validates: Requirements 5.2, 7.9, 16.4**

> **Approval Gate — Compatibility cutover（非執行任務）**：在執行 6.1 前，owner 必須審查 legacy comparison report、round-trip evidence、read-only enforcement、rollback 與 consumer inventory；未核准前不得把 runtime reader 從 legacy path 切到 canonical repository，也不得移除 legacy table。Cutover 後仍不得建立 JSON fallback；失敗必須回復上一個完整 compatibility generation／last committed state。

- [ ] 6. 建立 deterministic、lossless、read-only compatibility projection
  - [ ] 6.1 實作 canonical projection converter 與 reverse converter
    - 以 stable preorder、canonical encoding、Unicode normalization 與 converter version 保留 rule/version、required fields、nested semantics、condition fields、labels 與 source references；不能無損時整次拒絕。
    - Expected files/modules：`backend/app/rules/compatibility.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/rules/test_compatibility.py -q`
    - _Requirements: 6.1, 6.5–6.8_

  - [ ] 6.2 實作 atomic generation persistence 與 read-only view enforcement
    - 在新 generation 完整寫入、hash／reverse validate 後才切 active pointer；任何 direct INSERT／UPDATE／DELETE 或中途 failure 保留舊 generation。
    - Expected files/modules：`backend/app/adapters/sqlite/compatibility_repository.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_compatibility_projection.py -q`
    - _Requirements: 6.2–6.4, 6.8–6.10_

  - [ ] 6.3 撰寫 migration comparison 與 cutover tests
    - 比較 legacy reader 與 canonical projection 可表示資料、驗證不可表示資料停在 review、view DML 被拒、runtime reader 不再依賴 writable legacy table；只用 synthetic fixtures。
    - Expected files/modules：`backend/tests/integration/adapters/sqlite/test_compatibility_cutover.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_compatibility_cutover.py -q`
    - _Requirements: 5.1, 6.1–6.10, 15.7_

  - [ ]* 6.4 撰寫 Property 6：Converter deterministic lossless round trip
    - **Property 6: Converter deterministic lossless round trip**；重複 conversion bytes 相同，round trip 保留所有指定欄位與 evaluation semantics。
    - Expected files/modules：`backend/tests/property/test_property_06_converter_roundtrip.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_06_converter_roundtrip.py -q`
    - **Validates: Requirements 6.1, 6.5–6.8, 15.7**

  - [ ]* 6.5 撰寫 Property 7：Projection read-only atomic replacement
    - **Property 7: Projection read-only atomic replacement**；任一 failure point reader 只能看到完整 old 或 new generation，direct DML 永遠失敗。
    - Expected files/modules：`backend/tests/property/test_property_07_projection_atomicity.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_07_projection_atomicity.py -q`
    - **Validates: Requirements 6.2–6.4, 6.8–6.10**

- [ ] 7. 實作 Eligibility service、sorting 與 API／workflow compatibility mapping
  - [ ] 7.1 實作 status gates、rule selection 與 citation completeness orchestration
    - 統一處理六種 ProgramStatus、exactly-one approved rule、required fields、engine invocation count、evaluated source references 與 conservative downgrade；rejected／inactive direct evaluate 回 typed error。
    - Expected files/modules：`backend/app/application/eligibility_service.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/application/test_eligibility_service.py -q`
    - _Requirements: 5.10–5.12, 7.1–7.11, 10.5, 10.6, 16.3, 16.4, 16.14_

  - [ ] 7.2 實作 deterministic candidate total ordering
    - 依 verified→stale→under_review→candidate、finite score descending、missing／invalid score after valid、item_id tie-break 排序；safe data-quality event 不含 candidate content，score 不影響 eligibility。
    - Expected files/modules：`backend/app/application/candidate_sorting.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/application/test_candidate_sorting.py -q`
    - _Requirements: 8.1–8.6, 8.9–8.11_

  - [ ] 7.3 實作 domain→workflow 與 owner-aware API mappers
    - 維持 `itemId`、`publisherName`、legacy decisive conditions 的 additive compatibility，加入 program status／structured reasons／optional dates／amount quartet；所有 API shape 完全省略 relevance score 與衍生值。
    - Expected files/modules：`backend/app/application/mappers.py`、`backend/app/api/response_mapper.py`、`backend/app/schemas/session.py`、`backend/app/orchestration/state.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/application/test_mappers.py tests/unit/api/test_response_mapper.py -q`
    - _Requirements: 3.10–3.15, 7.3–7.6, 8.7, 8.8, 9.1, 9.2, 10.2–10.4_

  - [ ] 7.4 撰寫 required service／sorting／API compatibility tests
    - 覆蓋完整 status matrix、engine spy counts、citation gaps、optional dates、stable candidate order、score omission、legacy aliases 與 non-requesting recipient actual removal。
    - Expected files/modules：`backend/tests/unit/application/test_eligibility_service.py`、`backend/tests/unit/application/test_candidate_sorting.py`、`backend/tests/unit/api/test_response_mapper.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/application tests/unit/api/test_response_mapper.py -q`
    - _Requirements: 7.1–7.11, 8.1–8.11, 9.1, 9.2, 10.2–10.6_

  - [ ]* 7.5 撰寫 Property 8：Program status gate matrix
    - **Property 8: Program status gate matrix**；對 status×rule count×citation completeness×attributes 驗證 visibility、result／error 與 engine call count。
    - Expected files/modules：`backend/tests/property/test_property_08_status_gates.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_08_status_gates.py -q`
    - **Validates: Requirements 5.10–5.12, 7.1–7.8, 7.11, 16.3, 16.4, 16.14**

  - [ ]* 7.6 撰寫 Property 9：Candidate ordering 與 score non-exposure
    - **Property 9: Candidate total ordering 與 score non-exposure**；任意 permutation／score 皆穩定排序，score 不改 eligibility，serialization 不含 score／range／percentage。
    - Expected files/modules：`backend/tests/property/test_property_09_candidate_sorting.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_09_candidate_sorting.py -q`
    - **Validates: Requirements 8.1–8.11**

  - [ ]* 7.7 撰寫 Property 10：Citation exact mapping 與 completeness
    - **Property 10: Citation exact mapping 與 completeness**；每個 evaluated distinct reference 都須 exact mapping approved citation，optional date 缺失不單獨降級。
    - Expected files/modules：`backend/tests/property/test_property_10_citation_completeness.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_10_citation_completeness.py -q`
    - **Validates: Requirements 7.1, 7.8, 10.1–10.10**

- [ ] 8. 建立隱私 sanitizer、RawTextScope 與 fail-closed observability
  - [ ] 8.1 實作 recursive PrivacySanitizer
    - 遞迴處理 mappings、models、sequences、JSON strings 與 plain strings；移除 actual／raw text／denylisted keys，exception 僅保留 safe type／code／context IDs，不支援型別回 failure。
    - Expected files/modules：`backend/app/privacy/sanitizer.py`、`backend/app/privacy/__init__.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/privacy/test_sanitizer.py -q`
    - _Requirements: 9.3–9.8, 9.12_

  - [ ] 8.2 實作 requesting-user authorization mapping 與 RawTextScope disposal
    - Authorization context 不接受 caller 自報 boolean；raw text 僅在 request-local scope，success／failure／cancellation 都於 response／state transition 前 dispose，只複製 field-registry allowlist 交集。
    - Expected files/modules：`backend/app/privacy/raw_text_scope.py`、`backend/app/api/response_mapper.py`、`backend/app/orchestration/state_machine.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/privacy/test_raw_text_scope.py tests/unit/api/test_response_authorization.py -q`
    - _Requirements: 9.1, 9.2, 9.9–9.11, 9.13_

  - [ ] 8.3 將 observability 統一改為 sanitize→validate→serialize→emit
    - Logs、traces、metrics、exceptions、audit 共用入口；sanitizer uncertainty 時原 serializer／emitter call count 為零，只送固定 `sanitization_failed` indicator。
    - Expected files/modules：`backend/app/observability/logging.py`、`backend/app/observability/pipeline.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/observability/test_privacy_pipeline.py -q`
    - _Requirements: 9.3–9.8, 9.12, 9.13, 13.8_

  - [ ] 8.4 撰寫 required privacy lifecycle／authorization tests
    - 使用 synthetic markers 驗證 nested payload、stringified JSON、plain strings、exceptions、audit allowlist、request owner／non-owner、三種 RawTextScope exits 與 fail-closed behavior。
    - Expected files/modules：`backend/tests/unit/privacy/test_sanitizer.py`、`backend/tests/unit/privacy/test_raw_text_scope.py`、`backend/tests/unit/observability/test_privacy_pipeline.py`、`backend/tests/unit/api/test_response_authorization.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/privacy tests/unit/observability/test_privacy_pipeline.py tests/unit/api/test_response_authorization.py -q`
    - _Requirements: 9.1–9.13_

  - [ ]* 8.5 撰寫 Property 11：Requesting-user response authorization
    - **Property 11: Requesting-user response authorization**；只有當前 requesting user response 可保留必要 actual，其他 recipient 遞迴輸出完全移除。
    - Expected files/modules：`backend/tests/property/test_property_11_response_authorization.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_11_response_authorization.py -q`
    - **Validates: Requirements 9.1, 9.2**

  - [ ]* 8.6 撰寫 Property 12：Recursive sanitizer 與 fail-closed observability
    - **Property 12: Recursive sanitizer 與 fail-closed observability**；任何成功 emission 不含 markers，任何 sanitizer failure 都不 serialize／emit 原 payload。
    - Expected files/modules：`backend/tests/property/test_property_12_sanitizer.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_12_sanitizer.py -q`
    - **Validates: Requirements 9.3–9.8, 9.12, 9.13**

  - [ ]* 8.7 撰寫 Property 13：Raw text disposal
    - **Property 13: Raw text disposal**；success／failure／cancellation 都先 dispose，state 僅保留 allowlisted extracted keys。
    - Expected files/modules：`backend/tests/property/test_property_13_raw_text_disposal.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_13_raw_text_disposal.py -q`
    - **Validates: Requirements 9.9–9.11, 9.13**

- [ ] 9. 完成 FastAPI composition root、fakes 與 architecture boundaries
  - [ ] 9.1 實作唯一 FastAPI composition root
    - 建立 dependency dataclasses／overrides，default path 驗證 SQLite／schema 後建立四個 implementations；缺 dependency 在 routes 接受 request 前 safe fail，routes 不自行建 adapters。
    - Expected files/modules：`backend/app/application/composition.py`、`backend/app/main.py`、`backend/app/api/sessions.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/application/test_composition.py -q`
    - _Requirements: 1.3, 1.4, 2.5, 2.8–2.10_

  - [ ] 9.2 建立 no-SQL fakes 並注入 Workflow／state machine
    - 四個 fakes 只接受 immutable in-memory data，不 subclass SQLite、不接受 DB path；全部 supplied 時 app startup 不建立 factory／adapter／connection。
    - Expected files/modules：`backend/app/testing/fakes.py`、`backend/app/orchestration/state_machine.py`、`backend/tests/fakes.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/application/test_fake_composition.py tests/unit/orchestration/test_state_machine_dependencies.py -q`
    - _Requirements: 2.6, 2.8, 2.9_

  - [ ] 9.3 撰寫 architecture 與 fake-startup tests
    - AST／import scan 證明 workflow／state machine 無 SQL、sqlite3、table／column names 或 SQLite imports；fake startup spy 證明零 DB open；runtime import graph無 JSON exporter／snapshot reader。
    - Expected files/modules：`backend/tests/architecture/test_storage_boundaries.py`、`backend/tests/architecture/test_runtime_json_isolation.py`、`backend/tests/integration/test_app_fake_startup.py`。
    - Narrow validation：`cd backend && uv run pytest tests/architecture tests/integration/test_app_fake_startup.py -q`
    - _Requirements: 1.3, 2.5–2.10, 14.5, 14.6, 14.10_

- [ ] 10. 建立六個 MVP IDs 的安全 migration／curation scaffolding
  - [ ] 10.1 建立只含六個既有 ID 的 catalog scaffold
    - Migration／curation input 只能建立 intro 所列六個 IDs；若沒有現存且可驗證的 human-approved facts，所有 threshold／deadline／amount／excerpt 保持 unknown／null，status 保持 candidate／under_review。
    - Expected files/modules：`backend/app/adapters/sqlite/migration_sql/0007_mvp_catalog_scaffold.sql`、`data/benefit_discovery/mvp_catalog_manifest.v1.json`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_mvp_catalog_scaffold.py -q`
    - _Requirements: 15.1, 15.2, 15.3, 16.7, 16.8_

  - [ ] 10.2 實作 human review transition scaffolding
    - 只允許 Human Reviewer 與完整 approved rule／citation／excerpt 進 protected transitions；記錄 reviewer ref、timestamp、old/new status、version，禁止 crawler／LLM／importer／converter／exporter verify。
    - Expected files/modules：`backend/app/curation/review_service.py`、`scripts/review_benefit_status.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/curation/test_review_service.py -q`
    - _Requirements: 15.3, 15.4, 16.6–16.13_

  - [ ] 10.3 撰寫 MVP scaffold 與 synthetic isolation tests
    - 驗證 IDs 恰為六個、無未核准 facts／excerpt、protected transitions、synthetic fixtures 使用隔離 IDs／temporary DB，測試前後 canonical catalog checksum 不變。
    - Expected files/modules：`backend/tests/integration/adapters/sqlite/test_mvp_catalog_scaffold.py`、`backend/tests/integration/test_synthetic_catalog_isolation.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_mvp_catalog_scaffold.py tests/integration/test_synthetic_catalog_isolation.py -q`
    - _Requirements: 15.1–15.4, 15.9, 15.10, 16.6–16.13_

- [ ] 11. 實作 current-data-first local refresh worker 與 coverage invariants
  - [ ] 11.1 實作 request-start snapshot 與 non-blocking local worker boundary
    - Workflow 先組 current committed response，再 enqueue；request thread 不執行 crawl／attachments／LLM，worker delay／failure 不改變 response 或 prior committed state。
    - Expected files/modules：`backend/app/application/refresh_orchestration.py`、`backend/app/curation/local_worker.py`、`backend/app/orchestration/state_machine.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/test_current_data_first_refresh.py -q`
    - _Requirements: 11.1–11.3, 11.8–11.10, 16.1_

  - [ ] 11.2 實作 timezone-aware concurrency-safe same-day dedup
    - 以 source_id＋event_id＋Application Timezone calendar date 產生 key，atomic insert／conflict lookup 回同 job ID；並行時恰一個 false、其餘 true，不用 sleep 判斷 race。
    - Expected files/modules：`backend/app/adapters/sqlite/source_refresh_service.py`、`backend/app/config.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_refresh_dedup.py -q`
    - _Requirements: 11.2–11.7_

  - [ ] 11.3 實作 coverage tracker 與 honest response mapping
    - 建立 scope snapshot、共同 observed_at、per-source／aggregate invariants、gap categories、failure history preservation；API 只陳述可觀測進度，不產生 completeness／zero-omission claims。
    - Expected files/modules：`backend/app/application/coverage_tracker.py`、`backend/app/api/response_mapper.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/application/test_coverage_tracker.py tests/unit/api/test_coverage_mapper.py -q`
    - _Requirements: 12.1–12.13_

  - [ ] 11.4 撰寫 required refresh／coverage integration tests
    - 使用 barriers 與獨立 connections 測 concurrency、timezone date boundary、first failure、failure after success、current-data-first ordering、worker failure isolation 與 coverage arithmetic。
    - Expected files/modules：`backend/tests/integration/adapters/sqlite/test_refresh_dedup.py`、`backend/tests/integration/test_current_data_first_refresh.py`、`backend/tests/integration/test_coverage_snapshots.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/adapters/sqlite/test_refresh_dedup.py tests/integration/test_current_data_first_refresh.py tests/integration/test_coverage_snapshots.py -q`
    - _Requirements: 11.1–11.10, 12.1–12.13_

  - [ ]* 11.5 撰寫 Property 14：Concurrent same-day refresh dedup
    - **Property 14: Concurrent same-day refresh dedup**；N>=1 同 key requests 最終恰一 job、恰一 false、其餘 true、同 job ID。
    - Expected files/modules：`backend/tests/property/test_property_14_refresh_dedup.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_14_refresh_dedup.py -q`
    - **Validates: Requirements 11.2–11.7**

  - [ ]* 11.6 撰寫 Property 15：Current-data-first non-blocking refresh
    - **Property 15: Current-data-first non-blocking refresh**；任意 worker duration／failure 不阻塞 response，request path network／LLM call count 為零。
    - Expected files/modules：`backend/tests/property/test_property_15_current_data_first.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_15_current_data_first.py -q`
    - **Validates: Requirements 11.1, 11.3, 11.8–11.10**

  - [ ]* 11.7 撰寫 Property 16：Coverage snapshot invariants
    - **Property 16: Coverage snapshot invariants**；status sums、indexed sums、nonnegative counts、shared observed_at 與 history preservation 對任意合法 states 成立。
    - Expected files/modules：`backend/tests/property/test_property_16_coverage_invariants.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_16_coverage_invariants.py -q`
    - **Validates: Requirements 12.1–12.5, 12.9–12.13**

  - [ ]* 11.8 撰寫 Property 17：Coverage gap 誠實呈現
    - **Property 17: Coverage gap 誠實呈現**；保留 gap category，任何 response 都不包含 scope 外、完整保證、零遺漏或全數索引 claims。
    - Expected files/modules：`backend/tests/property/test_property_17_coverage_claims.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_17_coverage_claims.py -q`
    - **Validates: Requirements 12.6–12.8**

> **Approval Gate — Network-enabling work（非執行任務）**：在執行 12.1 前，local files／fixture HTTP／mock classifier／mock LLM／local worker 保持預設且可測試。Owner 可另行核准 live network、AWS SDK client、AWS resource 或 live LLM path；該批次必須從 Git 外取得 credentials、保留 local test path、不得加入隱藏 live feature flag，並同步更新唯一的 `docs/aws_migration_guide.md`。

- [ ] 12. 建立 later curation pipeline 的 local／mock scaffolding
  - [ ] 12.1 實作 registered-source structural discovery
    - 只接受 registered source 與 fixture/local fetcher，記錄 robots／login／JS-only／broken-link gaps，discovered pages 只能 candidate；不宣稱全面 crawl。
    - Expected files/modules：`backend/app/curation/structural_crawler.py`、`backend/app/curation/fetchers.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/curation/test_structural_crawler.py -q`
    - _Requirements: 10.7, 11.9, 11.10, 12.6–12.8, 16.1, 16.2, 16.7, 16.8_

  - [ ] 12.2 實作 local attachment metadata／extraction handling
    - 儲存 metadata、hash、local storage ref、status／method／time；掃描或失敗附件保留 gap，不假裝已提取，不提交大型 raw files。
    - Expected files/modules：`backend/app/curation/attachments.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/curation/test_attachments.py -q`
    - _Requirements: 10.7, 11.9, 12.6, 16.1, 16.7_

  - [ ] 12.3 實作 local/mock page classification 與 candidate extraction
    - 以 injectable local/mock clients 產生結構化 candidate／under_review payload；不得產生 eligibility status、verified state、真實未核准 excerpt 或推定 metadata。
    - Expected files/modules：`backend/app/curation/candidate_extractor.py`、`backend/app/curation/classifier.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/curation/test_candidate_extractor.py -q`
    - _Requirements: 10.7, 11.9, 11.10, 15.2, 15.3, 16.5–16.8_

  - [ ] 12.4 串接 human review transitions 與 candidate artifacts
    - Candidate page／attachment／rule／evidence 只有在 human review metadata 與必要 artifacts 完整時才可進 approved version；所有 protected transitions atomic 且 auditable。
    - Expected files/modules：`backend/app/curation/review_service.py`、`backend/app/curation/pipeline.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/curation/test_review_pipeline.py -q`
    - _Requirements: 10.7–10.9, 15.3, 15.4, 16.6–16.13_

  - [ ] 12.5 撰寫 required local/mock curation 與 governance tests
    - 驗證 registered-source scope、attachment gaps、mock outputs、human-only transitions，以及 live HTTP／AWS／credential／LLM spies 全為零；測試資料必須 synthetic／fixture isolated。
    - Expected files/modules：`backend/tests/unit/curation/test_structural_crawler.py`、`backend/tests/unit/curation/test_attachments.py`、`backend/tests/unit/curation/test_candidate_extractor.py`、`backend/tests/integration/curation/test_review_pipeline.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/curation tests/integration/curation/test_review_pipeline.py -q`
    - _Requirements: 10.7–10.9, 12.6–12.8, 15.3, 15.9, 15.10, 16.1–16.13_

  - [ ]* 12.6 撰寫 Property 20：Pre-August local/mock governance
    - **Property 20: Pre-August local/mock governance**；deadline 前所有 paths 的 live calls／credential lookup 為零，non-human actor 不能 protected transition，machine outputs 只能 candidate／under_review。
    - Expected files/modules：`backend/tests/property/test_property_20_pre_august_governance.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_20_pre_august_governance.py -q`
    - **Validates: Requirements 15.2–15.4, 16.1–16.13**

- [ ] 13. 選用 tests／release JSON exporter（不得成為 runtime prerequisite）
  - [ ] 13.1 實作 deterministic atomic one-way JSON exporter
    - 只從指定 SQLite schema／data／rule versions 與 explicit timestamp 匯出 canonical bytes，temp＋atomic replace，失敗保留舊檔；不提供 JSON-to-SQL importer／fallback。
    - Expected files/modules：`scripts/export_catalog_json.py`、`backend/app/testing/catalog_exporter.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/testing/test_catalog_exporter.py -q`
    - _Requirements: 1.3, 1.9, 14.1–14.11_

  - [ ] 13.2 撰寫 exporter atomicity 與 zero-runtime-dependency architecture tests
    - 驗證 stable row／field ordering、metadata、failure cleanup、existing snapshot preservation；AST／import／startup spy 證明 application runtime 不 import／read／write exporter 或 `.json` catalog。
    - Expected files/modules：`backend/tests/unit/testing/test_catalog_exporter.py`、`backend/tests/architecture/test_runtime_json_isolation.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/testing/test_catalog_exporter.py tests/architecture/test_runtime_json_isolation.py -q`
    - _Requirements: 1.3, 1.9, 14.1–14.11_

  - [ ]* 13.3 撰寫 Property 19：JSON deterministic atomic export 與 runtime isolation
    - **Property 19: JSON deterministic atomic export 與 runtime isolation**；任意 insertion order bytes 相同、任意 export failure 無 partial、任意 runtime request JSON calls 為零。
    - Expected files/modules：`backend/tests/property/test_property_19_json_export.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_19_json_export.py -q`
    - **Validates: Requirements 1.3, 1.9, 14.1–14.11**

- [ ] 14. 建立 validation CLI、integration suite 與完整 PBT profile
  - [ ] 14.1 實作 catalog validation CLI
    - 驗證 schema、operator allowlist、required fields、citations、referential integrity、status gates、amount、projection 與 synthetic isolation；失敗輸出 safe IDs／version／code 且 non-zero，成功輸出 count 且 zero。
    - Expected files/modules：`scripts/validate_catalog.py`、`backend/app/validation/catalog.py`。
    - Narrow validation：`cd backend && uv run pytest tests/unit/validation/test_catalog_validation.py -q`
    - _Requirements: 15.5–15.12_

  - [ ] 14.2 建立 cross-layer integration suite
    - 以 temporary SQLite＋fakes 串 migration→repositories→eligibility→workflow→API，覆蓋正常、boundary、missing、unreviewed、stale、rejected、inactive、privacy 與 no-runtime-JSON；不啟動 server 或 watcher。
    - Expected files/modules：`backend/tests/integration/test_data_layer_rule_engine.py`。
    - Narrow validation：`cd backend && uv run pytest tests/integration/test_data_layer_rule_engine.py -q`
    - _Requirements: 1–16_

  - [ ]* 14.3 整合並執行 owner-approved PBT profile
    - 設定每個 design property 對應單一 `@given` test、至少 100 examples、共同 marker／deadline；確認 Properties 1–20 各自可選擇執行且未核准 dependency 時不假稱通過。
    - Expected files/modules：`backend/pyproject.toml`、`backend/tests/property/conftest.py`、`backend/tests/property/test_property_manifest.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property -q`
    - _Requirements: 3–16 的 Correctness Properties_

  - [ ]* 14.4 撰寫 Property 18：SQLite lifecycle trace 與 closure
    - **Property 18: SQLite lifecycle trace 與 closure**；任意 operation／commit／rollback／close failure matrix 皆符合 trace、closure 與 sanitized error oracle。
    - Expected files/modules：`backend/tests/property/test_property_18_sqlite_lifecycle.py`。
    - Narrow validation：`cd backend && uv run pytest tests/property/test_property_18_sqlite_lifecycle.py -q`
    - **Validates: Requirements 1.8, 1.9, 13.1–13.11**

- [ ] 15. 執行 final implementation validation
  - [ ] 15.1 執行完整 safety checkpoint 與 diff validation
    - Ensure all tests pass, ask the user if questions arise.
    - 先執行各 task 的 narrow suites，再單次執行完整 pytest、Ruff lint／format check、task graph validator 與 whitespace check；不得啟動 server、watcher 或 live crawler。
    - 若 Hypothesis 未經 owner 核准，只能回報 optional PBT 未執行；不得將 skipped／missing dependency 說成通過。
    - 確認 runtime import graph 無 JSON catalog reader／fallback，local profile 的 live network／AWS／credential／live LLM spies 全為零；若存在 owner-approved cloud profile，確認 secrets 不進 Git 且 local tests 不依賴該 profile，並確認 synthetic validation data 未污染 canonical catalog。
    - Expected files/modules：`backend/tests/**`、`scripts/validate_catalog.py`、`.kiro/specs/data-layer-rule-engine/tasks.md`（只在 validator 發現 task metadata 錯誤時修正）。
    - Narrow validation：`cd backend && uv run pytest -q`、`cd backend && uv run ruff check app tests`、`cd backend && uv run ruff format --check app tests`、task Markdown／graph validator、`git diff --check`
    - _Requirements: 1–16_

## Notes

- 所有 checkbox 保持未完成；本文件只規劃，不實作 feature。
- Required implementation、unit、contract、integration、architecture 與 privacy tests 不標 `*`。所有 Hypothesis dependency／PBT tasks 標 `*`，只有 owner 核准 pinned dependency 後才執行；未核准可跳過，但不得假稱通過。
- PBT task 必須一個 design property 對應一個 test；使用 independent reference model／oracle，不得用 production code 自我驗證。
- Schema migration、Hypothesis dependency、compatibility cutover 與 network-enabling work 均由非 checkbox approval gates 保護；approval 本身不是 coding task，任何 scope 擴張都需重新核准。
- 六個 MVP IDs 以外不得加入 catalog scaffold。沒有既存 human-approved facts 時，threshold、deadline、amount、source excerpt 均維持 unknown／null 與 unreviewed status。
- Coverage 只表示指定 scope／observed_at 的可量測進度與 gaps，不得聲稱完整、零遺漏或所有福利均已索引。
- Runtime truth 僅為 SQLite last successful committed state；JSON exporter 是 optional tests／release tool，永不成為 startup、request、fallback 或回寫路徑。
- Local validation 不啟用 live network、AWS、credential lookup 或 live LLM，也不執行 dev server、watcher 或 live crawler；owner-approved cloud integration 另跑明確的 opt-in checks。

## Definition of Done

- 每個實作 task 必須通過其 narrow validation；最後由 15.1 執行完整 safety checkpoint。任何未執行、skipped 或缺 dependency 的檢查都不得回報為通過。
- 任何實作 feature 若新增或修改日後將由 AWS 服務取代的 local/mock boundary，**同一實作批次**必須更新唯一的 `docs/aws_migration_guide.md`，逐項記錄要移除／停用的 local code、未來 AWS SDK/API insertion point，以及 owner-approved service 所需的 exact environment variables。若 AWS service 仍待決策，只能明確標示 `TBD-after-ADR`，不得虛構 service 或 env var；此要求是 affected coding task 的完成條件，不建立獨立 documentation phase。
- 完成狀態必須維持 no-runtime-JSON、no JSON fallback、local tests 無 live network／AWS／credential lookup／live LLM 依賴、無未核准 benefit facts、無 raw user text／PII／secrets／大型 raw government artifacts，並保留所有 human-review 與 conservative eligibility safety gates；任何 owner-approved cloud path 另須符合 AGENTS.md 與 migration guide。
- Final diff 必須通過 task Markdown／dependency graph validation 與 `git diff --check`，且只包含 owner 核准的 implementation batch files。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4"] },
    { "id": 3, "tasks": ["1.5"] },
    { "id": 4, "tasks": ["1.6"] },
    { "id": 5, "tasks": ["1.7"] },
    { "id": 6, "tasks": ["2.1"] },
    { "id": 7, "tasks": ["2.2"] },
    { "id": 8, "tasks": ["2.3"] },
    { "id": 9, "tasks": ["2.4"] },
    { "id": 10, "tasks": ["2.5", "3.1"] },
    { "id": 11, "tasks": ["3.2"] },
    { "id": 12, "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": 13, "tasks": ["4.5"] },
    { "id": 14, "tasks": ["4.6", "4.7", "5.1"] },
    { "id": 15, "tasks": ["5.2"] },
    { "id": 16, "tasks": ["5.3"] },
    { "id": 17, "tasks": ["5.4"] },
    { "id": 18, "tasks": ["5.5", "5.6"] },
    { "id": 19, "tasks": ["6.1"] },
    { "id": 20, "tasks": ["6.2"] },
    { "id": 21, "tasks": ["6.3"] },
    { "id": 22, "tasks": ["6.4", "6.5"] },
    { "id": 23, "tasks": ["7.1", "7.2"] },
    { "id": 24, "tasks": ["7.3"] },
    { "id": 25, "tasks": ["7.4"] },
    { "id": 26, "tasks": ["7.5", "7.6", "7.7"] },
    { "id": 27, "tasks": ["8.1"] },
    { "id": 28, "tasks": ["8.2"] },
    { "id": 29, "tasks": ["8.3"] },
    { "id": 30, "tasks": ["8.4"] },
    { "id": 31, "tasks": ["8.5", "8.6", "8.7"] },
    { "id": 32, "tasks": ["9.1"] },
    { "id": 33, "tasks": ["9.2"] },
    { "id": 34, "tasks": ["9.3"] },
    { "id": 35, "tasks": ["10.1"] },
    { "id": 36, "tasks": ["10.2"] },
    { "id": 37, "tasks": ["10.3"] },
    { "id": 38, "tasks": ["11.1"] },
    { "id": 39, "tasks": ["11.2"] },
    { "id": 40, "tasks": ["11.3"] },
    { "id": 41, "tasks": ["11.4"] },
    { "id": 42, "tasks": ["11.5", "11.6", "11.7", "11.8"] },
    { "id": 43, "tasks": ["12.1", "12.2"] },
    { "id": 44, "tasks": ["12.3"] },
    { "id": 45, "tasks": ["12.4"] },
    { "id": 46, "tasks": ["12.5"] },
    { "id": 47, "tasks": ["12.6"] },
    { "id": 48, "tasks": ["13.1"] },
    { "id": 49, "tasks": ["13.2"] },
    { "id": 50, "tasks": ["13.3", "14.1"] },
    { "id": 51, "tasks": ["14.2"] },
    { "id": 52, "tasks": ["14.3", "14.4"] },
    { "id": 53, "tasks": ["15.1"] }
  ]
}
```
