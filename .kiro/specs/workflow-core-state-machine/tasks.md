# 實作計畫：Workflow Core State Machine（Phase 2, T5–T10）

## 概覽

將設計文件中的六個任務（T5 狀態機轉換、T6 護欄、T7 欄位登記表、T8 缺漏欄位、T9 規則引擎轉接、T10 判定組裝）轉為可執行的實作步驟。

**目前狀態**：`mock_advance.py` 已刪除，`api/sessions.py` 已改為呼叫 `state_machine.advance()`。骨幹（轉換表、守門、自動推進、兩道護欄、欄位登記表、缺漏計算、規則轉接層、接縫 Protocol）都已就位。尚未完成的是：真正的規則引擎接線（T18，見任務 9.1）、端到端整合測試（任務 13.1）、全部 property-based 測試（`hypothesis` 尚未加入依賴），以及 `schemas` ↔ `orchestration` 的循環依賴拆除（任務 16，獨立 PR）。

**語言**：Python（與設計文件一致）

**所有任務皆為「負責人」層級**：核心邏輯由後端負責人實作或密切審查。AI 可協助產生測試骨架與樣板程式碼。

**硬約束**：
- 不引入 AWS 依賴、不安裝 boto3
- 不呼叫 LLM
- Frozen Pydantic state model（ADR-0011）
- 公開 repo，測試不含 PII
- 不鎖定待決策項目（D1–D5）

## 任務列表

