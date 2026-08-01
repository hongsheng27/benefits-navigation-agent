# 後端 ↔ 資料層 溝通紀錄

這份文件記錄後端 workflow 層與資料層（政府來源、補助 catalog、規則引擎）之間的
交界：**對方提供什麼、我需要什麼、形狀哪裡對不上**。

- 資料層的完整說明見 `docs/architecture-overview.html` 與 `docs/data-model.md`。
- 後端 workflow 層的說明見 `docs/backend/backend-overview.html`。
- 這份文件與程式衝突時，**程式為準**。
- 最後更新：2026-07-30（第二次）

> **2026-07-30 第二次更新：對資料層沒有新的要求。** 後端這一輪接上了語言模型
> （事件辨識），那一段完全不碰資料層的任何契約。三件對資料層可能有意義的事：
>
> 1. **生命事件代號現在有一份登記表**：`data/life_events/events.v0.1.json`，
>    目前三筆（`spouse_death`、`parent_death`、`child_death`）。這是**暫行安排** ——
>    嚴格說事件集合屬於 entitlement graph，見五之三。
> 2. **後端已經能真的把一段話變成事件代號**，所以 `expand_from_event` 收到的
>    `event_id` 不再永遠是 `spouse_death`。SQLite 實作要能處理認不出的事件（回空序列）。
> 3. 落差九（規則條件的屬性代號與欄位登記表交集為零）**仍然未解決**，
>    而且現在更要緊：使用者的答案已經真的會流進判定了。

---

## 一、分工界線

| 層 | 負責回答 |
| --- | --- |
| 資料層 | 世界上有哪些補助、條件是什麼、依據在哪 |
| 規則引擎 | 這組屬性符不符合某個方案 |
| Workflow 層 | 現在該問什麼、能不能往下一步、什麼時候該停下來找人 |

**Workflow 層不判斷資格。** 判定權在規則引擎，這是 ADR-0003 的要求。

---

## 二、當前狀態

### 資料層已經提供的

| 東西 | 位置 | 狀態 |
| --- | --- | --- |
| 政府機關 OID | `government_organizations` | ✅ 可用 |
| 來源白名單與同步紀錄 | `source_registry`、`source_sync_runs` | ✅ 可用 |
| 已下載的官方頁面 | `source_documents` | ✅ 可用 |
| 補助方案 | `benefit_programs` | 🟡 有資料，多為候選狀態 |
| 方案證據（含引用段落） | `program_sources` | 🟡 同上 |
| 機關角色 | `program_organization_roles` | 🟡 同上 |
| 結構化規則欄位 | `program_rule_fields` | 🟡 有資料 |
| 轉接層（rule adapter） | `backend/app/orchestration/rule_adapter.py` | ✅ 完成（條件留空） |
| 跨層資料格式 | `backend/app/orchestration/data_contracts.py` | ✅ 完成（提案第 7 節逐字實作） |
| 四個資料層接口與離線實作 | `backend/app/orchestration/protocols.py` | ✅ 完成（沒有 SQLite 實作） |
| 來源刷新流程組裝 | `backend/app/orchestration/source_refresh.py` | ✅ 完成（本機佇列，不抓網路） |
| 逐項判定組裝 | `backend/app/orchestration/determination.py` | 🟡 安全檢查與單項失敗隔離已完成，真正的判定等資料層交出 `EligibilityService` 的 SQLite 實作 |
| 欄位登記表機制 | `backend/app/orchestration/field_registry.py` | ✅ 完成 |
| 缺漏欄位計算 | `backend/app/orchestration/missing_fields.py` | ✅ 完成 |
| 通用規則引擎 | `backend/app/rules/engine.py` | ✅ 可運作 |
| 相關性評分與排序 | `engine.py` 的 `compute_relevance_score` | ✅ 可運作 |
| 審查介面 | `scripts/review_server.py` | ✅ 可用 |

### Workflow 層需要但還沒有的

| 需要什麼 | 用在哪一步 | 現況 |
| --- | --- | --- |
| **Entitlement graph** — 事件對應哪些項目、彼此的前後順序與依賴 | 第 2 步展開項目、第 8 步排辦理順序 | ❌ `data/entitlement_graph/` 是空的 |
| **欄位登記表** — 有哪些資格欄位、型別、選項、為什麼問 | 第 3 步組出問題卡 | 🟡 機制完成，內容是三筆 draft |
| **項目層級的規則** — 不只是方案，也包含行政事項的適用與期限 | 第 5 步判定 | 🟡 只有方案的規則欄位 |
| **可依項目取得的官方依據** | 第 4 步檢索 | 🟡 `EvidenceRepository` 介面與離線實作已備好，但 `state_machine._do_retrieve_rules` 仍是空操作 —— 資料層還沒交出實作，後端不會編造依據 |

**最擋人的是 entitlement graph 和欄位登記表。** 沒有前者，使用者說「我先生過世」後
系統不知道要展開哪些項目；沒有後者，系統不知道要問什麼。

