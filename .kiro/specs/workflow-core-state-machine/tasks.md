# 實作計畫：Workflow Core State Machine（Phase 2, T5–T10）

## 概覽

將設計文件中的六個任務（T5 狀態機轉換、T6 護欄、T7 欄位登記表、T8 缺漏欄位、T9 規則引擎轉接、T10 判定組裝）轉為可執行的實作步驟。完成後，`mock_advance.py` 被刪除，整條流程在離線環境下以手寫規則跑完 UNDERSTAND_EVENT → COMPLETE。

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
  - [ ] 1.1 建立 `backend/app/orchestration/state_machine.py` 核心模組
    - 定義 `TransitionResult` dataclass（new_state, question_groups, guardrail_triggered）
    - 定義 `ALLOWED_INPUTS` 字典（每個 WorkflowState → frozenset of input kinds）
    - 定義 `InvalidTransitionError`、`UnknownFieldError`、`InvalidFieldValueError`、`UnknownItemError` 例外類別
    - 實作 `transition()` 函式：守門檢查 → dispatch → auto-advance → 回傳 TransitionResult
    - 實作 `_dispatch()` 分派邏輯，處理七種 input kind
    - 實作 `should_skip_confirm()` 判定 CONFIRM 是否跳過
    - 全程使用 `model_copy(update=...)` 確保 frozen 不變性
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 18.1, 18.2, 20.2_

  - [ ] 1.2 實作 `_auto_advance()` 自動推進邏輯
    - RESOLVE_ENTITLEMENTS → COLLECT_MISSING_FIELDS 自動
    - RETRIEVE_RULES → EVALUATE_ELIGIBILITY 自動（Phase 2 跳過真實檢索）
    - EVALUATE_ELIGIBILITY → COLLECT 或 EXPLAIN_RESULT 視項目狀態
    - EXPLAIN_RESULT → CONFIRM 或 COMPLETE 視 should_skip_confirm
    - 內部迴圈最多 4 步保護（防無限遞迴）
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ] 1.3 定義 orchestration 層的 input 類型（取代 schemas import）
    - 在 `backend/app/orchestration/inputs.py` 定義七種 parsed input dataclass
    - `LifeEventTextInput`、`EventConfirmationInput`、`AttributeAnswersInput`、`ReviewConfirmationInput`、`ReferralChoiceInput`、`HelpRequestInput`、`ItemDeclineInput`
    - 確保 state_machine.py 只 import orchestration 內部模組，不 import schemas/
    - _Requirements: 20.2_

  - [ ]* 1.4 撰寫 state_machine.py 單元測試
    - 測試每個合法轉換 (state, input) → expected_state
    - 測試守門拒絕不合法 input（InvalidTransitionError）
    - 測試 CONFIRM 跳過邏輯（should_skip_confirm）
    - 測試 exit_reason 非 None 時拒絕所有 input
    - 測試 workflow_state == COMPLETE 時拒絕所有 input
    - 測試自動推進鏈最多 4 步
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
  - [ ] 2.1 建立護欄模組 `backend/app/orchestration/guardrails.py`
    - 定義 `LoopGuardrails` frozen dataclass（max_iterations=6）
    - 定義 `GuardrailVerdict` StrEnum（CONTINUE, EXIT_LOOP_LIMIT, EXIT_NO_PROGRESS）
    - 實作 `check_guardrails(prev_state, curr_state, guardrails)` → GuardrailVerdict
    - 實作 `has_progress(prev, curr)` 進展判斷邏輯
    - 護欄 4（不重跑已定案項目）整合到 determination.py（T10 處理）
    - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

  - [ ] 2.2 在 state_machine.py 整合護欄呼叫
    - 在 `_auto_advance` 的 EVALUATE_ELIGIBILITY 後呼叫 `check_guardrails`
    - EXIT_LOOP_LIMIT：所有 PENDING 項目降級 NEEDS_HUMAN_REVIEW，設 exit_reason
    - EXIT_NO_PROGRESS：設 exit_reason 為 NO_PROGRESS，終止流程
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
    - 驗證觸發後所有 PENDING 項目降級
    - 驗證 auto-advance 內部迴圈最多 4 步
    - **Validates: Requirements 5.2, 5.3, 4.6**

  - [ ]* 2.5 撰寫 Property-Based Test：Progress Definition Correctness
    - **Property 5: Progress Definition Correctness**
    - 產生隨機 (prev_state, curr_state) 組合
    - 驗證 has_progress 回傳 True iff 至少一個 status 改變或 attributes 新增 key
    - **Validates: Requirements 6.2, 6.3, 6.4**