- [ ] 1. 建立狀態機轉換引擎（T5）
  - [x] 1.1 建立 `backend/app/orchestration/state_machine.py` 核心模組
    - 定義三張宣告表：`ALLOWED_INPUTS`（每個 WorkflowState → 允許的 input 類型集合）、`ENTRY_GUARDS`（進入狀態前的守門條件）、`NOMINAL_PATH`（正常路徑的下一步）
    - 定義 `InvalidTransitionError`、`UnknownFieldError`、`UnknownItemError` 例外類別
    - 實作 `advance()` 函式：已結束檢查 → 輸入允許清單守門 → `_handle_input()` → `_auto_advance()`
    - 實作 `_handle_input()` 分派邏輯，處理七種 input kind
    - CONFIRM 的條件性跳過由 `ENTRY_GUARDS[WorkflowState.CONFIRM]` 實作，不是獨立的 `should_skip_confirm()` 函式
    - 全程使用 `model_copy(update=...)` 確保 frozen 不變性
    - **偏離設計文件**：沒有 `TransitionResult`，`advance()` 直接回傳 `SessionState`；`question_groups` 由 `api/sessions.py` 的 `_snapshot()` 另外呼叫 `compute_question_groups()` 計算。理由是狀態機的產出就是狀態本身，問題卡是對外快照的一部分而非狀態的一部分
    - **偏離設計文件**：`InvalidFieldValueError` 尚未定義（值的型別與選項驗證屬 Req 16.3 / T11）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 18.1, 18.2_

  - [x] 1.2 實作 `_auto_advance()` 自動推進邏輯
    - RESOLVE_ENTITLEMENTS → COLLECT_MISSING_FIELDS 自動
    - RETRIEVE_RULES → EVALUATE_ELIGIBILITY 自動（Phase 2 跳過真實檢索）
    - EVALUATE_ELIGIBILITY → COLLECT 或 EXPLAIN_RESULT 視項目狀態
    - EXPLAIN_RESULT → CONFIRM 或 COMPLETE 由 `ENTRY_GUARDS` 決定
    - 防遞迴上限實作為 `max_auto_steps = 20`（**非**設計文件寫的 4 步）。設計文件的 4 步是「正常路徑最長多少步」的觀察，不是安全上限；實作用一個明顯寬鬆的數字，只用來擋無限迴圈
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ] 1.3 定義 orchestration 層的 input 類型（取代 schemas import）
    - **與任務 16 重疊，實作時併入任務 16 處理**（避免兩處各做一半）
    - 現況：`orchestration/inputs.py` 不存在。`state_machine.py`、`field_registry.py`、`missing_fields.py` 三個模組仍 `import app.schemas.session`，而 `schemas/session.py` 反向 import `app.orchestration.state`，形成套件級循環。Req 20.2 未達成
    - 在 `backend/app/orchestration/inputs.py` 定義七種 parsed input dataclass
    - `LifeEventTextInput`、`EventConfirmationInput`、`AttributeAnswersInput`、`ReviewConfirmationInput`、`ReferralChoiceInput`、`HelpRequestInput`、`ItemDeclineInput`
    - 確保 state_machine.py 只 import orchestration 內部模組，不 import schemas/
    - _Requirements: 20.2_

  - [ ]* 1.4 撰寫 state_machine.py 單元測試
    - 現況（部分完成）：`test_workflow_state.py`、`test_loop_guardrails.py`、`test_state_machine_guards.py` 已涵蓋守門拒絕、CONFIRM 條件性跳過、已結束的 session 拒絕所有輸入、兩道護欄
    - 缺口：**沒有逐一驗證完整轉換表的測試**（每個 (state, input) → expected_state 的窮舉）
    - 測試每個合法轉換 (state, input) → expected_state
    - 測試守門拒絕不合法 input（InvalidTransitionError）
    - 測試 CONFIRM 跳過邏輯（`ENTRY_GUARDS[CONFIRM]`）
    - 測試 exit_reason 非 None 時拒絕所有 input
    - 測試 workflow_state == COMPLETE 時拒絕所有 input
    - 測試自動推進鏈有界（`max_auto_steps`）
    - 測試 session_id 不變性
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.2, 3.1, 3.2, 4.6_

  - [ ]* 1.5 撰寫 Property-Based Test：State Machine Determinism
    - **Property 1: State Machine Determinism**
    - 使用 Hypothesis 產生隨機合法 (SessionState, AdvanceInput) 組合
    - 驗證同一組輸入呼叫兩次 transition 產生相同結果（忽略 resolved_at）
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 1.6 撰寫 Property-Based Test：Frozen State Immutability
    - **Property 2: Frozen State Immutability**
    - 驗證 transition 後原始 state 物件所有欄位未被修改
    - 驗證 result.new_state.session_id == state.session_id
    - **Validates: Requirements 1.3, 1.4, 18.1, 18.2**

  - [ ]* 1.7 撰寫 Property-Based Test：Input Allowlist Enforcement
    - **Property 3: Input Allowlist Enforcement**
    - 產生 input.kind 不在 ALLOWED_INPUTS[state.workflow_state] 的組合
    - 驗證必定拋出 InvalidTransitionError
    - 驗證 exit_reason 非 None 或 COMPLETE 狀態時所有 input 被拒
    - **Validates: Requirements 2.2, 1.5**

