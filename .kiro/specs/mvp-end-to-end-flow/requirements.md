# 需求文件：MVP 端對端流程

## 簡介

「接住」福利導航 Agent 的最小可行產品（MVP）端對端流程。使用者以自然語言描述配偶死亡的人生事件後，系統透過狀態機控制的工作流程，依序完成事件理解、相關福利展開、資格欄位收集、官方規則檢索、確定性資格判斷、白話解釋與使用者確認，最終產出附有官方來源的行動清單。

MVP 情境涵蓋四項福利與行政事項：死亡登記、喪葬給付、遺屬年金、全民健康保險身分變更。

## 詞彙表

- **State_Machine**：控制工作流程狀態轉換、工具允許清單、停止條件與人工確認的確定性狀態機。
- **Agent**：在 State_Machine 指定節點執行自然語言理解、問題生成與解釋生成的 LLM 代理程式，透過 AgentRunner interface 接入。
- **Rule_Engine**：以宣告式 JSON 規則與 Pydantic 驗證進行確定性資格判斷的引擎。
- **Retriever**：從已核准的官方文件中檢索相關段落並附帶引用來源的檢索模組。
- **Frontend**：React/TypeScript 使用者介面，負責對話互動、PII 遮罩與結果呈現。
- **Backend**：FastAPI Python 後端，負責 API 處理、協調邏輯與資料操作。
- **Session**：一次使用者互動的記憶體狀態，包含 session_id、workflow state 與去識別化屬性；不持久化。
- **Entitlement_Graph**：描述人生事件與相關福利、行政事項及負責機關之間關聯的 JSON 檔案。
- **Eligibility_Attributes**：判斷資格所需的去識別化使用者屬性（如投保年資、關係、年齡等）。
- **Action_Checklist**：包含申請順序、所需文件、負責機關、官方來源連結的行動清單。
- **PII**：個人可識別資訊，包含姓名、身分證字號、地址、電話、email。

## 需求

### 需求 1：建立對話 Session

**User Story:** 身為一位面臨配偶死亡的使用者，我希望開始一個對話，讓系統能夠協助我了解可以申請哪些福利與行政程序。

#### 驗收條件

1. WHEN 使用者開啟應用程式並發送第一則訊息（長度介於 1 至 500 字元），THE Frontend SHALL 於 3 秒內建立一個新的 Session 並取得 Backend 回傳的 session_id。
2. THE Backend SHALL 為每個新 Session 產生一個符合 UUID v4 格式、不含 PII 且在所有現存 Session 中唯一的 session_id。
3. WHEN Session 建立成功，THE State_Machine SHALL 將 workflow state 初始化為 UNDERSTAND_EVENT。
4. THE Backend SHALL 將 Session 資料僅存於記憶體中，不持久化至任何外部儲存，且同時存在的 Session 數量上限為 10,000 個。
5. IF Session 建立過程中發生錯誤（如記憶體不足或已達 Session 數量上限），THEN THE Backend SHALL 回傳錯誤回應，包含指出失敗原因的錯誤訊息，且不產生新的 Session。
6. IF 某 Session 閒置超過 30 分鐘未收到任何使用者訊息，THEN THE Backend SHALL 自動清除該 Session 資料並釋放相關記憶體資源。
7. IF 使用者發送的第一則訊息為空白或超過 500 字元，THEN THE Backend SHALL 拒絕建立 Session 並回傳驗證錯誤訊息，指出訊息長度必須介於 1 至 500 字元。

### 需求 2：理解人生事件

**User Story:** 身為使用者，我希望用自然語言描述我遭遇的狀況，讓系統辨識出是哪一種人生事件，並提取判斷資格所需的去識別化屬性。

#### 驗收條件

1. WHILE State_Machine 處於 UNDERSTAND_EVENT 狀態，WHEN 使用者提交自然語言輸入（最多 500 字元），THE Agent SHALL 將輸入對應至已定義的人生事件類型清單（MVP 階段僅含「配偶死亡」），並向使用者確認辨識結果。
2. WHEN Agent 辨識出人生事件為「配偶死亡」且使用者確認無誤，THE Agent SHALL 提取去識別化的 Eligibility_Attributes，必須包含以下欄位：死亡日期、申請人與亡者之關係、投保身分；若使用者輸入中未包含上述任一欄位，Agent SHALL 透過追問取得該欄位值。
3. WHILE State_Machine 處於 UNDERSTAND_EVENT 狀態，THE Agent SHALL 僅能呼叫 resolve_life_event 工具。
4. WHEN Agent 辨識出人生事件類型且已取得所有必要 Eligibility_Attributes（死亡日期、申請人與亡者之關係、投保身分），THE State_Machine SHALL 轉換至 RESOLVE_ENTITLEMENTS 狀態。
5. IF Agent 無法在 3 次互動內辨識人生事件，THEN THE Agent SHALL 建議使用者轉介人工協助，並提供人工服務聯絡方式。
6. IF 使用者輸入無法對應至任何已定義的人生事件類型，THEN THE Agent SHALL 回應告知目前支援的人生事件範圍，並請使用者重新描述或選擇轉介人工協助。

