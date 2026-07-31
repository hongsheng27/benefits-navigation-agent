# 前端 ↔ 後端 溝通紀錄

這份文件記錄前端與後端之間**已經談定的約定**，以及**還沒談定、正在擋人的事**。

不是設計文件，也不是規格書。目的是讓兩邊不用等會議就知道對面的狀態。

- 對外契約的真正定義在 `backend/app/schemas/session.py` 與
  `frontend/src/types/session.ts`。這份文件與程式衝突時，**程式為準**。
- 使用者流程與畫面設計見 `docs/backend/backend-overview.html`。
- 最後更新：2026-07-30（第二次）

> **2026-07-30 第二次更新：對前端沒有任何影響。** 後端加了一份示範資料，
> 讓喪葬給付在測試裡可以走到 `eligible`。但**端點不會使用它** —— 從 API 呼叫
> 得到的結果完全不變，仍然是四項 `needs_human_review`，`implementation.pending`
> 也還是同樣七項。前端不需要改任何東西。理由見
> [ADR-0014](../decisions/0014-keep-fixture-data-out-of-verified-status.md)。

---

## 一、當前狀態

| 項目 | 狀態 | 備註 |
| --- | --- | --- |
| 資料契約（後端 Pydantic） | ✅ 完成 | `backend/app/schemas/session.py` |
| 資料契約（前端 TypeScript） | ✅ 完成 | `frontend/src/types/session.ts` |
| 走鐘檢查測試 | ✅ 完成 | 改一邊忘了另一邊會讓測試失敗 |
| Session 儲存 | ✅ 完成 | 記憶體、2 小時過期 |
| 四個 session 端點 | 🟡 **可呼叫，但回佔位資料** | 見下一節 |
| 狀態機 | ✅ 完成 | 三張表、自動推進、兩道護欄。見 ADR-0012 |
| 事件辨識（LLM） | ❌ 未實作 | 一律回 `spouse_death` |
| 資格判定 | 🟡 機制完成，資料還不足 | 判定改由資料層的介面負責，但目前的資料一律回 `needs_human_review`。見一之三 |
| 欄位登記表 | ✅ 完成 | 三筆種子資料（draft），機制可用 |
| 缺漏欄位計算與分組 | ✅ 完成 | 按主題分組，每題帶 unlocks_item_ids |
| 問題卡 | 🟡 機制完成，內容是 draft | 有三組真的問題可以顯示，但欄位與選項是暫定的 |
| 欄位值的驗證 | ✅ 完成 | 型別或選項不符會回 `invalid_field_value`，見一之四 |
| 自由文字丟棄 | ❌ 未實作 | 結構上已擋（只有第一步帶文字），實際丟棄延後到接 LLM 時 |
| 前端呼叫程式 | ❌ 未實作 | `client.ts` 目前只有健康檢查 |
| 前端 PII 遮罩 | ❌ 未實作 | 目前只有文字提醒 |

**所以現在的實際情況是**：端點可以呼叫、狀態機會真的按規則推進、回答欄位會讓項目逐項
定案。但**事件辨識是寫死的**（一律 `spouse_death`）、**判定結果目前只會是需人工協助**
（資料尚未經人工核對，見一之三）、**決定性條件為空**（等資料層配合）。

## 一之二、佔位資料怎麼辨識

每個回應都帶一個 `implementation` 物件，說明這份資料有多少是真的：

```json
{
  "implementation": {
    "isMock": true,
    "pending": ["life_event_extraction", "entitlement_graph", "rule_evaluation", "..."],
    "placeholderNotice": "（此為後端傳來的暫時資料，尚未進行真實的事件辨識與資格判定）"
  }
}
```

| 欄位 | 用法 |
| --- | --- |
| `isMock` | 為 true 時前端應在畫面上標示這不是真實判定 |
| `pending` | 哪些能力還沒實作。實作完成會逐項消失，前端不用改程式 |
| `placeholderNotice` | 可直接顯示的中文提示。**這是臨時例外** |

`placeholderNotice` 是唯一由後端提供中文文案的欄位，違反本專案「後端給代號、前端給
文案」的分界。這是刻意的：它的讀者是開發者與 demo 觀眾，不是真正的使用者。
**佔位資料移除時，這個欄位連同整個 `implementation` 物件一起刪除。**

`pending` 目前有七項：`life_event_extraction`、`entitlement_graph`、
`rule_evaluation`、`official_citations`、`plain_language_explanation`、
`action_plan`、`privacy_gate`。

已經從清單移除的（代表那一項已實作）：`state_machine`、`field_registry`。
清單只會變短，前端不需要改程式。