---

## 三、後端會怎麼取用資料層

**後端不會直接寫 SQL 撈 catalog。** 已依提案第 6 節定義**四個**接口
（`backend/app/orchestration/protocols.py`），各自對應一種問題：

| 接口 | 問什麼 | 離線實作 |
| --- | --- | --- |
| `EntitlementGraphRepository` | 這個事件展開哪些項目？前置與後續關係是什麼？某個制度底下有哪些方案？ | `FixtureEntitlementGraphRepository` |
| `EligibilityService` | 這一項需要哪些欄位？判定單一項目、判定多個項目 | `FixtureEligibilityService` |
| `EvidenceRepository` | 這一項的官方依據是哪些文件、哪一段？ | `FixtureEvidenceRepository` |
| `SourceRefreshService` | 來源目前抓到什麼程度？把來源排入更新 | `LocalSourceRefreshService` |

分成多個而不是一個的理由沒有變：如果只有一個「資料層」介面，規則判定就有機會直接去
撈文件內容，兩者糾纏之後就沒辦法單獨測試規則了。四個接口切在四項責任上（圖、判定、
證據、來源刷新），任一項換實作不影響其他三項。

四個接口都有**不連資料庫的離線實作**，所以後端的 280 個測試不需要資料庫就能跑，
也不需要等資料層完成才能開發。

`protocols.py` 裡還有第五個 `Protocol` 叫 `PrivacyGate`，**它不是資料層接口**，
不要把它算進上表。它管的是「使用者送來的值可不可以寫進 state」，跟資料層無關。
預設實作在 2026-07-30 從 `PassThroughPrivacyGate`（原樣放行）換成
`app.privacy.attribute_gate.RegistryBackedPrivacyGate`（依欄位登記表驗證型別與選項），
這個改動對資料層有一個後果，見落差九。

**目前沒有任何連 SQLite 的實作** —— 那是資料層要交的東西。依提案第 6 節，repository
一律回傳 `app.orchestration.data_contracts` 的 domain dataclass，**不得回傳
`sqlite3.Row`、SQL tuple 或未解碼的 `metadata_json`**。這條規則是「workflow 不依賴
資料表欄名」的具體執行方式。

注入點是 `state_machine.advance()` 的具名參數（全部可省略，預設就是上表的離線實作），
換實作不需要改狀態機。

### 目前接上了什麼

- **規則引擎轉接層**已完成（`orchestration/rule_adapter.py`）。三個方向：
  `adapt_graph_candidate`（圖上的候選方案 → workflow 項目）、`apply_decision`
  （`EligibilityDecision` → workflow 項目）、`adapt_result`（SQL 規則引擎的
  `EligibilityResult` → workflow 項目）。決定性條件與 `amount_period` 仍留空。
- **逐項判定組裝**已完成安全檢查與單項失敗隔離（`orchestration/determination.py`），
  真正的判定改成呼叫注入進來的 `EligibilityService`。接上 SQLite 時只需要注入資料層
  的實作，這個模組不用改。
- **欄位登記表**已完成（`orchestration/field_registry.py` 讀
  `data/eligibility_fields/fields.v0.1.json`），三筆種子欄位。
- **缺漏欄位計算**已完成（`orchestration/missing_fields.py`），可直接產出
  `QuestionGroupView` 給前端。

## 三之二、跨層資料格式

`backend/app/orchestration/data_contracts.py` 是依提案第 7 節**逐字實作**的邊界格式。
它不是 SQLite schema，也不是對外 API 契約，只是兩層之間交換資料的形狀。

七個 dataclass（全部 `frozen`）：

| dataclass | 內容 |
| --- | --- |
| `GraphRelation` | 圖上的一條關係：`item_id`、`display_name`、`order` |
| `CandidateItem` | 資料層交出的候選方案，含 `program_status`、`relevance_score`、前後關係 |
| `StructuredReason` | 造成某個結論的單一條件，七個欄位 |
| `EligibilityDecision` | 某一項的判定結果，金額拆成上下限、週期、幣別 |
| `Citation` | 官方依據，八個欄位 |
| `FieldRegistryEntry` | 提問用的共同詞彙表一筆 |
| `CoverageMetadata` | 一個來源目前的抓取進度 |

三組固定值：`ProgramStatus`（六個值）、`EligibilityStatus`（四個值）、
`AmountPeriod`（`one_time`／`monthly`／`annual`）。

### 一個容易混淆的地方：兩個 `CandidateItem`

`data_contracts.CandidateItem` 與 `state.CandidateItem` **同名但語意不同**：

| | 回答什麼 | 帶什麼 |
| --- | --- | --- |
| `data_contracts.CandidateItem` | 資料層有什麼、可信到什麼程度 | `program_status`、`relevance_score`、`prerequisites`／`produces` |
| `state.CandidateItem` | 這位使用者這一項的結論是什麼 | `ItemStatus`、缺哪些欄位、決定性條件、金額 |

