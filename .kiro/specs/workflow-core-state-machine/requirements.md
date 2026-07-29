# Requirements Document

## Introduction

本文件定義 Workflow Core State Machine（Phase 2, T5–T10）的正式需求。涵蓋確定性狀態轉換引擎、迴圈護欄、欄位登記表機制、缺漏欄位計算與主題分組、規則引擎轉接層、以及逐項判定組裝。

完成判準：在沒有 AWS、沒有網路、沒有 LLM 的環境下，以手寫規則跑完整條流程（UNDERSTAND_EVENT → COMPLETE），得到正確判定（eligible / ineligible / needs_information / needs_human_review）與決定性條件。

## Glossary

- **State_Machine**：`orchestration/state_machine.py` 中的確定性狀態轉換引擎，負責推進 workflow state、守門、自動推進與護欄檢查
- **Field_Registry**：`orchestration/field_registry.py` 中的欄位登記表，宣告欄位代號、型別、選項與所屬項目
- **Missing_Fields_Computer**：`orchestration/missing_fields.py` 中的缺漏欄位計算與主題分組模組
- **Adapter**：`orchestration/adapter.py` 中的轉接層，將 `EligibilityResult` 轉為 `CandidateItem`
- **Determination_Assembler**：`orchestration/determination.py` 中的逐項判定組裝模組
- **SessionState**：`orchestration/state.py` 中已定義的 frozen Pydantic 模型，代表一次諮詢的完整狀態
- **CandidateItem**：`orchestration/state.py` 中的候選項目模型
- **EligibilityResult**：`rules/engine.py` 中規則引擎回傳的判定結果
- **AdvanceInput**：`schemas/session.py` 中定義的七種使用者輸入之 discriminated union
- **WorkflowState**：八個合法的工作流程狀態列舉
- **ItemStatus**：項目狀態列舉（PENDING, ELIGIBLE, INELIGIBLE, NEEDS_INFORMATION, NEEDS_HUMAN_REVIEW, DECLINED_BY_USER）
- **RULE_ENGINE_STATUSES**：規則引擎允許回傳的四個狀態子集（ELIGIBLE, INELIGIBLE, NEEDS_INFORMATION, NEEDS_HUMAN_REVIEW）
- **LoopGuardrails**：迴圈護欄的政策參數（max_iterations 預設 6）
- **GuardrailVerdict**：護欄判斷結果（CONTINUE, EXIT_LOOP_LIMIT, EXIT_NO_PROGRESS）
- **TransitionResult**：一次狀態轉換的產出，包含 new_state、question_groups 及可能的 guardrail_triggered
- **FieldDefinition**：欄位登記表中一個欄位的完整定義
- **QuestionGroupView**：按主題分組後的問題集合，供前端直接使用
- **DecisiveCondition**：造成判定結果的決定性條件

## Requirements

### Requirement 1: 狀態轉換引擎核心

**User Story:** 身為後端開發者，我需要一個確定性狀態轉換引擎，使得 workflow 能依據轉換表正確地從一個狀態推進到下一個狀態。

#### Acceptance Criteria

1. WHEN State_Machine 收到合法的 (WorkflowState, AdvanceInput) 組合, THE State_Machine SHALL 依據轉換表產生新的 SessionState 並回傳 TransitionResult
2. THE State_Machine SHALL 保證相同的 (SessionState, AdvanceInput) 輸入永遠產生相同的 TransitionResult（確定性，不依賴隨機或外部時鐘，resolved_at 除外）
3. WHEN State_Machine 完成轉換, THE State_Machine SHALL 保證原始輸入的 SessionState 物件未被修改（frozen 不變性）
4. WHEN 轉換完成, THE State_Machine SHALL 保證 TransitionResult.new_state.session_id 等於原始 state.session_id
5. IF state.exit_reason 非 None 或 state.workflow_state 為 COMPLETE, THEN THE State_Machine SHALL 拒絕任何進一步的轉換請求

### Requirement 2: 工具允許清單（Per-State Input Allowlist）

**User Story:** 身為後端開發者，我需要每個狀態只接受特定類型的輸入，使得非法操作在進入業務邏輯前就被攔截。

#### Acceptance Criteria

1. THE State_Machine SHALL 為每個 WorkflowState 維護一組允許的 input kind 集合（ALLOWED_INPUTS）
2. WHEN AdvanceInput.kind 不在目前 WorkflowState 對應的 ALLOWED_INPUTS 中, THE State_Machine SHALL 拋出 InvalidTransitionError
3. WHILE WorkflowState 為 COMPLETE, THE State_Machine SHALL 拒絕所有輸入（ALLOWED_INPUTS 為空集合）
4. THE State_Machine SHALL 在每個 WorkflowState 的 ALLOWED_INPUTS 中包含 help_request（COMPLETE 除外）

