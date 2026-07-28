# 需求文件：資料層與規則引擎補齊

## 簡介

為「接住」福利導航 Agent 的 MVP 情境（配偶死亡）補齊資料層內容與規則引擎驗證機制。本需求採用**關聯式圖模型**（Entitlement Graph）取代靜態 JSON 檔案，以 SQLite `graph_nodes` 與 `graph_edges` 資料表儲存人生事件、保險體系、福利方案、機關與文件需求之間的關聯，支援雙向遍歷與條件式展開。提取管線升級為多層架構，涵蓋 HTML 擷取、附件偵測與下載、附件文本提取、LLM 完整分析、以及人工審查。未審查方案可顯示但須附免責聲明，僅已驗證方案才進入 Rule Engine 資格評估。

MVP 六項核心福利方案：
1. 死亡登記（death_registration）
2. 勞保喪葬給付（labor_funeral_grant）— 條件：insurance_type = labor_insurance
3. 國保喪葬給付（national_pension_funeral_grant）— 條件：insurance_type = national_pension
4. 勞保遺屬年金（labor_survivor_pension）— 條件：insurance_type = labor_insurance
5. 國保遺屬年金（national_pension_survivor_pension）— 條件：insurance_type = national_pension
6. 全民健康保險身分變更（nhi_status_change）

## 詞彙表

- **Entitlement_Graph**：以 SQLite `graph_nodes` 與 `graph_edges` 資料表儲存的關聯式圖模型，描述人生事件、保險體系、福利方案、機關與文件需求之間的有向關聯，支援雙向遍歷。
- **Graph_Node**：`graph_nodes` 資料表中的一筆記錄，代表圖中一個實體節點，含 node_id、node_type、display_name、metadata_json。
- **Graph_Edge**：`graph_edges` 資料表中的一筆記錄，代表兩個節點之間的有向關聯，含 from_node_id、to_node_id、edge_type、condition_json、order、metadata_json。
- **Node_Type**：節點類型列舉值，合法值為 `life_event`（人生事件）、`insurance_system`（保險體系）、`benefit_program`（福利方案）、`agency`（機關）、`document_requirement`（文件需求）。
- **Edge_Type**：邊類型列舉值，合法值為 `triggers`（觸發）、`belongs_to`（歸屬）、`requires`（前置需求）、`produces`（產出）、`administered_by`（承辦機關）。
- **Condition_JSON**：邊上的條件式展開欄位（JSON 或 NULL），格式為 `{"attribute": "<使用者屬性名稱>", "value": "<該屬性須符合的值"}`。當使用者尚未提供該屬性時，遍歷所有邊；已提供時僅遍歷匹配邊。
- **Rule_Engine**：通用資格判斷引擎（`backend/app/rules/engine.py`），讀取 `program_rule_fields` 資料表中的宣告式欄位進行確定性評估。僅對 program_status 為 `verified` 的方案執行完整資格判斷。
- **Benefit_Catalog**：本機 SQLite 中 `benefit_programs`、`program_rule_fields`、`program_sources`、`program_organization_roles`、`graph_nodes`、`graph_edges` 等資料表的集合。
- **Program_Rule_Fields**：`program_rule_fields` 資料表中每筆記錄，定義一項福利的單一規則欄位，含 field_name、field_type、field_value、source_excerpt 與 review_status。
- **Source_Document**：`source_documents` 資料表中代表一份官方文件的記錄，含 canonical_url、title、document_type、jurisdiction_code 等 metadata。
- **Document_Attachment**：`document_attachments` 資料表中代表一份來源文件附件的記錄，含 attachment_id、document_id、filename、file_type、download_url、extracted_text_available 等欄位。
- **Evidence_Link**：`program_sources` 資料表中連結福利方案與來源文件的記錄，含 evidence_role 與 source_excerpt。
- **Extraction_Confidence**：提取結果信心等級，合法值為 `partial`（僅 HTML，頁面指出有附件但尚未處理）、`high_from_html`（僅 HTML，頁面內容看起來完整）、`high_from_full`（HTML + 所有附件已提取並分析）、`partial_ocr_needed`（附件為掃描圖檔，需 OCR）。
- **Validate_Rules_Script**：`scripts/validate_rules.py` 腳本，負責驗證所有已填入的 program_rule_fields 資料完整性與一致性。
- **Evaluation_Case**：用於測試 Rule_Engine 資格判斷正確性的結構化測試案例，含使用者屬性輸入與預期判斷結果。
- **Insurance_Type**：申請人或亡者的社會保險身分，MVP 區分為 `labor_insurance`（勞保）與 `national_pension`（國民年金）。
- **Provenance**：資料來源追溯性，每筆規則欄位須附 source_excerpt 引用官方文件原文。
- **Source_Monitor_Script**：`scripts/monitor_source_changes.py` 腳本，負責重新抓取來源文件並偵測內容變更。
- **LLM_Extraction_Pipeline**：使用 Structural_Crawl 發現來源頁面，再透過 AI 分類與 Amazon Bedrock LLM 從來源頁面與附件提取結構化福利候選資料的多層管線（Layer 0: 結構性發現 → Layer 1: 頁面分類 → Layer 2: 附件偵測 → Layer 3: 附件文本提取 → Layer 4: LLM 完整分析 → Layer 5: 人工審查）。
- **Check_Frequency**：來源監控頻率欄位，定義該機關官網應被重新爬取以發現新頁面的時間間隔（daily/weekly/monthly/manual）。
- **Structural_Crawl**：從已登記機關的官方網站首頁出發，依網站結構（福利專區、申辦服務、公告等導覽連結）逐層發現子頁面的系統性爬取方式。不依賴搜尋引擎或關鍵字搜尋。支援三種觸發模式：On-demand（查詢時發現 pending_crawl 機關即時觸發）、Scheduled（依 check_frequency 定期爬取到期機關）、Manual（維護者指定強制重爬）。
- **Coverage_Guarantee**：本系統的核心價值主張：透過 OID registry 窮舉所有公部門機關，再系統性掃描每個機關的官網，保證不遺漏任何公部門的福利資源。與 ChatGPT（依賴訓練資料，可能過時或遺漏方案）或 Google（SEO 排名，僅回傳排序靠前的結果，許多利基補助未被良好索引）不同，本系統從完整的機關清單出發進行窮舉式發現。
- **Domain_Tags**：source_registry 中的業務領域標籤欄位，以 JSON 字串陣列格式記錄該機關涉及的人生事件相關業務領域（如 death、unemployment、birth 等），用於快速篩選某主題相關的所有機關。