**兩者不能互換。** 資料層不知道也不該決定使用者的判定結果，workflow 也不該決定一筆
資料可不可信。轉換在 `rule_adapter.adapt_graph_candidate`，新項目一律從 `PENDING`
開始。

## 三之三、資料可信程度的安全檢查

依提案第 8 節，`determination.py` 現在依 `program_status` 決定能對一筆方案做到什麼
程度：

| `program_status` | 後端行為 |
| --- | --- |
| `verified` | 執行完整確定性判定 |
| `candidate`／`under_review` | 可以顯示，但不做完整判斷，一律回 `needs_human_review` |
| `rejected`／`inactive` | 隱藏，不進入候選結果，也不進入資格評估 |
| `stale` | **暫行**回 `needs_human_review`，見待確認事項第 10 項 |

另外，單一項目判定失敗（規則引擎拋例外）只會把那一項標成 `needs_human_review`，
其餘項目照常判定 —— 一次諮詢通常同時展開四、五項，讓一項的資料問題連帶讓整份清單
失敗，使用者會從「有三項可以辦」變成「什麼都沒有」。

### 兩件要記清楚的事

1. **`stale` 還沒定案。** 它是提案第 12 節第 2 項的待決事項，原文寫「任何一方都不得
   靜默選擇」。後端目前採較安全的那一端（等同方案 B 的效果），程式裡標成**暫行**
   （改 `determination._STALE_FALLBACK_STATUS` 一處即可），**不是已定案的決策**。
   兩個候選方案是：**方案 A** 用最後一次驗證過的快照加明確警告、**方案 B** 一律降級。

2. **這個檢查造成一個看得到的行為變化。** `FixtureEntitlementGraphRepository` 的四筆
   示範資料依提案第 14 節標為 `candidate`（crawler 與 LLM 只能建立候選資料），所以
   離線跑完整流程時**四項全部回 `needs_human_review`，不會再出現 `eligible`**。
   這是照提案的必然結果，不是 bug。

   後端在 2026-07-30 把這件事寫成正式決策
   （[ADR-0014](../decisions/0014-keep-fixture-data-out-of-verified-status.md)）：
   **示範資料一律不得標成 `verified`**，只有真的有人讀過法規、確認條件與依據並記錄
   審查之後才可以。所以離線流程走不到 `eligible` 是刻意維持的，不會為了讓示範好看
   而放寬。要拿到真正的 `eligible`，需要資料層那邊至少有一項經過人工審查 ——
   因為示範資料本來就窄，**一項就夠了**。

---

## 四、形狀落差

規則引擎的 `EligibilityResult` 與 workflow 層的 `CandidateItem` 都有四種判定狀態，
但其餘形狀還沒對齊。以下八項需要協調，其中**金額轉接已完成**，**命名轉接已完成**；
落差六、七、八是比對 `benefit_catalog.py` 的建表語句與提案契約後新發現的。

### 落差一：金額 — 形狀已補上，轉接已做（period 除外）

規則引擎回 `amount`（單一整數）與 `amount_label`（例如 `10000~20000`）。轉接層把
`amount` 映射到 `amount_min` 和 `amount_max`（兩者填同一個值），`amount_currency`
有值時固定為 `TWD`。Workflow 層已補上 `amount_min`、`amount_max`、`amount_period`、
`amount_currency` 四個欄位，決策見 ADR-0011 修訂一。**刻意不收 `amount_label`**，
因為那是給人看的文字，屬於前端；後端只給結構。

還需要協調的：

- 規則引擎的 `_evaluate_amount` 在 `min_amount == max_amount` 時回單一值、不相等時
  回 `None` 加一個字串。後端需要的是兩個數字都拿到，不是字串。
- **`amount_period` 仍然留空**：發放性質（一次性／按月／按年）目前不在規則欄位裡。
  遺屬年金是按月的、喪葬給付是一次性的，這個差別無法從金額數字推斷。需要在
  `program_rule_fields` 增加一個欄位。

### 落差二：`reasons` 是文字，workflow 層需要結構

規則引擎回的是 `reasons: list[str]`，內容是中文句子，例如 `需設籍該縣市`。

Workflow 層需要的是三段結構：**哪個欄位、要求什麼、實際什麼**。因為結果畫面要顯示
「差在這個條件：你的情況 X ／ 需要 Y」。

只有整段文字的話，前端只能原封不動印出來，那個對照就做不出來 —— 而那是整個專案最強
的差異點。也是「不符合必須說得出差在哪一個條件」這條約束的載體。

**這一項後端無法單方面補**，需要規則引擎在判定為 `ineligible` 時額外輸出結構化的
決定性條件。

**接收端的形狀後端已經定好了。** `data_contracts.StructuredReason` 有七個欄位：
`condition_id`、`field_id`、`operator`、`expected`、`actual`、`label`、
`source_reference`。`rule_adapter._decisive_conditions` 會把它轉成 workflow 的
`DecisiveCondition`，但**型別對不上的整筆略過**：`StructuredReason.expected` 與
`actual` 的型別是 `Any`（可能是巢狀的條件 JSON），而 `DecisiveCondition` 只接受
布林、整數、字串。不硬轉成字串 —— 錯的「差在哪一條」比不顯示更糟。

