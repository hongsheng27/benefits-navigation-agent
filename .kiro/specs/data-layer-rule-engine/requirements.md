# Requirements Document

**資料層與規則引擎補齊**

## Introduction

本需求定義「接住」福利導航 Agent 目前的本機資料層、Entitlement Graph、確定性資格判斷、官方證據、來源更新與隱私邊界。SQLite 是本機資料策展與 runtime 的單一真相來源，直到另有 owner-approved storage migration ADR 與替代 adapter；FastAPI application composition root 建立 storage-neutral repositories 與 services，再注入 Workflow 與 state machine。Runtime 不要求 JSON，也不提供 JSON fallback；Workflow 不接觸 SQL 或 SQLite 專屬資料形狀，LLM 不決定資格或自動驗證規則。

MVP catalog 保留下列既有方案識別碼，實際資格條件、期限、金額與來源原文只可來自人工審查通過的官方資料，本文件不新增或推定任何福利事實：

1. `death_registration`
2. `labor_funeral_grant`
3. `national_pension_funeral_grant`
4. `labor_survivor_pension`
5. `national_pension_survivor_pension`
6. `nhi_status_change`

## Glossary

- **System**：本需求涵蓋的福利導航後端系統。
- **Local_Data_Platform**：以本機 SQLite 支援資料策展與 runtime 查詢的資料平台。
- **Last_Successful_Committed_State**：最近一次成功完成 transaction commit 的 SQLite 狀態，不包含未提交或已 rollback 的變更。
- **Benefit_Catalog**：儲存方案、狀態、規則、來源、證據與機關角色的 canonical SQLite catalog。
- **Entitlement_Graph**：描述人生事件、保險體系、方案、機關與文件需求關聯的資料模型。
- **Repository_Layer**：Entitlement_Graph_Repository、Evidence_Repository 與 Source_Refresh_Service 的 storage-neutral 集合查詢邊界。
- **Entitlement_Graph_Repository**：以 storage-neutral domain contract 提供事件展開、前置需求、產出與體系反查的介面。
- **Eligibility_Service**：提供必要欄位查詢、確定性資格評估與方案狀態安全閘門的 storage-neutral 介面。
- **Evidence_Repository**：提供方案官方引用資料的 storage-neutral 介面。
- **Source_Refresh_Service**：提供 coverage 狀態與非阻塞來源更新請求的 storage-neutral 介面。
- **Application_Composition_Root**：FastAPI application 啟動時建立具體 adapters、repositories 與 services，並完成 dependency injection 的唯一組裝位置。
- **Workflow**：控制 session、state、提問順序、停止與人工轉介條件的 application 流程；包含 state machine。
- **SQLite_Adapter**：實作 storage-neutral 介面並封裝 SQLite 查詢、row mapping 與 connection lifecycle 的資料存取元件。
- **Domain_Contract_Layer**：定義 backend 模組間共享、不依賴資料表欄名，且建立後不可變更的 immutable domain models。
- **CandidateItem**：候選方案的 backend 共用 contract，包含 `item_id`、`display_name`、`program_status`、backend 內部 `relevance_score`、`missing_field_ids`、`prerequisites` 與 `produces`。
- **EligibilityDecision**：資格判斷共用 contract，包含 `item_id`、`status`、金額上下限、發放週期、幣別、`missing_field_ids` 與結構化原因。
- **StructuredReason**：結構化判斷原因，包含 `condition_id`、`field_id`、`operator`、`expected`、`actual`、`label` 與 `source_reference`。
- **Citation**：官方證據 contract，包含文件識別、標題、發布者、發布時間、生效時間、URL、已核准引用段落與擷取時間。
- **FieldRegistryEntry**：Workflow 提問使用的欄位定義，包含 `field_id`、資料型別、合法值、提問文字、需要原因與 PII 分類。
- **CoverageMetadata**：單一已登記來源在指定觀測時間的進度 contract，包含 `source_id`、爬取狀態、最後成功爬取時間、已索引文件數、領域標籤與 `observed_at`；不代表內容完整保證。
- **Coverage_Scope**：一次 coverage 統計納入的已登記 `source_id` 集合與 domain tags。
- **Rule_DSL**：儲存在 SQLite 的 canonical、versioned、可巢狀 `all_of`／`any_of` 宣告式資格規則語言。
- **Compatibility_Projection**：由 canonical Rule_DSL 自動產生的唯讀 `program_rule_fields` 相容檢視或等價投影。
- **Compatibility_Projection_Generator**：將 Rule_DSL 轉換為 Compatibility_Projection，並可重建語意等價 Rule_DSL 的 deterministic、lossless converter。
- **Rule_Engine**：只執行已核准 Rule_DSL 的確定性資格判斷元件。
- **Program_Status**：方案治理狀態，合法值為 `candidate`、`under_review`、`verified`、`stale`、`rejected`、`inactive`。
- **Eligibility_Status**：資格結果，合法值為 `eligible`、`ineligible`、`needs_information`、`needs_human_review`。
- **Relevance_Score**：只供 backend 排序使用的有限數值 metadata，不代表資格機率或符合程度；本需求不指定數值範圍。
- **Privacy_Sanitizer**：集中且遞迴移除 Raw_User_Text 與實際資格值的隱私過濾元件。
- **Requesting_User**：通過目前請求的身分驗證與授權檢查，且可接收該請求結果的使用者。
- **API_Response_Mapper**：將 backend domain contracts 映射為 Requesting_User 或 frontend-facing API response 的元件。
- **LLM_Integration**：負責語言理解、白話解釋、頁面分類與結構化候選提取的生成式模型邊界。
- **Observability_Pipeline**：產生 log、trace、metric、exception 與 audit event 的所有後端輸出路徑。
- **Raw_User_Text**：使用者輸入的未結構化原始文字。
- **Source_Curation_Pipeline**：來源發現、下載、附件處理、候選提取與人工審查流程。
- **Coverage_Tracker**：以已登記來源與爬取結果計算 CoverageMetadata 的元件。
- **Application_Timezone**：application configuration 明確指定、用來換算 refresh calendar date 的時區。
- **Refresh_Job**：在背景執行來源爬取、附件處理或候選提取的本機工作。
- **JSON_Exporter**：從 SQLite 單向產生測試 fixture 或 release snapshot 的非 runtime 工具。
- **Validation_Suite**：檢查 schema、規則、投影、狀態閘門、隱私與 lifecycle 的自動化驗證集合。
- **Synthetic_Validation_Data**：只供 Validation_Suite 使用，且與正式福利事實、Official_Source、Citation 及 canonical catalog 隔離的合成資料。
- **Official_Source**：經登記且由資料維護者確認的官方政府來源。
- **Human_Reviewer**：有權核准來源、證據、規則版本與方案治理狀態的人員。

