# 後端計畫與進度

最後更新：2026-07-30 ｜ 分支 `feat/backend-privacy-gate`

> 這是後端計畫與進度的**單一來源**。`TXX` 編號只在這裡定義，其他文件引用它。
> 每完成一個階段就更新這份檔案。

---

## 一句話的現狀

契約、端點、狀態機、欄位登記表、缺漏欄位計算、規則引擎轉接、隱私閘門都完成了。
使用者的回答會真的逐項觸發判定，不合法的欄位代號與值都會被拒絕。
但**事件辨識寫死**（一律 `spouse_death`）、**判定是 stub**（湊齊欄位標 eligible，
不會判不符合）、**決定性條件為空**。前端還沒接上。

階段 1 到 3 完成。階段 4 只剩 **T18（接 SQLite）未完成**，被 `feat/databaseV3` 這個
未合併的分支擋著，理由寫在階段 4 那一節。

**現在進行中的是階段 5（接上 LLM）。** T19 到 T23 已依查證結果重新定義（ADR-0015）：
不做 agent 迴圈，改做一個窄的 LLM 隔離層，先接自己的 Gemini，之後可換成 Bedrock。
選它的理由是**它完全沒有被任何人擋住**，而 T18 有。

---

## 排序原則

任務順序**不是按重要性排**，是按兩個問題排：

1. **這件事會不會卡住別人？** 會的先做。
2. **這件事會不會被別人卡住？** 會的往後排。

這是四人小團隊在有限時間內最有效的排法。例如規則引擎（T9）是專案價值核心，
但它需要資料層先改輸出，所以排在後面；而 session 儲存（T3）本身價值不高，
但沒有它前端完全接不上，所以排在前面。

第二個原則的實際效果是：**階段 2 做完之後，整條流程可以在沒有 AWS、沒有網路、
沒有 LLM 的環境下跑完**。這剛好就是 `docs/positioning.md` 的自我檢驗標準
（把 LLM 移除，系統還能不能運作）。

---

## 負責層級

依 `AGENTS.md` 的 learn-by-building boundary：

| 標記 | 意思 |
| --- | --- |
| **負責人** | 核心邏輯，必須由後端負責人實作或密切審查 |
| AI 可做 | 樣板、設定、CRUD、明確的文件 |
| 他人 | 由其他成員負責 |

屬於核心邏輯的範圍：schemas、prompts、工具契約、流程轉換、資格規則、
PII 處理、檢索依據、評測邏輯。

---

## 階段 1：讓前端能動 ✅ 完成

目標是解開前端的阻塞。前端在此之前寫的每一行都在猜後端會回什麼。

| # | 任務 | 狀態 | 負責 | 產出 |
| --- | --- | --- | --- | --- |
| T1 | Workflow state 資料形狀 | ✅ | 負責人 | `orchestration/state.py`、ADR-0011 |
| T2 | 對外契約（後端 + 前端型別） | ✅ | 負責人 | `schemas/session.py`、`types/session.ts` |
| T3 | Session 儲存 | ✅ | AI 可做 | `orchestration/session_store.py` |
| T4 | 四個端點回佔位快照 | ✅ | AI 可做 | `api/sessions.py`、`api/errors.py`、`api/implementation.py` |

**完成判準**：前端能真的呼叫後端拿到結構完整的快照。已達成（手動端到端驗證通過）。

### 階段 1 的額外產出

- `api/errors.py` 不在原本規劃內。加它的理由是 Pydantic 驗證錯誤會把不合法的值
  原文回傳，那是隱私問題不是美觀問題。
- 契約多了 `implementation` 物件，讓前端知道哪些能力還沒實作。
- 走鐘檢查測試會直接讀前端型別檔案比對，防止兩邊不同步。

---

## 階段 2：讓流程真的會走 ✅ 完成

**完全不依賴 AWS、網路、LLM 或資料層。** 這是後端價值最核心的部分。

