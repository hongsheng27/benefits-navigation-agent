# Technical Design Document

## Overview

Case 2 使用現有 React、FastAPI、session state machine 與 repository protocols。LLM
把自然語言轉成有順序的 `occupational_injury` 與 `long_term_care_need`；後端保留完整清單並維持單數 primary event 相容欄位。

```text
POST life_event_text
  -> LanguageModelPort: {event_ids: [occupational_injury, long_term_care_need]}
  -> SessionSnapshot: lifeEvents[] + primary lifeEvent
  -> 使用者確認
  -> FixtureEntitlementGraphRepository.expand_from_event(...)
  -> FieldRegistry / questionGroups
  -> POST attribute_answers
  -> repository 依最新 attributes 重新展開並做 relevance filter
  -> governance gate: candidate -> needs_human_review
  -> SessionSnapshot.items
  -> React 結果頁
```

## Responsibilities

### LLM

- 只辨識 1 至 5 個已登記、不重複的生命事件代號，主要事件排在第一。
- Case 2 回傳 `occupational_injury` 與 `long_term_care_need`，不把身障方案或減少工時自動當成額外事件。
- 不選問題、不篩選方案、不判斷資格。

### Backend fixture

- 將 `occupational_injury` 展開成最多七個候選項目。
- 依已知結構化 answers 執行固定的 relevance predicates。
- 缺少 predicate 欄位時保留項目，避免過早排除。
- 所有項目的 `program_status` 維持 `candidate`。

### Field registry

- 登記七個欄位、固定選項、用途、主題與 `used_by`。
- `compute_question_groups` 依目前仍 pending 的項目產生問題。
- `RegistryBackedPrivacyGate` 驗證欄位與選項後才寫入 session。

### State machine

- Session 保存 ordered `life_events`，並以第一項同步相容欄位 `life_event`。
- 確認事件後依順序呼叫 repository，以 item ID 去重後取得初始候選清單。
- 每次接受 attributes 後，以完整的最新 attributes 再查 repository。
- 重新查詢時保留仍存在項目的既有判定狀態，移除已明確不相關的項目，加入新出現項目。
- 非 `verified` 項目由既有 governance gate 定案為 `needs_human_review`。

### Frontend

- 正式模式只依 API snapshot 選擇確認、問題與結果畫面。
- 確認頁依 `lifeEvents` 逐項顯示「職業災害」與「長照需求」；問題與結果標題以頓號串接。
- Case 2 的選項先存在 `QuestionGroupList` 的 component state；選項點擊不呼叫 API，只有使用者按下「送出答案」才將整組 answers 送到 backend。
- Case 2 結果依既有 item audience mapping 分成父親／照顧者。
- 中文題目、選項及展示名稱仍由前端 copy mapping 負責；後端擁有欄位、選項與項目 ID。
- Demo mode 與既有 mock scenes 全部保留。

## Fixture Candidate Rules

條件只做「是否相關」篩選，不是資格規則。缺值時條件視為尚未排除。

| Item                                        | 保留條件（欄位已有答案時）                                                       |
| ------------------------------------------- | -------------------------------------------------------------------------------- |
| `occupational_injury_recognition_follow_up` | `disability_cause= cause_occupational_injury` 且認定狀態不是 `injury_recognized` |
| `occupational_accident_disability_benefit`  | 職災原因，且投保為勞保或職災保險                                                 |
| `disability_assessment`                     | 身障鑑定狀態不是 `disability_certificate_obtained`                               |
| `long_term_care_assessment`                 | Case 2 一律保留，等待正式長照規則                                                |
| `caregiver_support_services`                | 親屬照顧，且目前不是完全由聘僱看護承擔                                           |
| `caregiver_employment_support`              | 已離職、減少工時或正在考慮調整工作                                               |
| `caregiver_support_contact`                 | Case 2 一律保留，提供人工出口                                                    |

Case 2 的示範答案會保留七項。

## Data and Privacy

- 原始自然語言只活在單次 LLM 呼叫範圍，不進 state、log 或 response。
- Session 只保存已登記的事件 ID 與固定欄位的 option ID。
- Fixture 不含真實姓名、公司、事故資料或其他 PII。
- 沒有 verified rules 或 verified citations，因此不產生正式資格結論。

## Frontend Session Lifecycle

正式諮詢的 `sessionId` 只放在 `useBackendSession` 的 memory ref。建立 session 後，同一個
component mount 期間的 confirm、answers 與 delete 都重用該 ID；不寫入
`localStorage`、`sessionStorage` 或 cookie。

因此重新整理頁面，或先回產品首頁再重新進入諮詢，都會建立新的 frontend session
context。舊的 backend in-memory session 不會被自動復原，依既有兩小時 TTL 到期；使用者
在同一頁按「重新開始」時仍會立即呼叫 delete endpoint。

## Migration Boundary

未來合併 `origin/feat/databaseV3` 後，以 `SqliteEntitlementGraphRepository` 取代 fixture。
只要 SQLite adapter 維持相同 protocol 與 filtering semantics，前端 API 與 state machine
呼叫流程不需改寫。欄位登記內容之後可移至 SQLite，但本批仍使用既有 reviewed JSON
loader，避免在 `main` 重做未合併分支的 schema。

## Verification

- Backend integration：事件確認後回七個候選項目與七個問題；送出示範答案後得到七個 `needs_human_review`。
- Multi-event extraction：Case 2 的 LLM schema、session snapshot 與確認頁都保留職災與長照兩個事件。
- Backend boundary：明確不符合的結構化答案會移除對應 relevance-only 項目。
- Frontend regression：正式模式使用 API snapshots 從描述走到雙線結果。
- Frontend submit regression：Case 2 選完最後一題仍留在問題頁，按「送出答案」後才發出 `attribute_answers` 並進入結果。
- Frontend session regression：即使瀏覽器存在舊版 `jiezhu.sessionId`，載入後仍停在首頁且不呼叫 restore endpoint。
- Browser：以本機 backend 與 frontend 完整操作四頁。
- Repository hygiene：執行相關 checks 與 `git diff --check`。
