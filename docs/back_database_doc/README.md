# 後端 ↔ 資料層 溝通紀錄

這份文件記錄後端 workflow 層與資料層（政府來源、補助 catalog、規則引擎）之間的
交界：**對方提供什麼、我需要什麼、形狀哪裡對不上**。

- 資料層的完整說明見 `docs/architecture-overview.html` 與 `docs/data-model.md`。
- 後端 workflow 層的說明見 `docs/backend/backend-overview.html`。
- 這份文件與程式衝突時，**程式為準**。
- 最後更新：2026-07-26

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
| 逐項判定組裝 | `backend/app/orchestration/determination.py` | 🟡 stub |
| 欄位登記表機制 | `backend/app/orchestration/field_registry.py` | ✅ 完成 |
| 缺漏欄位計算 | `backend/app/orchestration/missing_fields.py` | ✅ 完成 |
| 通用規則引擎 | `backend/app/rules/engine.py` | ✅ 可運作 |
| 相關性評分與排序 | `engine.py` 的 `compute_relevance_score` | ✅ 可運作 |
| 審查介面 | `scripts/review_server.py` | ✅ 可用 |

### Workflow 層需要但還沒有的

| 需要什麼 | 用在哪一步 | 現況 |
| --- | --- | --- |
| **Entitlement graph** — 事件對應哪些項目、彼此的前後順序與依賴 | 第 2 步展開項目、第 8 步排辦理順序 | ❌ `data/entitlement_graph/` 是空的 |
| **欄位登記表** — 有哪些資格欄位、型別、選項、為什麼問 | 第 3 步組出問題卡 | ❌ 不存在 |
| **項目層級的規則** — 不只是方案，也包含行政事項的適用與期限 | 第 5 步判定 | 🟡 只有方案的規則欄位 |
| **可依項目取得的官方依據** | 第 4 步檢索 | 🟡 有文件，但還沒有「依項目取引用」的查法 |

**最擋人的是 entitlement graph 和欄位登記表。** 沒有前者，使用者說「我先生過世」後
系統不知道要展開哪些項目；沒有後者，系統不知道要問什麼。

---

## 三、後端會怎麼取用資料層

**後端不會直接寫 SQL 撈 catalog。** 會定義三個介面，各自對應一種問題：

| 介面 | 問什麼 |
| --- | --- |
| Entitlement graph | 這個事件牽動哪些項目？順序與依賴是什麼？ |
| 規則來源 | 這個項目的判斷條件是什麼？ |
| 官方依據檢索 | 這個項目的依據是哪些文件、哪一段？ |

分成三個而不是一個的理由：如果只有一個「資料層」介面，規則判定就有機會直接去撈文件
內容，兩者糾纏之後就沒辦法單獨測試規則了。

每個介面會先配一個回固定資料的假實作，所以**後端不需要等資料層完成才能開發**。

### 目前接上了什麼

- **規則引擎轉接層**已完成（`orchestration/rule_adapter.py`）。目前使用 stub：
  湊齊欄位就標 eligible。接上真正的 SQLite 時只需要把
  `determination.py` 裡的 `evaluate_ready_items_stub` 換掉。
- **欄位登記表**已完成（`orchestration/field_registry.py` 讀
  `data/eligibility_fields/fields.v0.1.json`），三筆種子欄位。
- **缺漏欄位計算**已完成（`orchestration/missing_fields.py`），可直接產出
  `QuestionGroupView` 給前端。

---

## 四、形狀落差

規則引擎的 `EligibilityResult` 與 workflow 層的 `CandidateItem` 都有四種判定狀態，
但其餘形狀還沒對齊。以下五項需要協調，其中**金額轉接已完成**，**命名轉接已完成**。

### 落差一：金額 — 形狀已補上，轉接已做（period 除外）

規則引擎回 `amount`（單一整數），轉接層映射到 `amount_min` 和 `amount_max`（兩者填
同一個值）。`amount_currency` 有值時固定為 `TWD`。

**`amount_period` 仍然留空**：規則欄位裡還沒有「一次性／按月／按年」這個資訊。
需要在 `program_rule_fields` 增加一個欄位。

規則引擎回 `amount`（單一整數）與 `amount_label`（例如 `10000~20000`）。

Workflow 層已補上 `amount_min`、`amount_max`、`amount_period`、`amount_currency`
四個欄位，決策見 ADR-0011 修訂一。

**刻意不收 `amount_label`**，因為那是給人看的文字，屬於前端。後端只給結構。

還需要協調的：

- 規則引擎的 `_evaluate_amount` 在 `min_amount == max_amount` 時回單一值、不相等時
  回 `None` 加一個字串。後端需要的是兩個數字都拿到，不是字串。
- **發放性質（一次性／按月／按年）目前不在規則欄位裡。** 遺屬年金是按月的，喪葬給付
  是一次性的，這個差別無法從金額數字推斷。需要在 `program_rule_fields` 增加一個欄位。

### 落差二：`reasons` 是文字，workflow 層需要結構

規則引擎回的是 `reasons: list[str]`，內容是中文句子，例如 `需設籍該縣市`。