| # | 任務 | 狀態 | 負責 | 產出 |
| --- | --- | --- | --- | --- |
| T5 | 狀態機轉換與守門條件 | ✅ | 負責人 | `orchestration/state_machine.py`、ADR-0012 |
| T6 | 迴圈護欄（前兩道） | ✅ | 負責人 | 同上 |
| T7 | 欄位登記表機制 | ✅ | 負責人 | `orchestration/field_registry.py`、`data/eligibility_fields/` |
| T8 | 缺漏欄位計算與主題分組 | ✅ | 負責人 | `orchestration/missing_fields.py` |
| T9 | 接上規則引擎並轉成 workflow 形狀 | 🟡 | 負責人 | `orchestration/rule_adapter.py`，決定性條件留空 |
| T10 | 逐項判定的組裝 | 🟡 | 負責人 | `orchestration/determination.py`，stub 版 |

**完成判準**：在沒有網路、AWS、LLM 的環境下跑完整條流程，得到正確判定。
已達成（手動端到端驗證通過：答一個欄位 → `funeral_benefit` 變 eligible，
答齊三個 → `survivor_pension` 也 eligible，停在 `confirm`）。

### 階段 2 的額外產出與修正

- `mock_advance.py` 與它的 16 個測試已刪除，`implementation_notice` 搬到
  `api/implementation.py`。
- `pending` 能力清單從 9 項降到 7 項（移除 `state_machine`、`field_registry`）。
- **修掉一個功能缺漏**：T8 做完了但 `api/sessions.py` 沒有呼叫它，導致
  `questionGroups` 永遠是空的。這個只有端到端驗證才看得出來，單元測試全過。
- **修掉一個判定錯誤**：登記表沒有宣告任何欄位的項目原本被判 `eligible`，
  改成 `needs_human_review`（資料缺漏不等於符合資格）。

### 只做了兩道護欄

| 護欄 | 狀態 |
| --- | --- |
| 迭代上限（6 圈） | ✅ |
| 必須有進展 | ✅ |
| 找不到依據就標人工協助 | 🔴 等 `EvidenceRepository` 接上，因為檢索目前是空操作 |
| 已定案不重跑 | 🔴 等真正的判定，因為 stub 不會重跑 |

### T9 的範圍改過兩次

**原本規劃**：寫一個規則引擎。
**發現**：資料層已經寫了 `app/rules/engine.py`，可運作，還有相關性評分。
**改成**：寫一層轉接，把 `EligibilityResult` 轉成 `CandidateItem`。
**實際完成**：命名、狀態、金額的轉接都做了；**決定性條件留空**，因為規則引擎只回
中文句子。判定邏輯不能散在兩個地方，所以不自己反推 —— 見「被阻擋的項目」。

---

## 階段 3：隱私閘門 ✅ 完成

排在階段 2 之後，但**不能排到最後** —— 階段 4 開始接外部資料和 LLM，
那時如果閘門還沒建好，敏感資料的流向就會失控。

| # | 任務 | 狀態 | 負責 | 產出 |
| --- | --- | --- | --- | --- |
| T11 | 屬性值的型別與選項驗證 | ✅ | 負責人 | `privacy/attribute_gate.py` |
| T12 | 錯誤轉換 | ✅ | 負責人 | 已完整，本輪沒有動程式 |
| T13 | 自由文字只存在第一步 | 🟡 結構已擋 | 負責人 | 延後到 T21，會在那裡完成 |
| T14 | 紀錄檔埋點 | ✅ | AI 可做 | `state_machine.py` 四種事件 |

### 三道防線的現況

| 防線 | 誰擋 |
| --- | --- |
| 欄位**代號**不在登記表上 → 拒絕整筆 | 狀態機的 `_record_answers`（合併進來的 main 已有） |
| 欄位**值**型別或選項不符 → 拒絕整筆 | `RegistryBackedPrivacyGate`（T11 本輪完成） |
| 紀錄檔只接受允許清單上的欄位名稱 | `observability/logging.py`（原本就有） |

T11 補的是中間那道。原本 `PassThroughPrivacyGate` 什麼都不擋，所以送
`{"deceased_insurance_type": "一整段自由文字"}` 會通過 —— 代號合法，值卻是任意文字，
然後被存進 state 再原值回到前端。那正是 ADR-0007 要防的事。

四種型別的檢查：`code` 和 `band` 比對選項清單、`boolean` 只接受真正的布林值、
`integer` 必須是整數**且不能是 `bool`**（Python 的 `True` 是 `int` 的子類別，
不特別擋會通過整數檢查）。

### T12 為什麼沒有動程式