- [ ] 2. 實作迴圈護欄（T6）
  - [x] 2.1 實作護欄邏輯（**併在 `backend/app/orchestration/state_machine.py` 裡，沒有獨立的 `guardrails.py`**，見 ADR-0012）
    - 政策參數為模組層常數 `MAX_LOOP_ITERATIONS = 6` 與 `MAX_EVENT_RETRIES = 2`，不是 `LoopGuardrails` dataclass
    - 未定案狀態的共用定義是 `UNSETTLED_STATUSES`（PENDING、NEEDS_INFORMATION）
    - 實作 `_check_loop_guardrails(state, state_before_iteration)`，直接回傳新的 `SessionState`，不經過 `GuardrailVerdict` 中介列舉
    - 進展判斷內嵌在 `_check_loop_guardrails` 中（status 有變化或 attributes 鍵數增加），不是獨立的 `has_progress()`
    - 實作 `_downgrade_unsettled_items()` 把未定案項目降級為 NEEDS_HUMAN_REVIEW
    - **只有兩道護欄**：護欄 2（迭代上限）與護欄 3（必須有進展）
    - 護欄 4（不重跑已定案）在 `determination.find_ready_item_ids` 以 `status != PENDING` 過濾實現
    - 護欄 1（檢索先行）**未實作** —— Phase 2 沒有真實檢索，等 Phase 4（T15/T18）
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

  - [x] 2.2 在 state_machine.py 整合護欄呼叫
    - 在 `_auto_advance` 的 EVALUATE_ELIGIBILITY 步驟後呼叫 `_check_loop_guardrails`
    - 迭代上限觸發：未定案項目降級 NEEDS_HUMAN_REVIEW，設 `exit_reason = LOOP_LIMIT_REACHED`
    - 無進展觸發：設 `exit_reason = NO_PROGRESS`，終止流程
    - _Requirements: 5.2, 5.3, 6.4_

  - [ ]* 2.3 撰寫護欄單元測試
    - 測試 max_iterations 觸發 EXIT_LOOP_LIMIT
    - 測試 no_progress 觸發 EXIT_NO_PROGRESS
    - 測試 has_progress 正確判斷（status 變化 / attributes 新增 key）
    - 測試 PENDING 項目降級為 NEEDS_HUMAN_REVIEW
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

  - [ ]* 2.4 撰寫 Property-Based Test：Guardrail Termination Guarantee
    - **Property 4: Guardrail Termination Guarantee**
    - 驗證 loop_iterations 永不超過 max_iterations
    - 驗證觸發後所有未定案項目降級
    - 驗證 auto-advance 內部迴圈有界（`max_auto_steps = 20`，非設計文件的 4）
    - **Validates: Requirements 5.2, 5.3, 4.6**

  - [ ]* 2.5 撰寫 Property-Based Test：Progress Definition Correctness
    - **Property 5: Progress Definition Correctness**
    - 產生隨機 (prev_state, curr_state) 組合
    - 進展判斷內嵌在 `_check_loop_guardrails`，沒有獨立的 `has_progress()` 可測；驗證方式是觀察 `exit_reason` 是否為 NO_PROGRESS
    - 驗證「至少一個 status 改變或 attributes 新增 key」時不觸發 NO_PROGRESS，反之觸發
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [ ] 3. 中間檢查點
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 實作欄位登記表機制（T7）
  - [x] 4.1 建立 `backend/app/orchestration/field_registry.py`
    - 定義 `FieldValueKind` StrEnum
    - 定義 `FieldDefinition` frozen dataclass
    - 實作 `FieldRegistry`（**具體類別，不是 Protocol**；也沒有另一個 `InMemoryFieldRegistry`）
    - 方法：`get`、`has`、`all_field_ids`、`fields_for_items`、`topics`、`fields_in_topic`、`count`
    - **偏離設計文件的命名**：`get` / `has` / `all_field_ids` / `fields_for_items` 取代了設計文件的 `get_field` / `is_known_field` / `get_all_fields` / `get_fields_for_item`；`fields_for_items` 接受一組 item_id 而非單一 item_id（呼叫端幾乎都是一次查多個項目）
    - 欄位定義以 `used_by` 表示哪些項目需要它（設計文件寫 `required_by_items`）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 4.2 建立登記表資料與載入機制
    - 登記表資料在 `data/eligibility_fields/fields.v0.1.json`（**不是** `backend/tests/fixtures/`）—— 它是正式的政策資料，不是測試 fixture
    - 由 `FieldRegistry.from_json()` 載入；`state_machine.default_registry()` 做 lazy 快取
    - 資料不含 PII，適用於公開 repo
    - _Requirements: 8.5, 17.3_

  - [x]* 4.3 撰寫 Field Registry 單元測試
    - `backend/tests/unit/test_field_registry.py`
    - 測試 `get` 存在/不存在
    - 測試 `fields_for_items` 正確回傳
    - 測試 `has` 布林值正確
    - 測試 `all_field_ids` 回傳全部
    - 測試空 registry 的邊界情況
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 4.4 撰寫 Property-Based Test：Field Registry Index Consistency
    - **Property 7: Field Registry Index Consistency**
    - 產生隨機 FieldDefinition 集合注入 registry
    - 驗證 `get(f.field_id)` 回傳正確的 f
    - 驗證 `fields_for_items` 回傳 `used_by` 含該 item_id 的所有欄位
    - 驗證 `has` 與 registered 一致
    - **Validates: Requirements 8.1, 8.2, 8.4, 8.5**