Workflow 層需要的是三段結構：**哪個欄位、要求什麼、實際什麼**。因為結果畫面要顯示
「差在這個條件：你的情況 X ／ 需要 Y」。

只有整段文字的話，前端只能原封不動印出來，那個對照就做不出來 —— 而那是整個專案最強
的差異點。也是「不符合必須說得出差在哪一個條件」這條約束的載體。

**這一項後端無法單方面補**，需要規則引擎在判定為 `ineligible` 時額外輸出結構化的
決定性條件。

### 落差三：相關性評分沒有對應的欄位

規則引擎新增了 `relevance_score`（0 到 100）與 `compute_relevance_score`，用結構化
欄位匹配算分，`evaluate_all_programs` 依分數由高到低排序。README 已把它標為**已實作**。

這是好事 —— 排序是確定性的、可解釋的，不依賴 LLM，跟本專案的主張一致。

但 workflow 層目前接不到：

- `CandidateItem` 沒有放分數的欄位
- 對外的 `SessionSnapshot.items` 是一個清單，順序由後端決定，但**沒有任何欄位說明順序
  的依據**。前端無法分辨「這是相關性排序」還是「這只是查詢回來的順序」

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
| `source_url`（單一字串） | `Citation`（六個欄位的結構） | 組成最小的 Citation（只有 URL） |
| `status`（純字串） | `ItemStatus`（列舉） | 查對照表，未知字串降級為 `NEEDS_HUMAN_REVIEW` |

不要求資料層改名。轉接集中在 `orchestration/rule_adapter.py` 一個函式裡。

`source_url` 那一項值得注意：workflow 層需要的是文件代號、標題、發布機關、發布日期、
網址、引用段落六項，因為畫面上要顯示「依據：〈條例名稱〉第 X 條，官方連結，發布日期」。
這些欄位 `source_documents` 與 `program_sources` 都已經有，只是規則引擎目前只往外
傳一個網址。

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

---

## 五、屬性詞彙已經被規則引擎隱含定義了

這一點很重要，會影響欄位登記表怎麼寫。

`engine.py` 的 `evaluate_program` 已經在讀這些 `user_attrs` 的鍵：

```
registered_in_city      是否設籍該縣市
remains_type            骨灰骸類型
deceased_status         亡者身分
eco_burial_completed    是否完成環保葬
```

也就是說**屬性名稱的實際詞彙已經存在於資料層**，不是待定義的。

後端的欄位登記表（T7）應該**沿用這些名稱**，而不是另外發明一套再寫轉換。這也表示
欄位登記表的內容應該由政策資料負責人維護，跟 `program_rule_fields` 一起演進。

另外要注意：目前的規則欄位偏向殯葬與環保葬情境（`remains_type`、`eco_burial_*`），
而 MVP 情境「配偶過世」的四個項目還需要投保身分、與亡者關係這類欄位。這些還不存在。

---

## 六、待確認事項

| # | 事項 | 誰要回答 | 狀態 |
| --- | --- | --- | --- |
| 1 | Entitlement graph 用什麼形狀？JSON 還是 SQLite 表 | 兩邊 | **未討論，最擋人** |
| 2 | 欄位登記表放哪、由誰維護 | 兩邊 | **未討論** |
| 3 | 規則引擎能否輸出結構化的決定性條件（落差二、四） | 資料層 | **未討論** |
| 4 | `program_rule_fields` 能否增加「發放性質」欄位（落差一） | 資料層 | 未討論 |
| 5 | 行政事項（死亡登記、健保變更）也要進規則引擎，規則放哪 | 兩邊 | 已定方向：要進，形狀未定 |
| 6 | 互斥福利（領了 A 不能領 B）怎麼表達 | 兩邊 | `mutual_exclusion_text` 已預留，組合未確認 |
| 7 | 依項目取官方依據的查法 | 資料層 | 未討論 |
| 8 | 相關性分數要露給前端，還是只用順序隱含表達（落差三） | 兩邊 | 待 T9 |
| 9 | `relevance_score` 的權重表由誰維護、調整時要不要記錄 | 資料層 | 未討論 |

---

## 七、已知的環境問題

這兩項不屬於形狀協調，但會影響開發，記在這裡避免重複踩。

**測試指令目前兩邊都不通。**
`backend/README.md` 寫的 `cd backend; uv run pytest` 會在收集階段失敗，因為資料層的
四個測試檔用的 import 路徑是從 repository 根目錄算的，而 `backend/pyproject.toml`
設定以 `backend/` 為根。從根目錄執行 `backend/.venv/Scripts/python.exe -m pytest
backend/tests` 可以跑，但在 Windows 上有 7 個測試會失敗。

**Windows 上 SQLite 連線沒有關閉。**
上面那 7 個失敗的原因是 `with sqlite3.connect(...)` 只提交交易、**不關閉連線**。
macOS 與 Linux 允許刪除還開著的檔案，Windows 不允許，所以暫存目錄清理失敗。
長時間執行的程序（例如 FastAPI 後端）沿用同樣寫法會累積不釋放的連線。
修法是用 `contextlib.closing` 包起來或明確呼叫 `close()`。