### 需求 3：展開相關福利與行政事項

**User Story:** 身為使用者，我希望系統能自動列出與配偶死亡相關的所有福利與行政事項，避免遺漏重要申請。

#### 驗收條件

1. WHEN State_Machine 轉換至 RESOLVE_ENTITLEMENTS 狀態，THE Backend SHALL 以 life_event 值 `spouse_death` 查詢 Entitlement_Graph JSON 檔案，回傳該事件定義的所有 steps（MVP 為 4 項），每筆 step 包含 benefit_id、order、produces 與 requires 欄位。
2. THE Entitlement_Graph SHALL 包含 MVP 情境的四項 steps，其 benefit_id 分別為：`death_registration`、`labor_funeral_grant`、`survivor_pension`、`nhi_status_change`。
3. THE Backend SHALL 為每一項候選福利記錄其 program_id（對應 benefit_id）、所需欄位清單（取自該福利對應 rule 的 required_attributes；若 rule_id 為 null 則所需欄位清單為空）、以及負責機關名稱。
4. WHEN Backend 成功取得至少 1 筆候選福利且每筆皆包含 program_id 與負責機關，THE State_Machine SHALL 轉換至 COLLECT_MISSING_FIELDS 狀態。
5. IF Entitlement_Graph 檔案不存在、無法解析、或對應 life_event 查無任何 step，THEN THE Backend SHALL 回傳錯誤訊息指出無法載入該人生事件的福利關聯，且 State_Machine 不進行狀態轉換。

### 需求 4：收集缺漏資格欄位

**User Story:** 身為使用者，我希望系統只問我判斷資格所需、且尚未提供的資訊，避免重複提問或詢問無關問題。

#### 驗收條件

1. WHILE State_Machine 處於 COLLECT_MISSING_FIELDS 狀態，THE Agent SHALL 比對各候選福利所需欄位與已取得的 Eligibility_Attributes，列出缺漏欄位，並依據「可解鎖最多候選福利資格判斷」之順序排列優先級。
2. WHEN 存在缺漏欄位，THE Agent SHALL 以自然語言逐次詢問使用者，每次追問一個優先級最高的缺漏欄位（即填入該欄位後可滿足最多候選福利之必要條件者優先）。
3. WHEN 使用者回應追問，THE Agent SHALL 驗證回應是否可解析為該欄位預期的資料型別（如日期、數值、布林值或預定義選項）；若驗證通過，SHALL 立即更新 Session 中的 Eligibility_Attributes。
4. IF 使用者回應無法解析為該欄位預期的資料型別，THEN THE Agent SHALL 以自然語言說明預期的格式或選項，並重新詢問同一欄位，此次計為一次追問。
5. WHEN 所有候選福利的必要欄位皆已收集完成，THE State_Machine SHALL 轉換至 RETRIEVE_RULES 狀態。
6. IF 使用者對同一欄位連續 3 次回應皆無法提供有效值（包含明確表示不知道、回應與欄位無關、或回應無法解析為預期格式），THEN THE Agent SHALL 將該欄位標記為 unavailable，告知使用者哪些福利因該欄位缺漏無法判斷資格，並以已知資訊繼續評估其餘福利。
7. WHILE State_Machine 處於 COLLECT_MISSING_FIELDS 狀態，THE Backend SHALL 不傳送使用者原始自由文字至日誌或儲存，僅保留提取後的結構化屬性。
8. WHILE State_Machine 處於 COLLECT_MISSING_FIELDS 狀態，THE Agent SHALL 累計追問次數不超過 15 次；達到上限時，THE State_Machine SHALL 以當前已收集的 Eligibility_Attributes 轉換至 RETRIEVE_RULES 狀態。

### 需求 5：檢索官方規則

**User Story:** 身為使用者，我希望系統的判斷依據來自官方政府文件，而非 LLM 自行編造。

#### 驗收條件