- [ ] 5. 實作缺漏欄位計算與主題分組（T8）
  - [x] 5.1 建立 `backend/app/orchestration/missing_fields.py`
    - 缺漏計算內嵌在 `compute_question_groups(state, registry)` 裡，**沒有**獨立的 `compute_missing_fields()`：唯一的呼叫端就是分組，多一層 `dict[item_id, fields]` 中介結構沒有用到
    - 只考慮 PENDING/NEEDS_INFORMATION 項目
    - 排除已在 `state.attributes` 中的 field_id
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 5.2 實作 `compute_question_groups()` 問題分組
    - 以 topic_id 為分組鍵，順序取自 `registry.topics()`
    - 跨項目去重：同一 field_id 只問一次，`unlocks_item_ids` 列出所有相關的待定案項目
    - group_index 從 1 開始，group_total = 本次 group 數量
    - 回傳 `tuple[QuestionGroupView, ...]`（`QuestionGroupView` 沿用 `schemas/session.py` 已有的定義，未新增 dataclass）
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x]* 5.3 撰寫 missing_fields 單元測試
    - `backend/tests/unit/test_missing_fields.py`
    - 測試只考慮 PENDING/NEEDS_INFORMATION 項目
    - 測試排除已有的 attributes
    - 測試主題分組正確
    - 測試跨項目去重
    - 測試空 topic_id 獨立成組
    - _Requirements: 10.1, 10.2, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [ ]* 5.4 撰寫 Property-Based Test：Missing Fields Computation Correctness
    - **Property 9: Missing Fields Computation Correctness**
    - 產生隨機 (items, attributes, registry) 三元組
    - 驗證結果只包含 PENDING/NEEDS_INFORMATION 項目的欄位
    - 驗證結果不包含已在 attributes 中的 field_id
    - **Validates: Requirements 10.1, 10.2**

  - [ ]* 5.5 撰寫 Property-Based Test：Question Group Structure Invariants
    - **Property 10: Question Group Structure Invariants**
    - 驗證同 topic_id 非空欄位在同一組
    - 驗證空 topic_id 各自獨立
    - 驗證 field_id 跨組唯一
    - 驗證 group_index 連續遞增
    - 驗證 group_total 正確
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6**

- [ ] 6. 在 state_machine.py 整合欄位驗證
  - [x] 6.1 實作 AttributeAnswersInput 的欄位 allowlist 檢查
    - 在 `_record_answers` 中呼叫 `registry.has()` 檢查所有 key
    - 任一 field_id 不在 registry → raise `UnknownFieldError`（拒絕整筆，不做部分接受也不靜默丟棄）
    - 全部合格 → 交給 `PrivacyGate.validate_attributes()` 後合併到 `state.attributes`
    - _Requirements: 9.1, 9.2_

  - [ ]* 6.2 撰寫 Property-Based Test：Unknown Field Rejection
    - **Property 8: Unknown Field Rejection**
    - 產生含未知 field_id 的 answers
    - 驗證必定拋出 UnknownFieldError
    - 產生全部已知 field_id 的 answers
    - 驗證請求被接受
    - **Validates: Requirements 9.1, 9.2**