### Requirement 3: CONFIRM 狀態條件性跳過

**User Story:** 身為後端開發者，我需要在不需要人工複查時自動跳過 CONFIRM 狀態，使得使用者不需經歷不必要的步驟。

#### Acceptance Criteria

1. WHEN 所有 CandidateItem 的 status 皆不為 NEEDS_HUMAN_REVIEW, THE State_Machine SHALL 從 EXPLAIN_RESULT 直接轉換到 COMPLETE（跳過 CONFIRM）
2. WHEN 至少一個 CandidateItem 的 status 為 NEEDS_HUMAN_REVIEW, THE State_Machine SHALL 從 EXPLAIN_RESULT 轉換到 CONFIRM

### Requirement 4: 自動推進（Auto-Advance）

**User Story:** 身為後端開發者，我需要不需使用者輸入的內部狀態能自動連續推進，使得一次 HTTP 請求能完成整段自動路徑。

#### Acceptance Criteria

1. WHEN WorkflowState 為 RESOLVE_ENTITLEMENTS, THE State_Machine SHALL 自動推進到 COLLECT_MISSING_FIELDS
2. WHEN WorkflowState 為 RETRIEVE_RULES, THE State_Machine SHALL 自動推進到 EVALUATE_ELIGIBILITY（Phase 2 無真實檢索）
3. WHEN WorkflowState 為 EVALUATE_ELIGIBILITY 且所有項目已定案, THE State_Machine SHALL 自動推進到 EXPLAIN_RESULT
4. WHEN WorkflowState 為 EVALUATE_ELIGIBILITY 且仍有 PENDING 項目, THE State_Machine SHALL 自動推進回 COLLECT_MISSING_FIELDS 並遞增 loop_iterations
5. WHEN WorkflowState 為 EXPLAIN_RESULT, THE State_Machine SHALL 自動推進到 CONFIRM 或 COMPLETE（依需求 3 的條件）
6. THE State_Machine SHALL 保證自動推進內部迴圈最多執行 4 步（RESOLVE→COLLECT→RETRIEVE→EVALUATE 或 EVALUATE→EXPLAIN→CONFIRM/COMPLETE），防止無限遞迴

### Requirement 5: 迴圈護欄 — 迭代上限

**User Story:** 身為後端開發者，我需要限制追問與判定迴圈的最大圈數，使得系統不會因資料不完整而無限循環。

#### Acceptance Criteria

1. THE State_Machine SHALL 以 LoopGuardrails.max_iterations（預設 6）為迴圈上限
2. WHEN loop_iterations 達到 max_iterations, THE State_Machine SHALL 將所有仍為 PENDING 的項目降級為 NEEDS_HUMAN_REVIEW 並設定 exit_reason 為 LOOP_LIMIT_REACHED
3. WHEN 護欄觸發 EXIT_LOOP_LIMIT, THE State_Machine SHALL 終止流程且不再接受新輸入

### Requirement 6: 迴圈護欄 — 必須有進展

**User Story:** 身為後端開發者，我需要偵測沒有進展的迴圈並提前終止，使得系統不會在相同狀態原地打轉。

#### Acceptance Criteria

1. THE State_Machine SHALL 在每圈結束時比較 prev_state 與 curr_state 以判斷是否有進展
2. WHEN 至少一個項目的 status 從 PENDING 或 NEEDS_INFORMATION 變為其他值, THE State_Machine SHALL 判定為有進展
3. WHEN curr_state.attributes 比 prev_state.attributes 多了至少一個 key, THE State_Machine SHALL 判定為有進展
4. IF 一圈結束後既無項目狀態變化也無新增屬性（無進展）, THEN THE State_Machine SHALL 設定 exit_reason 為 NO_PROGRESS 並終止流程

### Requirement 7: 迴圈護欄 — 不重跑已定案項目

**User Story:** 身為後端開發者，我需要確保已定案的項目不再被規則引擎重新評估，使得已確定的結果不被覆蓋。

#### Acceptance Criteria

1. WHEN Determination_Assembler 執行判定迴圈, THE Determination_Assembler SHALL 只對 status 為 PENDING 或 NEEDS_INFORMATION 的項目呼叫規則引擎
2. WHILE 項目 status 為 ELIGIBLE、INELIGIBLE、NEEDS_HUMAN_REVIEW 或 DECLINED_BY_USER, THE Determination_Assembler SHALL 保持該項目不變且不呼叫規則引擎

### Requirement 8: 欄位登記表機制

**User Story:** 身為後端開發者，我需要一個欄位登記表來宣告所有資格欄位的代號、型別、選項及所屬項目，使得系統能驗證使用者輸入並計算缺漏。

#### Acceptance Criteria