## 需求

### 需求 1：Entitlement Graph 關聯模型

**User Story:** 身為 orchestration 模組，我需要透過關聯式圖模型查詢人生事件對應的保險體系、福利方案、文件需求與承辦機關，且支援雙向遍歷與條件式展開，以便動態展開候選福利而不需硬編碼任何事件特定邏輯。

#### 驗收條件

1. THE Benefit_Catalog SHALL 包含 `graph_nodes` 資料表，schema 為：node_id（TEXT PRIMARY KEY）、node_type（TEXT NOT NULL，CHECK 約束限制為 `life_event`、`insurance_system`、`benefit_program`、`agency`、`document_requirement`）、display_name（TEXT NOT NULL）、metadata_json（TEXT，可為 NULL）、created_at（TEXT NOT NULL）、updated_at（TEXT NOT NULL）。
2. THE Benefit_Catalog SHALL 包含 `graph_edges` 資料表，schema 為：from_node_id（TEXT NOT NULL，外鍵參照 graph_nodes）、to_node_id（TEXT NOT NULL，外鍵參照 graph_nodes）、edge_type（TEXT NOT NULL，CHECK 約束限制為 `triggers`、`belongs_to`、`requires`、`produces`、`administered_by`）、condition_json（TEXT，可為 NULL）、order（INTEGER NOT NULL DEFAULT 0）、metadata_json（TEXT，可為 NULL）、created_at（TEXT NOT NULL），主鍵為 (from_node_id, to_node_id, edge_type)。
3. THE `graph_edges` 資料表 SHALL 支援雙向查詢：透過 `SELECT * FROM graph_edges WHERE from_node_id = ?` 查詢正向關聯（如從 life_event 找到所有 triggers 的 insurance_system），以及透過 `SELECT * FROM graph_edges WHERE to_node_id = ?` 查詢反向關聯（如從 insurance_system 找到所有觸發它的 life_event）。
4. WHEN Condition_JSON 為非 NULL 時，THE Graph_Edge SHALL 包含格式為 `{"attribute": "<屬性名稱>", "value": "<屬性值>"}` 的條件物件；WHEN orchestration 模組遍歷該邊時，IF 使用者已提供該 attribute 且值不匹配，SHALL 跳過該邊；IF 使用者尚未提供該 attribute，SHALL 遍歷該邊（保守策略）。
5. THE `graph_edges` 資料表 SHALL 設定外鍵約束：from_node_id 參照 `graph_nodes(node_id)` ON DELETE RESTRICT、to_node_id 參照 `graph_nodes(node_id)` ON DELETE RESTRICT，確保不會出現指向不存在節點的邊。
6. WHEN 新增一個人生事件時，THE 系統 SHALL 僅需：（a）新增對應的 graph_nodes 記錄（life_event 類型）、（b）新增該事件觸發的 graph_edges 記錄、（c）新增對應的 benefit_programs 與 program_rule_fields 資料 — 不需修改任何 Python 程式碼。
7. THE `graph_nodes` 與 `graph_edges` 資料表 SHALL 建立適當索引：graph_nodes 上的 node_type 索引、graph_edges 上的 from_node_id 索引、graph_edges 上的 to_node_id 索引、graph_edges 上的 edge_type 索引。

### 需求 2：MVP 福利方案基本資料

**User Story:** 身為 Rule_Engine，我需要從 `benefit_programs` 資料表讀取每項 MVP 福利的基本識別資訊與分類，並透過 graph_nodes 與 graph_edges 記錄表示其在 Entitlement Graph 中的位置，以便正確載入對應的規則欄位進行評估。

#### 驗收條件