- [ ] 7. 中間檢查點
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 實作規則引擎轉接層（T9）
  - [x] 8.1 建立 `backend/app/orchestration/rule_adapter.py`（檔名是 `rule_adapter.py`，**不是** `adapter.py`）
    - 實作 `adapt_result(result, *, item_kind)` → CandidateItem（函式名是 `adapt_result`，**不是** `adapt_eligibility_result`；不接受 `existing_item` 與 `rules` 參數）
    - Status 映射：`_STATUS_MAP` 把四種字串轉成 `ItemStatus`；未知字串安全降級為 NEEDS_HUMAN_REVIEW
    - 金額映射：`result.amount` 同時填入 amount_min 與 amount_max（規則欄位還沒有 min/max 區間）
    - `amount_period` 恆為 None（規則欄位還沒有 payout_nature，優雅降級）
    - 新增 `downgrade_unexplained_ineligible(status, decisive_conditions)`：INELIGIBLE 且無決定性條件 → 降級 NEEDS_HUMAN_REVIEW（Req 12.3）。拆成獨立函式是為了可測試性 —— `adapt_result` 目前恆產生空的 decisive_conditions，從它那邊測不到「有條件時不降級」那一半
    - `missing_inputs` → `missing_field_ids`（tuple）
    - `source_url` 有值時組成最小的 `Citation`
    - _Requirements: 12.1, 12.2, 12.3, 13.1, 13.2, 13.3, 14.1_

  - [x]* 8.2 撰寫 rule_adapter 單元測試
    - `backend/tests/unit/test_rule_adapter.py`
    - 測試 status 映射（四種合法值）
    - 測試 INELIGIBLE 無結構化 reason 的降級
    - 測試金額映射：有 min/max、只有 result.amount、無金額
    - 測試 payout_nature 缺失時 amount_period = None
    - 測試 missing_inputs 轉換
    - _Requirements: 12.1, 12.2, 12.3, 13.1, 13.2, 13.3, 14.1_

  - [ ]* 8.3 撰寫 Property-Based Test：Adapter Status Constraint and Graceful Downgrade
    - **Property 11: Adapter Status Constraint and Graceful Downgrade**
    - 驗證回傳 status 永遠在 RULE_ENGINE_STATUSES 中
    - 驗證 INELIGIBLE + 無法解構 reasons → NEEDS_HUMAN_REVIEW
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [ ]* 8.4 撰寫 Property-Based Test：Adapter Amount Mapping
    - **Property 12: Adapter Amount Mapping**
    - 產生隨機 (EligibilityResult, rules) 組合
    - 驗證金額映射規則符合規格
    - 驗證 payout_nature 缺失 → None
    - 驗證 missing_inputs → tuple 轉換
    - **Validates: Requirements 13.1, 13.2, 13.3, 14.1**

- [ ] 9. 實作逐項判定組裝（T10）
  - [ ] 9.1 建立 `backend/app/orchestration/determination.py`
    - 現況（部分完成）：模組已存在，有 `find_ready_item_ids`、`find_undeclared_item_ids`、`gated_status`、`visible_items`、`evaluate_ready_items(state, registry, eligibility_service)`，逐項判定由 `_resolve_item` 負責
    - 已達成：護欄 4（不重跑已定案）以 `status != PENDING` 過濾實現；`resolved_at` 有蓋時間戳
    - 已達成：**單一項目失敗隔離（Req 15.4）** —— `_resolve_item` 對每一項各自包 `try/except Exception`，某一項的規則引擎拋例外時只把該項標成 `NEEDS_HUMAN_REVIEW` 並記一筆 `item_evaluation_failed`（只記項目代號、結果狀態與例外類別，走 `exc_info`，例外訊息不會進紀錄檔），其他項目照常判定
    - 已達成：依 `program_status` 的安全檢查 —— `verified` 才做完整判定，`candidate` / `under_review` 回 `needs_human_review`，`rejected` / `inactive` 由 `visible_items` 隱藏，`stale` 依 `_STALE_FALLBACK_STATUS` 暫行降級（待決策，不得靜默定案）
    - 缺口：**沒有接上真正的規則引擎**。目前 `evaluate_ready_items` 呼叫的是注入進來的 `EligibilityService`，而離線實作 `FixtureEligibilityService` 對每一項都回 `needs_human_review`，因為沒有任何已核准的規則。**等 T18 接上 SQLite 規則資料**
    - _Requirements: 7.1, 7.2, 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x]* 9.2 撰寫 determination 單元測試
    - `backend/tests/unit/test_determination.py`（涵蓋現有的 stub 行為）
    - 測試不重跑已定案項目
    - 測試單一項目失敗不影響其他
    - 測試回傳長度一致
    - 測試仍有缺漏欄位時保持 PENDING + 更新 missing_field_ids
    - 測試 resolved_at 有值
    - _Requirements: 7.1, 7.2, 15.1, 15.4_

  - [ ]* 9.3 撰寫 Property-Based Test：No Re-evaluation of Finalized Items
    - **Property 6: No Re-evaluation of Finalized Items**
    - 產生含已定案項目的 state
    - 驗證 rules engine 不被呼叫，項目不變
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 9.4 撰寫 Property-Based Test：Determination Output Integrity
    - **Property 13: Determination Output Integrity**
    - 驗證回傳 tuple 長度 == state.items 長度
    - 模擬單一項目 engine 拋例外，驗證該項目 NEEDS_HUMAN_REVIEW 且其他不受影響
    - **Validates: Requirements 15.1, 15.4**