1. WHEN State_Machine 轉換至 RETRIEVE_RULES 狀態，THE Retriever SHALL 針對每項候選福利，從 official_status 為 verified_official 的已核准文件中檢索規則段落，每項福利最多回傳 5 個段落。
2. THE Retriever SHALL 為每個檢索結果附上來源文件標題、發布機關名稱、原始 URL，以及該段落在來源文件中的定位資訊（如章節標題或段落編號）。
3. WHEN 檢索完成且至少有一項福利取得一個以上的規則段落，THE State_Machine SHALL 轉換至 EVALUATE_ELIGIBILITY 狀態。
4. IF 某項福利在所有已核准文件中未能匹配到任何規則段落，THEN THE Backend SHALL 將該項福利標記為 needs_human_review 狀態，並在回應中註明未找到規則的福利名稱。
5. WHILE State_Machine 處於 RETRIEVE_RULES 狀態，THE Agent SHALL 僅能呼叫 retrieve_official_rules 工具。
6. IF 檢索作業在 30 秒內未完成，THEN THE Backend SHALL 中止該次檢索，將所有未完成檢索的候選福利標記為 needs_human_review 狀態，並將錯誤事件寫入結構化日誌。
7. IF 檢索服務本身無法連線或回傳錯誤，THEN THE Backend SHALL 將該次請求中所有候選福利標記為 needs_human_review 狀態，並向呼叫端回傳錯誤訊息指出檢索服務不可用。

### 需求 6：確定性資格判斷

**User Story:** 身為使用者，我希望系統以規則引擎而非 LLM 判斷我是否符合資格，確保結果可重現、可稽核。

#### 驗收條件

1. WHEN State_Machine 轉換至 EVALUATE_ELIGIBILITY 狀態，THE Rule_Engine SHALL 以使用者的 Eligibility_Attributes 與檢索到的規則，對每項候選福利進行資格判斷，且相同的 Eligibility_Attributes 與相同的規則輸入在任何時間點執行皆 SHALL 產生相同的判斷結果。
2. THE Rule_Engine SHALL 為每項福利回傳結構化結果，包含：福利識別碼、福利名稱、狀態（eligible、ineligible、needs_information、needs_human_review 四者之一）、以及來源網址。
3. WHEN 判斷結果為 eligible，THE Rule_Engine SHALL 一併回傳預估金額（整數）或金額範圍標示（文字格式如「最低金額~最高金額」）；若該福利規則未定義金額相關欄位，則金額與金額標示皆為空值。
4. WHEN 判斷結果為 ineligible，THE Rule_Engine SHALL 回傳至少一條不符合資格的原因，每條原因須指明未通過的規則條件（例如：超過申請期限、設籍條件不符、骨灰骸類型不適用）。
5. WHEN 判斷結果為 needs_information，THE Rule_Engine SHALL 回傳缺少的使用者屬性欄位名稱清單（至少一項），以供系統向使用者追問。
6. WHEN 所有候選福利的資格判斷完成，THE State_Machine SHALL 轉換至 EXPLAIN_RESULT 狀態。
7. IF Rule_Engine 在評估過程中無法載入規則資料（例如資料來源不可用），THEN THE System SHALL 回傳錯誤指示，且不產出任何資格判斷結果，State_Machine 不得轉換至 EXPLAIN_RESULT 狀態。
8. WHILE State_Machine 處於 EVALUATE_ELIGIBILITY 狀態，THE Agent SHALL 僅能呼叫 evaluate_eligibility 工具。

### 需求 7：生成白話解釋

**User Story:** 身為使用者，我希望系統用我能理解的語言解釋判斷結果，而不是列出法律條文或系統代碼。

#### 驗收條件

1. WHEN State_Machine 轉換至 EXPLAIN_RESULT 狀態，THE Agent SHALL 以繁體中文為每項福利的資格判斷結果產生白話解釋，解釋中不得使用未經定義的法律專有名詞或系統內部代碼，若需引用法規名稱則須附上白話說明。
2. THE Agent SHALL 在每項福利的解釋中引用至少一個官方來源文件的標題與 URL 連結，使用者可驗證資訊來源。
3. THE Agent SHALL 明確區分「符合資格」、「不符合資格」、「資訊不足無法判斷」與「建議洽詢承辦人員」四種情況，且「不符合資格」的解釋須包含使用者不符合的具體條件描述。
4. WHEN 所有候選福利皆已產生對應的白話解釋，THE State_Machine SHALL 轉換至 CONFIRM 狀態。
5. WHILE State_Machine 處於 EXPLAIN_RESULT 狀態，THE Agent SHALL 不得呼叫任何工具，僅基於先前狀態已取得的判斷結果與檢索來源產生解釋。
6. IF Agent 無法為某項福利產生符合格式的白話解釋，THEN THE State_Machine SHALL 重試一次；若仍失敗，SHALL 將該項福利的解釋標記為 needs_human_review 並繼續處理其餘福利。

