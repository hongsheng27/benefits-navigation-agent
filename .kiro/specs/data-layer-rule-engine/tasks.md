# 實作計畫：資料層與規則引擎補齊

## 概述

本計畫將「資料層與規則引擎補齊」功能拆分為七個階段，依相依性順序實作：Schema 基礎建設 → Graph 查詢模組 → Rule Engine 擴充 → MVP 資料種子 → 驗證與測試 → 提取管線 → 來源管理。所有功能在本機 SQLite 執行，不依賴 AWS 服務。

## Tasks

- [ ] 1. Schema 與基礎建設
  - [ ] 1.1 建立 graph_nodes 與 graph_edges 資料表
    - 在資料庫初始化腳本中新增 `graph_nodes` 資料表（含 node_id, node_type, display_name, metadata_json, created_at, updated_at）
    - 新增 `graph_edges` 資料表（含 from_node_id, to_node_id, edge_type, condition_json, order, metadata_json, created_at）
    - 建立 CHECK 約束：node_type 限制為 life_event/insurance_system/benefit_program/agency/document_requirement
    - 建立 CHECK 約束：edge_type 限制為 triggers/belongs_to/requires/produces/administered_by
    - 建立外鍵約束 ON DELETE RESTRICT
    - 建立索引：idx_graph_nodes_type、idx_graph_edges_from、idx_graph_edges_to、idx_graph_edges_type
    - _Requirements: 1.1, 1.2, 1.5, 1.7_

  - [ ] 1.2 建立 document_attachments 資料表
    - 新增 `document_attachments` 資料表（含 attachment_id, document_id, filename, file_type, download_url, storage_ref, content_hash, extracted_text_available, extraction_method, extracted_at, created_at）
    - 建立 CHECK 約束：file_type 限制為 pdf/docx/odt/xlsx/other
    - 建立外鍵約束參照 source_documents
    - 建立索引：idx_document_attachments_document
    - _Requirements: 12.1_

  - [ ] 1.3 擴充 source_registry 資料表欄位
    - 新增 `check_frequency` 欄位（TEXT, DEFAULT 'manual', CHECK 約束 daily/weekly/monthly/manual）
    - 新增 `crawl_status` 欄位（TEXT, DEFAULT 'pending_crawl', CHECK 約束 pending_crawl/crawled/error）
    - 新增 `last_crawled_at` 欄位（TEXT, 可為 NULL）
    - 新增 `entry_url` 欄位（TEXT, 可為 NULL — 機關官網首頁 URL）
    - 新增 `domain_tags` 欄位（TEXT, DEFAULT '[]' — JSON 字串陣列）
    - _Requirements: 13.1, 13.7, 14.1_

  - [ ] 1.4 擴充 source_documents 資料表欄位
    - 新增 `domain_tags` 欄位（TEXT, DEFAULT '[]' — JSON 字串陣列，記錄文件層級業務領域標籤）
    - _Requirements: 12.15_

- [ ] 2. Graph 查詢模組
  - [ ] 2.1 實作 entitlement_graph.py 核心資料模型與 expand_from_event
    - 建立 `backend/app/services/entitlement_graph.py`
    - 定義 GraphNode 與 GraphEdge dataclass（frozen=True）
    - 實作 `expand_from_event(connection, event_id, user_attributes)` 函式
    - 實作條件式邊遍歷邏輯：condition_json 為 NULL → 通過；使用者未提供屬性 → 通過（保守策略）；值匹配 → 通過；不匹配 → 跳過
    - 依 order 欄位排序回傳結果
    - _Requirements: 9.1, 9.2, 9.3, 9.6_

  - [ ] 2.2 實作 get_prerequisites、get_produces、get_programs_by_system
    - 實作 `get_prerequisites(connection, program_node_id)` — 查詢 requires 邊
    - 實作 `get_produces(connection, program_node_id)` — 查詢 produces 邊
    - 實作 `get_programs_by_system(connection, system_node_id)` — 反向查詢 belongs_to 邊
    - 所有函式依 order 排序回傳
    - _Requirements: 9.4, 9.5, 9.7_

  - [ ]* 2.3 撰寫 Property Test：條件式邊遍歷正確性（Property 1）
    - **Property 1: 條件式邊遍歷正確性**
    - 使用 Hypothesis 驗證：任何 condition_json 與 user_attributes 組合，expand_from_event 的遍歷決策正確
    - **Validates: Requirements 1.4, 9.1, 9.2, 9.3**

  - [ ]* 2.4 撰寫 Property Test：圖展開結果排序穩定性（Property 2）
    - **Property 2: 圖展開結果排序穩定性**
    - 使用 Hypothesis 驗證：相同輸入的 expand_from_event 產出相同順序的結果
    - **Validates: Requirements 9.6**

  - [ ]* 2.5 撰寫 Property Test：前置需求與產出查詢完整性（Property 3）
    - **Property 3: 前置需求與產出查詢完整性**
    - 使用 Hypothesis 驗證：get_prerequisites/get_produces 回傳結果精確匹配圖中對應邊
    - **Validates: Requirements 9.4, 9.5**