1. THE Benefit_Catalog SHALL 包含 6 筆 `benefit_programs` 記錄，其 program_id 分別為：`death_registration`、`labor_funeral_grant`、`national_pension_funeral_grant`、`labor_survivor_pension`、`national_pension_survivor_pension`、`nhi_status_change`。
2. THE `benefit_programs` 記錄中每筆 SHALL 填入 canonical_name（繁體中文福利名稱）、summary（50 字以內的用途摘要）、support_purpose、program_basis、delivery_form、jurisdiction_code，且所有欄位值 SHALL 符合 `benefit_programs` 資料表定義的 CHECK 約束。
3. WHEN program_id 為 `death_registration`，THE 記錄 SHALL 設定 support_purpose 為 NULL（行政程序非福利給付）、program_basis 為 NULL、delivery_form 為 NULL、jurisdiction_code 為 `TW`。
4. WHEN program_id 為 `labor_funeral_grant`，THE 記錄 SHALL 設定 support_purpose 為 `funeral_cost`、program_basis 為 `social_insurance`、delivery_form 為 `cash_once`、jurisdiction_code 為 `TW`。
5. WHEN program_id 為 `national_pension_funeral_grant`，THE 記錄 SHALL 設定 support_purpose 為 `funeral_cost`、program_basis 為 `social_insurance`、delivery_form 為 `cash_once`、jurisdiction_code 為 `TW`。
6. WHEN program_id 為 `labor_survivor_pension`，THE 記錄 SHALL 設定 support_purpose 為 `survivor_livelihood`、program_basis 為 `social_insurance`、delivery_form 為 `cash_recurring`、jurisdiction_code 為 `TW`。
7. WHEN program_id 為 `national_pension_survivor_pension`，THE 記錄 SHALL 設定 support_purpose 為 `survivor_livelihood`、program_basis 為 `social_insurance`、delivery_form 為 `cash_recurring`、jurisdiction_code 為 `TW`。
8. WHEN program_id 為 `nhi_status_change`，THE 記錄 SHALL 設定 support_purpose 為 NULL（行政程序非福利給付）、program_basis 為 NULL、delivery_form 為 NULL、jurisdiction_code 為 `TW`。
9. THE `benefit_programs` 記錄在初始填入時 SHALL 將 program_status 設為 `under_review`，不得設為 `verified`，因為尚未完成證據連結與人工審查流程。
10. THE Entitlement_Graph SHALL 為配偶死亡情境包含以下 Graph_Node 記錄：`spouse_death`（node_type: life_event）、`labor_insurance`（node_type: insurance_system）、`national_pension`（node_type: insurance_system）、`nhi`（node_type: insurance_system）、`household_registration`（node_type: agency）、`death_certificate`（node_type: document_requirement），以及 6 筆 benefit_program 類型節點對應 6 項 MVP 福利。
11. THE Entitlement_Graph SHALL 為配偶死亡情境包含以下 Graph_Edge 記錄：`spouse_death` --triggers--> `labor_insurance`、`spouse_death` --triggers--> `national_pension`、`spouse_death` --triggers--> `nhi`、`spouse_death` --triggers--> `household_registration`、`labor_insurance` --belongs_to--> `labor_funeral_grant`、`labor_insurance` --belongs_to--> `labor_survivor_pension`、`national_pension` --belongs_to--> `national_pension_funeral_grant`、`national_pension` --belongs_to--> `national_pension_survivor_pension`、`nhi` --belongs_to--> `nhi_status_change`、`household_registration` --belongs_to--> `death_registration`、`death_registration` --produces--> `death_certificate`、`labor_funeral_grant` --requires--> `death_certificate`、`labor_survivor_pension` --requires--> `death_certificate`。
12. THE `spouse_death` --triggers--> `labor_insurance` 邊 SHALL 設定 condition_json 為 `{"attribute": "insurance_type", "value": "labor_insurance"}`；`spouse_death` --triggers--> `national_pension` 邊 SHALL 設定 condition_json 為 `{"attribute": "insurance_type", "value": "national_pension"}`；其餘 triggers 邊的 condition_json SHALL 為 NULL。

### 需求 3：MVP 規則欄位（6 項核心）

**User Story:** 身為 Rule_Engine，我需要從 `program_rule_fields` 資料表讀取 6 項核心 MVP 福利的宣告式規則（含必要屬性、資格條件、金額計算、期限），以便僅靠資料驅動的方式評估資格。

#### 驗收條件

1. WHEN program_id 為 `death_registration`，THE Program_Rule_Fields SHALL 定義以下規則欄位：required_attributes（json 型別，值為需要的使用者屬性名稱清單，至少包含 `death_date` 與 `relationship_to_deceased`）、application_deadline_days（integer 型別，值為 30，代表死亡後 30 日內須辦理）、deadline_starts_from（text 型別，值為 `death_date`）。
2. WHEN program_id 為 `labor_funeral_grant`，THE Program_Rule_Fields SHALL 定義以下規則欄位：required_attributes（json 型別，至少包含 `insurance_type`、`insurance_months`、`death_date`、`relationship_to_deceased`）、eligible_insurance_types（json 型別，值包含 `labor_insurance`）、min_insurance_months（integer 型別）、application_deadline_days（integer 型別）、deadline_starts_from（text 型別）、min_amount（integer 型別）、max_amount（integer 型別）、amount_conditions（json 型別，定義依投保薪資級距或月數計算的金額條件）。
3. WHEN program_id 為 `national_pension_funeral_grant`，THE Program_Rule_Fields SHALL 定義以下規則欄位：required_attributes（json 型別，至少包含 `insurance_type`、`insurance_months`、`death_date`、`relationship_to_deceased`）、eligible_insurance_types（json 型別，值包含 `national_pension`）、application_deadline_days（integer 型別）、deadline_starts_from（text 型別）、min_amount（integer 型別）、max_amount（integer 型別）。
4. WHEN program_id 為 `labor_survivor_pension`，THE Program_Rule_Fields SHALL 定義以下規則欄位：required_attributes（json 型別，至少包含 `insurance_type`、`insurance_months`、`death_date`、`relationship_to_deceased`、`applicant_age`）、eligible_insurance_types（json 型別，值包含 `labor_insurance`）、eligible_relationships（json 型別，定義可申請的親屬關係清單）、application_deadline_days（integer 型別）、deadline_starts_from（text 型別）。
5. WHEN program_id 為 `national_pension_survivor_pension`，THE Program_Rule_Fields SHALL 定義以下規則欄位：required_attributes（json 型別，至少包含 `insurance_type`、`insurance_months`、`death_date`、`relationship_to_deceased`、`applicant_age`）、eligible_insurance_types（json 型別，值包含 `national_pension`）、eligible_relationships（json 型別，定義可申請的親屬關係清單）、application_deadline_days（integer 型別）、deadline_starts_from（text 型別）。
6. WHEN program_id 為 `nhi_status_change`，THE Program_Rule_Fields SHALL 定義以下規則欄位：required_attributes（json 型別，至少包含 `death_date`、`applicant_nhi_dependent_status`）、application_deadline_days（integer 型別）、deadline_starts_from（text 型別）。
7. THE Program_Rule_Fields 中每筆記錄 SHALL 包含非空白的 source_excerpt 欄位，引用該規則所依據的官方文件原文片段（至少 10 個字元），以確保規則資料具備 Provenance。
8. THE Program_Rule_Fields 中每筆記錄的 review_status SHALL 初始設為 `pending`，待人工確認後才可更新為 `verified`。
9. THE Program_Rule_Fields 中 field_type 欄位 SHALL 僅使用 `program_rule_fields` 資料表定義的合法值之一：text、integer、number、boolean、json、date。
10. THE 規則欄位 schema SHALL 定義通用的欄位模式（field patterns），包含但不限於：required_attributes、eligible_insurance_types、min_insurance_months、eligible_relationships、application_deadline_days、deadline_starts_from、min_amount、max_amount、amount_conditions、requires_city_registration、eligible_remains_types。其他方案（非核心 6 項）的具體 rule_fields 資料透過 LLM_Extraction_Pipeline 提取並經人工審查後填入。