## Requirements

### 需求 1：SQLite 單一真相來源

**User Story:** 身為 backend 維護者，我需要資料策展與 runtime 共用單一 SQLite 真相來源，以便避免人工維護兩份互相矛盾的資料。

#### 驗收條件

1. WHILE 尚未有 owner-approved storage migration ADR 與替代 adapter，THE Local_Data_Platform SHALL 使用本機 SQLite 儲存與讀取來源、Entitlement Graph、方案、規則、證據、coverage metadata 與審查狀態。
2. WHEN runtime 查詢候選方案、規則、證據或 coverage 資料時，THE Local_Data_Platform SHALL 從 Last_Successful_Committed_State 提供資料。
3. THE System SHALL 在不載入任何 runtime JSON 檔案的情況下完成 application 啟動與本機查詢。
4. IF SQLite schema 版本不受目前 application 支援，THEN THE Local_Data_Platform SHALL 拒絕啟動資料服務並回報不含使用者資料的 schema version error。
5. THE Local_Data_Platform SHALL 將資料庫 schema version 與每筆 canonical Rule_DSL version 保存為可查詢值。
6. THE Benefit_Catalog SHALL 排除 Raw_User_Text、direct identifiers、credentials 與 session 對話內容。
7. WHEN 已成功完成的 runtime 查詢沒有符合條件的資料時，THE Local_Data_Platform SHALL 回傳該查詢 contract 所定義的空結果。
8. IF SQLite 無法開啟、無法讀取或查詢未成功完成，THEN THE Local_Data_Platform SHALL 拒絕 application 啟動或受影響的查詢並回報不含使用者資料的 SQLite unavailable 或 query failure error。
9. IF SQLite 無法開啟、無法讀取或查詢未成功完成，THEN THE System SHALL 保持 Last_Successful_Committed_State 不變且不切換至 JSON fallback。

### 需求 2：Storage-neutral 邊界與 composition-root 注入

**User Story:** 身為 Workflow 開發者，我需要透過 storage-neutral repositories 與 services 取得資料，以便更換儲存 adapter 時不重寫流程邏輯。

#### 驗收條件

1. THE Entitlement_Graph_Repository SHALL 提供事件展開、前置需求查詢、產出查詢與體系反查操作，並回傳 Domain_Contract_Layer models。
2. THE Eligibility_Service SHALL 提供必要欄位查詢、單一方案評估與多方案評估操作，並回傳 FieldRegistryEntry 或 EligibilityDecision。
3. THE Evidence_Repository SHALL 依 `item_id` 回傳 Citation 集合，並提供依 `item_id` 與實際評估的 `source_references` 回傳對應 Citation 集合的操作。
4. THE Source_Refresh_Service SHALL 以 `CoverageScope(source_ids, domain_tags)` 提供 `CoverageSnapshot` coverage 狀態查詢，並以 `RefreshRequest(event_id, source_ids, requested_at)` 接受 batch on-demand refresh，回傳 `RefreshReceipt(job_id, accepted, deduplicated)`。
5. WHEN FastAPI application 啟動且未提供替代 implementation 時，THE Application_Composition_Root SHALL 建立 SQLite_Adapter implementations 並注入 Workflow 與 state machine。
6. THE Workflow SHALL 只依賴 Entitlement_Graph_Repository、Eligibility_Service、Evidence_Repository、Source_Refresh_Service 與 Domain_Contract_Layer。
7. THE Workflow SHALL 排除 SQL statement、SQLite connection、`sqlite3.Row`、SQL tuple、資料表名稱與 SQLite 欄名。
8. WHEN Workflow tests 提供 fake implementations 時，THE Application_Composition_Root SHALL 將 fake implementations 注入 Workflow 與 state machine。
9. WHILE fake implementations 已注入 Workflow tests，THE Application_Composition_Root SHALL 排除建立 SQLite_Adapter 或開啟 SQLite connection 的行為。
10. IF FastAPI application 啟動驗證缺少任一必要 dependency，THEN THE Application_Composition_Root SHALL 在接受任何使用者請求前中止啟動並回報指出 dependency 類別的 configuration error。
11. WHEN 任一 repository 的集合查詢成功但沒有符合條件的資料時，THE Repository_Layer SHALL 回傳對應 contract 的空集合而非 repository failure。
12. IF 任一 repository 查詢未成功完成，THEN THE Repository_Layer SHALL 回報 storage-neutral repository error 而非空集合。