**要特別寫明的後果**：因為規則引擎目前不輸出結構化條件，決定性條件恆為空，
`downgrade_unexplained_ineligible` 會把所有「不符合但說不出決定性條件」降級為
`needs_human_review`。也就是說**現階段系統不會回報任何「不符合資格」**。這是刻意的
取捨（沒有理由的「你不符合」比轉人工更糟），等資料層開始輸出結構化條件就會自動停止
觸發，**不需要再改程式**。

### 落差三：相關性評分沒有對應的欄位

規則引擎新增了 `relevance_score`（0 到 100）與 `compute_relevance_score`，用結構化
欄位匹配算分，`evaluate_all_programs` 依分數由高到低排序。README 已把它標為**已實作**。

這是好事 —— 排序是確定性的、可解釋的，不依賴 LLM，跟本專案的主張一致。

邊界格式已經有位置放它：`data_contracts.CandidateItem.relevance_score`，型別是
`int | float | None`。但 `rule_adapter.adapt_graph_candidate` **刻意不把它搬進
workflow 形狀**，理由是它只代表相關性、不代表符合資格的程度（提案第 7 節），而
`state.CandidateItem` 沒有任何欄位承載排序分數 —— 硬塞一個進去會讓下游有機會把它
讀成「有多符合」。

所以 workflow 層目前仍然接不到：

- `state.CandidateItem` 沒有放分數的欄位
- 對外的 `SessionSnapshot.items` 是一個清單，順序由後端決定，但**沒有任何欄位說明順序
  的依據**。前端無法分辨「這是相關性排序」還是「這只是查詢回來的順序」

另外要記一筆：`rules/engine.py` 的 `EligibilityResult.relevance_score` 預設值是 `0`
而不是 `None`，所以**無法區分「沒有計算相關性」與「算出 0 分」**。邊界格式那一邊允許
`None`，接上時需要決定 `0` 要對應哪一種。

要決定的是：**分數要露給前端，還是只用順序隱含表達。**

- 露出分數：前端可以標「最相關」或顯示排序理由，但也可能被誤讀成「符合程度」——
  那是兩件不同的事（相關性高不等於符合資格）
- 只給順序：契約簡單，但前端無法解釋為什麼這樣排

留到 T9（接上規則引擎）再決定，因為那時才會真的有分數流進來。

### 落差四：欄位命名不一致 — 已由轉接層處理

| 規則引擎 | Workflow 層 | 轉接方式 |
| --- | --- | --- |
| `program_id` | `item_id` | 直接映射 |
| `program_name` | 前端自己提供文案 | 不轉 |
| `missing_inputs` | `missing_field_ids` | 直接映射 |
| `source_url`（單一字串） | `state.Citation`（六個欄位的結構） | 組成最小的 Citation（只有 URL 與標題） |
| `status`（純字串） | `ItemStatus`（列舉） | 查對照表，未知字串降級為 `NEEDS_HUMAN_REVIEW` |

不要求資料層改名。轉接集中在 `orchestration/rule_adapter.py` 一個函式裡。

`source_url` 那一項值得注意：workflow 層需要的是文件代號、標題、發布機關、發布日期、
網址、引用段落六項，因為畫面上要顯示「依據：〈條例名稱〉第 X 條，官方連結，發布日期」。
這些欄位 `source_documents` 與 `program_sources` 都已經有，只是規則引擎目前只往外
傳一個網址。

**邊界格式的 `Citation` 比 workflow 內部的多兩個欄位、改了一個名字。**
`data_contracts.Citation` 有八個欄位：`document_id`、`title`、`publisher`、
`published_at`、`effective_at`、`url`、`excerpt`、`retrieved_at`；
`state.Citation` 只有六個（`document_id`、`title`、`publisher_name`、`published_at`、
`url`、`excerpt`），沒有 `effective_at` 與 `retrieved_at`，且發布機關叫
`publisher_name`。差異是刻意的：提案要求邊界格式保留生效時間與擷取時間，讓「這份依據
什麼時候抓的、什麼時候生效」可以被追問。補齊 `state.Citation` 屬於**對外契約那一批**
（要同步改前端型別），擁有者決定晚點做。

### 落差五：`reasons` 裡嵌入了使用者提供的值（隱私）

這一項是我在讀 `engine.py` 時發現的，需要提出來。

規則引擎目前有這樣的寫法：

```python
reasons=[f"不適用此骨灰骸類型: {user_type}"]
```

`user_type` 來自使用者提供的屬性。也就是說**這個字串裡混入了使用者的值**。

為什麼要在意：ADR-0007 規定紀錄檔只能記結構化欄位，使用者提供的值永遠不進紀錄檔。
`app/observability/logging.py` 已經在程式層強制這件事 —— 它的允許欄位清單裡沒有任何
欄位可以放值。