本輪查過四件事都已到位：狀態機三種例外全部被攔並轉成 `ErrorResponse`、
屬性值錯誤在 T11 接上、Pydantic 的 `RequestValidationError` 有專屬 handler
只留欄位路徑、`ApiError` 回契約形狀不包在 `detail` 底下。沒有剩下的工作。

### T14 加了四種事件

| 事件 | 記什麼 |
| --- | --- |
| `state_transitioned` | 每個自動推進的前後狀態 |
| `state_skipped` | 被守門條件跳過的狀態與 `guard` 名稱 |
| `loop_iteration_started` | 迴圈回跳與迭代次數 |
| `loop_guardrail_triggered` | 哪一道護欄中止了流程 |

`state_skipped` 值得說明：沒有這一筆，之後看到流程直接從 `explain_result` 跳到
`complete` 時，無法分辨是守門條件生效還是轉換表寫錯。

### T13 為什麼延後

「不保存原文」目前是靠**沒有那個欄位**達成的，結構上已經擋住。而接收流程還沒真的
用到那段文字 —— 事件辨識是寫死的，根本沒讀它。等 T21 接上 LLM 時一起做，
那時才測得到真實情況。

---

## 階段 4：資料來源介面 🟡 大部分已由他人完成

重點是**跟資料層解耦，不是等資料層**。

**這一段的 T15、T16 不是我們做的** —— 合併進來的 `main` 已經有
`orchestration/protocols.py`、`data_contracts.py`、`source_refresh.py`。
2026-07-30 查證的結果如下：

| # | 任務 | 狀態 | 負責 | 現況 |
| --- | --- | --- | --- | --- |
| T15 | 資料介面定義 | ✅ | 他人 | `protocols.py` 定了五個接縫，比原本規劃的三個多 |
| T16 | 每個介面的假實作 | ✅ | 他人 | 五個離線實作，全部不碰 SQLite |
| T17 | 窄而深的假資料 | ✅ | 負責人 | `demo_fixtures.py`，喪葬給付一項可走到 `eligible`。依 ADR-0014 不是預設值 |
| T18 | 接上真實的 SQLite | 🔴 **未完成** | 負責人 | 四個原因都還在，見下方「T18 為什麼還沒做」 |

### 五個接縫，不是三個

| 介面 | 問什麼 | 接進狀態機了嗎 |
| --- | --- | --- |
| `EntitlementGraphRepository` | 這個事件牽動哪些項目？順序與依賴？ | ✅ |
| `EligibilityService` | 這個項目的判斷條件是什麼？ | ✅ |
| `EvidenceRepository` | 這個項目的依據是哪些文件、哪一段？ | 🔴 欄位留著，`RETRIEVE_RULES` 仍是空操作 |
| `SourceRefreshService` | 本機資料抓到什麼程度？該重抓了嗎？ | ✅ |
| `PrivacyGate` | 這些值可以寫進 state 嗎？ | ✅ 預設換成 T11 的實作 |

如果只有一個「資料層」介面，規則判定就有機會直接去撈文件內容，
兩者糾纏之後就沒辦法單獨測試規則了。

### T17 做了什麼（2026-07-30）

新增 `orchestration/demo_fixtures.py`，把**喪葬給付一項**填到底：資料治理狀態提升為
`verified`、判定回 `eligible`、帶一條決定性條件與一次性金額。其餘三項不動。

`DemoEntitlementGraphRepository` 是包在 `FixtureEntitlementGraphRepository` 外面的
一層，只把示範項目的狀態換掉，不複製那四筆候選清單 —— 複製會讓同一份資料有兩個定義，
其中一份遲早過期。

依 ADR-0014，這些示範資料**不是任何預設值**，HTTP 端點也不注入它們，所以從 API 跑
出來仍然是四項需人工協助。有一個測試專門守這件事：預設路徑若哪天產出 `verified`，
那個測試會失敗。

**沒有做官方依據。** `EligibilityDecision` 沒有依據欄位，依據要走
`EvidenceRepository`，而那個還沒接進狀態機。分開做才各自驗證得出來。

### T18 為什麼還沒做（2026-07-30 實際查證）

**這一段是本輪查證的結果，不是推測。** T18 是階段 4 唯一剩下的任務，四個原因都成立，
其中第二個是新發現的。

**一、這台機器上沒有資料庫。** 全域搜過 `*.db`、`*.sqlite`、`*.sqlite3`，一個都沒有。
`.gitignore` 排除 `*.db`，所以資料庫是本機產物，要靠 `scripts/` 的腳本生成。
`data/benefits/` 目前只有 `.gitkeep`。**沒有東西可以接。**