### 需求 3：共享 domain contracts

**User Story:** 身為跨模組開發者，我需要穩定且 storage-neutral 的資料 contracts，以便 data layer、rule engine、Workflow 與 API mapping 使用相同語意。

#### 驗收條件

1. THE Domain_Contract_Layer SHALL 定義 immutable CandidateItem、EligibilityDecision、StructuredReason、Citation、FieldRegistryEntry 與 CoverageMetadata contracts。
2. THE Domain_Contract_Layer SHALL 拒絕 contract 建立後的欄位重新指派與 collection 內容變更。
3. THE CandidateItem SHALL 提供 `item_id`、`display_name`、`program_status`、`relevance_score`、`missing_field_ids`、`prerequisites` 與 `produces`。
4. THE EligibilityDecision SHALL 提供 `item_id`、Eligibility_Status、`amount_min`、`amount_max`、`amount_period`、`amount_currency`、已去重且穩定排序的 `missing_field_ids` 與 StructuredReason 集合。
5. THE StructuredReason SHALL 提供 `condition_id`、`field_id`、`operator`、`expected`、`actual`、`label` 與 `source_reference`。
6. THE Citation SHALL 提供必填的 `document_id`、`title`、`publisher`、`url` 與 `excerpt`，以及可為空值且有值時必須為 timezone-aware `datetime` 的 `published_at`、`effective_at` 與 `retrieved_at`。
7. THE FieldRegistryEntry SHALL 提供 `field_id`、`data_type`、`allowed_values`、`prompt_label`、`why_needed` 與 `pii_classification`。
8. THE CoverageMetadata SHALL 提供 `source_id`、`crawl_status`、`last_crawled_at`、`indexed_document_count`、`domain_tags` 與 `observed_at`。
9. THE Domain_Contract_Layer SHALL 將所有 collection fields 定義為不可為空值、允許零個項目且建立後不可變更的 collections。
10. WHEN SQLite_Adapter 讀取資料列時，THE SQLite_Adapter SHALL 將 SQLite 欄名與 encoded values 映射為 Domain_Contract_Layer fields。
11. THE Domain_Contract_Layer SHALL 使用 `item_id` 與 `field_id` 作為跨層識別名稱，不要求 Workflow 使用 `program_id`、`field_name` 或其他資料庫欄名。
12. IF adapter 無法建立符合 contract 的 model，THEN THE SQLite_Adapter SHALL 終止該次 mapping、回報不含原始資料列內容的 mapping error 且不回傳部分 model。
13. WHEN EligibilityDecision 表示已核准的金額資料時，THE Domain_Contract_Layer SHALL 要求 `amount_min` 小於或等於 `amount_max`，並要求 `amount_period` 與 `amount_currency` 同時有值。
14. WHEN EligibilityDecision 沒有已核准的金額資料時，THE Domain_Contract_Layer SHALL 將 `amount_min`、`amount_max`、`amount_period` 與 `amount_currency` 全部保留為空值。
15. IF 已核准的結構化資料未提供金額欄位，THEN THE SQLite_Adapter SHALL 排除從 Citation、標題、摘錄或其他文字推定金額值的行為。

### 需求 4：Entitlement Graph 查詢

**User Story:** 身為 Workflow，我需要透過 Entitlement_Graph_Repository 從人生事件展開相關方案與辦理關係，以便在不硬編碼個別事件流程的情況下建立候選清單。

#### 驗收條件

1. THE Entitlement_Graph SHALL 表示人生事件、保險體系、方案、機關與文件需求之間具有唯一 node ID 的 typed nodes 與 directed edges。
2. THE Entitlement_Graph SHALL 支援 `triggers`、`belongs_to`、`requires`、`produces` 與 `administered_by` edge types。
3. WHEN Entitlement_Graph_Repository 取得有效 event ID 與使用者屬性時，THE Entitlement_Graph_Repository SHALL 為每個可由至少一條未被排除的 path 到達的方案回傳一筆不重複 CandidateItem。
4. IF 使用者尚未提供任一 path condition 所需的 field ID，THEN THE Entitlement_Graph_Repository SHALL 保留該 path 並將所有未被排除 paths 缺少的 field IDs 去重後加入對應 CandidateItem 的 `missing_field_ids`。
5. WHEN Entitlement_Graph_Repository 建立 `missing_field_ids` 時，THE Entitlement_Graph_Repository SHALL 依 `field_id` 升冪回傳穩定順序。
6. IF 使用者提供的 field ID 值不符合任一 path condition，THEN THE Entitlement_Graph_Repository SHALL 僅排除包含該 condition 的 path。
7. IF 同一方案的所有 paths 均被排除，THEN THE Entitlement_Graph_Repository SHALL 排除對應 CandidateItem。
8. WHEN Entitlement_Graph_Repository 回傳 prerequisites 或 produces relations 時，THE Entitlement_Graph_Repository SHALL 先依 canonical order 排序，再以 relation target ID 升冪作為穩定 secondary ordering。
9. WHEN 相同資料版本、event ID 與使用者屬性重複查詢時，THE Entitlement_Graph_Repository SHALL 回傳相同內容與順序。
10. IF graph 資料變更包含不存在的 edge endpoint、方案 ID、field ID 或 relation target，THEN THE Local_Data_Platform SHALL 原子拒絕整筆變更並回報不含原始資料內容的 referential integrity error。
11. IF event ID 不存在或不是人生事件 node，THEN THE Entitlement_Graph_Repository SHALL 回報 invalid event ID error 而非成功的空 CandidateItem 集合。
12. WHEN event ID 有效但沒有任何未被排除的方案 path 時，THE Entitlement_Graph_Repository SHALL 回傳成功的空 CandidateItem 集合。

