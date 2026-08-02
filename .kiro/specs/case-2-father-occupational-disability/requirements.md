# Requirements Document

## Introduction

本功能把「父親職災失能」從只有事件確認的畫面，接成由後端 session workflow 驅動的
完整 vertical slice。自然語言由 LLM 萃取成 `occupational_injury` 與
`long_term_care_need`；確認後的候選項目、問題、篩選與結果來源由後端 repository
提供。本機使用 SQLite，取得 RDS 網路與帳密後可切換至 PostgreSQL adapter。

目前 seed 與 RDS ingestion 內容是可替換的候選資料，不是資格判定捷徑。它沒有經過
官方資料審查，因此所有保留在結果中的項目一律為 `needs_human_review`，不得標成
`eligible` 或 `ineligible`。候選官方摘錄可以顯示供使用者查閱，但不得通過 verified
evidence gate 或支撐資格結論。

## Glossary

- **Case_2_Input**：父親工作事故失能、需要長期照顧，且照顧者因此減少工時的虛構描述
- **Entitlement_Repository**：實作既有 protocol 的 SQLite 或 PostgreSQL 資料查詢層
- **Candidate_Citation**：資料庫中的候選官方摘錄，只供結果頁查閱，不是已驗證資格依據
- **Candidate_Item**：可能相關的福利或行政事項，不代表使用者已符合資格
- **Question_Field**：後端登記、只接受固定選項的去識別化欄位
- **Relevance_Filter**：依結構化答案決定哪些 Candidate_Item 仍與情境相關的確定性條件
- **Session_Snapshot**：後端回給前端的權威流程快照
- **Deterministic_Rules_Engine**：唯一可以產生資格結論的規則引擎；本批不新增正式規則

## Requirements

### Requirement 1: LLM 事件萃取與確認

**User Story:** 身為使用者，我想用自然語言描述父親的職災與照顧處境，確認系統理解到的所有相關事件。

#### Acceptance Criteria

1. WHEN LLM 處理 Case_2_Input, THE backend SHALL 取得 `{"event_ids":["occupational_injury","long_term_care_need"]}`
2. THE LLM SHALL 只負責事件代號，不得產生候選項目、問題、相關性或資格結論
3. THE `event_ids` SHALL contain 1 to 5 unique registered IDs, ordered with the primary event first
4. THE LLM SHALL NOT add `disability_onset` or `caregiver_burden` to Case_2_Input merely because it mentions disability, childcare, or reduced work hours
5. WHEN 事件萃取成功, THE Session_Workflow SHALL 停在 `understand_event` 等待確認
6. THE Session_Snapshot SHALL expose the ordered IDs as `lifeEvents` and SHALL retain `lifeEvent` as the first ID for backward compatibility
7. THE frontend SHALL display both「職業災害」and「長照需求」on the confirmation page
8. WHEN 使用者確認事件, THE Session_Workflow SHALL 依順序展開每個事件的候選項目並以 item ID 去重
9. WHEN 使用者否認事件, THE Session_Workflow SHALL 清除所有事件代號並回到重新描述

### Requirement 2: 後端提供 Case 2 問題

**User Story:** 身為使用者，我希望系統只詢問篩選目前方向所需的問題。

#### Acceptance Criteria

1. WHEN `occupational_injury` 已確認, THE backend SHALL 回傳四個主題、七個 Question_Field
2. THE Question_Field SHALL 包含 `caregiver_relationship`、`disability_cause`、`occupational_injury_recognition`、`care_recipient_insurance_type`、`disability_assessment_status`、`current_care_arrangement` 與 `caregiver_employment_impact`
3. THE Question_Field SHALL 只接受登記表中的固定 option ID
4. IF 任一欄位或選項未登記, THEN THE backend SHALL 拒絕整筆答案且不修改 session
5. THE backend SHALL 不詢問或保存姓名、身分證字號、公司、事故細節、地址、電話或電子郵件
6. THE frontend SHALL 依 Session_Snapshot 的 `questionGroups` 顯示問題，不用 demo scene 推進正式流程
7. WHEN 使用者在 Case 2 第三頁選擇答案, THE frontend SHALL 只暫存選擇且 SHALL NOT 自動送出
8. WHEN 所有必填問題已回答, THE frontend SHALL 啟用明確的「送出答案」按鈕
9. WHEN 使用者按下「送出答案」, THE frontend SHALL 以一筆 `attribute_answers` 請求送出目前整組答案
10. IF `lifeEvents` contains `occupational_injury`, THEN the frontend SHALL use the explicit-submit Case 2 form regardless of that ID's position in the ordered list