**二、資料表定義還在未合併的分支上，而且正在改。**
`origin/feat/databaseV3`（三筆 commit，未合併）的內容：

| 檔案 | 變動 |
| --- | --- |
| `backend/app/adapters/sqlite/migrations.py` | 新增約 1020 行 |
| `backend/app/adapters/sqlite/migration_sql/*.sql` | 兩個 migration，約 221 行 |
| `backend/app/orchestration/protocols.py` | 約 +242 行（新增 `CoverageScope`、`CoverageSnapshot`）|
| `determination.py`、`state_machine.py`、`rule_adapter.py`、`source_refresh.py`、`data_contracts.py` | 都有改 |
| `docs/back_database_doc/README.md` | 約 508 行變動，大部分是刪除 |
| `docs/decisions/0013-use-sqlite-runtime-behind-repositories.md` | 新增 |

那個分支做的是 **schema 與 migration 工具**，不是 repository 實作 —— 搜過沒有任何
`class Sqlite*` 實作那四個接縫。所以 T18 本身沒有被別人做掉，但它要依賴的契約
**正在被那個分支修改**。現在寫 adapter 等於對著移動的目標寫。

**三、接上了也看不出差別。** `determination.gated_status` 只讓 `verified` 走完整判定，
而 `benefit_programs` 只有候選狀態的資料。接上 SQLite 之後結果仍然是四項全部需人工
協助，跟現在完全一樣。

**四、落差九未解決。** 規則條件的屬性代號與欄位登記表交集為零
（見 `docs/back_database_doc/README.md`）。接上之後那些項目會永遠停在資訊不足，
而且全程不報錯。

### 一個好消息：人工審查在資料層有地方存了

`feat/databaseV3` 的 migration 建了 `program_status_history` 與 `review_approvals`
兩張表，欄位包含 `reviewer_ref`、`reviewed_at`、`approved_version`，還有一個 trigger
限制 `actor_type` 只能是 `human_reviewer` 或 `migration`。

**那正是 ADR-0014 需要的機制** —— 「有人真的審查過並記錄下來」在資料層有了落點。
所以「拿到真正的 `eligible`」那條路是通的，只是還沒到。

### 這一段實際剩下的工作

1. **催 `feat/databaseV3` 合併。** 它擋著 T18，而 T18 是階段 4 唯一剩下的事。
   合併之前做 T18 都是繞路。
2. **接上 `EvidenceRepository`**：`_do_retrieve_rules` 目前什麼都不做。接上之後
   階段 2 那道「找不到依據就標人工協助」的護欄才有東西可以判斷，示範項目也才會帶
   `citations`。碰撞風險中等（要改 `state_machine.py`，那個分支也改了它）。
3. **T18 接 SQLite**：等上面第 1 項，並且落差九要先有結論。

---

## 階段 5：接上 LLM � 進行中

**T19 到 T23 在 2026-07-30 依查證結果重新定義過**，舊版的任務內容已經不適用。
變更理由見下方「為什麼改掉 T19 到 T23」，決策記錄在 ADR-0015。

| # | 任務 | 狀態 | 負責 | 依賴 |
| --- | --- | --- | --- | --- |
| T19 | LLM port 介面與邊界形狀 | 🔴 | 負責人 | 無 |
| T20 | 離線假實作（`FakeLanguageModel`） | 🔴 | AI 可做 | T19 |
| T21 | `resolve_life_event`（**含原文丟棄，完成 T13**） | 🔴 | 負責人（prompt 屬核心） | T20 |
| T23 | **Gemini adapter**（第一個真實 adapter） | 🔴 | 負責人 | T19 |
| T22 | 白話解釋 | 🔴 | 負責人 | T20、官方依據檢索 |
| T28 | Bedrock adapter | 🔴 | 成員 A | T19 + Bedrock 權限 |

表格順序**就是實際的執行順序**，不是編號順序。T23 排在 T22 前面，理由見下。

### 為什麼改掉 T19 到 T23

**舊版規劃的是 `AgentRunner`** —— 一個帶工具呼叫的 agent 迴圈，用 Strands 實作
（ADR-0004）。查證後認為這一階段不該做 agent 迴圈，改做一個窄的 LLM port：