### 需求 5：Canonical versioned Rule DSL

**User Story:** 身為規則維護者，我需要唯一且有版本的 `all_of`／`any_of` Rule DSL，以便表達可稽核的巢狀資格條件而不維護相互競爭的規則格式。

#### 驗收條件

1. THE Rule_DSL SHALL 是 SQLite 中資格規則的唯一 canonical representation。
2. THE Rule_DSL SHALL 為每個規則保存 `rule_id`、`item_id`、`version`、`required_field_ids`、`logic` 與 source references。
3. THE Rule_DSL SHALL 以可遞迴巢狀的 `all_of` 與 `any_of` nodes 表示條件組合。
4. WHEN Rule_DSL 評估 `all_of` node 時，THE Rule_DSL SHALL 只在所有 children 遞迴成立時將該 node 判定為成立。
5. WHEN Rule_DSL 評估 `any_of` node 時，THE Rule_DSL SHALL 只在至少一個 child 遞迴成立時將該 node 判定為成立。
6. THE Rule_DSL SHALL 為每個 leaf condition 保存 `condition_id`、`field_id`、`operator`、expected value、`label` 與 `source_reference`。
7. THE Rule_DSL SHALL 將合法 operators 限制為 version 所定義的 allowlist。
8. WHEN Human_Reviewer 核准規則內容變更時，THE Benefit_Catalog SHALL 建立新的 Rule_DSL version 並保留先前 versions 的稽核識別資料。
9. IF Rule_DSL version、operator、node shape、field reference 或 source reference 無效，THEN THE Local_Data_Platform SHALL 拒絕將該規則標記為 `verified`。
10. WHEN Program_Status 為 `verified` 的方案進入評估時，THE Eligibility_Service SHALL 要求該方案恰有一個目前有效且經 Human_Reviewer 核准的 Rule_DSL version。
11. WHEN Rule_Engine 評估方案時，THE Rule_Engine SHALL 只使用該方案目前唯一有效且已核准的 canonical Rule_DSL version。
12. IF verified 方案沒有目前有效的已核准 Rule_DSL version 或存在多個目前有效的已核准 Rule_DSL versions，THEN THE Eligibility_Service SHALL 不執行 Rule_Engine 並回傳 `needs_human_review`。
13. THE Rule_Engine SHALL 排除硬編碼於 Python control flow 的個別方案門檻、期限、金額與適用條件。

### 需求 6：唯讀相容投影與 lossless converter

**User Story:** 身為舊有整合的維護者，我需要從 canonical Rule DSL 自動產生 `program_rule_fields` 相容投影，以便在遷移期間保留讀取相容性而不建立第二份真相。

#### 驗收條件

1. WHEN Compatibility_Projection_Generator 接收有效的 canonical Rule_DSL version 時，THE Compatibility_Projection_Generator SHALL 在不修改輸入 Rule_DSL 的情況下產生完整 Compatibility_Projection。
2. THE Compatibility_Projection SHALL 對 application 與維護工具只提供讀取存取。
3. IF 任一操作嘗試直接新增、更新或刪除 Compatibility_Projection 資料，THEN THE Local_Data_Platform SHALL 拒絕該操作並保持 Compatibility_Projection 與 Rule_DSL 不變。
4. WHILE Compatibility_Projection_Generator 正在產生投影，THE Local_Data_Platform SHALL 只向讀取者提供產生前最後一份完整投影。
5. WHEN 相同 Rule_DSL version 與相同 converter version 重複產生投影時，THE Compatibility_Projection_Generator SHALL 產生 byte-equivalent canonical serialization 與穩定順序。
6. WHEN 有效 Rule_DSL 完成 canonical-to-projection-to-canonical round trip 時，THE Compatibility_Projection_Generator SHALL 保留規則版本、required field IDs、巢狀布林語意、condition IDs、field IDs、operators、expected values、labels 與 source references。
7. WHEN 原始 Rule_DSL 與 round trip 後的 Rule_DSL 接收相同合法輸入時，THE Compatibility_Projection_Generator SHALL 確保兩者產生相同 Eligibility_Status、缺少的 field IDs 與 StructuredReason condition IDs。
8. IF Rule_DSL 包含 Compatibility_Projection_Generator 無法無損表示的內容，THEN THE Compatibility_Projection_Generator SHALL 拒絕整次投影產生並回報 converter version error。
9. IF Compatibility_Projection 產生失敗，THEN THE Local_Data_Platform SHALL 不提供任何部分產出並保留產生前最後一份完整投影。
10. THE Benefit_Catalog SHALL 排除人工分別新增、更新或同步維護 Rule_DSL 與 `program_rule_fields` 的流程。

### 需求 7：確定性資格判斷與方案狀態閘門

**User Story:** 身為使用者，我需要系統依方案治理狀態採取一致且保守的資格行為，以便過期或未審查規則不會產生完整結論。

#### 驗收條件