### 需求 4：官方來源文件證據

**User Story:** 身為審查人員，我需要每項 MVP 福利都有對應的官方來源文件 metadata 與證據連結，以便追溯規則的依據並確認資料正確性。

#### 驗收條件

1. THE Source_Document 資料表 SHALL 至少包含 6 筆記錄，分別對應 6 項 MVP 福利步驟的主要官方法規或說明頁面，每筆記錄的 canonical_url 須為 HTTPS 臺灣政府網域（.gov.tw）。
2. THE Source_Document 記錄 SHALL 填入 title（繁體中文文件標題）、document_type（benefit_page 或 legal_text）、jurisdiction_code（TW）、publisher_name（發布機關名稱），且 review_status 初始設為 `candidate`。
3. THE Evidence_Link 資料表 SHALL 為每項 MVP 福利至少建立 1 筆 `program_sources` 記錄，連結該福利的 program_id 與對應 Source_Document 的 document_id，evidence_role 設為 `eligibility` 或 `legal_basis`。
4. THE Evidence_Link 記錄 SHALL 包含非空白的 source_excerpt（至少 10 個字元），引用來源文件中與該福利資格條件相關的原文片段。
5. IF 某項 MVP 福利的 Evidence_Link 尚未建立或 source_excerpt 為空白，THEN THE Benefit_Catalog SHALL 不允許該福利的 program_status 更新為 `verified`（由既有 CHECK 約束保證）。

### 需求 5：規則驗證腳本

**User Story:** 身為開發者，我需要一個驗證腳本來檢查所有已填入的 program_rule_fields 資料是否完整、格式正確且與 benefit_programs 記錄一致，以便在資料填入後快速發現錯誤。

#### 驗收條件

1. THE Validate_Rules_Script SHALL 存放於 `scripts/validate_rules.py`，可透過 `python3 scripts/validate_rules.py` 執行，不需額外命令列參數即可使用預設資料庫路徑（`data/local/government_oid.db`）。
2. WHEN 執行驗證時，THE Validate_Rules_Script SHALL 檢查以下條件：（a）每個在 `benefit_programs` 中 program_status 為 `under_review` 或 `verified` 的 program_id，在 `program_rule_fields` 中至少有 1 筆記錄；（b）每筆 program_rule_fields 的 field_type 為合法值；（c）field_type 為 json 的欄位其 field_value 可被 `json.loads()` 正確解析；（d）field_type 為 integer 的欄位其 field_value 可被 `int()` 正確轉換。
3. WHEN 執行驗證時，THE Validate_Rules_Script SHALL 檢查每筆 program_rule_fields 的 source_excerpt 是否為非空白字串（長度至少 10 個字元）；若為空白或長度不足，SHALL 標記為警告（warning）。
4. WHEN 驗證完成，THE Validate_Rules_Script SHALL 輸出摘要報告，包含：檢查的 program 數量、通過驗證的 program 數量、有警告的 program 數量、有錯誤的 program 數量，以及每個錯誤或警告的具體 program_id、field_name 與問題描述。
5. IF 驗證發現任何錯誤（非警告），THEN THE Validate_Rules_Script SHALL 以非零 exit code 結束執行，以便 CI 環境偵測失敗。
6. IF 驗證未發現任何錯誤，THEN THE Validate_Rules_Script SHALL 以 exit code 0 結束執行，並輸出「所有規則驗證通過」的成功訊息。

### 需求 6：評測案例

**User Story:** 身為測試人員，我需要結構化的測試案例來驗證 Rule_Engine 對 6 項 MVP 福利的資格判斷是否正確，涵蓋正常、邊界與不符合資格的情境。

#### 驗收條件

1. THE Evaluation_Case 集合 SHALL 以 JSON 檔案存放於 `data/evaluations/mvp_eligibility.v0.1.json`，且符合 JSON 語法規範。
2. THE Evaluation_Case 集合 SHALL 包含至少 18 筆測試案例，涵蓋 6 項 MVP 福利步驟各自至少 3 種情境：正常符合資格（eligible）、邊界條件（如剛好在期限內或期限當天）、不符合資格（ineligible）。
3. THE Evaluation_Case 中每筆案例 SHALL 包含以下欄位：case_id（唯一字串識別碼）、title（繁體中文案例名稱）、program_id（對應的福利 program_id）、user_attributes（模擬使用者的 Eligibility_Attributes 字典）、expected_status（eligible、ineligible、needs_information 之一）、expected_reasons（預期回傳的原因清單，可為空陣列）。
4. THE Evaluation_Case 集合 SHALL 包含至少 2 筆 needs_information 情境的案例，模擬使用者尚未提供必要屬性（如缺少 insurance_type 或 insurance_months），且 expected_missing_inputs 欄位列出預期的缺漏欄位名稱。
5. THE Evaluation_Case 集合 SHALL 包含至少 4 筆測試案例覆蓋 Insurance_Type 分支：勞保喪葬給付、國保喪葬給付、勞保遺屬年金、國保遺屬年金各至少 1 筆，驗證 Rule_Engine 依投保身分正確區分適用方案。
6. THE Evaluation_Case 集合 SHALL 包含 schema_version 欄位與 notes 陣列（說明案例用途與限制），格式與 `data/evaluations/death_benefit_discovery.v0.2.json` 一致。