1. **系統裡只有兩個 LLM 工作，兩個都是單次問答。** 聽懂事件（第 1 步）、把已定案的
   結果翻成白話（第 6 步）。中間的檢索與判定是確定性的，模型不需要決定下一步。
2. **給模型工具反而擴大風險面。** ADR-0003 禁止模型影響資格判定。一個能呼叫工具的
   迴圈就是給了它一條介入的路；不給迴圈，那條路在結構上不存在。
3. **ADR-0004 自己允許。** 它寫「單次結構化任務不需要 agent 迴圈時可以直接呼叫」。

因此 T23 從「Strands / Bedrock adapter」改成「Gemini adapter」，Bedrock 那個往後排成
**T28**（T24 到 T27 已被階段 6 使用，不重號）。

### 兩個 API 的形狀比較（查證結果）

比較 Bedrock Converse API 與 Gemini `generateContent` 之後，**骨架幾乎相同**：

| 概念 | Bedrock Converse | Gemini `generateContent` |
| --- | --- | --- |
| 訊息 | `messages[].role` + `content[].text` | `contents[].role` + `parts[].text` |
| 輸出格式 | `outputConfig.textFormat` | `generationConfig.responseSchema` |
| 描述方式 | JSON Schema | JSON Schema |
| 推論設定 | `inferenceConfig` | `generationConfig` |

三個差異：欄位命名不同（改名即可）、**Bedrock 要求 schema 是字串**
（`json.dumps()` 一行）、**認證機制完全不通用**（Gemini 是 header 放金鑰，
Bedrock 需要 AWS SigV4 簽章，實務上必須用 `boto3`）。

### 寫 schema 的硬規則：只用 Bedrock 支援的子集

**這是這次查證最有價值的結果，寫在這裡是為了讓之後寫 schema 的人不必再查一次。**

Bedrock 只支援 JSON Schema Draft 2020-12 的一個子集。以下**不支援**：

| 不支援 | 意思 |
| --- | --- |
| `minimum` / `maximum` | 不能限制數值範圍 |
| `minLength` / `maxLength` | 不能限制文字長度 |
| 遞迴 schema | 不能自我參照 |
| 外部 `$ref` | 只能參照同一份文件內的定義 |
| `additionalProperties` 不為 `false` | **必須明寫不允許多餘欄位** |

`enum`（值只能是清單裡的其中一個）**支援**，而那正是我們最需要的 —— 我們要模型回的
就是代號。

**所以本專案的 schema 一律只用 Bedrock 支援的功能。** 現在若使用 Gemini 允許但
Bedrock 不允許的寫法，換過去那天會收到 400 錯誤，而且每一個 schema 都要重新設計。

### 隔離層的位置

```
app/llm/
├── port.py     LanguageModelPort（Protocol）與請求／回應的邊界形狀
├── fake.py     FakeLanguageModel，回固定內容，不連網路
├── gemini.py   GeminiLanguageModel（直接打 HTTP，只有這個檔案 import httpx）
└── tasks/      resolve_life_event.py、explain_result.py
```

Port 只負責「送一段提示給模型，拿回符合指定結構的結果」，**不知道**什麼是生命事件。
Prompt 屬於核心資產放在 `tasks/`，廠商細節關在 adapter 裡 —— 換廠商時只動一個檔案，
不必重新決定 prompt。

注入方式與現有接縫一致：`advance()` 的具名參數，預設是 `FakeLanguageModel`，
所以整套測試不需要網路也不需要金鑰。

### 三條不能破的規則

| 規則 | 怎麼強制 |
| --- | --- |
| 模型回來的屬性一律走隱私閘門 | 與使用者直接送答案走同一道檢查，模型不享有特權 |
| 原文送出去但不留下 | 不寫 state（結構上已不可能）、不寫紀錄檔、不回前端。**完成 T13** |
| 解釋不得改結論 | `explain_result` 的回傳型別**只有文字**，沒有 status 欄位 |

另外**刻意不做多輪對話**：每次呼叫獨立，不帶歷史。沒有歷史就沒有「歷史存在哪裡」
的問題，而且不帶歷史的請求在兩邊 API 上形狀最單純。

### 失敗行為刻意不對稱