1. WHEN Program_Status 為 `verified` 且方案具有唯一有效的已核准 Rule_DSL version 與完整 Citation mapping 時，THE Eligibility_Service SHALL 執行 Rule_Engine 並回傳完整 EligibilityDecision。
2. WHEN Program_Status 為 `candidate` 或 `under_review` 時，THE Eligibility_Service SHALL 不執行 Rule_Engine 並回傳 `needs_human_review`。
3. WHEN Program_Status 為 `candidate` 或 `under_review` 時，THE Entitlement_Graph_Repository SHALL 保留 CandidateItem 並提供對應 Program_Status 供 API 顯示「尚未二次確認」。
4. WHEN Program_Status 為 `stale` 時，THE Entitlement_Graph_Repository SHALL 保留 CandidateItem 並提供 `stale` Program_Status 供 API 顯示警示。
5. WHEN Program_Status 為 `stale` 時，THE Eligibility_Service SHALL 不執行 Rule_Engine 並回傳 `needs_human_review`。
6. WHEN Program_Status 為 `rejected` 或 `inactive` 時，THE Entitlement_Graph_Repository SHALL 從候選結果排除該方案。
7. WHEN Program_Status 為 `rejected` 或 `inactive` 時，THE Eligibility_Service SHALL 不執行 Rule_Engine 且回傳 non-evaluable status error。
8. IF verified 方案缺少唯一有效的已核准 Rule_DSL version 或任一必要 Citation，THEN THE Eligibility_Service SHALL 不執行 Rule_Engine 並回傳 `needs_human_review`。
9. IF Rule_Engine 缺少必要使用者欄位，THEN THE Eligibility_Service SHALL 回傳 `needs_information` 並列出已去重且穩定排序的 field IDs。
10. WHEN Rule_Engine 產生判斷原因時，THE Eligibility_Service SHALL 回傳 StructuredReason 而非只有展示文字。
11. THE Validation_Suite SHALL 對每個 Program_Status 與 verified 資料缺漏案例驗證 Eligibility_Status 及 Rule_Engine 執行次數。

### 需求 8：Relevance score 僅供 backend 排序

**User Story:** 身為使用者，我需要相關候選以一致順序呈現且不看到容易被誤解的分數，以便不將相關性誤認為資格機率。

#### 驗收條件

1. THE Relevance_Score SHALL 只接受有限數值或空值，且只作為 backend 內部排序 metadata。
2. THE Relevance_Score SHALL 排除本需求未核准的固定數值範圍。
3. WHEN CandidateItem 集合需要排序時，THE System SHALL 依 `verified`、`stale`、`under_review`、`candidate` 的 Program_Status safety ordering 建立群組。
4. WHEN 同一 Program_Status 群組內的 CandidateItem 具有有效 Relevance_Score 時，THE System SHALL 依 Relevance_Score 降冪排序並以 `item_id` 升冪作為分數相同時的 secondary key。
5. IF CandidateItem 缺少 Relevance_Score，THEN THE System SHALL 將 CandidateItem 排在同一 Program_Status 群組內所有有效分數之後並以 `item_id` 升冪排序。
6. IF CandidateItem 的 Relevance_Score 為非數值、NaN 或無限值，THEN THE System SHALL 將該分數視為無效排序值、排在同一群組的有效分數之後並記錄不含候選內容的 data-quality error。
7. THE API_Response_Mapper SHALL 排除 `relevance_score` 欄位。
8. THE API_Response_Mapper SHALL 排除 Relevance_Score 的數值、區間與衍生百分比。
9. THE Eligibility_Service SHALL 排除以 Relevance_Score 的存在、缺漏、有效性或數值決定或修改 Eligibility_Status 的行為。
10. THE StructuredReason SHALL 排除將 Relevance_Score 描述為資格機率、符合程度或法定判斷依據的內容。
11. WHEN 相同資料與使用者屬性重複排序時，THE System SHALL 產生相同候選順序。

### 需求 9：StructuredReason 與 raw user text 隱私

**User Story:** 身為使用者，我需要實際資格值只在我的回應中用於解釋，且不進入可觀測性與稽核資料，以便降低個人情境外洩風險。

#### 驗收條件

1. WHERE response 接收者是 Requesting_User，THE API_Response_Mapper SHALL 只在目前請求的 EligibilityDecision response 中回傳必要的 `StructuredReason.actual`。
2. IF response 接收者不是 Requesting_User，THEN THE API_Response_Mapper SHALL 從 response 移除所有 `StructuredReason.actual` values。
3. THE Privacy_Sanitizer SHALL 從 log、trace、metric、exception 與 audit payload 移除所有 `StructuredReason.actual` values。
4. THE Privacy_Sanitizer SHALL 從 log、trace、metric、exception 與 audit payload 移除所有 Raw_User_Text。
5. WHEN observability payload 進入輸出路徑時，THE Observability_Pipeline SHALL 在任何 serialization 與 emission 前將完整 payload 集中交由 Privacy_Sanitizer 處理。
6. IF payload 在頂層、巢狀物件、陣列元素或字串化內容中包含 `StructuredReason.actual` values 或 Raw_User_Text，THEN THE Privacy_Sanitizer SHALL 在 emission 前遞迴移除每一處對應內容。
7. WHEN exception handler 接收包含使用者值或 Raw_User_Text 的 exception 時，THE Privacy_Sanitizer SHALL 只保留 error type、safe code 與不含使用者值的 context IDs。
8. WHEN audit event 記錄資格操作時，THE Privacy_Sanitizer SHALL 只保留 item ID、rule version、Eligibility_Status、時間與不含使用者值的 actor/session pseudonymous ID。
9. WHILE Workflow 使用 Raw_User_Text 進行結構化屬性提取，THE Workflow SHALL 將 Raw_User_Text 限於目前請求的暫時處理範圍。
10. WHEN 結構化屬性提取成功、失敗或取消時，THE Workflow SHALL 在 response 或後續 state transition 前丟棄 server-side Raw_User_Text。
11. WHEN 結構化屬性提取成功時，THE Workflow SHALL 只保留 allowlisted attributes。
12. IF Privacy_Sanitizer 失敗或無法確認完整 payload 已完成 sanitization，THEN THE Observability_Pipeline SHALL 取消原始 payload 的 serialization 與 emission 並只產生不含原始 payload 衍生內容的 sanitization failure indication。
13. THE Validation_Suite SHALL 使用 Synthetic_Validation_Data 驗證 authorization、遞迴 sanitization、Raw_User_Text lifecycle 與 fail-closed observability 行為。