但如果有人寫 `log_event(..., 某欄位=result.reasons)`，那個值就會跟著進去。目前
`reasons` 不在允許清單裡，所以會被擋下來；風險是**未來有人為了除錯把它加進清單**，
那時候就不會有人記得裡面混著使用者的值。

建議的處理方式：規則引擎輸出結構化的決定性條件（落差二），值放在獨立欄位而不是句子
裡。這樣落差二和落差四會一起解決。

### 落差六：沒有存福利前後順序的表

`EntitlementGraphRepository.expand_from_event` 與 `get_prerequisites` /
`get_produces` 需要圖的**節點與邊**，但 `benefit_catalog.py` 建的表只有
`source_registry`、`source_sync_runs`、`source_documents`、`document_discoveries`、
`benefit_programs`、`program_sources`、`program_organization_roles` 等，**沒有任何
地方存這個關係**。

提案第 2 節把「關聯式 Entitlement Graph nodes／edges 與雙向遍歷」列為新範圍，目前
還沒建。後端這邊只有一份寫死的離線對照表
（`protocols._FIXTURE_ITEMS_BY_EVENT`，四筆，只有配偶過世情境）。

這與待確認事項第 1 項（entitlement graph 用什麼形狀）是**同一件事**，兩邊要一起決定。

### 落差七：`benefit_programs.program_status` 多了一個值

實際的 CHECK 約束允許**七個**值：`candidate`、`under_review`、`verified`、`rejected`、
`stale`、`inactive`、**`status_unknown`**。

提案第 7 節的 `ProgramStatus` 只有前六個，後端的 `data_contracts.ProgramStatus` 照抄
提案，也只有前六個。

如果真的接上，遇到 `status_unknown` 時後端會走「未知狀態安全降級」那條路，變成
`needs_human_review`（`determination.gated_status` 對非 `verified` 的值一律不做完整
判定）。功能上不會壞，但那是降級不是設計。

需要確認：**資料層移除這個值，還是提案補上它。**

### 落差八：抓取進度缺兩個欄位

`CoverageMetadata` 需要 `domain_tags`（這個來源屬於哪些主題，用來挑出與事件相關的
來源）以及判斷到期用的「多久該重抓一次」。`source_registry` 目前**沒有這兩個欄位**。

後端暫時把它們放在 `protocols.LocalSourceRecord`（本機來源表）。其中
`check_frequency_days` **刻意不放進 `CoverageMetadata` 契約**：「多久該重抓」是來源
自己的設定，不是可量測的抓取進度，所以到期判斷屬於持有來源表的 service，不屬於拿到
coverage 的呼叫端。

接上真實資料時，`source_registry` 需要補這兩個欄位。

### 落差九：規則條件用的屬性代號，欄位登記表上一個都沒有

**這是接上 SQLite 之前一定會撞到的落差。** 2026-07-30 發現。

規則引擎的屬性代號**不是寫死在 `engine.py` 裡的**，是從資料庫的條件字串當場解析出來
的。`_evaluate_condition` 收到像 `remains_type=ash AND source=X` 這樣的字串，用 `=`
切開，左邊當成 `user_attrs` 的鍵去查。所以**規則資料寫什麼代號，引擎就要求什麼代號**。

現在兩邊的代號完全沒有交集：

| 來源 | 代號 |
| --- | --- |
| 規則條件（`program_rule_fields` 現有資料） | `registered_in_city`、`remains_type`、`deceased_status`、`eco_burial_completed` |
| 欄位登記表（`data/eligibility_fields/fields.v0.1.json`） | `deceased_insurance_type`、`has_dependent_children`、`applicant_age_band` |

**交集是零。**

以前這只是「詞彙沒對齊」，現在它變成一個**走不出去的迴圈**。原因是 2026-07-30 之後
欄位登記表成了唯一入口：

1. 使用者能被問到什麼問題，由欄位登記表決定（`missing_fields.py` 只看登記表）
2. 使用者能送進來什麼欄位，也由欄位登記表決定 —— 不在表上的代號整筆被拒
   （`unknown_field`），值不符型別或選項也整筆被拒（`invalid_field_value`）
3. 所以 `state.attributes` 裡**永遠只會有登記表上的三個代號**

於是：規則條件要求 `remains_type` → 登記表沒有這個欄位 → 系統不會問 → 使用者無法回答
→ 引擎永遠把它算進 `missing_inputs` → 那一項永遠停在資訊不足。**而且沒有任何一步會
報錯**，所以這個問題不會自己浮出來，只會表現成「怎麼問完了還是沒結論」。

這一項**不是靠後端改程式能解的**，需要兩邊挑一個方向：

- **方向一**：欄位登記表補上規則條件在用的代號。最直接，但登記表的每一筆都要填
  `purpose`（為什麼要問使用者這件事），而 `remains_type`、`eco_burial_completed`
  屬於殯葬與環保葬情境，跟 MVP 的「配偶過世」對不上，硬填會是假的理由。