| 任務 | 失敗時 | 為什麼 |
| --- | --- | --- |
| `resolve_life_event` | **不准猜。** 請使用者從清單挑選，或走人工協助出口 | 事件猜錯，後面七步全錯 |
| `explain_result` | 照樣顯示判定結果，只是沒有白話說明 | 說明是附加的，不能因為它壞掉就不給結果 |

### 為什麼 T22 排在 T23 後面

ADR-0003 要求「用檢索到的官方來源解釋確定性結果」。**目前 `citations` 永遠是空的**
（`_do_retrieve_rules` 是空操作），沒有依據可錨定，模型只能自己編 —— 那是本專案最不能
出的錯。所以順序是先接依據檢索，再做白話解釋。

### 開始前要確認的事

- 新依賴只有 **`httpx`**（HTTP 客戶端），而且**只有 `gemini.py` 會 import 它**，
  所以沒有金鑰的人照樣能跑全部測試。舊版規劃寫的 `google-genai` SDK 不採用，
  理由見 ADR-0015。
- `GEMINI_API_KEY` 只放在本機 `.env`（已 gitignore），`.env.example` 只放變數名稱。
  **沒有金鑰時不得報錯**，要落回 `FakeLanguageModel`。
- 模型代號進設定（`GEMINI_MODEL_ID`），不寫死 —— 模型會下線，寫死之後會突然壞掉
  而且看不出原因。
- T28 開始前要先確認比賽帳號有 Bedrock 權限，並加上 `boto3`。目前後端沒裝。
- 原本 `AGENTS.md` 有「8 月 1 日前不准建立實際的 AWS 連線」這條規則，**現在已經解除**。

---

## 階段 6：收尾 🔴 未開始

| # | 任務 | 狀態 | 負責 |
| --- | --- | --- | --- |
| T24 | 七種出口路徑的處理 | 🔴 | 負責人 |
| T25 | 辦理清單組裝（順序、依賴、期限、文件） | 🔴 | 負責人 |
| T26 | 端到端測試 | 🔴 | AI 可做 |
| T27 | 轉介窗口資料 | 🔴 | 與資料層協調 |

---

## 被阻擋的項目

| 任務 | 在等什麼 | 等誰 | 影響 |
| --- | --- | --- | --- |
| T9 | 規則引擎輸出**結構化的決定性條件**，而不是中文句子 | 資料層 | 沒有它，「差在哪個條件」做不出來，而那是專案最強的差異點 |
| T9 | 規則欄位增加**發放性質**（一次性／按月／按年） | 資料層 | 遺屬年金是按月、喪葬給付是一次性，這無法從金額數字推斷 |
| T18 | `feat/databaseV3` 合併（schema 與 migration 在那上面） | 資料層 | **最直接的阻塞**。本機沒有任何 `.db` 檔案，資料表定義也還沒進 `main` |
| T18 | `benefit_programs` 填入正式方案 | 資料層 | 目前那張表只有候選狀態的資料 |
| T18 | 落差九：規則條件的屬性代號與欄位登記表統一 | 兩邊 | 不解決的話接完會表現成「問完了還是沒結論」而且不報錯 |
| T23 | Bedrock 帳號權限確認 | 成員 A | 沒確認之前無法驗，但已經沒有日期限制 |
| T7 | 欄位登記表的**正式**欄位與選項（目前是三筆 draft） | 政策資料負責人 | 前端可以先接，但問的問題不是最終版本 |
| T25 | Entitlement graph 的順序與依賴資料 | 政策資料負責人 | 辦理清單的那個「完成後才能辦」箭頭做不出來 |

**最擋人的兩項是欄位登記表（T7 的內容）和 entitlement graph。** 兩者都是資料，
不是程式，需要有人去讀法規。

---

## 建議的下一步順序

| 順序 | 做什麼 | 理由 |
| --- | --- | --- |
| 1 | **T19 + T20**：LLM port 與假實作 | 不連網路、不加依賴。做完之後所有 LLM 相關的工作都能離線開發與測試 |
| 2 | T21 `resolve_life_event` | 用假實作先做通，順便完成 T13（原文丟棄） |
| 3 | T23 Gemini adapter | 第一次真實連線，驗證 T21 對真模型也成立 |
| 4 | 接上 `EvidenceRepository` | `_do_retrieve_rules` 是空操作，接上之後第三道護欄才成立，示範項目也才會帶官方依據 |
| 5 | T22 白話解釋 | 必須排在依據之後，否則模型沒有東西可錨定 |
| 6 | **前端接上那四個端點** | 後端做好了但沒人用。不是後端的工作，但應該優先推動 |
| 7 | 跟資料層談落差九 | 代號對不上，不解決的話 T18 接完會表現成「問完了還是沒結論」而且不報錯 |
| 8 | T18 接真正的 SQLite 規則引擎 | 等 `feat/databaseV3` 合併，且落差九要先有結論 |