1. THE Field_Registry SHALL 提供 get_field(field_id) 方法，回傳 FieldDefinition 或 None
2. THE Field_Registry SHALL 提供 get_fields_for_item(item_id) 方法，回傳該項目需要的所有 FieldDefinition
3. THE Field_Registry SHALL 提供 get_all_fields() 方法，回傳全部已登記的欄位
4. THE Field_Registry SHALL 提供 is_known_field(field_id) 方法，回傳布林值表示欄位是否在登記表上
5. WHEN 外部注入 FieldDefinition 集合, THE Field_Registry SHALL 正確建立以 field_id 為鍵的索引與以 item_id 為鍵的反向索引

### Requirement 9: 欄位 Allowlist 驗證

**User Story:** 身為後端開發者，我需要拒絕未在登記表上的欄位代號，使得隱私閘門能防止注入未知屬性。

#### Acceptance Criteria

1. WHEN AttributeAnswersInput.answers 包含任何 field_id 不在 Field_Registry 中, THE State_Machine SHALL 拒絕整筆請求並拋出 UnknownFieldError
2. WHEN 所有 answers 中的 field_id 都在 Field_Registry 中, THE State_Machine SHALL 接受請求並更新 state.attributes

### Requirement 10: 缺漏欄位計算

**User Story:** 身為後端開發者，我需要根據登記表與已收集的屬性計算每個待定項目還缺哪些欄位，使得系統能精確追問。

#### Acceptance Criteria

1. WHEN Missing_Fields_Computer 計算缺漏, THE Missing_Fields_Computer SHALL 只考慮 status 為 PENDING 或 NEEDS_INFORMATION 的項目
2. WHEN 項目所需的 field_id 已存在於 state.attributes 中, THE Missing_Fields_Computer SHALL 不將該 field_id 列為缺漏
3. THE Missing_Fields_Computer SHALL 回傳 dict[str, tuple[str, ...]] 格式（item_id → 缺漏的 field_id 清單）

### Requirement 11: 問題主題分組

**User Story:** 身為後端開發者，我需要將缺漏欄位按主題分組產生 QuestionGroupView，使得前端能直接顯示結構化的問題卡。

#### Acceptance Criteria

1. THE Missing_Fields_Computer SHALL 以 FieldDefinition.topic_id 為分組鍵將缺漏欄位分組
2. WHEN FieldDefinition.topic_id 為空字串, THE Missing_Fields_Computer SHALL 將該欄位獨立成一組
3. WHEN 同一 field_id 被多個項目需要, THE Missing_Fields_Computer SHALL 只問一次並在 unlocks_item_ids 列出所有相關項目
4. THE Missing_Fields_Computer SHALL 確保每個 QuestionGroupView.questions 內的 field_id 不重複
5. THE Missing_Fields_Computer SHALL 確保同一 field_id 只出現在一個 group 中（跨組去重）
6. THE Missing_Fields_Computer SHALL 設定 group_index 從 1 開始遞增，group_total 等於本次產生的 group 數量

### Requirement 12: 規則引擎轉接 — Status 映射

**User Story:** 身為後端開發者，我需要將 EligibilityResult.status 正確映射到 CandidateItem.status，使得規則引擎的結果能無縫整合進 workflow。

#### Acceptance Criteria

1. WHEN EligibilityResult.status 為合法值（eligible, ineligible, needs_information, needs_human_review）, THE Adapter SHALL 將其映射為對應的 ItemStatus
2. THE Adapter SHALL 保證回傳的 CandidateItem.status 屬於 RULE_ENGINE_STATUSES
3. WHEN EligibilityResult.status 為 ineligible 且 reasons 無法解構為 DecisiveCondition, THE Adapter SHALL 將 status 降級為 NEEDS_HUMAN_REVIEW

### Requirement 13: 規則引擎轉接 — 金額映射

**User Story:** 身為後端開發者，我需要將規則欄位中的金額資訊正確映射到 CandidateItem 的金額欄位，使得前端能顯示金額範圍。

#### Acceptance Criteria

1. WHEN rules 中存在 min_amount 與 max_amount, THE Adapter SHALL 將其映射為 CandidateItem.amount_min 與 amount_max
2. WHEN rules 中無 min_amount/max_amount 但 EligibilityResult.amount 有值, THE Adapter SHALL 將 amount 同時填入 amount_min 與 amount_max
3. WHEN rules 中無 payout_nature 欄位, THE Adapter SHALL 將 amount_period 設為 None（優雅降級）

### Requirement 14: 規則引擎轉接 — 缺漏欄位傳遞

**User Story:** 身為後端開發者，我需要將 EligibilityResult.missing_inputs 轉為 CandidateItem.missing_field_ids，使得系統知道還需追問哪些欄位。

#### Acceptance Criteria