**`privacy_gate` 還留著，但它已經做了一半。** 前端會用到的那一半已經完成：
不在登記表上的欄位代號會讓整筆請求被拒（`unknown_field`），值本身也會依登記表的
型別與選項驗證（`invalid_field_value`）。留著是因為「使用者輸入的原文不保存」
還沒真的實作 —— 目前事件辨識是寫死的，後端根本沒有收下那段文字，所以現在寫丟棄
邏輯會沒有東西可丟。這一項會在接上 LLM 時一起完成。

前端可以據此判斷：看到 `privacy_gate` 在清單裡，**不代表送錯的值會被默默收下**。

## 一之三、目前的判定結果會是什麼（2026-07-29）

三件會影響前端畫面、但**不是前端 bug** 的事。

**1. 後端目前不會回傳 `eligible` 或 `ineligible`。** 項目的 `status` 只會是
`needs_human_review` 或 `pending`（加上使用者自己選的 `declined_by_user`）。兩個原因：

- 候選項目的資料尚未經人工核對，後端不會拿未核對的資料下結論
- 規則引擎還不輸出結構化的決定性條件，而「不符合但說不出差在哪個條件」一律降級為
  `needs_human_review`

所以結果畫面的「你符合」與「不符合」分區短期內會是空的。這是刻意的安全預設，資料層
交出經核對的資料與結構化條件之後就會自動出現，前端不需要改程式。

**2. 資料可信程度沒有露在對外契約裡。** 後端內部有一個資料治理狀態
（`program_status`：候選／審查中／已核對／過期等），它決定一項能不能下結論，但
**`ItemView` 沒有這個欄位**。要不要露出屬於對外契約那一批（要同時改兩邊的型別），
晚點決定。目前前端能看到的只有結果 —— 不能下結論的項目就是 `needs_human_review`。

**3. 相關性分數也沒有露出。** `items` 的順序由後端決定，但**沒有任何欄位說明排序依據**，
前端無法分辨那是相關性排序還是查詢回來的順序。這一項與待確認事項一起追蹤。

## 一之四、送錯的值會發生什麼（2026-07-30）

送答案（`attribute_answers`）時有兩道檢查，**兩道都是拒絕整筆，不會部分接受**。

| 情況 | 回什麼 |
| --- | --- |
| 欄位代號不在登記表上 | `unknown_field`，`fieldIds` 帶出問題的代號 |
| 值的型別或選項不符 | `invalid_field_value`，`fieldIds` 帶出問題的代號 |

四種型別的規則：

| `value_kind` | 接受什麼 |
| --- | --- |
| `code`、`band` | 只接受該欄位 `option_ids` 裡的字串 |
| `boolean` | 只接受 JSON 的 `true` / `false`，不接受 `"true"` 或 `1` |
| `integer` | 只接受整數，**不接受布林值**，也不接受 `"5"` 這種字串 |

**為什麼拒絕整筆而不是收下對的、退回錯的**：如果部分接受，前端送三個欄位、後端收了
兩個，畫面上沒有任何地方能表達「有一個沒收到」，使用者會以為都填好了。整筆拒絕讓
前端一定會發現。

`fieldIds` 只帶**代號**，不帶使用者送來的值。所以錯誤回應永遠不會把使用者打的內容
送回來，也不會進紀錄檔。

實務上前端不該遇到這兩種錯誤 —— 選項是後端在 `questionGroups` 裡給的，照著送就不會
錯。遇到了代表兩邊的型別或選項不同步，屬於程式錯誤，應該回報而不是顯示給使用者。

---

## 二、已定案的約定

這些已經討論過並定案，改動需要兩邊都同意。

| 主題 | 決定 |
| --- | --- |
| 端點數量 | 三個：建立 session、推進一步、查目前狀態 |
| 回應內容 | **完整快照**，不是只回變動。後端擁有權威狀態 |
| Session 識別 | `session_id` 走 **HTTP header**，不走網址路徑 |
| 線路欄位命名 | **camelCase**（`itemId`），後端 Python 內部是 snake_case |
| 列舉值命名 | **snake_case**（`needs_information`），因為那是資料不是欄位名 |
| 問題卡 | 後端給結構與代號，**前端給所有文字** |
| 型別同步 | 兩邊手寫，靠自動測試抓不一致 |
| 錯誤回應 | 只有一種形狀，只帶代號 |

### `session_id` 為什麼走 header

它同時扮演「是誰」和「證明是本人」兩個角色，誰拿到就能讀。放在網址會被瀏覽記錄、
referrer 與伺服器日誌帶走，所以走 header。

前端需要把它存在 `localStorage`（使用者可選擇不保留），並在每次呼叫時帶上。