順序改成 LLM 先做的理由：**T18 被別人的分支擋著，而 LLM 這一段完全沒有被任何人擋。**
在等待期間做被擋住的事只會繞路。

---

## 範圍變更紀錄

| 日期 | 任務 | 變更 | 原因 |
| --- | --- | --- | --- |
| 07-27 | T9 | 從「寫規則引擎」改成「寫轉接層」 | 資料層已經寫了 `rules/engine.py` |
| 07-27 | T1 | 追加金額四個欄位 | 原本沒有地方放金額，會出現「判定符合但金額傳不到畫面」 |
| 07-27 | T4 | 從三個端點變成四個 | 加上 `DELETE`，對應畫面上的「現在就清除」 |
| 07-27 | T2 | 追加 `implementation` 物件 | 讓前端能標示佔位資料 |
| 07-28 | T12 | 部分提前完成 | HTTP 層的錯誤轉換在 T4 就必須做，否則驗證錯誤會外洩使用者輸入 |
| 07-28 | T6 | 從四道護欄縮成兩道 | 另外兩道要等檢索與判定有真正內容才會發生 |
| 07-29 | T9 | 決定性條件確定留空 | 判定邏輯不能散在兩個地方，等資料層輸出結構 |
| 07-29 | T10 | 加上「資料缺漏」的處理 | 登記表沒宣告欄位的項目原本被判 eligible，改為 needs_human_review |
| 07-30 | T11 | 從「屬性允許清單」改成「值的型別與選項驗證」 | 代號的允許清單檢查在合併進來的 `main` 已經有了（`_record_answers` 會拋 `UnknownFieldError`），剩下沒人擋的是值本身 |
| 07-30 | T12 | 查證後確認已完整，沒有動程式 | 四個環節都已到位，寫程式只會是重複的 |
| 07-30 | T13 | 延後到 T21 | 事件辨識目前寫死，沒有讀那段文字，測不到真實情況 |
| 07-30 | T15、T16 | 由他人完成，我們只做查證 | 合併進來的 `main` 已有 `protocols.py` 與五個離線實作 |
| 07-30 | T17 | 官方依據移出範圍 | 依據要走 `EvidenceRepository`，那條線還沒接。分開做才各自驗證得出來 |
| 07-30 | ADR-0014 | 決定句從「示範資料一律不得標 `verified`」改成「預設路徑不得產生 `verified`」 | 原句執行不了：`gated_status` 只讓 `verified` 走完整判定，照字面做的話示範連 `ineligible` 都到不了 |
| 07-30 | T19、T20 | 從 `AgentRunner`（agent 迴圈）改成窄的 LLM port | 只有兩個單次問答任務；給模型工具會擴大它影響資格判定的風險面。見 ADR-0015 |
| 07-30 | T23 | 從「Strands / Bedrock adapter」改成「Gemini adapter」 | 先接自己的 Gemini 驗證整條路，Bedrock 往後排成 T28 |
| 07-30 | T22 | 依賴增加「官方依據檢索」 | 沒有依據可錨定的解釋等於讓模型自己編法規 |
| 07-30 | 階段 5 依賴 | 從 `google-genai` SDK 改成直接打 HTTP（`httpx`） | 送出去的內容要能在一個函式裡看完，這是隱私可稽核性的要求。見 ADR-0015 |
| 07-30 | T28 | 新增 | Bedrock adapter 從 T23 拆出來獨立排序 |

---

## 合併時要注意的衝突（2026-07-30）

`feat/databaseV3` 跟本分支合併會產生**兩個衝突，都在文件上**。實際跑過
`git merge-tree`（只算不寫）的結果：

```
CONFLICT (content): docs/back_database_doc/README.md
CONFLICT (content): docs/decisions/README.md
```

程式碼檔案全部乾淨自動合併。兩個衝突的內容：

