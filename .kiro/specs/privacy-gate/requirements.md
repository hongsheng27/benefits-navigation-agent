# Requirements Document

## Introduction

本文件定義 Privacy Gate（Phase 3, T11–T14）的正式需求。涵蓋三件事：

1. **屬性欄位的兩道檢查** —— 代號 allowlist（狀態機）與值的型別／選項驗證（隱私閘門）
2. **錯誤只帶欄位代號** —— 例外、HTTP 回應與紀錄檔都不得出現使用者填的值
3. **狀態轉換的可觀察性** —— 四個狀態機埋點，加上紀錄檔欄位的結構性強制機制

完成判準：在沒有 AWS、沒有網路、沒有 LLM 的環境下，任何一筆帶有未登記欄位代號或
不合法屬性值的請求都會被整筆拒絕，且拒絕的回應與紀錄檔中不含任何使用者輸入的值；
同時整條流程的每一次狀態轉換、迴圈回跳、護欄觸發與狀態跳過都留下一筆結構化紀錄。

### 實作狀態

- **T11（屬性 allowlist 與值驗證）**：已完成。實作於 `state_machine._record_answers`
  與 `privacy/attribute_gate.py`
- **T12（錯誤不外洩使用者輸入）**：已完成。實作於 `UnknownFieldError`、
  `InvalidAttributeValueError` 與 `api/errors.py`
- **T14（狀態機紀錄檔埋點）**：已完成。四個埋點實作於 `state_machine.py`；
  紀錄檔欄位的強制機制（`ALLOWED_FIELDS`、`JsonFormatter`）在 Phase 1 就已存在，
  **非本階段新增**，本文件僅記錄其必須維持的行為
- **T13（自由文字抽取後即丟棄）**：**延後至階段 5**。理由：目前事件辨識是寫死回
  `spouse_death`（`state_machine._receive_life_event` 的 `TODO(T21)`），系統根本沒有
  收下並處理使用者文字，寫了也沒有東西可丟。Requirement 8 完整描述目標行為與驗收
  條件，接上 LLM 抽取時可以直接拿來驗收。

## Glossary

- **State_Machine**：`orchestration/state_machine.py` 中的確定性狀態轉換引擎
- **Privacy_Gate**：`orchestration/protocols.py` 中的 `PrivacyGate` Protocol，
  定義屬性值進入 state 前的檢查介面
- **Registry_Gate**：`privacy/attribute_gate.py` 中的 `RegistryBackedPrivacyGate`，
  依欄位登記表驗證屬性值的 `Privacy_Gate` 實作
- **PassThrough_Gate**：`orchestration/protocols.py` 中的 `PassThroughPrivacyGate`，
  離線用的原樣回傳實作
- **Field_Registry**：`orchestration/field_registry.py` 中的 `FieldRegistry`，
  宣告欄位代號、型別、選項與所屬項目
- **FieldDefinition**：`Field_Registry` 中一個欄位的完整定義，含 `value_kind`
  與 `option_ids`
- **AttributeValueKind**：屬性值的四種型別列舉（`code`、`boolean`、`band`、`integer`）
- **AttributeAnswersInput**：`schemas/session.py` 中攜帶一組屬性答案的輸入型別
- **UnknownFieldError**：`state_machine.py` 中代號不在登記表上時拋出的例外
- **InvalidAttributeValueError**：`attribute_gate.py` 中值不符合欄位宣告時拋出的例外
- **Error_Handler**：`api/errors.py` 中的例外處理器，把例外轉成 `ErrorResponse`
- **ErrorResponse**：`schemas/session.py` 中的錯誤回應契約，含 `error_code`、
  `field_ids` 與 `current_state`
- **Event_Logger**：`observability/logging.py` 中的 `log_event` 函式
- **ALLOWED_FIELDS**：`observability/logging.py` 中允許出現在紀錄檔的欄位名稱集合
- **DisallowedLogFieldError**：欄位名稱不在 `ALLOWED_FIELDS` 中時拋出的例外
- **Json_Formatter**：`observability/logging.py` 中的 `JsonFormatter`，
  將每筆紀錄輸出為一行 JSON
- **SessionState**：`orchestration/state.py` 中的 frozen Pydantic 模型
- **WorkflowState**：八個合法的工作流程狀態列舉
- **ENTRY_GUARDS**：`state_machine.py` 中各狀態的進入守門條件
- **ExitReason**：流程提前終止的原因列舉（含 `LOOP_LIMIT_REACHED`、`NO_PROGRESS`）