- [ ] 3. 中間檢查點
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 實作欄位登記表機制（T7）
  - [ ] 4.1 建立 `backend/app/orchestration/field_registry.py`
    - 定義 `FieldValueKind` StrEnum（CODE, BOOLEAN, BAND, INTEGER）
    - 定義 `FieldOption` frozen dataclass
    - 定義 `FieldDefinition` frozen dataclass（field_id, value_kind, options, required_by_items, topic_id, purpose_id）
    - 定義 `FieldRegistry` Protocol 介面（get_field, get_fields_for_item, get_all_fields, is_known_field）
    - 實作 `InMemoryFieldRegistry` 類別（以 dict 索引 + item_id 反向索引）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ] 4.2 建立手寫 fixture JSON 與載入機制
    - 建立 `backend/tests/fixtures/field_registry_fixture.json`（含 2-3 個範例欄位用於喪葬給付情境）
    - 在 InMemoryFieldRegistry 加一個 `from_dicts()` 類別方法從 JSON 載入
    - 確保測試 fixture 不含 PII
    - _Requirements: 8.5, 17.3_

  - [ ]* 4.3 撰寫 Field Registry 單元測試
    - 測試 get_field 存在/不存在
    - 測試 get_fields_for_item 正確回傳
    - 測試 is_known_field 布林值正確
    - 測試 get_all_fields 回傳全部
    - 測試空 registry 的邊界情況
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 4.4 撰寫 Property-Based Test：Field Registry Index Consistency
    - **Property 7: Field Registry Index Consistency**
    - 產生隨機 FieldDefinition 集合注入 registry
    - 驗證 get_field(f.field_id) 回傳正確的 f
    - 驗證 get_fields_for_item 回傳 required_by_items 含 item_id 的所有欄位
    - 驗證 is_known_field 與 registered 一致
    - **Validates: Requirements 8.1, 8.2, 8.4, 8.5**

- [ ] 5. 實作缺漏欄位計算與主題分組（T8）
  - [ ] 5.1 建立 `backend/app/orchestration/missing_fields.py`
    - 實作 `compute_missing_fields(items, attributes, registry)` → dict[str, tuple[str, ...]]
    - 只考慮 PENDING/NEEDS_INFORMATION 項目
    - 排除已在 attributes 中的 field_id
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 5.2 實作 `compute_question_groups()` 問題分組
    - 以 topic_id 為分組鍵
    - 空 topic_id 各自獨立成組
    - 跨項目去重：同一 field_id 只問一次，unlocks_item_ids 列出所有相關項目
    - group_index 從 1 開始，group_total = 本次 group 數量
    - 回傳 `tuple[QuestionGroupView, ...]`（定義 QuestionGroupView dataclass）
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [ ]* 5.3 撰寫 missing_fields 單元測試
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
  - [ ] 6.1 實作 AttributeAnswersInput 的欄位 allowlist 檢查
    - 在 _dispatch 處理 attribute_answers 時，呼叫 registry.is_known_field 檢查所有 key
    - 任一 field_id 不在 registry → raise UnknownFieldError
    - 全部合格 → 合併到 state.attributes
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
  - [ ] 8.1 建立 `backend/app/orchestration/adapter.py`
    - 實作 `adapt_eligibility_result(result, existing_item, rules)` → CandidateItem
    - Status 映射：EligibilityResult.status → ItemStatus（名稱一致直接轉）
    - 金額映射：rules min_amount/max_amount → amount_min/max；或 result.amount 填兩邊
    - payout_nature 缺失時 amount_period = None（優雅降級）
    - INELIGIBLE 且 reasons 無法解構 → 降級 NEEDS_HUMAN_REVIEW
    - missing_inputs → missing_field_ids (tuple)
    - _Requirements: 12.1, 12.2, 12.3, 13.1, 13.2, 13.3, 14.1_

  - [ ]* 8.2 撰寫 adapter 單元測試
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
    - 實作 `evaluate_pending_items(state, registry, rules_connection)` → tuple[CandidateItem, ...]
    - 只對 PENDING/NEEDS_INFORMATION 項目呼叫 rules engine
    - 已定案項目（ELIGIBLE, INELIGIBLE, NEEDS_HUMAN_REVIEW, DECLINED_BY_USER）保持不變（護欄 4）
    - 單一項目 engine 失敗 → 標 NEEDS_HUMAN_REVIEW，不影響其他
    - 回傳 tuple 長度 == state.items 長度
    - 實作 `assemble_determination(item, result, rules)` → CandidateItem（整合 adapter + resolved_at）
    - _Requirements: 7.1, 7.2, 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ]* 9.2 撰寫 determination 單元測試
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