- [x] 10. 定義 Seams（接縫）Protocol 介面
  - [x] 10.1 建立 `backend/app/orchestration/protocols.py`
    - 定義 `EntitlementSource` Protocol（resolve → tuple[CandidateItem, ...]）
    - 定義 `RuleSource` Protocol（load_rules → dict[str, Any]）
    - 定義 `EvidenceRetriever` Protocol（retrieve → tuple[Citation, ...]）
    - 定義 `PrivacyGate` Protocol（validate_attributes）
    - 實作 `PassThroughPrivacyGate`（Phase 2 pass-through，複製一份後回傳）
    - 實作 `FixtureEntitlementSource`（回傳寫死的 CandidateItem fixture；認不出事件回空 tuple）
    - `advance()` 已開四個具名注入點，內部收在 `_Seams` dataclass 中
    - _Requirements: 19.1, 19.2, 19.3_

  - [x]* 10.2 撰寫 protocols 單元測試
    - `backend/tests/unit/test_protocols.py`
    - 測試 PassThroughPrivacyGate 直接回傳
    - 測試 FixtureEntitlementSource 回傳正確 fixture
    - _Requirements: 19.1, 19.2_

- [x] 11. 錯誤處理與 API 整合
  - [x] 11.1 更新 `backend/app/api/sessions.py` 接入 state_machine
    - `mock_advance()` 呼叫已替換為 `state_machine.advance()`
    - 四種錯誤映射齊備：`InvalidTransitionError` → INVALID_TRANSITION（409）、`UnknownFieldError` → UNKNOWN_FIELD（422）、`UnknownItemError` → UNKNOWN_ITEM（422），以及 `errors.py` 的 INVALID_FIELD_VALUE（422）
    - 所有 ErrorResponse 不含使用者輸入值（只有 error_code、field_ids、current_state）
    - 註：AdvanceInput 目前仍是 `schemas/session.py` 的類型，orchestration 層直接吃它 —— 解析責任的移交在任務 16
    - _Requirements: 16.1, 16.2, 16.4, 16.5, 16.6_

  - [x] 11.2 刪除 `backend/app/orchestration/mock_advance.py`
    - 已刪除，所有 import 已改為 state_machine
    - _Requirements: 20.1_

  - [x]* 11.3 撰寫 API 層錯誤處理整合測試
    - `backend/tests/integration/test_sessions_api.py`，涵蓋錯誤回應格式
    - 測試 ErrorResponse 不含使用者值
    - _Requirements: 16.1, 16.2, 16.4, 16.5_