### 需求 7：Rule Engine 擴充

**User Story:** 身為 Rule_Engine，我需要支援依使用者投保身分（勞保或國保）、投保月數與親屬關係判斷是否適用特定福利，以便正確區分勞保與國保的喪葬給付及遺屬年金。

#### 驗收條件

1. WHEN program_rule_fields 包含 `eligible_insurance_types` 欄位（json 型別，值為保險類型字串陣列），THE Rule_Engine SHALL 檢查使用者的 `insurance_type` 屬性是否在該陣列中；若不在陣列中，SHALL 回傳 status 為 `ineligible` 且 reasons 包含說明投保身分不符的中文訊息。
2. IF 使用者未提供 `insurance_type` 屬性且該福利定義了 `eligible_insurance_types` 欄位，THEN THE Rule_Engine SHALL 回傳 status 為 `needs_information` 且 missing_inputs 包含 `insurance_type`。
3. WHEN program_rule_fields 包含 `min_insurance_months` 欄位（integer 型別），THE Rule_Engine SHALL 檢查使用者的 `insurance_months` 屬性是否大於或等於該值；若不足，SHALL 回傳 status 為 `ineligible` 且 reasons 包含說明投保月數不足的中文訊息。
4. IF 使用者未提供 `insurance_months` 屬性且該福利定義了 `min_insurance_months` 欄位，THEN THE Rule_Engine SHALL 回傳 status 為 `needs_information` 且 missing_inputs 包含 `insurance_months`。
5. WHEN program_rule_fields 包含 `eligible_relationships` 欄位（json 型別，值為親屬關係字串陣列），THE Rule_Engine SHALL 檢查使用者的 `relationship_to_deceased` 屬性是否在該陣列中；若不在陣列中，SHALL 回傳 status 為 `ineligible` 且 reasons 包含說明申請人與亡者關係不符的中文訊息。
6. THE Rule_Engine 的新增檢查邏輯 SHALL 與既有檢查（城市設籍、骨灰類型、環保葬、期限等）以相同模式整合，遵循「先檢查是否缺少輸入、再判斷是否符合條件」的順序。

### 需求 8：資料種子腳本

**User Story:** 身為開發者，我需要一個可重複執行的腳本，能將 MVP 的福利方案、規則欄位、來源證據與 Graph 節點/邊填入本機 SQLite，以便團隊成員能從零重建完整的 MVP 資料環境。

#### 驗收條件

1. THE 資料填入機制 SHALL 以結構化 JSON 種子檔案存放於 `data/benefits/` 目錄下，與程式碼分離，每項 MVP 福利對應一個 JSON 檔案或集中於一個檔案。
2. THE 資料填入機制 SHALL 提供一個腳本（建議為 `scripts/load_mvp_benefits.py`），讀取種子檔案並將資料寫入 `benefit_programs`、`program_rule_fields`、`source_documents`、`program_sources`、`graph_nodes`、`graph_edges` 資料表。
3. WHEN 腳本重複執行時，THE 資料填入腳本 SHALL 採用 INSERT OR REPLACE 或等效的冪等策略，不產生重複記錄，且既有手動更新的 review_status 或 program_status 不被覆寫。
4. WHEN 腳本執行完成，THE 資料填入腳本 SHALL 輸出摘要：新增的 benefit_programs 數量、新增的 program_rule_fields 數量、新增的 source_documents 數量、新增的 program_sources 數量、新增的 graph_nodes 數量、新增的 graph_edges 數量。
5. THE 種子檔案中每項福利的規則欄位 SHALL 包含 source_excerpt，引用官方文件原文；source_excerpt 不得為佔位符號或虛構內容。
6. IF 種子檔案中任一必要欄位（program_id、canonical_name、field_name、field_type）缺失或為空白，THEN THE 資料填入腳本 SHALL 拒絕該筆記錄並輸出錯誤訊息，不中斷其餘記錄的處理。
7. THE 種子檔案 SHALL 包含配偶死亡情境的完整 graph_nodes 與 graph_edges 定義（如需求 2 驗收條件 10-12 所述），確保執行一次腳本即可建立完整的 MVP 圖資料。

### 需求 9：Graph 查詢與展開邏輯

**User Story:** 身為 orchestration 模組，我需要一套 Graph 查詢 API，能從人生事件節點出發逐層展開關聯的保險體系與福利方案，支援條件式過濾與排序，以便動態產生候選福利清單。

#### 驗收條件