## Requirements

### Requirement 1: 屬性欄位代號 Allowlist（第一道檢查）

**User Story:** 身為後端開發者，我需要在答案寫進 state 之前先拒絕未登記的欄位代號，
使得未知屬性沒有任何路徑能被保存下來。

#### Acceptance Criteria

1. WHEN `AttributeAnswersInput.answers` 中的每一個 `field_id` 都通過
   `Field_Registry.has()` 檢查, THE State_Machine SHALL 接受該筆請求並繼續執行值驗證
2. IF `AttributeAnswersInput.answers` 中有任何一個 `field_id` 未通過
   `Field_Registry.has()` 檢查, THEN THE State_Machine SHALL 拋出 UnknownFieldError
   並拒絕整筆請求
3. THE State_Machine SHALL 在拒絕整筆請求時不將該筆 answers 中的任何欄位寫入
   `SessionState.attributes`
4. THE State_Machine SHALL 在 `_record_answers` 中執行代號檢查，使得代號檢查的生效
   不依賴任何 Privacy_Gate 實作

### Requirement 2: 屬性值型別與選項驗證（第二道檢查）

**User Story:** 身為後端開發者，我需要在代號合法之後驗證值本身，使得自由文字無法藉著
一個合法代號被存進 `SessionState.attributes`。

#### Acceptance Criteria

1. WHERE `FieldDefinition.value_kind` 為 `code`, THE Registry_Gate SHALL 僅接受型別為
   `str` 且出現在 `FieldDefinition.option_ids` 中的值
2. WHERE `FieldDefinition.value_kind` 為 `band`, THE Registry_Gate SHALL 僅接受型別為
   `str` 且出現在 `FieldDefinition.option_ids` 中的值
3. WHERE `FieldDefinition.value_kind` 為 `boolean`, THE Registry_Gate SHALL 僅接受
   `True` 或 `False`
4. WHERE `FieldDefinition.value_kind` 為 `boolean`, THE Registry_Gate SHALL 拒絕字串
   `"true"` 與字串 `"false"`
5. WHERE `FieldDefinition.value_kind` 為 `integer`, THE Registry_Gate SHALL 僅接受型別
   為 `int` 且不為 `bool` 的值
6. WHERE `FieldDefinition.value_kind` 為 `integer` 且值為 `True` 或 `False`,
   THE Registry_Gate SHALL 拒絕該值（`bool` 是 `int` 的子類別，必須顯式排除）
7. IF `Field_Registry.get(field_id)` 回傳 `None`, THEN THE Registry_Gate SHALL 將該
   欄位視為不合法（防止繞過 Requirement 1 直接呼叫本方法的路徑）
8. THE Registry_Gate SHALL 實作 `Privacy_Gate` Protocol，使得替換 PassThrough_Gate
   不需修改 State_Machine

### Requirement 3: 拒絕整筆而非部分接受

**User Story:** 身為後端開發者，我需要任何一個值不合法就拒絕整筆答案，使得使用者不會
以為答案都收到了，也使得前端送錯值的 bug 不會看起來像正常運作。

#### Acceptance Criteria

1. IF 一筆 answers 中有任何一個值不符合 Requirement 2 的規則, THEN THE Registry_Gate
   SHALL 拋出 InvalidAttributeValueError 並拒絕整筆請求
2. THE Registry_Gate SHALL 在單筆請求含多個不合法欄位時，於同一個
   InvalidAttributeValueError 中回報全部不合法的欄位代號
3. THE Registry_Gate SHALL 在拒絕時不回傳任何部分結果，使得呼叫端沒有寫入部分答案
   的路徑
4. THE Registry_Gate SHALL 在拒絕時不記錄任何被拒絕的值

### Requirement 4: 驗證通過後回傳複本

**User Story:** 身為後端開發者，我需要閘門回傳答案的複本而非原 dict，使得呼叫端之後
改動自己持有的 dict 不會影響已寫入 state 的內容。

#### Acceptance Criteria

1. WHEN 所有值都通過驗證, THE Registry_Gate SHALL 回傳一個新的 dict，其內容與輸入
   相同且不與輸入共用同一個物件
2. WHEN 呼叫端在取得回傳值後修改原輸入 dict, THE Registry_Gate SHALL 保證回傳的 dict
   內容不受影響
3. THE PassThrough_Gate SHALL 同樣回傳複本，使得兩個實作在這一點上行為一致