- [ ] 3. Rule Engine 擴充
  - [ ] 3.1 新增 insurance_type、min_insurance_months、eligible_relationships 檢查
    - 修改 `backend/app/rules/engine.py` 的 `evaluate_program()` 函式
    - 新增步驟 2a：檢查 eligible_insurance_types（json 陣列比對）
    - 新增步驟 2b：檢查 min_insurance_months（整數比較）
    - 新增步驟 2c：檢查 eligible_relationships（json 陣列比對）
    - 遵循既有模式「先檢查缺少輸入、再判斷是否符合」
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ] 3.2 新增 program_status 檢查與排序邏輯
    - 修改 `evaluate_all_programs()` 函式
    - candidate/under_review → 回傳 needs_human_review，不執行完整判斷
    - verified → 執行既有完整判斷邏輯
    - 排序：verified 優先（by relevance_score desc），再 unverified（by name）
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ]* 3.3 撰寫 Property Test：投保身分資格判斷（Property 4）
    - **Property 4: 投保身分資格判斷**
    - 使用 Hypothesis 驗證：任何 insurance_type 與 eligible_list 組合的判斷結果正確
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 3.4 撰寫 Property Test：投保月數資格判斷（Property 5）
    - **Property 5: 投保月數資格判斷**
    - 使用 Hypothesis 驗證：任何 insurance_months 與 min_insurance_months 組合的判斷結果正確
    - **Validates: Requirements 7.3, 7.4**

  - [ ]* 3.5 撰寫 Property Test：親屬關係資格判斷（Property 6）
    - **Property 6: 親屬關係資格判斷**
    - 使用 Hypothesis 驗證：任何 relationship 與 eligible_relationships 組合的判斷結果正確
    - **Validates: Requirements 7.5**

  - [ ]* 3.6 撰寫 Property Test：未審查方案處理（Property 7）
    - **Property 7: 未審查方案不進行完整資格判斷**
    - 使用 Hypothesis 驗證：candidate/under_review 方案一律回傳 needs_human_review
    - **Validates: Requirements 10.1, 10.2, 10.3**

  - [ ]* 3.7 撰寫 Property Test：已驗證方案排序優先（Property 8）
    - **Property 8: 已驗證方案排序優先**
    - 使用 Hypothesis 驗證：混合結果中 verified 方案永遠排在 unverified 之前
    - **Validates: Requirements 10.4, 10.5**

- [ ] 4. Checkpoint - 確認所有測試通過
  - 確認所有測試通過，若有問題請向使用者詢問。

- [ ] 5. MVP 資料種子
  - [ ] 5.1 建立 MVP 種子 JSON 檔案
    - 建立 `data/benefits/mvp_programs.v0.1.json`
    - 包含 6 項核心福利的 benefit_programs 資料（canonical_name, summary, support_purpose, program_basis, delivery_form, jurisdiction_code）
    - 包含每項福利的 program_rule_fields（含真實 source_excerpt）
    - 包含配偶死亡情境的 graph_nodes（12 個節點）
    - 包含配偶死亡情境的 graph_edges（13 條邊，含 condition_json）
    - 包含來源文件與證據連結資料
    - _Requirements: 2.1-2.12, 3.1-3.10, 4.1-4.5, 8.1, 8.5, 8.7_

  - [ ] 5.2 實作 load_mvp_benefits.py 種子載入腳本
    - 建立 `scripts/load_mvp_benefits.py`
    - 實作 INSERT OR IGNORE 冪等策略（不覆寫手動更新的 review_status/program_status）
    - 載入 benefit_programs、program_rule_fields、source_documents、program_sources、graph_nodes、graph_edges
    - 驗證必要欄位非空：program_id、canonical_name、field_name、field_type
    - 拒絕無效記錄並輸出錯誤訊息，不中斷其餘處理
    - 執行完成後輸出摘要統計
    - _Requirements: 8.2, 8.3, 8.4, 8.6_

  - [ ]* 5.3 撰寫 Property Test：種子腳本冪等性（Property 10）
    - **Property 10: 種子腳本冪等性**
    - 使用 Hypothesis 驗證：執行兩次 load 結果與一次相同
    - **Validates: Requirements 8.3**