1. THE Graph 查詢模組 SHALL 提供 `expand_from_event(event_id, user_attributes)` 函式，接受人生事件 node_id 與使用者屬性字典，回傳該事件觸發的所有 benefit_program 節點清單（經條件式過濾後）。
2. WHEN 展開流程執行時，THE Graph 查詢模組 SHALL 依以下順序遍歷：（a）從 life_event 節點出發，找到所有 edge_type 為 `triggers` 的目標節點（insurance_system 或 agency）；（b）對每個目標節點，找到所有 edge_type 為 `belongs_to` 的 benefit_program 節點；（c）回傳完整的 benefit_program 清單。
3. WHEN 遍歷 triggers 類型的邊時，IF 邊的 condition_json 非 NULL 且使用者已提供該 attribute，THE Graph 查詢模組 SHALL 僅遍歷 condition 匹配的邊；IF 使用者尚未提供該 attribute，SHALL 遍歷所有 triggers 邊（保守策略，不遺漏潛在適用方案）。
4. THE Graph 查詢模組 SHALL 提供 `get_prerequisites(program_node_id)` 函式，回傳該 benefit_program 的所有 edge_type 為 `requires` 的前置 document_requirement 節點，以供 orchestration 判斷申請順序。
5. THE Graph 查詢模組 SHALL 提供 `get_produces(program_node_id)` 函式，回傳該 benefit_program 完成後產出的所有 edge_type 為 `produces` 的 document_requirement 節點。
6. THE Graph 查詢模組 SHALL 依 graph_edges 的 order 欄位排序回傳結果，確保展開順序穩定且可預測。
7. THE Graph 查詢模組 SHALL 支援反向查詢：給定任一 insurance_system 節點，能查詢所有 belongs_to 該系統的 benefit_program，不限於特定人生事件。

### 需求 10：未審查方案呈現規則

**User Story:** 身為使用者，我希望看到系統已發現但尚未完成二次驗證的福利方案，並清楚知道其審查狀態，以便不遺漏可能相關的福利，同時了解資訊可能不完整。

#### 驗收條件

1. WHEN benefit_programs 中某方案的 program_status 為 `candidate` 或 `under_review`，THE 系統 SHALL 將該方案納入查詢結果中呈現給使用者，不因未驗證而完全隱藏。
2. WHEN 呈現 program_status 為 `candidate` 或 `under_review` 的方案時，THE 系統 SHALL 於結果中附加明確的免責標記文字「尚未二次確認」，使用者可辨識該方案的審查狀態。
3. WHEN program_status 為 `candidate` 或 `under_review` 時，THE Rule_Engine SHALL 不對該方案執行完整的資格判斷邏輯，而是回傳 status 為 `needs_human_review` 且 reasons 包含「可能相關，建議洽詢承辦機關」的中文提示。
4. WHEN program_status 為 `verified` 時，THE Rule_Engine SHALL 對該方案執行完整的資格判斷邏輯（檢查 insurance_type、insurance_months、relationships、deadline 等所有規則欄位）。
5. THE 系統 SHALL 在排序結果時將 `verified` 方案排在 `candidate` 與 `under_review` 方案之前，確保已驗證的資訊優先呈現。
6. IF 某方案由 `candidate` 或 `under_review` 更新為 `verified`，THEN THE Rule_Engine SHALL 自動對該方案啟用完整資格判斷，不需額外設定。

### 需求 11：來源監控與變更偵測

**User Story:** 身為資料維護者，我需要偵測官方來源文件的內容是否已變更，以便及時標記需要人工重新審查的規則欄位，確保系統中的資格規則與現行法規一致。

#### 驗收條件

1. THE Source_Monitor_Script SHALL 存放於 `scripts/monitor_source_changes.py`，可透過 `python3 scripts/monitor_source_changes.py` 執行，不需互動式輸入（cron-friendly）。
2. WHEN 執行時，THE Source_Monitor_Script SHALL 重新抓取所有 `source_documents` 中 review_status 為 `verified` 或 `candidate` 的文件的 canonical_url 內容。
3. WHEN 抓取完成後，THE Source_Monitor_Script SHALL 計算新內容的 content_hash 並與 `source_documents.current_content_hash` 比較；IF hash 不同，SHALL 更新 `last_changed_at` 為當前時間戳、將 `review_status` 更新為 `stale`、並記錄變更事件至日誌。
4. WHEN 執行完成，THE Source_Monitor_Script SHALL 輸出變更報告，列出所有偵測到內容變更的文件的 document_id、title 與 canonical_url。
5. THE Source_Monitor_Script SHALL 不自動更新 program_rule_fields — 來源變更僅標記文件為 `stale`，實際規則更新需人工審查。
6. THE Source_Monitor_Script SHALL 將每次執行結果記錄至 `source_sync_runs` 資料表，包含 started_at、completed_at、status、changed_document_count，以建立稽核軌跡。
7. IF 執行過程中遇到網路錯誤或 HTTP 非 200 回應，THEN THE Source_Monitor_Script SHALL 記錄該文件的錯誤訊息但繼續處理其餘文件，最終以非零 exit code 結束（若有任何錯誤）。
8. THE Source_Monitor_Script SHALL 支援 `--dry-run` 參數，僅輸出將會檢查的文件清單而不實際抓取，方便測試。

### 需求 12：多層提取管線（含結構性發現與附件）

**User Story:** 身為資料擴充人員，我需要使用多層提取管線，從 source_registry 中已登記的公部門機關官網出發，系統性爬取其網站結構以發現所有福利相關頁面，再從這些頁面與其附件（PDF、Word、ODS 等）自動提取結構化福利候選資料，以實現 Coverage_Guarantee（不遺漏任何已登記機關的福利資源），同時確保所有提取結果都經過人工審查才正式納入。

#### 驗收條件