| 檔案 | 兩邊各做了什麼 |
| --- | --- |
| `docs/back_database_doc/README.md` | 我們加了落差九與幾段狀態更新；那個分支大改這份文件 |
| `docs/decisions/README.md` | 我們加了 ADR-0014 那列與編號說明；那個分支加了 ADR-0013 那列 |

**解衝突時不要整段挑一邊。** 落差九是新資訊，那個分支不知道它存在；ADR-0013 與
ADR-0014 是兩份不同的決策，索引裡兩列都要留。

---

## 已知的技術債

| 項目 | 說明 | 何時處理 |
| --- | --- | --- |
| `state_machine.py` import `schemas/` | 流程層依賴傳輸層，依賴方向錯了。`mock_advance.py` 刪除後這個問題**轉移到了 state_machine**，沒有消失。正確做法是把七種輸入的種類定義在 `orchestration/`，讓 `schemas/` 投影它 | 未分配 |
| 登記表快取是模組層的全域變數 | `default_registry()` 讀一次就快取，重讀磁碟的問題解決了。但快取放在模組層而不是 `app.state`，意思是同一個行程裡無法讓兩個 app 實例用不同的登記表 | 未分配，目前只有一個實例 |
| `placeholderNotice` 是後端提供的中文文案 | 違反「後端給代號、前端給文案」的分界 | 佔位資料移除時一起刪 |
| ADR-0005 的文字落差 | 它把轉換歷程列為後端狀態，我們記在紀錄檔 | 已在程式註記，ADR 未改 |

### 已解決（2026-07-30 查證）

這四筆是合併進來的 `main` 修掉的，不是本輪的工作，列出來避免有人以為還存在：

| 原本的問題 | 現況 |
| --- | --- |
| 完整測試套件跑不起來（資料層 import 路徑） | `uv run pytest -q` 從 `backend/` 跑，232 passed |
| Windows 上 7 個資料層測試失敗（sqlite 連線沒關） | 已無失敗 |
| 資料層 4 個檔案未通過 `ruff format` | 60 個檔案全部通過 |
| `determination.py` 每次請求重讀 JSON | `default_registry()` 快取，兩個呼叫點都改用它 |

---

## 未決事項

需要決定但目前不急的：

- 相關性分數（`relevance_score`）要露給前端，還是只用順序隱含表達（待 T9）
- 「我不確定」在契約上怎麼表達：一個保留的選項代號，還是不送該欄位
- 互斥福利（領了 A 就不能領 B）怎麼表達（待 T9）
- 辦理清單是儲存下來還是需要時即時推導（待 T5）
- **問題分組的總數會跳動**：目前 `group_total` 是「還有缺漏的主題數」，所以答完一組
  之後總數會變小（3 之 3 → 2 之 2）。使用者看到「共 3 組」變成「共 2 組」可能會困惑。
  要改成「一開始就算出固定總數」還是接受跳動，未決定
- 暫時性錯誤（網路斷、模型超時）怎麼標記（待 T19）
- Session 的正式持久化方案，以及是否需要狀態 schema 版本
- Entitlement graph 用什麼形狀：JSON 還是資料表
- 欄位登記表放哪、由誰維護

---

## 相關文件

| 文件 | 內容 |
| --- | --- |
| `docs/backend/feat-frontend-backend-contracts.html` | 本分支的完整說明，含後端架構攤開、已知的坑 |
| `docs/backend/backend-overview.html` | 後端 workflow 層的常態說明 |
| `docs/front_back_doc/README.md` | 前後端已定案的約定與待確認事項 |
| `docs/back_database_doc/README.md` | 後端與資料層的五個形狀落差 |
| `docs/decisions/0007-limit-data-retention-and-egress.md` | 資料保存與外送的限制，隱私閘門的依據 |
| `docs/decisions/0011-frozen-pydantic-session-workflow-state.md` | 狀態形狀的決策與已知限制 |
| `docs/decisions/0012-deterministic-state-machine-with-guardrails.md` | 狀態機的三張宣告表與護欄的決策 |
| `docs/decisions/0014-keep-fixture-data-out-of-verified-status.md` | 示範資料不得標成已核對，以及 T17 為什麼這樣做 |
| `docs/aws_migration_guide.md` | AWS 遷移說明的唯一來源 |
| `backend/README.md` | 啟動與測試指令，含兩個環境坑 |