### Requirement 5: 例外只攜帶欄位代號

**User Story:** 身為隱私審查者，我需要所有隱私閘門的例外只帶欄位代號，使得例外流到
HTTP 回應或紀錄檔時不會洩漏使用者輸入。

#### Acceptance Criteria

1. THE UnknownFieldError SHALL 僅公開 `field_ids` 屬性，不公開使用者填的值
2. THE InvalidAttributeValueError SHALL 僅公開 `field_ids` 屬性，不公開使用者填的值
3. THE UnknownFieldError SHALL 將 `field_ids` 排序後儲存，使得同一組違規欄位永遠得到
   同一個順序
4. THE InvalidAttributeValueError SHALL 將 `field_ids` 排序後儲存，使得同一組違規欄位
   永遠得到同一個順序
5. THE Error_Handler SHALL 在回應中只填入 `error_code`、`field_ids` 與 `current_state`
6. WHEN Error_Handler 處理 Pydantic 驗證錯誤, THE Error_Handler SHALL 只取每一筆錯誤
   的 `loc` 並丟棄 `input` 與 `msg`

### Requirement 6: 狀態機紀錄檔埋點

**User Story:** 身為後端開發者，我需要每一次狀態轉換、迴圈回跳、護欄觸發與狀態跳過都
留下一筆結構化紀錄，使得在不保存使用者文字的前提下仍能追查流程走向。

#### Acceptance Criteria

1. WHEN State_Machine 在自動推進中完成一次內部轉換, THE State_Machine SHALL 發出
   `state_transitioned` 事件，攜帶 `session_id`、`state`、`next_state` 與
   `transition="auto_advance"`
2. WHEN State_Machine 判斷需要回跳到 `COLLECT_MISSING_FIELDS`, THE State_Machine SHALL
   發出 `loop_iteration_started` 事件，攜帶 `session_id`、`state`、`next_state`、
   `transition="loop_back"` 與 `agent_iterations`
3. WHEN 迴圈護欄設定了 ExitReason, THE State_Machine SHALL 發出
   `loop_guardrail_triggered` 事件，攜帶 `session_id`、`state`、
   `guard`（值為 `ExitReason.value`）與 `agent_iterations`
4. WHEN ENTRY_GUARDS 中的守門條件使某個 WorkflowState 被跳過, THE State_Machine SHALL
   發出 `state_skipped` 事件，攜帶 `session_id`、`state`、`next_state` 與
   `guard`（值為 `entry_guard:{被跳過的狀態}`）
5. THE State_Machine SHALL 在 `state_skipped` 事件中記錄被跳過的狀態代號，使得日後
   觀察到流程從 `explain_result` 直接進入 `complete` 時，能分辨那是守門條件正確生效
   還是轉換表寫錯
6. THE State_Machine SHALL 在四個埋點中只傳入狀態代號、護欄代號、`session_id` 與
   計數，不傳入任何使用者提供的值

### Requirement 7: 紀錄檔欄位強制機制（已有，非本階段新增）

**User Story:** 身為隱私審查者，我需要紀錄檔的欄位限制以程式結構強制執行而非靠慣例，
使得誤傳使用者文字會立即失敗而不是流到 CloudWatch。

#### Acceptance Criteria

1. WHEN Event_Logger 收到的欄位名稱全部在 ALLOWED_FIELDS 中, THE Event_Logger SHALL
   輸出一筆結構化紀錄
2. IF Event_Logger 收到任何不在 ALLOWED_FIELDS 中的欄位名稱, THEN THE Event_Logger
   SHALL 拋出 DisallowedLogFieldError 且不輸出該筆紀錄
3. THE Event_Logger SHALL 在 DisallowedLogFieldError 的訊息中列出被拒絕的**欄位名稱**
4. WHEN Json_Formatter 處理帶有例外資訊的紀錄, THE Json_Formatter SHALL 只記錄例外的
   類別名稱與 `traceback.format_tb` 產生的堆疊框架
5. THE Json_Formatter SHALL 使用 `traceback.format_tb` 而非
   `traceback.format_exception`，使得例外訊息不會進入紀錄檔（Pydantic 的
   `ValidationError` 訊息會複述違規的原值）
6. THE Json_Formatter SHALL 將每一筆紀錄輸出為單一行 JSON 物件

### Requirement 8: 自由文字抽取後即丟棄（延後至階段 5）