### Requirement 3: 確定性相關性篩選

**User Story:** 身為使用者，我希望回答後只保留與父親及照顧者情況相關的辦理方向。

#### Acceptance Criteria

1. WHEN 新的結構化答案被接受, THE Session_Workflow SHALL 以最新 attributes 再次查詢 Entitlement_Repository
2. THE Relevance_Filter SHALL 由固定條件執行，不得呼叫 LLM
3. WHILE 篩選所需欄位尚未回答, THE Entitlement_Repository SHALL 保留可能相關的項目並讓 workflow 繼續提問
4. WHEN 一個項目的固定相關性條件明確不成立, THE Entitlement_Repository SHALL 從後續候選清單移除該項目
5. THE Relevance_Filter SHALL 不把相關性解讀為符合資格

### Requirement 4: Case 2 結果

**User Story:** 身為使用者，我希望最後分別看到父親與照顧者可以繼續確認的方向。

#### Acceptance Criteria

1. THE Entitlement_Repository SHALL 最多提供七個 Case 2 Candidate_Item：追蹤職災認定、職災保險失能給付、身心障礙鑑定、長照需求評估、家庭照顧者支持與喘息服務、照顧者就業支持、支持專線與人工協助
2. WHEN Case_2_Input 的示範答案全部送出, THE result SHALL 保留上述七個項目
3. THE frontend SHALL 依 item ID 將結果分為「給父親（被照顧者）」與「給你（照顧者）」
4. THE result SHALL 顯示資料庫候選資料尚未完成正式規則與官方依據審查
5. EVERY retained Candidate_Item SHALL have status `needs_human_review`
6. THE result SHALL NOT contain fabricated amounts, deadlines, agencies, legal provisions, eligibility conclusions, or application guarantees
7. WHEN Candidate_Citation exists for a retained item, THE result SHALL expose its database title, publisher, URL and excerpt
8. Candidate_Citation SHALL NOT satisfy the verified citation query used by deterministic eligibility evaluation

### Requirement 5: 可替換資料來源

**User Story:** 身為開發者，我希望現在先跑通後端流程，未來接 SQLite 時不用重寫前端或 workflow。

#### Acceptance Criteria

1. THE SQLite and PostgreSQL adapters SHALL implement the existing `EntitlementGraphRepository` boundary
2. THE Session_Workflow SHALL depend on repository contracts rather than fixture constants
3. THE API SHALL expose database `displayName` and `summary` so UUID-based RDS programs do not require frontend ID mappings
4. THE frontend SHALL NOT inspect whether candidates came from SQLite or PostgreSQL to decide the next step
5. THE live frontend SHALL use citations returned in Session_Snapshot and SHALL NOT fall back to frontend legal fixtures
6. THE demo frontend MAY retain fixture provisions because demo mode does not call backend services
7. THE PostgreSQL adapter SHALL translate legacy RDS event IDs such as `work_injury` and `long_term_care` without changing canonical workflow IDs
8. THE implementation notice SHALL continue reporting rule evaluation, verified official citations and action plan as incomplete

### Requirement 6: 重新進入時開始新諮詢

**User Story:** 身為使用者，我希望重新整理或離開諮詢後再次進入時從頭開始，不自動接回舊進度。

#### Acceptance Criteria

1. THE frontend SHALL keep the active `sessionId` only in memory while the consultation component is mounted
2. THE frontend SHALL NOT write the `sessionId` to `localStorage`、`sessionStorage`、cookie 或其他 persistent browser storage
3. WHEN the page is reloaded, THE frontend SHALL show the landing page and SHALL NOT call `/sessions/current` to restore an earlier session
4. WHEN the user leaves the consultation page and later enters it again, THE frontend SHALL create a new session on the next description submission
5. WHILE the user remains on the same consultation page, THE frontend SHALL continue using the same in-memory session for every advance request
6. WHEN the user explicitly selects「重新開始」, THE frontend SHALL still request deletion of the currently active backend session when one exists
7. A backend session abandoned by reload or navigation SHALL expire according to the existing server TTL and SHALL NOT be recoverable automatically by the frontend

## Out of Scope

- 正式 eligibility Rule DSL 與 `eligible`／`ineligible` 結論
- citation 人工審查、RAG 或法律完整性宣稱
- 從第一段自然語言直接萃取七個 Question_Field
- 保存原始描述、session 持久化、AWS deployment 或建立新的雲端服務
- 跨重新整理、跨頁面或跨瀏覽器分頁恢復諮詢進度