1. THE Adapter SHALL 將 EligibilityResult.missing_inputs 轉為 CandidateItem.missing_field_ids（tuple 格式）

### Requirement 15: 逐項判定組裝

**User Story:** 身為後端開發者，我需要對所有未定案項目逐一執行規則引擎並組裝最終結果，使得每個項目都能獲得判定。

#### Acceptance Criteria

1. WHEN Determination_Assembler 執行, THE Determination_Assembler SHALL 回傳與 state.items 相同長度的 tuple
2. WHEN 項目所有 required fields 已有值, THE Determination_Assembler SHALL 執行規則引擎並回傳新 status
3. WHEN 項目仍有缺漏欄位, THE Determination_Assembler SHALL 保持 PENDING 並更新 missing_field_ids
4. IF 規則引擎對單一項目拋出非預期例外, THEN THE Determination_Assembler SHALL 將該項目標為 NEEDS_HUMAN_REVIEW 且不影響其他項目的判定
5. WHEN 定案完成, THE Determination_Assembler SHALL 在 CandidateItem 上設定 resolved_at 時間戳

### Requirement 16: 錯誤處理

**User Story:** 身為後端開發者，我需要所有錯誤都以結構化方式回報且不洩漏使用者輸入值，使得隱私得到保護。

#### Acceptance Criteria

1. WHEN input.kind 不在 ALLOWED_INPUTS 中, THE State_Machine SHALL 拋出 InvalidTransitionError（對應 ErrorCode.INVALID_TRANSITION）
2. WHEN AttributeAnswersInput 中有不在登記表的 field_id, THE State_Machine SHALL 拋出 UnknownFieldError（對應 ErrorCode.UNKNOWN_FIELD）
3. WHEN 屬性值不符合 FieldDefinition 宣告的型別或選項, THE State_Machine SHALL 拋出 InvalidFieldValueError（對應 ErrorCode.INVALID_FIELD_VALUE）
4. WHEN ItemDeclineInput 的 item_id 不在 state.items 中, THE State_Machine SHALL 拋出 UnknownItemError（對應 ErrorCode.UNKNOWN_ITEM）
5. THE State_Machine SHALL 確保所有錯誤回應只包含 error_code、field_ids 與 current_state，不含使用者輸入的值
6. IF 規則引擎 DB 連線失敗, THEN THE State_Machine SHALL 保持 PENDING 項目不變，流程不中斷，下一圈重試

### Requirement 17: 離線端到端執行

**User Story:** 身為後端開發者，我需要整條流程在沒有 AWS、沒有網路、沒有 LLM 的環境下能從頭跑到尾，使得開發與測試完全自給自足。

#### Acceptance Criteria

1. THE State_Machine SHALL 不引入任何 AWS SDK 依賴（包括 boto3）
2. THE State_Machine SHALL 不呼叫任何 LLM 服務
3. WHEN 使用手寫 registry fixture 與本機 SQLite 規則資料庫, THE State_Machine SHALL 能完成從 UNDERSTAND_EVENT 到 COMPLETE 的完整流程
4. THE State_Machine SHALL 在完整流程結束後產出所有項目的最終 status（非 PENDING）及相應的 decisive_conditions

### Requirement 18: Frozen State 不變性

**User Story:** 身為後端開發者，我需要狀態轉換始終透過 model_copy 產生新物件而非就地修改，使得符合 ADR-0011 的 frozen model 約束。

#### Acceptance Criteria

1. THE State_Machine SHALL 透過 model_copy(update=...) 產生新的 SessionState，永遠不修改傳入的狀態物件
2. WHEN 轉換完成後檢查原始 state 物件, THE State_Machine SHALL 保證其所有欄位值未改變

### Requirement 19: Seams（接縫）預留

**User Story:** 身為後端開發者，我需要為未來的資料來源、LLM 執行器與隱私閘門預留介面接縫，使得 Phase 4/5 替換實作時不需修改狀態機本身。

#### Acceptance Criteria

1. THE State_Machine SHALL 接受 EntitlementSource、RuleSource 與 EvidenceRetriever 三個 Protocol 介面作為參數或注入點
2. THE State_Machine SHALL 接受 PrivacyGate Protocol 介面，Phase 2 預設注入 pass-through 實作
3. WHEN Phase 4 或 Phase 5 替換實作, THE State_Machine SHALL 不需修改自身程式碼（依賴反轉）

### Requirement 20: 技術債清除

**User Story:** 身為後端開發者，我需要在狀態機完成後刪除 mock_advance.py 佔位模組，使得依賴方向恢復正確。

#### Acceptance Criteria

1. WHEN T5 完成, THE State_Machine SHALL 取代 mock_advance.py 的功能且該檔案被刪除
2. THE State_Machine SHALL 不從 schemas/session.py 匯入任何類型（API 層負責解析後傳入已解析的值）