### 需求 10：官方證據與 citations

**User Story:** 身為使用者與審查人員，我需要資格結論連結完整且可追溯的官方證據，以便查核規則依據而不依賴虛構或截斷資訊。

#### 驗收條件

1. THE Evidence_Repository SHALL 只從 Benefit_Catalog 中已登記的 Official_Source 建立 Citation。
2. WHEN Evidence_Repository 建立 Citation 時，THE Evidence_Repository SHALL 將已核准來源記錄的 `document_id`、`title`、`publisher`、`url` 與 `excerpt` 完整映射至 Citation。
3. WHERE Official_Source 明確提供 `published_at`、`effective_at` 或成功擷取記錄提供 `retrieved_at`，THE Evidence_Repository SHALL 將對應值映射至 Citation。
4. IF 已核准來源記錄未提供任一 optional 日期值，THEN THE Evidence_Repository SHALL 將對應 Citation 欄位保留為空值而不推定替代值。
5. WHEN Eligibility_Service 準備回傳 `eligible` 或 `ineligible` 時，THE Evidence_Repository SHALL 為 Rule_Engine 實際評估的每個 distinct `source_reference` 提供至少一筆可追溯 Citation。
6. IF 任一已評估的 `source_reference` 無法解析為包含必填欄位的 Citation，THEN THE Eligibility_Service SHALL 將結果降級為 `needs_human_review` 且不以其他 Citation 替代。
7. THE Source_Curation_Pipeline SHALL 拒絕將 placeholder、AI 生成內容、未核對文字或推定 metadata 保存為已核准 Citation 證據。
8. THE Evidence_Repository SHALL 排除自行補寫、推定或改寫 Official_Source 的標題、發布者、日期與引用段落。
9. THE Benefit_Catalog SHALL 保留 Rule_DSL version、每個 `source_reference`、對應 Citation 與 Human_Reviewer 核准紀錄之間的可追溯關聯。
10. IF Citation 的 optional 日期欄位為空值，THEN THE Eligibility_Service SHALL 不僅因該空值而降級 Eligibility_Status。

### 需求 11：非阻塞且同日去重的 on-demand refresh

**User Story:** 身為使用者，我需要系統先使用目前資料回應，再於背景更新到期來源，以便網路或提取作業不阻塞目前請求。

#### 驗收條件

1. WHEN 使用者請求候選方案時，THE System SHALL 先使用請求開始時的 Last_Successful_Committed_State 建立回應。
2. WHEN Source_Refresh_Service 發現相關來源為 `pending_crawl` 或已超過設定更新頻率時，THE Source_Refresh_Service SHALL 排入受同日去重規則約束的本機 Refresh_Job。
3. WHEN refresh request 建立至少一個新的 Refresh_Job 時，THE Source_Refresh_Service SHALL 在等待爬取、附件處理或候選提取完成前回傳 `accepted=true` 且 `deduplicated=false` 的 refresh receipt；若沒有任何來源排入則回傳 `accepted=false`。
4. THE Source_Refresh_Service SHALL 以 `source_id`、event/topic 與 request time 依 Application_Timezone 換算的 calendar date 組成 deterministic deduplication key。
5. IF 相同 deduplication key 已有 Refresh_Job，THEN THE Source_Refresh_Service SHALL 回傳 `deduplicated=true` 的 refresh receipt 且不建立第二個 Refresh_Job。
6. WHEN 相同 deduplication key 的 refresh requests 並行執行時，THE Source_Refresh_Service SHALL 以 concurrency-safe atomic operation 只建立一個 Refresh_Job。
7. WHEN 並行 refresh requests 共用相同 deduplication key 時，THE Source_Refresh_Service SHALL 向一個 request 回傳 `deduplicated=false` 並向其他 requests 回傳 `deduplicated=true`。
8. IF Refresh_Job 失敗，THEN THE System SHALL 保留原始回應與 Last_Successful_Committed_State。
9. WHEN Refresh_Job 產生新頁面、附件或規則候選時，THE Source_Curation_Pipeline SHALL 將產出保存為 `candidate` 或 `under_review`。
10. THE Source_Refresh_Service SHALL 排除在使用者 request lifecycle 內同步執行網路爬取或 LLM 分析。

### 需求 12：可量測 coverage status

**User Story:** 身為資料維護者，我需要量測來源爬取與索引進度，以便辨識缺口而不宣稱無法證明的完整覆蓋。

#### 驗收條件