### 需求 8：使用者確認

**User Story:** 身為使用者，我希望在系統產出最終行動清單前，能夠確認結果是否正確、是否需要修改。

#### 驗收條件

1. WHEN State_Machine 轉換至 CONFIRM 狀態，THE Frontend SHALL 顯示資格判斷結果摘要，內容須包含：每項候選福利的名稱與判斷狀態（eligible / ineligible / needs_information / needs_human_review）、判斷所依據的 Eligibility_Attributes 值、以及各項福利對應的官方來源連結，並提供「確認」與「修正」兩種操作選項。
2. WHEN 使用者選擇確認結果正確，THE State_Machine SHALL 轉換至 COMPLETE 狀態。
3. WHEN 使用者要求修正某項 Eligibility_Attributes，THE State_Machine SHALL 轉換回 COLLECT_MISSING_FIELDS 狀態，收集修正後的屬性，並依序重新經過 RETRIEVE_RULES 與 EVALUATE_ELIGIBILITY 狀態完成重新評估，再轉換回 CONFIRM 狀態。
4. IF 使用者已累計修正達 3 次，THEN THE Frontend SHALL 顯示提示訊息建議使用者聯繫承辦人員協助，但仍允許使用者選擇繼續修正或確認目前結果。
5. THE Frontend SHALL 在確認畫面中以結構化方式顯示使用者提供的所有 Eligibility_Attributes 及其對應值，供使用者逐項核對。
6. IF 使用者於 CONFIRM 狀態超過 10 分鐘未進行任何操作，THEN THE Frontend SHALL 顯示提示訊息詢問使用者是否仍在操作，並保留目前的 Session 狀態不變。

### 需求 9：產出行動清單

**User Story:** 身為使用者，我希望取得一份完整的行動清單，告訴我要依序去哪些機關、準備哪些文件、有哪些期限。

#### 驗收條件

1. WHEN State_Machine 轉換至 COMPLETE 狀態，THE Backend SHALL 為所有 eligible 或 needs_information 的福利產出 Action_Checklist；needs_information 的項目須額外標註尚缺哪些資訊以及建議洽詢的承辦機關。
2. THE Action_Checklist SHALL 為每項福利包含以下欄位：建議申請順序（整數序號）、福利名稱、負責機關名稱、負責機關地址與電話、所需文件清單（列出每份文件名稱）、申請期限（以死亡日期為基準計算之截止日期）、預估金額或金額範圍（若 Rule_Engine 判斷結果有提供）、官方來源 URL。
3. THE Frontend SHALL 以結構化卡片或列表方式呈現 Action_Checklist，每張卡片包含福利名稱、機關、所需文件、期限與來源連結。
4. THE Action_Checklist SHALL 將死亡登記排在序號 1，其餘項目依申請期限由近至遠排序；若期限相同，則依 Entitlement_Graph 中定義的優先順序排列。
5. IF 所有候選福利皆為 ineligible 或 needs_human_review 而無任何 eligible 或 needs_information 項目，THEN THE Backend SHALL 回傳空的 Action_Checklist 並附帶訊息說明無可產出的行動項目，建議使用者洽詢承辦機關。
6. THE Action_Checklist SHALL 在清單末尾以摘要方式列出所有被判定為 ineligible 的福利名稱及其不符合資格的原因，供使用者參考。

### 需求 10：隱私保護

**User Story:** 身為使用者，我希望我的個人可識別資訊不會被傳送到後端伺服器，確保隱私安全。

#### 驗收條件