- [ ] 12. 中間檢查點
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. 端到端離線測試
  - [ ] 13.1 建立完整流程整合測試
    - 建立 `backend/tests/integration/test_workflow_e2e.py`
    - 使用手寫 registry fixture + 本機 SQLite rules DB
    - 測試場景：配偶死亡 → 喪葬給付判定（UNDERSTAND_EVENT → COMPLETE）
    - 驗證所有項目最終 status 非 PENDING
    - 驗證 decisive_conditions 有值（eligible 或 ineligible 的項目）
    - 全程離線，無 AWS、無網路、無 LLM
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [ ] 13.2 建立護欄觸發整合測試
    - 現況（部分完成）：護欄觸發的測試已存在於 `backend/tests/unit/test_loop_guardrails.py`，但在 **unit 層**，不是 integration 層
    - 缺口：尚未在 integration 層以完整 HTTP 流程驗證護欄觸發後的對外回應
    - test_guardrail_no_progress_exits：送重複空答案，驗證 NO_PROGRESS 觸發
    - test_guardrail_loop_limit_exits：模擬 6 圈有進展但仍 PENDING，驗證 LOOP_LIMIT
    - _Requirements: 5.2, 5.3, 6.4_

  - [ ]* 13.3 撰寫 Property-Based Test：CONFIRM Skip Logic
    - **Property 14: CONFIRM Skip Logic**
    - 產生隨機 CandidateItem 集合
    - 對象是 `ENTRY_GUARDS[WorkflowState.CONFIRM]`，不是獨立的 `should_skip_confirm()`
    - 驗證無 NEEDS_HUMAN_REVIEW / NEEDS_INFORMATION → 守門回 False（跳過 CONFIRM 直達 COMPLETE）
    - 驗證有 NEEDS_HUMAN_REVIEW → 守門回 True（進入 CONFIRM）
    - **Validates: Requirements 3.1, 3.2**

- [ ] 14. 最終檢查點
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. ~~（選擇性/加分）假的 AgentRunner（T20 提前）~~ **已作廢，改用 LLM port**
  - **不要實作這一項。** 2026-07-30 的
    [ADR-0015](../../../docs/decisions/0015-narrow-llm-port-instead-of-agent-loop.md)
    決定不做 `AgentRunner`，因為那意味著給模型一個可以呼叫工具的迴圈 ——
    而那是一條它可以影響資格判定的路（ADR-0003 明文禁止）。
  - 實際做出來的東西在 `backend/app/llm/`：`port.py`（形狀與契約）、
    `fake.py`（離線實作，`advance()` 的預設值）、`gemini.py`（真實 adapter）、
    `factory.py`（有金鑰用真的、沒金鑰用示範）、
    `tasks/resolve_life_event.py`（事件辨識）。
  - 差別不只是改名：**`FakeLanguageModel` 刻意不回寫死的 `spouse_death`**。
    沒登記答案就拋錯 —— 一個會「大概猜一下」的假實作會讓測試在真實模型接上之前
    就通過，於是缺口被藏起來。寫死答案的版本在
    `orchestration/demo_fixtures.demo_language_model()`，而且必須明確注入。

- [ ] 16. 拆開 `schemas` ↔ `orchestration` 的循環依賴
  - **獨立 PR，不與本批混合**（擁有者明確要求）
  - 現況：`state_machine.py`、`field_registry.py`、`missing_fields.py` 三個模組 `import app.schemas.session`，而 `schemas/session.py` 反向 import `app.orchestration.state`，形成套件級循環。這也是 `protocols.py` 的 `PrivacyGate.registry` 只能標成 `Any` 的原因
  - 任務 1.3 是同一件事的子集，實作時併入這裡處理

  - [ ] 16.1 建立 `backend/app/orchestration/inputs.py`
    - 把七種輸入類型定義在 orchestration 層：`LifeEventTextInput`、`EventConfirmationInput`、`AttributeAnswersInput`、`ReviewConfirmationInput`、`ReferralChoiceInput`、`HelpRequestInput`、`ItemDeclineInput`
    - _Requirements: 20.2_

  - [ ] 16.2 讓 orchestration 模組改 import 自己層的類型
    - `state_machine.py`、`field_registry.py`、`missing_fields.py` 改成 import `app.orchestration.inputs`（以及 orchestration 層的 view 類型），不再 import `app.schemas.session`
    - _Requirements: 20.2_

  - [ ] 16.3 把 `schemas/session.py` 改成投影（projection）
    - `schemas/session.py` 只負責 HTTP 邊界的形狀，由 orchestration 層的定義投影而來（單向依賴：schemas → orchestration）
    - 影響 `api/sessions.py` 的解析責任：**API 層負責把 HTTP payload 解析成 orchestration 層的輸入類型**，再傳給 `advance()`
    - _Requirements: 20.2_

  - [ ] 16.4 驗證循環消失
    - 檢查 `python -c "import app.schemas.session"` 與 `python -c "import app.orchestration.state_machine"` 兩個方向都能單獨匯入
    - 加一個測試斷言模組相依圖：`app.orchestration.*` 不得出現對 `app.schemas.*` 的 import
    - _Requirements: 20.2_