- **方向二**：規則資料改用登記表的代號。等於承認登記表是屬性詞彙的權威來源。
  代價是現有的殯葬類規則資料要重寫條件字串。
- **方向三**：兩邊各留一套，中間加一層代號對照。後端不建議 —— 對照表會變成第三個
  需要維護的真相，而且它會安靜地過期。

這與待確認事項第 2 項（欄位登記表放哪、由誰維護）和第 14 項（以哪一邊的形狀為準）
是**同一個問題的三個面向**，應該一起決定。

---

## 五、屬性詞彙已經被規則資料隱含定義了

這一點很重要，會影響欄位登記表怎麼寫。

**修正一個先前寫錯的說法**（2026-07-30）：這份文件原本寫「`engine.py` 的
`evaluate_program` 已經在讀這些鍵」。實際上 `engine.py` **沒有寫死任何屬性代號**，
它是把資料庫裡的條件字串（例如 `remains_type=ash AND source=X`）用 `=` 切開，
左邊當成 `user_attrs` 的鍵去查。所以定義詞彙的是**規則資料**，不是引擎程式。

差別在責任歸屬：改詞彙不需要改 `engine.py`，改的是 `program_rule_fields` 裡的條件
字串。目前那些條件字串在用的代號是：

```
registered_in_city      是否設籍該縣市
remains_type            骨灰骸類型
deceased_status         亡者身分
eco_burial_completed    是否完成環保葬
```

也就是說**屬性名稱的實際詞彙已經存在於資料層的資料裡**，不是待定義的。

原本的建議是「後端的欄位登記表應該沿用這些名稱」。**這個建議現在需要重新討論**，
因為那批代號屬於殯葬與環保葬情境，跟 MVP 的「配偶過世」對不上，而登記表的每一筆都
必須填得出「為什麼要問使用者這件事」。完整說明見落差九。無論選哪個方向，結論都一樣：
欄位登記表的內容應該由政策資料負責人維護，跟 `program_rule_fields` 一起演進，
不能兩邊各自長。

另外要注意：目前的規則欄位偏向殯葬與環保葬情境（`remains_type`、`eco_burial_*`），
而 MVP 情境「配偶過世」的四個項目還需要投保身分、與亡者關係這類欄位。這些還不存在。

還有一件會在示範時看到的事：`data/eligibility_fields/fields.v0.1.json` 的三筆種子欄位
目前只宣告了 `funeral_benefit` 與 `survivor_pension` 需要的欄位，所以
**`death_registration` 與 `health_insurance_change` 在登記表裡沒有任何欄位宣告需要
它們**，會被 `determination.find_undeclared_item_ids` 判定為資料缺漏而標成
`needs_human_review`。這是刻意的安全預設（說不出理由的判定要降級，不能把資料缺漏誤讀
成「沒有條件所以符合」），但意味著示範時必然有兩項需人工協助。

---

## 五之二、`feat/databaseV3` 這個分支擋著 T18（2026-07-30）

後端這邊查證的結果，寫在這裡讓兩邊看到同一份事實。

**後端本機沒有任何資料庫檔案。** 全域搜過 `*.db`、`*.sqlite`、`*.sqlite3`，一個都沒有。
`.gitignore` 排除 `*.db`，所以那是本機產物。`data/benefits/` 也只有 `.gitkeep`。

**資料表定義還沒進 `main`。** `origin/feat/databaseV3`（三筆 commit）有：

| 內容 | 規模 |
| --- | --- |
| `backend/app/adapters/sqlite/migrations.py` | 約 1020 行 |
| `migration_sql/0001_metadata.sql`、`0002_programs_fields.sql` | 約 221 行 |
| `protocols.py` 增加 `CoverageScope`、`CoverageSnapshot` | 約 +242 行 |
| `determination.py`、`state_machine.py`、`rule_adapter.py`、`source_refresh.py`、`data_contracts.py` | 都有改 |
| 本文件 | 約 508 行變動，大部分是刪除 |

那個分支做的是 **schema 與 migration 工具**，不是 repository 實作 —— 後端搜過沒有任何
`class Sqlite*` 實作那四個接縫。所以後端要接的東西沒有被做掉，但**要接的契約正在被
那個分支修改**，現在寫 adapter 等於對著移動的目標寫。

### 後端請求

1. **`feat/databaseV3` 合併進 `main` 之前，後端不會開始 T18。** 這不是拖延，是避免
   對著兩份不同的契約各寫一次。
2. **合併那個分支時，本文件會衝突。** 後端實際跑過 `git merge-tree`，衝突有兩處：
   本文件與 `docs/decisions/README.md`，程式碼檔案全部乾淨合併。
   **請不要整段挑一邊** —— 落差九（規則條件的屬性代號與欄位登記表交集為零）是後端
   2026-07-30 新發現的資訊，那個分支不知道它存在，整段覆蓋會讓它消失。