1. THE Frontend SHALL 在傳送任何使用者輸入至 Backend 之前，以固定長度遮罩字元取代偵測到的 PII，偵測範圍包含：姓名（連續 2-4 個中文字元符合姓名模式）、身分證字號（符合台灣國民身分證字號格式：1 個英文字母加 9 位數字）、地址（含縣市/鄉鎮區/路街/號之組合）、電話（符合台灣市話或行動電話格式）、email（符合 local@domain 格式）。
2. THE Backend SHALL 僅接收 sanitized text 與 allowlisted Eligibility_Attributes。
3. IF Backend 接收到的請求內容符合任一 PII 偵測模式（身分證字號格式、電話格式、email 格式），THEN THE Backend SHALL 拒絕該請求，回傳錯誤回應指出請求包含不允許的資料模式，且不處理該請求內容。
4. WHEN Backend 拒絕請求後，THE Frontend SHALL 顯示提示訊息告知使用者輸入包含個人資訊需重新輸入，Session 狀態維持不變。
5. WHEN Backend 完成屬性提取，THE Backend SHALL 立即從記憶體中丟棄原始自由文字，同一請求處理流程結束前不得將自由文字寫入任何暫存結構，僅保留結構化的 Eligibility_Attributes。
6. THE Backend SHALL 在所有日誌與追蹤紀錄中僅記錄結構化欄位（如 session_id、workflow state、program_id），使用者輸入的原始文字不得出現在任何 log 欄位中。
7. THE Frontend SHALL 不載入任何非本專案建置產出的第三方分析、廣告追蹤或錯誤回報 runtime 依賴；開發建置工具與編譯期依賴不受此限。

### 需求 11：安全邊界與錯誤處理

**User Story:** 身為使用者，我希望系統在遇到錯誤時能妥善處理，不會給出錯誤的資格判斷或卡在無限迴圈中。

#### 驗收條件

1. THE State_Machine SHALL 為每個狀態中的 Agent 執行設定最大迭代次數上限為 10 次；超過上限時停止 Agent 執行，向使用者回傳截至該時間點已收集的部分結果，並將該步驟標記為 needs_human_review。
2. WHILE Agent 處於任何狀態，THE State_Machine SHALL 僅允許該狀態定義的工具清單中的工具被呼叫；IF Agent 嘗試呼叫不在允許清單中的工具，THEN THE State_Machine SHALL 拒絕該呼叫並記錄違規事件。
3. IF Backend 發生未預期錯誤，THEN THE Backend SHALL 回傳結構化錯誤回應（含錯誤類型分類與繁體中文非技術性使用者訊息），而非暴露內部堆疊追蹤。
4. IF Agent 產出的結果未通過該狀態對應的 Pydantic schema 驗證，THEN THE State_Machine SHALL 重試一次；若仍失敗，SHALL 將該步驟標記為 needs_human_review 並向使用者顯示訊息表示該項目需要人工協助。
5. THE State_Machine SHALL 記錄每次狀態轉換的 ISO 8601 時間戳、來源狀態、目標狀態與觸發原因，供除錯與稽核使用。
6. THE State_Machine SHALL 為每次工具呼叫（含 Retriever 查詢與 Rule_Engine 評估）設定 30 秒逾時上限；IF 工具呼叫超過逾時上限未回應，THEN THE State_Machine SHALL 終止該呼叫、記錄逾時事件，並視為該次執行失敗以觸發重試邏輯。
7. IF State_Machine 在某狀態遭遇不可恢復錯誤（重試後仍失敗且無部分結果可回傳），THEN THE State_Machine SHALL 轉換至 CONFIRM 狀態，向使用者呈現已完成的部分結果並明確標示哪些福利項目無法完成評估。

### 需求 12：前端對話互動

**User Story:** 身為使用者，我希望透過類似聊天的介面與系統互動，能夠自然地描述我的狀況並即時看到回應。

#### 驗收條件

1. THE Frontend SHALL 提供以對話氣泡形式呈現的聊天介面，使用者訊息靠右對齊、系統回應靠左對齊，並以不同背景色區分訊息來源。
2. WHEN Backend 正在處理請求，THE Frontend SHALL 在 200 毫秒內顯示載入指示器（如動畫圓點或 spinner），告知使用者系統正在運作。
3. IF Backend 回應超過 30 秒未返回，THEN THE Frontend SHALL 隱藏載入指示器並顯示逾時提示訊息，告知使用者可重新發送或稍後再試。
4. WHEN 系統需要使用者提供特定資訊（如 COLLECT_MISSING_FIELDS 狀態的追問），THE Frontend SHALL 以視覺上與一般回應有所區隔的問題格式呈現，包含問題文字與可供輸入的欄位，讓使用者明確知道需要回答什麼。
5. THE Frontend SHALL 提供文字輸入區域與送出按鈕，使用者輸入長度上限為 500 字元，且不可送出空白訊息。
6. THE Frontend SHALL 支援最小視窗寬度 320px 至最大 1920px 的響應式佈局，所有互動元素在觸控裝置上的點擊目標不小於 44×44px。
7. WHEN 新訊息產生，THE Frontend SHALL 自動捲動至最新訊息，確保使用者無需手動捲動即可看到最新回應。