---

## 三、端點

已實作，可以呼叫。

| 方法 | 路徑 | 用途 | 成功狀態碼 |
| --- | --- | --- | --- |
| `POST` | `/sessions` | 建立一次諮詢，回應含 `sessionId` | 201 |
| `POST` | `/sessions/advance` | 送一筆輸入，推進一步 | 200 |
| `GET` | `/sessions/current` | 查目前狀態（輪詢用） | 200 |
| `DELETE` | `/sessions/current` | 立刻清除這次諮詢 | 204 |

前三個都回同一個形狀：`SessionSnapshot`。`DELETE` 沒有回應本體。

**除了 `POST /sessions` 之外，每次呼叫都要帶 header `X-Session-Id`。**
路徑裡沒有 id，理由見下一段。

`DELETE` 在 session 已經不存在或已過期時**仍然回 204**，因為呼叫端的目的是「確保它
不在了」，而那個目的已經達成。

---

## 四、七種輸入

`POST advance` 的請求本體是 `{ "input": { "kind": ..., ... } }`。
`kind` 決定其餘欄位。

| kind | 對應畫面 | 其餘欄位 |
| --- | --- | --- |
| `life_event_text` | 1 描述事件 | `text` |
| `event_confirmation` | 2 確認理解 | `confirmed` |
| `attribute_answers` | 4 送一組答案；7 修正答案 | `answers`（欄位代號對值） |
| `item_decline` | 「這一項我不想辦」 | `itemId` |
| `review_confirmation` | 7 確認產生清單 | `confirmed` |
| `referral_choice` | 7 要不要轉介 | `requested` |
| `help_request` | 隨時要求人工協助 | 無 |

**`life_event_text` 是唯一帶文字的形狀。** 其他六種在型別上沒有文字欄位，所以自由
文字不可能出現在後面的步驟。前端不需要擔心誤送，型別會擋。

文字長度上限 **2000 字元**，兩邊都有常數 `MAX_LIFE_EVENT_TEXT_LENGTH`。

---

## 五、回應快照

`SessionSnapshot` 的欄位。「現在」那一欄是目前實作狀況。

| 欄位 | 內容 | 現在 |
| --- | --- | --- |
| `sessionId` | 這次諮詢的隨機編號 | 端點做好後才有 |
| `workflowState` | 八個步驟之一 | — |
| `stepIndex` / `stepTotal` | 進度顯示用。**因為中間有迴圈，可能往回走** | — |
| `lifeEvent` | 事件代號，第 2 步確認後才有值 | — |
| `attributes` | 使用者答過的答案，第 7 步複查用 | — |
| `items` | 候選項目與各自結果 | — |
| `questionGroups` | 問題卡 | **只在 `collect_missing_fields` 狀態有值**，其他狀態是空陣列 |
| `exitReason` | 提前結束的原因 | — |
| `referralRequested` | 是否要求轉介 | — |
| `isProcessing` | 為 true 時輪詢要繼續 | **目前永遠是 false**（同步處理） |
| `createdAt` / `expiresAt` | 建立與失效時間 | — |

### 項目（`items` 裡的每一筆）

| 欄位 | 內容 |
| --- | --- |
| `itemId` | 項目代號 |
| `kind` | `benefit`（福利）或 `administrative`（行政事項） |
| `status` | 六種之一，見下 |
| `missingFieldIds` | 這一項還缺哪些欄位 |
| `decisiveConditions` | 決定這個結果的條件，含 `expected` 與 `actual` |
| `citations` | 官方依據 |
| `amountMin` / `amountMax` / `amountPeriod` / `amountCurrency` | 金額，**只有結構沒有文字** |
| `explanation` | 白話說明，第 6 步才填入 |

**狀態是每個項目各自一個**，所以同時有好幾項符合是正常情況。結果畫面就是把這份清單
按狀態分區。

| status | 意思 | 誰設定 |
| --- | --- | --- |
| `pending` | 待確認，還在等欄位 | 初始值 |
| `eligible` | 符合 | 規則引擎 |
| `ineligible` | 不符合，**會附決定性條件** | 規則引擎 |
| `needs_information` | 資訊不足 | 規則引擎 |
| `needs_human_review` | 需人工協助 | 規則引擎 |
| `declined_by_user` | 使用者不想辦 | 使用者 |

`kind` 的區分在畫面上很重要：**不能讓使用者把「你符合死亡登記的資格」讀成一項可以
選擇放棄的福利。** 行政事項是義務，福利是權利。

---

## 六、錯誤

所有錯誤共用一種形狀，只有三個欄位，**都不會包含使用者輸入的值**。