1. WHEN coverage status 被請求時，THE Coverage_Tracker SHALL 回報 Coverage_Scope 與該次快照的 `observed_at`。
2. WHEN coverage status 被請求時，THE Coverage_Tracker SHALL 回報 scope 內的已登記來源數、`crawled` 來源數、`pending_crawl` 來源數、`error` 來源數與已索引文件數。
3. WHEN Coverage_Tracker 建立 coverage 快照時，THE Coverage_Tracker SHALL 為 scope 內每個已登記來源回報 `source_id`、`crawl_status`、`last_crawled_at`、`indexed_document_count`、domain tags 與相同的 `observed_at`。
4. THE CoverageMetadata SHALL 將 `crawl_status` 限制為 `pending_crawl`、`crawled` 或 `error`。
5. THE CoverageMetadata SHALL 將 `indexed_document_count` 表示為非負整數。
6. WHEN 來源因 robots policy、登入限制、JavaScript-only content、失效連結、掃描附件或連線錯誤無法處理時，THE Coverage_Tracker SHALL 將來源標記為 `error` 並記錄可識別的 coverage gap category。
7. THE CoverageMetadata SHALL 只表達指定 Coverage_Scope 在 `observed_at` 時觀測到的進度與缺口。
8. THE API_Response_Mapper SHALL 排除法律內容完整性、網站內容完整性、scope 外覆蓋、「零遺漏」、「完整保證」與「所有福利均已索引」的主張。
9. WHEN 來源成功完成爬取時，THE Coverage_Tracker SHALL 將 `crawl_status` 設為 `crawled` 並更新 `last_crawled_at` 與 `indexed_document_count`。
10. IF 來源爬取失敗且存在最近一次成功 metadata，THEN THE Coverage_Tracker SHALL 將 `crawl_status` 設為 `error` 並保留最近一次成功的 `last_crawled_at` 與 `indexed_document_count`。
11. IF 來源爬取失敗且不存在成功 metadata，THEN THE Coverage_Tracker SHALL 將 `crawl_status` 設為 `error`、將 `last_crawled_at` 保留為空值並將 `indexed_document_count` 設為 0。
12. WHEN Coverage_Tracker 回報 coverage 快照時，THE Coverage_Tracker SHALL 使已登記來源數等於 `pending_crawl`、`crawled` 與 `error` 來源數之和。
13. WHEN Coverage_Tracker 回報 coverage 快照時，THE Coverage_Tracker SHALL 使 aggregate 已索引文件數等於所有 per-source `indexed_document_count` 之和。

### 需求 13：SQLite connection lifecycle

**User Story:** 身為 backend 維護者，我需要每條 SQLite connection 路徑明確關閉資源，以便避免測試與 runtime 發生 connection leak 或 file lock。

#### 驗收條件

1. WHEN SQLite_Adapter 建立 SQLite connection 時，THE SQLite_Adapter SHALL 使用 `contextlib.closing` 或在所有路徑明確呼叫 `close()` 的等價 lifecycle wrapper。
2. WHEN transaction scope 的主要操作與 commit 均成功時，THE SQLite_Adapter SHALL 先完成 commit、再關閉 connection、最後回傳操作結果。
3. IF transaction scope 的主要操作或 commit 失敗，THEN THE SQLite_Adapter SHALL 先嘗試 rollback、再嘗試關閉 connection、最後回報 sanitized error。
4. WHEN 唯讀 SQLite operation 成功完成時，THE SQLite_Adapter SHALL 在回傳查詢結果前關閉 connection。
5. IF 唯讀 SQLite operation 失敗，THEN THE SQLite_Adapter SHALL 在回報 sanitized error 前嘗試關閉 connection。
6. IF rollback 失敗，THEN THE SQLite_Adapter SHALL 仍嘗試關閉 connection 並只回報 sanitized lifecycle error。
7. IF close 失敗，THEN THE SQLite_Adapter SHALL 不回傳操作結果並只回報 sanitized lifecycle error。
8. THE SQLite_Adapter SHALL 從 lifecycle error 排除 SQL、原始資料列內容、Raw_User_Text、`StructuredReason.actual` 與其他使用者資料。
9. WHEN Validation_Suite 注入主要操作、commit、rollback 或 close failure 時，THE Validation_Suite SHALL 驗證 commit、rollback 與 close 的執行順序及 sanitized error 行為。
10. WHEN Validation_Suite 執行 transaction 與唯讀操作的成功及失敗案例時，THE Validation_Suite SHALL 驗證未注入 close failure 的每個 SQLite connection 已關閉。
11. THE SQLite_Adapter SHALL 排除只依賴 `with sqlite3.connect(...)` 來保證 connection closure 的實作。

### 需求 14：JSON 僅供自動產生的測試或 release snapshot

**User Story:** 身為 release 與測試維護者，我需要可重現的 JSON snapshots 而不讓 JSON 成為 runtime truth，以便進行 fixture 測試與版本差異檢視。

#### 驗收條件

1. WHERE tests 需要 fixture，THE JSON_Exporter SHALL 從指定 SQLite schema 與資料版本自動產生 JSON。
2. WHERE release 流程需要 snapshot，THE JSON_Exporter SHALL 從指定 SQLite schema 與資料版本自動產生 versioned JSON。
3. WHEN 相同 SQLite schema version、資料版本、Rule_DSL versions 與 export timestamp 重複匯出時，THE JSON_Exporter SHALL 以 canonical field ordering 與 stable collection ordering 產生 byte-equivalent output。
4. THE JSON_Exporter SHALL 在 snapshot metadata 中包含 schema version、export timestamp 與來源 Rule_DSL versions。
5. THE System SHALL 將 JSON_Exporter 執行與 JSON snapshot 讀取限制於 tests 或 release 流程。
6. THE System SHALL 排除 runtime request lifecycle 使用 JSON_Exporter 或 JSON snapshot 的行為。
7. IF JSON_Exporter 無法開啟 SQLite 或讀取指定 schema 與資料版本，THEN THE JSON_Exporter SHALL 回報明確 SQLite error 且不讀取或產生 JSON fallback。
8. WHEN JSON export 成功時，THE JSON_Exporter SHALL 以 atomic replacement 只讓單一完整 snapshot 成為可觀察結果。
9. IF JSON export 失敗，THEN THE JSON_Exporter SHALL 不建立 partial output 並保留既有完整 snapshot 不變。
10. THE System SHALL 排除從 JSON snapshot 回寫 canonical SQLite 資料的 runtime 路徑。
11. THE Source_Curation_Pipeline SHALL 排除人工同時維護 SQLite 與 JSON 內容的工作流程。