3. **`benefit_programs` 需要至少一項經過人工審查。** 沒有 `verified` 狀態的資料，
   接上 SQLite 之後結果跟現在完全一樣（四項全部需人工協助），看不出接上了。

### 一件後端認為做對了的事

`feat/databaseV3` 的 migration 建了 `program_status_history` 與 `review_approvals`
兩張表，帶 `reviewer_ref`、`reviewed_at`、`approved_version`，還有 trigger 限制
`actor_type` 只能是 `human_reviewer` 或 `migration`。

那正好是後端
[ADR-0014](../decisions/0014-keep-fixture-data-out-of-verified-status.md)
需要的機制 —— 「有人真的審查過並記錄下來」在資料層有了落點。兩邊的想法在這件事上
是一致的。

---

## 五之三、生命事件的清單暫時放在後端（2026-07-30）

新增 `data/life_events/events.v0.1.json`，目前三筆事件。後端需要它是因為模型辨識事件時
必須被限制在一個**封閉清單**內 —— schema 用 `enum` 表達「值只能是這幾個之一」，
而 `enum` 需要一份明確的清單。

這帶來一個比事後檢查更強的保證：**模型在結構上無法回一個我們不認得的事件代號**，
因為它沒有那個選項。

### 但這個位置是暫行的

`orchestration/state.py` 對 `life_event` 有一條原則：

> 刻意不用列舉：事件的集合是由 entitlement graph 擁有的 curated 資料，
> 寫死在這裡會把政策放進應用程式碼。

那條原則仍然成立，而這份 JSON 是資料不是列舉，所以沒有違反它。但**嚴格來說「有哪些
事件」屬於 entitlement graph**，更正確的做法是在 `EntitlementGraphRepository` 加一個
`list_events()`。

沒有那樣做的原因純粹是時機：`orchestration/protocols.py` 正被 `feat/databaseV3`
大幅修改（約 +242 行），現在動同一個檔案會製造衝突。

### 後端的請求

**如果資料層打算在 graph 契約上提供事件清單，請告訴後端。** 那份 JSON 應該退場，
改由 repository 供應，屆時只有 `default_life_events()` 的呼叫端需要改。

反之如果資料層認為事件清單不屬於 graph，那也請說一聲 —— 那份 JSON 就會從「暫行」
變成正式安排，需要決定由誰維護。

---

## 六、待確認事項

| # | 事項 | 誰要回答 | 狀態 |
| --- | --- | --- | --- |
| 1 | Entitlement graph 用什麼形狀？JSON 還是 SQLite 表（落差六） | 兩邊 | **未討論，最擋人**。後端已備好 `EntitlementGraphRepository` 介面，資料層還沒有存關係的表 |
| 2 | 欄位登記表放哪、由誰維護 | 兩邊 | **未討論**，另見第 14 項（以哪邊的形狀為準） |
| 3 | 規則引擎能否輸出結構化的決定性條件（落差二、四） | 資料層 | **未討論**。後端接收端已就緒（`StructuredReason`），在此之前不會回報任何「不符合資格」 |
| 4 | `program_rule_fields` 能否增加「發放性質」欄位（落差一） | 資料層 | 未討論 |
| 5 | 行政事項（死亡登記、健保變更）也要進規則引擎，規則放哪 | 兩邊 | 已定方向：要進，形狀未定 |
| 6 | 互斥福利（領了 A 不能領 B）怎麼表達 | 兩邊 | `mutual_exclusion_text` 已預留，組合未確認 |
| 7 | 依項目取官方依據的查法 | 資料層 | 未討論。`EvidenceRepository` 介面已備好，實作未交，所以 `RETRIEVE_RULES` 仍是空操作 |
| 8 | 相關性分數要露給前端，還是只用順序隱含表達（落差三） | 兩邊 | 未決。邊界格式已有 `relevance_score`，但刻意不搬進 workflow 形狀 |
| 9 | `relevance_score` 的權重表由誰維護、調整時要不要記錄 | 資料層 | 未討論 |
| 10 | `stale` 採方案 A（最後驗證快照加警告）還是方案 B（一律降級） | 兩邊 | **未決**（提案第 12 節第 2 項）。後端目前暫行方案 B 的效果，非定案 |
| 11 | `benefit_programs.program_status` 的 `status_unknown` 要移除，還是納入契約（落差七） | 資料層 | **未討論** |
| 12 | `source_registry` 要不要補 `domain_tags` 與重抓頻率欄位（落差八） | 資料層 | **未討論** |
| 13 | ADR-0008「runtime 只讀 JSON、永不查 SQL」的修訂或取代 | 兩邊 | **未決**，見下方說明 |
| 14 | 欄位登記表以哪一邊的形狀為準 | 兩邊 | **未討論**，見下方說明 |
| 15 | 同一天不重複觸發的紀錄要移到共用儲存 | 兩邊 | 已記在 `docs/aws_migration_guide.md`。目前只在單一 process 內有效，多個 worker 時同一天仍會重複抓同一個來源 |
| 16 | 「哪些項目是行政事項、哪些是福利」的分類欄位 | 資料層 | **未討論**。目前由 `rule_adapter._ADMINISTRATIVE_ITEM_IDS` 一份寫死清單判斷，因為提案第 7 節的契約沒有這個分類欄位。資料層若帶上就能刪掉 |
| 17 | 規則條件的屬性代號與欄位登記表要怎麼統一（落差九） | 兩邊 | **未討論，接 SQLite 前必須解決**。兩邊代號交集為零，而登記表現在是屬性的唯一入口，所以規則要求的欄位系統問不出來也收不進來。三個方向見落差九 |
| 18 | `feat/databaseV3` 什麼時候合併進 `main` | 資料層 | **T18 最直接的阻塞**，見五之二。合併時本文件會衝突，請保留落差九與五之三 |
| 19 | 生命事件的清單要不要進 entitlement graph 契約（`list_events()`） | 兩邊 | **未討論**，見五之三。目前暫時放在後端的一份 JSON |