```json
{ "errorCode": "session_expired", "fieldIds": [], "currentState": "collect_missing_fields" }
```

| errorCode | 什麼情況 | 前端建議做什麼 |
| --- | --- | --- |
| `session_not_found` | 找不到這個 session（404），或沒帶 header（401） | 清除本機 id，重新開始 |
| `session_expired` | 超過保存時間（410） | 告知已過期，重新開始 |
| `unknown_field` | 送了不在登記表上的欄位 | 這是程式錯誤，回報 |
| `invalid_field_value` | 值不符合欄位型別或選項 | 這是程式錯誤，回報 |
| `unknown_item` | 項目代號不在候選清單裡（422） | 這是程式錯誤，回報 |
| `invalid_transition` | 目前狀態不允許這個動作（409） | 重新取得快照後再試 |
| `internal_error` | 後端自身錯誤 | 顯示一般性錯誤訊息 |

**錯誤本體就是 `ErrorResponse`，沒有包在 `detail` 底下。** FastAPI 的預設格式已經被
覆寫，因為預設的驗證錯誤會把不合法的值原文放進訊息裡 —— 那可能是使用者打的一段話。
現在回應只會有欄位路徑，例如 `["input.life_event_text.text"]`。

**沒有錯誤訊息文字**，只有代號。文字由前端提供。

---

## 七、文案責任分界

後端給**代號**，前端給**所有給人看的文字**。這條界線讓新增一個資格欄位時不需要改
前端邏輯，也讓文案由負責使用體驗的人掌握 —— 這個產品的使用者正在人生低谷，用字
很重要。

前端需要準備的文案：

| 代號來源 | 需要什麼文字 |
| --- | --- |
| `lifeEvent` | 事件名稱（例如 `spouse_death` → 「配偶過世」） |
| `itemId` | 項目名稱與簡述 |
| `status` | 分區標題（「你符合」「需要補充資訊」「不符合」「應辦理的行政事項」） |
| `QuestionView.fieldId` | 題目文字 |
| `QuestionView.optionIds` | 每個選項的文字 |
| `QuestionView.purposeId` | 「為什麼問這個？」那段說明 |
| `QuestionGroupView.topicId` | 這一組的標題 |
| `DecisiveConditionView` | 「差在這個條件」的句型與值的說法 |
| `amount*` | 金額的呈現（千分位、「每月」等） |
| `errorCode` | 錯誤訊息 |
| `exitReason` | 走到人工協助時的說明 |

---

## 八、待確認事項

有問題就加一列。解決了就標記並保留紀錄。

| # | 事項 | 誰要回答 | 狀態 |
| --- | --- | --- | --- |
| 1 | 端點什麼時候可以呼叫 | 後端 | ✅ 已完成，回佔位資料 |
| 8 | `placeholderNotice` 何時移除（狀態機與判定實作完成時） | 後端 | 追蹤中 |
| 9 | 前端 `client.ts` 由誰接上這四個端點 | 兩邊 | 未分配 |
| 2 | 問題卡的**正式**欄位與選項代號 | 政策資料 | 目前是三筆 draft 種子資料，前端可以先接 |
| 3 | 事件代號有哪些（目前只知道會有 `spouse_death`） | 政策資料 | 未開始 |
| 4 | 項目代號有哪些 | 政策資料 | 未開始 |
| 5 | 「不確定」要怎麼送？是一個特殊的選項代號，還是不送這個欄位 | 兩邊 | **未討論** |
| 6 | 輪詢間隔多久合適 | 兩邊 | 未討論，目前後端同步處理所以不急 |
| 7 | 前端遮罩不掉中文姓名，後端如何處理 | 後端 | 已有方向：抽取後丟棄原文 |
| 10 | 資料可信程度（`program_status`）要不要露在 `ItemView` 上 | 兩邊 | 未決，屬於對外契約那一批 |
| 11 | `items` 的排序依據要不要露出（相關性分數或排序理由） | 兩邊 | 未決，後端目前不露出分數 |

第 5 項值得注意：畫面上有「我不確定」這個選項，但契約還沒定它怎麼表達。兩種可能是
「一個保留的選項代號」或「乾脆不送這個欄位」。這件事會影響前端的表單邏輯。

---

## 九、改契約的規則

1. 兩邊都要改：`backend/app/schemas/session.py` 與 `frontend/src/types/session.ts`。
2. 跑 `cd backend; uv run pytest tests/unit/test_session_schemas.py`。走鐘檢查會比對
   欄位名稱、列舉值與文字長度常數，不一致就失敗。
3. 前端跑 `npm run typecheck`。
4. 在這份文件的「已定案的約定」或「待確認事項」留下紀錄。