1. THE Benefit_Catalog SHALL 包含 `document_attachments` 資料表，schema 為：attachment_id（TEXT PRIMARY KEY）、document_id（TEXT NOT NULL，外鍵參照 source_documents）、filename（TEXT NOT NULL）、file_type（TEXT NOT NULL，CHECK 約束限制為 `pdf`、`docx`、`odt`、`xlsx`、`other`）、download_url（TEXT NOT NULL）、storage_ref（TEXT）、content_hash（TEXT）、extracted_text_available（INTEGER NOT NULL DEFAULT 0）、extraction_method（TEXT）、extracted_at（TEXT）、created_at（TEXT NOT NULL）。
2. THE LLM_Extraction_Pipeline SHALL 實作以下六層提取流程：Layer 0（Structural_Crawl — 結構性發現）從 source_registry 中每個已登記機關的官方網站入口頁出發，依網站結構（如福利專區、申辦服務、最新公告等導覽連結）逐層發現子頁面，將所有發現的 URL 記錄至 `source_documents` 資料表，不依賴搜尋引擎或關鍵字搜尋；Layer 1（頁面分類）AI 對 Layer 0 發現的每個 URL 進行分類判斷：該頁面是否為福利方案頁面（yes/no/maybe），僅將分類為 yes 或 maybe 的頁面送入後續提取層；Layer 2（附件偵測與下載）掃描已分類頁面中的 .pdf/.doc/.docx/.odt/.xlsx 連結，下載至 `data/local/attachments/` 目錄，並將 metadata 記錄至 `document_attachments` 資料表；Layer 3（附件文本提取）使用 pdfplumber（PDF）或 python-docx（Word）提取附件文字內容，並更新 extracted_text_available 為 1；Layer 4（LLM 完整分析）結合 HTML 內容與附件文本，透過 Amazon Bedrock LLM 產生完整的結構化候選，提取 rule_fields；Layer 5（人工審查）所有候選以 `candidate` 狀態等待人工 approve/reject/modify。
3. THE LLM_Extraction_Pipeline SHALL 為每筆候選標記 Extraction_Confidence 等級：`partial`（僅 HTML，頁面指出有附件但尚未處理）、`high_from_html`（僅 HTML，頁面內容看起來完整）、`high_from_full`（HTML + 所有附件已提取並分析）、`partial_ocr_needed`（附件為掃描圖檔，需 OCR 但目前不支援）。
4. THE LLM_Extraction_Pipeline SHALL 提供一個腳本（建議為 `scripts/extract_benefit_candidates.py`），支援以下模式：單文件模式（指定 document_id）與批次模式（`--batch` 參數，處理所有尚未提取的 source_documents）。
5. WHEN Layer 1 分類一份來源頁面時，THE LLM_Extraction_Pipeline SHALL 使用 LLM 判斷該頁面是否描述一項福利或補助方案（分類為 yes/no/maybe）；WHEN 分類為 yes 或 maybe 且進入 Layer 4 時，SHALL 提取以下結構化欄位：canonical_name、support_purpose、program_basis、delivery_form、eligibility_text、amount_text、deadline_text、required_documents、accepting_agency。
6. THE LLM_Extraction_Pipeline 的提取結果 SHALL 一律設定 review_status 為 `candidate`，存放於 `data/benefit_discovery/` 目錄，永遠不自動插入為 `verified` 狀態的資料。
7. THE LLM_Extraction_Pipeline SHALL 使用 Amazon Bedrock 模型（hackathon 技術需求），模型呼叫透過 boto3 bedrock-runtime client 執行。
8. THE LLM_Extraction_Pipeline 的提取 prompt 與輸出 schema SHALL 存放於可審查的檔案中（建議 `data/extraction_prompts/benefit_extraction.prompt.md` 與 `data/extraction_prompts/benefit_schema.json`），不得硬編碼於 Python 程式碼中。
9. IF LLM 回應無法解析為有效的候選 JSON 格式，THEN THE LLM_Extraction_Pipeline SHALL 記錄該文件的解析錯誤並繼續處理其餘文件，不中斷批次流程。
10. IF 附件下載失敗或文本提取失敗，THEN THE LLM_Extraction_Pipeline SHALL 記錄錯誤、將 extraction_confidence 設為 `partial`、並繼續以 HTML 內容進行 Layer 4 分析，不中斷整體流程。
11. THE Structural_Crawl（Layer 0）SHALL 以 source_registry 中已登記的公部門機關清單為爬取範圍的母體，該機關清單源自 OID registry；Structural_Crawl 的角色僅為發現頁面 URL，AI 的角色僅在後續 Layer 1 進行分類與過濾，不用於「搜尋」或「找到」來源頁面。
12. THE Structural_Crawl SHALL 從每個機關的官方網站入口頁出發，依網站結構（如福利專區、申辦服務、最新公告等導覽連結）逐層發現子頁面，而非以關鍵字搜尋方式找頁面；發現的所有 URL SHALL 記錄至 `source_documents` 資料表並標記 review_status 為 `candidate`，等待 Layer 1 分類。
13. THE Structural_Crawl SHALL 支援三種觸發模式：（a）On-demand — 當系統查詢某主題相關機關時，發現 crawl_status 為 `pending_crawl` 的機關，立即觸發該機關的爬取；（b）Scheduled — 依 check_frequency 定期檢查所有到期需重爬的機關；（c）Manual — 維護者指定特定機關強制重爬，不受 check_frequency 或 last_crawled_at 限制。
14. THE Structural_Crawl 腳本 SHALL 支援以下命令列介面：`--topic <event_id>`（On-demand 模式，爬取所有 domain_tags 包含該主題但 crawl_status 為 pending_crawl 的機關）、`--scheduled`（Scheduled 模式，爬取所有到期需重爬的機關）、`--source-id <source_id>`（Manual 模式，強制重爬指定機關）。
15. WHEN Layer 4（LLM 完整分析）產出結構化候選時，THE LLM_Extraction_Pipeline SHALL 同時為該 source_document 標記 domain_tags（JSON 字串陣列），記錄該文件實際涉及的業務領域（可能與機關的 domain_tags 不同或更精確）；`source_documents` 資料表 SHALL 新增 `domain_tags` 欄位（TEXT 型別，預設值為 `'[]'`），支援文件層級的多標籤查詢。