第 13 項（ADR-0008）：提案第 2 節指出 SQLite runtime 與「runtime 只讀 JSON」直接衝突，
但**這需要雙方 owner 共同核准**，後端沒有、也不會單方面宣告 ADR-0008 失效 —— 在正式
決策完成前它仍是現行 accepted ADR。有一個降低風險的事實可以先記下：ADR-0008 第 3 節
的「啟動時把 `data/` 載入記憶體」**目前沒有實作**，後端既不讀 JSON 也不讀 SQL 取方案
資料（唯一讀 JSON 的地方是欄位登記表），所以沒有既有的 JSON 載入器要拆。

第 14 項（欄位登記表形狀）：兩邊各有對方沒有的欄位。後端的
`field_registry.FieldDefinition` 有 `topic_id`（問題分組用）與 `used_by`（哪些項目需要
它），提案的 `FieldRegistryEntry` 沒有；提案的有 `pii_classification`，後端沒有。
兩者目前並存（`FieldRegistryEntry` 只出現在 `EligibilityService.get_required_fields`
的回傳型別上），但長期只能有一份是準的。

---

## 七、已解決的環境問題（歷史紀錄）

這兩項曾經擋住開發，**2026-07-29 實際驗證已解決**。保留原本的問題描述，讓之後遇到
類似症狀的人知道曾經有這個坑、修法是什麼。

### ✅ 測試指令現在可以跑（2026-07-29 驗證）

**曾經的問題**：`cd backend; uv run pytest` 會在收集階段失敗，因為資料層的四個測試檔
用的 import 路徑是從 repository 根目錄算的，而 `backend/pyproject.toml` 設定以
`backend/` 為根。當時只能從根目錄執行
`backend/.venv/Scripts/python.exe -m pytest backend/tests`。

**修法**：`backend/pyproject.toml` 的 `pythonpath` 兩個目錄都收（`[".", ".."]`），
兩種 import 慣例都能解析。這是繞過而非根治 —— 兩種慣例應該統一成一種，但那要改動多個
測試檔。

**驗證結果**（在 `backend/` 目錄下執行）：

- `uv run pytest` → **226 個測試全部通過，沒有收集階段失敗**
- `uv run ruff check .` → 通過
- `uv run ruff format --check .` → 57 個檔案已排版

**2026-07-30 重新驗證仍然成立**：280 passed、`ruff check` 通過、
`ruff format --check` 76 個檔案已排版。

### ✅ SQLite 連線沒有關閉 —— 已不成立（2026-07-29 驗證）

**曾經的問題**：資料層到處用 `with sqlite3.connect(...) as connection:`。Python 的
`sqlite3` 用 `with` 包起來只會提交或回滾交易、**不會關閉連線**。macOS 與 Linux 允許
刪除還開著的檔案，Windows 不允許，所以測試的暫存目錄清理失敗 —— 當時 Windows 上有
7 個測試因 `PermissionError` 失敗。長時間執行的程序沿用同樣寫法會累積不釋放的連線。

**修法**：改用 `contextlib.closing` 包起來，或在 `try/finally` 裡明確呼叫 `close()`。

**現在的實際情形**（全 repo 搜 `sqlite3.connect`）：

| 位置 | 處數 | 生命週期怎麼管 |
| --- | --- | --- |
| `backend/app/orchestration`、`app/api`、`app/schemas` | 0 | 完全不碰 SQLite |
| `backend/app/services`、`app/rules` | 0 | 以 `connection` 參數接收連線，由呼叫端管生命週期 |
| `scripts/` | 10 | 5 處 `with closing(...)`、4 處 `try/finally: connection.close()`；`review_server.py:53` 的 `_get_connection()` 本身不關，但 9 個呼叫點都用 `with closing(...)` |
| `backend/tests/` | 10 | 全部用 `with closing(sqlite3.connect(...)) as connection, connection:` |

所以「Windows 上 7 個測試失敗」與「連線沒有關閉」都不再成立。新增資料層程式碼時仍請
沿用上表的寫法，這個坑會安靜地回來。