**User Story:** 身為使用者，我需要我描述處境的原文在抽取出結構化欄位後就不再被保存，
使得系統持有的資料僅限於去識別化的欄位代號與選項。

> **狀態：延後。** 目前 `_receive_life_event` 寫死回 `spouse_death`，系統沒有收下並
> 處理使用者文字，因此沒有可丟棄的對象。以下驗收條件在接上 LLM 事件抽取（T21）時
> 直接生效。

#### Acceptance Criteria

1. WHEN State_Machine 從自由文字抽取出事件代號與屬性, THE State_Machine SHALL 只將
   抽取結果寫入 SessionState，不將原文寫入任何欄位
2. THE SessionState SHALL 不提供任何可存放使用者自由文字的欄位
3. WHEN 抽取完成, THE State_Machine SHALL 在同一次請求結束前釋放原文，使得原文不進入
   任何持久化儲存
4. IF 抽取失敗, THEN THE State_Machine SHALL 只記錄失敗的事實與例外類別名稱，
   不記錄原文
5. THE State_Machine SHALL 在抽取相關的紀錄中只使用 `life_event`
   （去識別化的事件類別代號）與 `extracted_field_names`（欄位名稱），不使用原文

### Requirement 9: 離線可驗證

**User Story:** 身為後端開發者，我需要隱私閘門的所有行為在沒有 AWS、沒有網路、
沒有 LLM 的環境下可驗證，使得測試完全自給自足。

#### Acceptance Criteria

1. THE Registry_Gate SHALL 不引入任何 AWS SDK 依賴（包括 `boto3`）
2. THE Registry_Gate SHALL 不呼叫任何 LLM 服務或網路端點
3. WHEN 使用手寫的 Field_Registry fixture, THE Registry_Gate SHALL 能完成
   Requirement 2 全部四種型別的驗證
4. THE Event_Logger SHALL 在無網路環境下將紀錄輸出到標準輸出

## Known Limitations

以下三項是已知且刻意接受的現況，**不列為本階段的待做事項**，也沒有對應的驗收條件。

### 1. `integer` 型別沒有範圍檢查

`Registry_Gate` 對 `integer` 只檢查「是整數且不是 `bool`」，不檢查上下限。因此人數
欄位送 `999999999` 在型別上仍然合法。

不處理的理由：`FieldDefinition` 目前沒有欄位可以放範圍，而 `fields.v0.1.json` 的三筆
種子欄位都還是 `draft` —— 現在加上 `min_value` / `max_value` 也不知道該填什麼。等
登記表有正式內容（`status` 轉為 `active`）時再決定是否加入範圍宣告。

風險評估：低。整數值不會流回前端做為自由文字顯示，而規則引擎對超出常理的人數會
產出 `needs_human_review` 而非錯誤結論。

### 2. `api/errors.py` 的 `loc` 可能包含請求主體的鍵名

`_handle_validation_error` 把 Pydantic 的 `exc.errors()` 縮減成 `loc` 組成的欄位路徑
字串。`loc` 反映的是**請求主體的結構位置**，若請求主體含有以使用者輸入為鍵的動態
物件（例如 `answers` 這種以 `field_id` 為鍵的 mapping），那個鍵名會出現在
`ErrorResponse.field_ids` 與 `request_validation_failed` 紀錄中。

刻意不處理的理由：

- 這個處理器**只取 `loc`**，`input`（不合法的原值）與 `msg`（會複述原值的訊息）
  一律丟棄，所以使用者填的**值**沒有洩漏路徑
- `answers` 的鍵在通過 Requirement 1 之前都必須是登記表上的欄位代號，那是系統定義的
  常數，不是使用者自由輸入的內容
- 唯一會出現非登記代號的情況是請求本身就違規（前端送錯代號），此時回報那個代號正是
  除錯所需的資訊，且該代號未被寫入任何持久狀態

加一層鍵名白名單過濾會讓錯誤回應失去除錯價值，換到的隱私改善接近於零。

### 3. `Privacy_Gate` 的 `registry` 參數型別標為 `Any`

`Privacy_Gate` Protocol 與 `Registry_Gate.validate_attributes` 都把 `registry` 標成
`Any` 而非 `FieldRegistry`。理由是 `field_registry` 會 import `app.schemas.session`，
而後者又 import `app.orchestration.state`；為了型別註記加上這條 import 會讓模組相依圖
更難拆。這是型別精確度與模組邊界之間的取捨，不是漏洞。