### 需求 13：資料擷取策略與來源優先序

**User Story:** 身為資料維護者，我需要明確的系統性來源發現策略與重新爬取頻率設定，以 OID registry 中已登記的完整公部門機關清單為母體，保證窮舉式發現所有機關的福利頁面（Coverage_Guarantee），並在資源有限的情況下以適當頻率重新爬取各機關官網以發現新增頁面。

#### 驗收條件

1. THE `source_registry` 資料表 SHALL 新增 `check_frequency` 欄位（TEXT 型別），合法值為 `daily`、`weekly`、`monthly`、`manual`，預設值為 `manual`；此欄位定義多久重新爬取該機關官網以發現新頁面。
2. THE 系統 SHALL 以 OID registry 中已登記的公部門機關清單為搜尋範圍的母體，不依賴外部搜尋引擎或 SEO 排名來發現來源；source_registry 中的每筆機關記錄源自 OID registry 的完整機關清單。
3. THE Structural_Crawl SHALL 從每個機關的官方網站入口頁出發，依網站結構（如福利專區、申辦服務、最新公告等導覽連結）逐層發現子頁面，而非以關鍵字搜尋方式找頁面。
4. THE 來源發現完整流程 SHALL 遵循以下順序：（a）OID registry 提供完整公部門機關清單；（b）機關清單匯入 source_registry；（c）Structural_Crawl 從每個機關的官方網站入口頁爬取福利/服務相關區塊；（d）所有發現的 URL 記錄至 source_documents；（e）AI（Layer 1）分類哪些頁面為福利方案頁面；（f）人工審核確認。
5. THE 來源重新爬取頻率策略 SHALL 定義以下分級：Priority 1（daily）為中央政府福利索引（如我的E政府、勞動部、衛福部主要入口頁）；Priority 2（weekly）為直轄市/縣市政府福利頁面；Priority 3（monthly）為特定機關方案頁面。check_frequency 決定多久重新爬取該機關官網以發現新增或異動的頁面。
6. WHEN Source_Monitor_Script 執行時，THE 腳本 SHALL 依據 `check_frequency` 欄位判斷是否需要重新爬取：僅爬取上次檢查時間早於其頻率間隔的機關官網（例如 daily 來源需 last_seen_at 超過 24 小時才重新爬取）。
7. THE MVP 階段所有來源的 check_frequency SHALL 初始設為 `manual`，表示不會自動排程爬取；check_frequency 欄位為未來自動化排程預留。
8. THE 系統 SHALL 保證 Coverage_Guarantee：OID registry 中每個已登記的公部門機關最終都應有其福利頁面被索引（indexed）；未爬取的機關應被追蹤為「pending_crawl」狀態。
9. WHEN 新增機關至 source_registry 時，THE 資料維護者 SHALL 設定適當的 check_frequency 值，依據機關的重要性與福利頁面更新頻率選擇分級。


### 需求 14：來源機關業務標籤與分階段匯入

**User Story:** 身為資料維護者，我需要從 OID registry 的完整機關清單中，依業務相關性分批篩選並匯入 source_registry，且每個機關標注其相關業務領域，以便在探索新人生事件主題時能快速找到應爬取的機關清單。

#### 驗收條件

1. THE source_registry 資料表 SHALL 新增 `domain_tags` 欄位（TEXT 型別，儲存 JSON 字串陣列），記錄該機關相關的業務領域標籤；合法標籤值至少包含 `death`、`unemployment`、`retirement`、`birth`、`childcare`、`disability`、`poverty`、`housing`、`medical`、`education`、`long_term_care`。
2. WHEN 查詢某人生事件主題相關的機關時，THE 系統 SHALL 支援以 domain_tags 過濾 source_registry，回傳所有業務領域包含該主題標籤的機關清單（例如查詢 `death` 標籤即可取得勞保局、國保局、健保署、戶政司等所有跟死亡事件相關的機關）。
3. THE 系統 SHALL 提供 OID 篩選腳本（建議為 `scripts/filter_oid_for_benefits.py`），從 OID registry 的 ~8000 個機關中，依據機關層級（中央二級機關、直轄市/縣市一級機關）與業務屬性關鍵字（社會、勞動、衛生、民政、教育等）自動篩選出福利相關候選機關，產出待審核清單。
4. THE OID 篩選腳本產出的候選清單 SHALL 以 JSON 格式儲存（建議路徑 `data/source_registry/oid_candidates.json`），每筆候選包含 oid、organization_name、suggested_domain_tags（腳本依業務屬性建議的標籤）、review_status（`pending`），待人工確認後才匯入 source_registry。
5. THE 分階段匯入策略 SHALL 定義以下優先序：Priority 1（MVP 核心，手動列入 ~10-15 個機關：勞保局、健保署、戶政司、衛福部社家署等）→ Priority 2（中央福利主管機關與執行機關 ~30 個）→ Priority 3（直轄市/縣市社會局/處 ~22 個）→ Priority 4（區公所/鄉鎮市公所等基層窗口，依需求逐步新增）。
6. THE MVP 階段 SHALL 僅需手動列入 10-15 個核心機關至 source_registry（含 domain_tags），不需執行完整的 OID 自動篩選流程；OID 篩選腳本為後續擴充階段使用。
7. WHEN 新增人生事件至 Entitlement Graph 時，THE 資料維護者 SHALL 能透過 `SELECT source_id, name, entry_url FROM source_registry WHERE domain_tags LIKE ?` 查詢已登記且標記該業務領域的機關清單，以此決定 Structural Crawl 的爬取範圍。