- [ ] 6. 驗證與評測
  - [ ] 6.1 實作 validate_rules.py 驗證腳本
    - 建立 `scripts/validate_rules.py`
    - 檢查條件：(a) 每個 active program 至少 1 筆 rule_field；(b) field_type 合法；(c) json 可解析；(d) integer 可轉換；(e) source_excerpt 非空且 ≥ 10 字元
    - 輸出摘要報告：program 數量、通過/警告/錯誤數量、每個問題的詳細資訊
    - 錯誤 → 非零 exit code；無錯誤 → exit code 0 + 成功訊息
    - 預設資料庫路徑為 `data/local/government_oid.db`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ] 6.2 建立 MVP 評測案例 JSON
    - 建立 `data/evaluations/mvp_eligibility.v0.1.json`
    - 至少 18 筆案例：6 項福利各 3 種情境（eligible / ineligible / boundary）
    - 至少 2 筆 needs_information 案例（缺少 insurance_type 或 insurance_months）
    - 至少 4 筆 Insurance_Type 分支案例
    - 含 schema_version、notes 欄位
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 6.3 撰寫 Property Test：規則驗證器偵測無效資料（Property 9）
    - **Property 9: 規則驗證器偵測無效資料**
    - 使用 Hypothesis 驗證：field_type=json 但 value 非合法 JSON → 報告 error；field_type=integer 但 value 非整數 → 報告 error
    - **Validates: Requirements 5.2, 3.9**

  - [ ]* 6.4 撰寫整合測試：MVP 評測案例端對端驗證
    - 建立 `backend/tests/integration/test_mvp_eligibility.py`
    - 載入種子資料 → 逐案執行 evaluate_program → 比對 expected_status
    - _Requirements: 6.2, 6.3_

- [ ] 7. Checkpoint - 確認所有測試通過
  - 確認所有測試通過，若有問題請向使用者詢問。

- [ ] 8. 多層提取管線
  - [ ] 8.1 建立提取管線目錄結構與共用模型
    - 建立 `backend/app/extraction/__init__.py`
    - 建立 `backend/app/extraction/models.py`：定義 CrawlReport、AttachmentMeta、ExtractionResult 等 dataclass
    - _Requirements: 12.1, 12.3_

  - [ ] 8.2 實作 Layer 0：Structural Crawler（結構性爬取）
    - 建立 `backend/app/extraction/structural_crawler.py`
    - 實作 StructuralCrawler class（init 含 rate_limit_seconds, max_depth）
    - 實作 crawl_agency(source_id)：從 source_registry 取得 entry_url，逐層跟隨導覽連結
    - 實作 crawl_all_pending()：爬取所有 pending_crawl 或到期機關
    - 實作 _should_recrawl()：依 check_frequency 判斷是否重爬
    - 實作 _discover_navigation_links()：識別福利/服務相關區塊連結
    - 實作 _respect_robots_txt()：遵守 robots.txt 規則
    - 將發現的 URL 記錄至 source_documents（review_status='candidate'）
    - _Requirements: 12.2, 12.11, 12.12, 12.13, 13.3, 13.8_

  - [ ] 8.3 實作 Layer 1：Page Classifier（頁面分類）
    - 建立 `backend/app/extraction/page_classifier.py`
    - 實作 PageClassifier class
    - classify_page(document_id) → 'yes'/'no'/'maybe'
    - classify_batch() → 批次分類所有未分類的 source_documents
    - 使用 mock Bedrock client（Aug 1 前）
    - _Requirements: 12.2, 12.5_

  - [ ] 8.4 實作 Layer 2：Attachment Detector 與 Downloader
    - 建立 `backend/app/extraction/attachment_detector.py`
    - 掃描 HTML 中的 .pdf/.doc/.docx/.odt/.xlsx 連結
    - 下載至 `data/local/attachments/` 目錄
    - 將 metadata 寫入 document_attachments 資料表
    - _Requirements: 12.2, 12.10_

  - [ ] 8.5 實作 Layer 3：Text Extractor（文本提取）
    - 建立 `backend/app/extraction/text_extractor.py`
    - 使用 pdfplumber 處理 PDF
    - 使用 python-docx 處理 Word 文件
    - 更新 extracted_text_available 為 1
    - 失敗時記錄錯誤，設 confidence='partial'
    - _Requirements: 12.2, 12.10_

  - [ ] 8.6 實作 Layer 4：LLM Analyzer（含 mock）
    - 建立 `backend/app/extraction/llm_analyzer.py`
    - 結合 HTML 內容與附件文本，呼叫 Bedrock LLM
    - 產出結構化候選：canonical_name、support_purpose、program_basis、delivery_form、eligibility_text、amount_text、deadline_text、required_documents、accepting_agency
    - 結果一律設 review_status='candidate'
    - 使用 mock Bedrock client（Aug 1 前）
    - 解析失敗時記錄錯誤並繼續
    - 同時為 source_document 標記 domain_tags
    - _Requirements: 12.2, 12.5, 12.6, 12.7, 12.9, 12.15_

  - [ ] 8.7 實作提取管線協調器（pipeline.py）
    - 建立 `backend/app/extraction/pipeline.py`
    - 實作 ExtractionPipeline class（整合 Layer 2→3→4）
    - process_document(document_id) → ExtractionResult
    - process_batch() → 批次處理已分類為 yes/maybe 的文件
    - 標記 Extraction_Confidence 等級
    - _Requirements: 12.3, 12.10_

  - [ ] 8.8 建立提取 prompt 與 schema 檔案
    - 建立 `data/extraction_prompts/benefit_extraction.prompt.md`（分類 + 提取 prompt）
    - 建立 `data/extraction_prompts/benefit_schema.json`（候選 JSON schema）
    - _Requirements: 12.8_

  - [ ] 8.9 實作 extract_benefit_candidates.py CLI 腳本
    - 建立 `scripts/extract_benefit_candidates.py`
    - 支援單文件模式（--document-id）與批次模式（--batch）
    - 支援 Structural Crawl 命令列：--topic、--scheduled、--source-id
    - _Requirements: 12.4, 12.13, 12.14_