## 備註

- 標記 `*` 的子任務為選擇性，可跳過以加速 MVP
- 每個任務標注具體 requirements 供追溯
- Checkpoints 確保漸進式驗證
- Property tests 使用 Hypothesis 框架（需加為 dev dependency）
- 任務 15 是 T20 的提前實作，設計文件建議在 Phase 2 完成後立即做，有了它端到端測試完全不需要網路
- 任務 16 是獨立 PR，不與本批混合
- 所有測試 fixture 使用虛構資料（不含 PII），適用於公開 repo
- 全部 property-based 測試（1.5、1.6、1.7、2.4、2.5、4.4、5.4、5.5、6.2、8.3、8.4、9.3、9.4、13.3）尚未開始：`hypothesis` 還沒加入 dev dependency，測試檔案也不存在

### 與設計文件的已知偏離

實作過程中刻意偏離 `design.md` 的地方，記錄於此以免日後誤判為 bug：

- **護欄併入 `state_machine.py`，沒有獨立的 `guardrails.py`**（見 ADR-0012）。護欄只有兩處呼叫點，且都在自動推進迴圈內，拆檔會讓一段連續的邏輯跨兩個檔案
- **沒有 `TransitionResult`**，`advance()` 直接回傳 `SessionState`。`question_groups` 由 `api/sessions.py` 的 `_snapshot()` 另外呼叫 `compute_question_groups()` 計算 —— 問題卡是對外快照的一部分，不是狀態的一部分
- **`rule_adapter.py` / `adapt_result` 的命名與設計文件不同**（設計文件寫 `adapter.py` / `adapt_eligibility_result`），且簽章改為 `adapt_result(result, *, item_kind)`
- **`FieldRegistry` 的方法命名與設計文件不同**（`get` / `has` / `all_field_ids` / `fields_for_items` 對應 `get_field` / `is_known_field` / `get_all_fields` / `get_fields_for_item`），且它是**具體類別而非 Protocol**，沒有另一個 `InMemoryFieldRegistry`
- **自動推進的防遞迴上限是 20（`max_auto_steps`）而非設計文件的 4**。4 是正常路徑的長度觀察，不適合當安全上限
- **護欄 1（檢索先行）未實作**，等 Phase 4 接上真實檢索（T15/T18）。目前 `RETRIEVE_RULES` 是空操作，沒有「找不到官方依據」這個狀況可以判斷

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "4.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "4.2"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "1.7", "2.2", "4.3", "4.4"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1"] },
    { "id": 5, "tasks": ["5.3", "5.4", "5.5", "6.2", "8.1"] },
    { "id": 6, "tasks": ["8.2", "8.3", "8.4", "9.1", "10.1"] },
    { "id": 7, "tasks": ["9.2", "9.3", "9.4", "10.2", "11.1"] },
    { "id": 8, "tasks": ["11.2", "11.3"] },
    { "id": 9, "tasks": ["13.1", "13.2", "13.3"] },
    { "id": 10, "tasks": ["15.1"] },
    { "id": 11, "tasks": ["15.2"] },
    { "id": 12, "tasks": ["16.1"] },
    { "id": 13, "tasks": ["16.2"] },
    { "id": 14, "tasks": ["16.3"] },
    { "id": 15, "tasks": ["16.4"] }
  ]
}
```