### 需求 15：MVP catalog、來源與驗證

**User Story:** 身為資料維護者，我需要可驗證的 MVP catalog 與測試資料，以便確認資料形狀、狀態閘門與 deterministic rule behavior，而不在需求文件中臆測福利事實。

#### 驗收條件

1. THE Benefit_Catalog SHALL 支援簡介所列六個既有 MVP program IDs。
2. WHEN 任一 MVP 方案缺少人工核准的資格事實、期限、金額或來源摘錄時，THE Benefit_Catalog SHALL 保留未知值或未審查狀態而不建立推定值。
3. THE Source_Curation_Pipeline SHALL 只接受人工核准的 Official_Source metadata 與 source excerpts 作為 verified evidence。
4. WHEN Human_Reviewer 核准方案、Rule_DSL 或 Citation 時，THE Benefit_Catalog SHALL 記錄 reviewer identity reference、review timestamp 與核准 version。
5. THE Validation_Suite SHALL 驗證 Rule_DSL schema、operator allowlist、required field references、Citation references、referential integrity 與 Program_Status gates。
6. THE Validation_Suite SHALL 驗證 EligibilityDecision 的 amount field consistency。
7. THE Validation_Suite SHALL 驗證 Compatibility_Projection 的 deterministic output 與 round-trip semantic equivalence。
8. THE Validation_Suite SHALL 以正常、邊界、缺少資訊、未審查、stale、rejected 與 inactive cases 驗證 Eligibility_Status 行為。
9. WHEN Validation_Suite 使用 Synthetic_Validation_Data 時，THE Validation_Suite SHALL 將合成規則、來源內容與資格值隔離於 Benefit_Catalog、Official_Source metadata、verified evidence 與正式 Citation 之外。
10. WHEN Synthetic_Validation_Data 驗證完成時，THE Validation_Suite SHALL 確認 canonical catalog 未包含任何合成資料。
11. IF validation 發現錯誤，THEN THE Validation_Suite SHALL 以非零 exit status 結束並指出 item ID、rule version、error code 與不含敏感值的描述。
12. IF validation 未發現錯誤，THEN THE Validation_Suite SHALL 以零 exit status 結束並輸出受檢項目數量。

### 需求 16：技術治理、AWS safety 與人工核准邊界

**User Story:** 身為專案 owner，我需要 MVP 在核准的技術與責任邊界內運作，以便安全驗證雲端整合，同時避免 secrets 外洩或讓生成式模型控制資格與資料驗證。

#### 驗收條件

1. WHILE data-layer 尚未有 owner-approved storage migration ADR 與替代 adapter，THE System SHALL 以本機 SQLite、本機檔案與本機 Refresh_Job implementations 作為預設且可測試的資料儲存、檔案處理與 background job path。
2. WHEN owner 核准 live AWS integration，THE System SHALL 從 Git 外部取得 credentials、排除將 credentials 或 account-specific secrets 寫入 repository，保留不需要 live AWS 的 local test path，並在同一批次更新 `docs/aws_migration_guide.md`。
3. WHEN Eligibility_Status 為 `eligible` 或 `ineligible` 時，THE Eligibility_Service SHALL 只使用 Rule_Engine 的確定性評估結果產生該狀態。
4. WHEN 方案狀態閘門或必要欄位檢查阻止完整評估時，THE Eligibility_Service SHALL 依需求 7 產生 `needs_human_review` 或 `needs_information` 而不執行完整規則判斷。
5. THE LLM_Integration SHALL 排除產生、覆寫或升級 Eligibility_Status 的權限。
6. THE LLM_Integration SHALL 排除請求、核准或執行任何將方案、Rule_DSL、Citation 或 source excerpt 標記為 `verified` 的狀態轉換。
7. WHEN LLM_Integration、crawler 或 importer 產生頁面分類或結構化提取結果時，THE Source_Curation_Pipeline SHALL 將結果保存為 `candidate` 或 `under_review`。
8. THE Source_Curation_Pipeline SHALL 排除 crawler、importer、Compatibility_Projection_Generator 與 JSON_Exporter 將資料標記為 `verified` 的操作。
9. WHEN Human_Reviewer 將 `candidate` 轉為 `under_review` 時，THE Benefit_Catalog SHALL 記錄 reviewer identity reference、review timestamp、原狀態與新狀態。
10. WHEN Human_Reviewer 將 `candidate`、`under_review` 或 `stale` 轉為 `verified` 時，THE Benefit_Catalog SHALL 只在目標 version 具有已核准 Rule_DSL、Citation 與 source excerpt 時套用轉換並記錄審查資料。
11. WHEN Human_Reviewer 將 `candidate`、`under_review` 或 `stale` 轉為 `rejected` 或 `inactive` 時，THE Benefit_Catalog SHALL 套用明確目標狀態並記錄審查資料。
12. WHEN Human_Reviewer 將 `verified` 轉為 `stale` 或 `inactive` 時，THE Benefit_Catalog SHALL 套用明確目標狀態並記錄審查資料。
13. IF Human_Reviewer 以外的 actor 要求將資料轉為 `verified`、`rejected` 或 `inactive`，THEN THE Benefit_Catalog SHALL 拒絕轉換並保留目前狀態。
14. IF 已核准規則或證據不足以產生完整資格結論，THEN THE Eligibility_Service SHALL 回傳 `needs_human_review`。