- [ ] 9. 來源管理
  - [ ] 9.1 實作 monitor_source_changes.py 來源監控腳本
    - 建立 `scripts/monitor_source_changes.py`
    - 重新抓取 verified/candidate 文件的 canonical_url
    - 計算 content_hash 比對，hash 不同則標記 review_status='stale'
    - 記錄至 source_sync_runs 資料表
    - 輸出變更報告
    - 支援 --dry-run 參數
    - 有任何錯誤 → 非零 exit code
    - 不自動更新 program_rule_fields
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [ ] 9.2 實作 filter_oid_for_benefits.py OID 篩選腳本
    - 建立 `scripts/filter_oid_for_benefits.py`
    - 從 OID registry ~8000 機關中依層級與業務屬性關鍵字篩選福利相關候選
    - 產出 `data/source_registry/oid_candidates.json`（含 oid、organization_name、suggested_domain_tags、review_status）
    - _Requirements: 14.3, 14.4_

  - [ ]* 9.3 撰寫單元測試：Structural Crawler 與來源監控
    - 建立 `backend/tests/unit/test_structural_crawler.py`（mock HTTP）
    - 建立 `backend/tests/unit/test_page_classifier.py`（mock LLM）
    - 建立 `backend/tests/integration/test_source_monitor.py`（mock HTTP）
    - _Requirements: 11.7, 12.11_

- [ ] 10. Final Checkpoint - 確認所有測試通過
  - 確認所有測試通過，若有問題請向使用者詢問。

## Notes

- 標記 `*` 的子任務為選用，可跳過以加速 MVP 開發
- 每個任務引用具體的需求編號，確保可追溯性
- Checkpoint 確保各階段增量驗證
- Property Tests 驗證通用正確性屬性（使用 Hypothesis）
- 所有 AWS 呼叫（Bedrock）使用 mock，不建立真實連線（Aug 1 前）
- 種子檔案中的 source_excerpt 須為真實官方文件引用，不可為虛構內容

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["2.5", "3.3", "3.4", "3.5", "3.6", "3.7"] },
    { "id": 4, "tasks": ["5.1", "8.1"] },
    { "id": 5, "tasks": ["5.2", "8.2", "8.8"] },
    { "id": 6, "tasks": ["5.3", "6.1", "8.3", "8.4"] },
    { "id": 7, "tasks": ["6.2", "8.5", "8.6"] },
    { "id": 8, "tasks": ["6.3", "6.4", "8.7"] },
    { "id": 9, "tasks": ["8.9", "9.1", "9.2"] },
    { "id": 10, "tasks": ["9.3"] }
  ]
}
```