- [ ] 10. 定義 Seams（接縫）Protocol 介面
  - [ ] 10.1 建立 `backend/app/orchestration/protocols.py`
    - 定義 `EntitlementSource` Protocol（resolve → tuple[CandidateItem, ...]）
    - 定義 `RuleSource` Protocol（load_rules → dict[str, Any]）
    - 定義 `EvidenceRetriever` Protocol（retrieve → tuple[Citation, ...]）
    - 定義 `PrivacyGate` Protocol（validate_attributes）
    - 實作 `PassThroughPrivacyGate`（Phase 2 pass-through，直接回傳 answers）
    - 實作 `FixtureEntitlementSource`（回傳寫死的 CandidateItem fixture）
    - 在 transition() 參數中預留注入點
    - _Requirements: 19.1, 19.2, 19.3_

  - [ ]* 10.2 撰寫 protocols 單元測試
    - 測試 PassThroughPrivacyGate 直接回傳
    - 測試 FixtureEntitlementSource 回傳正確 fixture
    - _Requirements: 19.1, 19.2_

- [ ] 11. 錯誤處理與 API 整合
  - [ ] 11.1 更新 `backend/app/api/sessions.py` 接入 state_machine
    - 將 `mock_advance()` 呼叫替換為 `transition()` 呼叫
    - API 層負責解析 AdvanceInput → orchestration 層 input 類型
    - 處理 InvalidTransitionError → ErrorCode.INVALID_TRANSITION
    - 處理 UnknownFieldError → ErrorCode.UNKNOWN_FIELD
    - 處理 InvalidFieldValueError → ErrorCode.INVALID_FIELD_VALUE
    - 處理 UnknownItemError → ErrorCode.UNKNOWN_ITEM
    - 確保所有 ErrorResponse 不含使用者輸入值
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

  - [ ] 11.2 刪除 `backend/app/orchestration/mock_advance.py`
    - 確認所有 import 已替換為 state_machine
    - 移除 `implementation_notice()` 與 `placeholder_notice`
    - _Requirements: 20.1_

  - [ ]* 11.3 撰寫 API 層錯誤處理整合測試
    - 測試四種 error code 的回應格式
    - 測試 ErrorResponse 不含使用者值
    - 測試 DB 連線失敗不中斷流程
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

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
    - test_guardrail_no_progress_exits：送重複空答案，驗證 NO_PROGRESS 觸發
    - test_guardrail_loop_limit_exits：模擬 6 圈有進展但仍 PENDING，驗證 LOOP_LIMIT
    - _Requirements: 5.2, 5.3, 6.4_

  - [ ]* 13.3 撰寫 Property-Based Test：CONFIRM Skip Logic
    - **Property 14: CONFIRM Skip Logic**
    - 產生隨機 CandidateItem 集合
    - 驗證無 NEEDS_HUMAN_REVIEW → should_skip_confirm 回 True
    - 驗證有 NEEDS_HUMAN_REVIEW → 回 False
    - **Validates: Requirements 3.1, 3.2**

- [ ] 14. 最終檢查點
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. （選擇性/加分）假的 AgentRunner（T20 提前）
  - [ ] 15.1 建立 `backend/app/orchestration/agent_runner.py`
    - 定義 `AgentRunner` Protocol（extract_life_event, explain_results）
    - 實作 `FakeAgentRunner`：extract_life_event 回傳寫死的 `"spouse_death"`，explain_results 回傳空字串
    - 在 state_machine.py 中的 UNDERSTAND_EVENT handler 預留呼叫 AgentRunner 的 seam
    - _Requirements: 19.1（擴展）_

  - [ ]* 15.2 撰寫 FakeAgentRunner 單元測試
    - 測試 extract_life_event 回傳正確值
    - 測試 explain_results 回傳空 dict
    - 確保無 LLM 呼叫
    - _Requirements: 17.2_

## 備註

- 標記 `*` 的子任務為選擇性，可跳過以加速 MVP
- 每個任務標注具體 requirements 供追溯
- Checkpoints 確保漸進式驗證
- Property tests 使用 Hypothesis 框架（需加為 dev dependency）
- 任務 15 是 T20 的提前實作，設計文件建議在 Phase 2 完成後立即做，有了它端到端測試完全不需要網路
- 所有測試 fixture 使用虛構資料（不含 PII），適用於公開 repo

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
    { "id": 11, "tasks": ["15.2"] }
  ]
}
```
