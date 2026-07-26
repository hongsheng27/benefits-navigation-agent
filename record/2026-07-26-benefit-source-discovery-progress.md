# 政府補助來源建置進度紀錄

- 紀錄日期：2026-07-26
- 功能分支：`feat/benefit-source-discovery`
- 目前主題：親人過世後可使用的政府補助、費用減免與政府服務
- 目前狀態：已完成本機 OID 資料庫、來源登記、入口頁同步、候選清單及第一批 5 筆頁面下載

## 一、這次要解決的問題

系統未來不能在每次使用者提問時才搜尋政府網站。這樣會重複消耗網路請求、執行時間
與 AI token，而且同一個問題可能因搜尋結果變動而得到不同答案。

目前採用的做法是先建立本機資料流程：

1. 匯入政府機關 OID，建立政府機關基本資料。
2. 登記允許連線的官方資料來源。
3. 定期同步指定的官方入口頁。
4. 從入口頁找出可能有用的子連結。
5. 人工確認哪些連結是真的補助、減免或政府服務。
6. 之後才下載確認過的子頁，抽取申請資格、金額、期限與辦理方式。
7. 使用者查詢時讀取已整理的資料，不在當下重新爬完整網站。

關鍵原則是：

- 關鍵字只負責發現與排序候選，不直接判定一筆資料是補助。
- AI 可以協助理解文字，但不能自行決定使用者是否符合資格。
- 正式方案必須保留官方來源網址與證據。
- 網站發布機關不一定是補助主管機關，機關角色要另外確認。

## 二、目前已完成的功能

### 1. 政府機關 OID SQLite 資料庫

官方來源是數位發展部政府機關 OID 資料集。匯入程式會把 CSV 轉成：

```text
data/local/government_oid.db
```

目前實際匯入的有效機關數是 **7,988 筆**。

主要資料表：

| 資料表 | 用途 |
| --- | --- |
| `government_organizations` | 保存官方 OID、機關名稱、地址、電話等資料 |
| `tags` | 保存專案自己建立的標籤 |
| `organization_tags` | 建立機關與標籤的多對多關係 |
| `sync_runs` | 記錄每次 OID 匯入結果 |
| `schema_metadata` | 記錄本機 schema 版本 |

官方資料更新時只更新官方欄位，不覆寫專案標籤。新版本缺少的 OID 先標記為 inactive，
不直接刪除。

### 2. 補助來源與證據 catalog

同一個 SQLite 檔案另外建立來源與補助 catalog，與 OID 匯入紀錄分開。

主要資料表：

| 資料表 | 用途 |
| --- | --- |
| `source_registry` | 登記來源名稱、網址、存取方式與連線狀態 |
| `source_sync_runs` | 記錄每次網站同步成功、失敗與數量 |
| `source_documents` | 保存已下載官方文件的網址、標題、雜湊與本機位置 |
| `document_discoveries` | 記錄某份文件是從哪個來源找到的 |
| `benefit_programs` | 未來保存人工確認後的正式補助方案 |
| `program_sources` | 保存方案所使用的官方證據 |
| `program_organization_roles` | 保存主管、受理、執行或發布機關角色 |

目前登記三個來源：

| 來源 | 用途 | 目前狀態 |
| --- | --- | --- |
| 數位發展部政府機關 OID | 政府機關 reference dataset | active |
| 我的 E 政府 | 親人過世與綠色殯葬入口頁 | active |
| 臺北市殯葬管理處 | 參加聯合奠祭官方頁面 | active |

### 3. 兩個政府入口頁的最小對接

目前只同步兩個已人工確認的入口頁：

1. 我的 E 政府：
   `https://www.gov.tw/News_Content_26_666371`
2. 臺北市殯葬管理處：
   `https://mso.gov.taipei/cp.aspx?n=485C4E58C9A2DD7B`

同步程式目前只做：

- 下載指定入口頁 HTML。
- 記錄最後網址、標題、HTTP 狀態、抓取時間與內容雜湊。
- 把原始 HTML 存在本機。
- 網頁內容沒有實質變動時標記為 unchanged。
- 發生錯誤時保存失敗紀錄。

同步程式目前不做：

- 不爬完整網站。
- 不自動展開或下載子連結。
- 不呼叫 AI。
- 不建立正式補助方案。

### 4. 第一輪子連結發現

連結發現程式讀取已下載的入口頁，不重新連網。兩個政府頁面都使用
`CCMS_Content` 標示主要內容區，因此程式只讀這個區域，避開網站選單、分享按鈕與
頁尾連結。

處理順序：

1. 讀取本機入口頁 HTML。
2. 找出主要內容中的 `<a href>`。
3. 將相對網址轉成完整網址。
4. 移除頁內跳轉、JavaScript、Email、電話與重複網址。
5. 標記網址是否屬於臺灣政府網域。
6. 使用 v0.2 關鍵字將候選排序為 high、medium 或 review。
7. 將結果輸出成本機 JSON。

目前結果：

| 項目 | 數量 |
| --- | ---: |
| 全部候選連結 | 71 |
| 臺灣政府網域 | 69 |
| 我的 E 政府入口頁候選 | 69 |
| 臺北市殯葬管理處入口頁候選 | 2 |
| high | 8 |
| medium | 18 |
| review | 45 |

候選排序不是正式分類。例如「聯合奠祭捐款」命中「聯合奠祭」，但它是捐款入口，
不是提供給家屬的補助，因此後續人工審查應排除。

## 三、親人過世主題的收錄範圍

第一輪優先收錄：

- 喪葬、殮葬、火化、納骨等現金或費用補助。
- 公立殯葬設施費用免收、減徵或優惠。
- 聯合奠祭等直接降低家屬支出的政府服務。
- 重要的死亡或喪葬社會保險給付。
- 因死亡事實發給的一次性救助、慰問或補償。

次要收錄：

- 遺屬年金、遺屬津貼等持續生活支持。
- 撫卹與犯罪被害補償等特殊制度資源。

第一輪排除：

- 只有死亡登記、除戶或證件註銷的行政說明。
- 遺產稅與一般繼承資訊。
- 私人殯葬商品、廣告、業者或民間募款。
- 動物、家畜、家禽或寵物補助。
- 純新聞、統計、預決算、採購或活動紀錄。

## 四、候選連結怎麼人工挑選

### 優先下載

同時符合以下條件：

- 是已確認的政府官方來源。
- 與死亡、喪葬或遺族直接相關。
- 提供金錢、免費服務、費用減免或可請領的給付。
- 頁面可能包含資格、金額、期限或辦理方式。

第一批已核准下載：

1. 臺北市多元環保葬鼓勵金。
2. 新北市環保葬鼓勵金。
3. 桃園市環保葬鼓勵金。
4. 澎湖縣多元環保葬補助。
5. 臺北市參加聯合奠祭。

實際下載結果：

| 項目 | 結果 |
| --- | --- |
| 臺北市多元環保葬鼓勵金 | 已下載；原候選網址回傳 404，改用同機關目前有效的官方頁面 |
| 新北市環保葬鼓勵金 | 已下載 |
| 桃園市環保葬鼓勵金 | 已下載 |
| 澎湖縣多元環保葬補助 | 已下載 |
| 臺北市參加聯合奠祭 | 沿用先前已下載的正式頁面 |

第一批清單只代表專案負責人批准下載，尚未代表這 5 筆都已完成方案、金額、資格與期限
的正式審查。資料庫目前共有 6 份來源文件，正式方案仍為 0 筆。

### 暫時保留

標題可能有用，但無法直接確認是否提供補助：

- 收費標準。
- 殯葬資訊入口。
- 下載專區。
- 申辦標準流程。

### 排除

- 捐款。
- 場次查詢或活動日曆。
- 統計、芳名錄或成果報告。
- 純祭拜、殯葬知識或行政說明。

## 五、重建與操作指令

所有指令都要在 repository 根目錄執行。

### 1. 匯入政府 OID

```bash
python3 scripts/import_government_oid.py
```

如果已經先下載官方 `GDS.csv`：

```bash
python3 scripts/import_government_oid.py --source-file /path/to/GDS.csv
```

### 2. 初始化來源與方案 catalog

```bash
python3 scripts/init_benefit_catalog.py
```

### 3. 同步兩個指定政府入口頁

```bash
python3 scripts/sync_benefit_sources.py
```

### 4. 從入口頁產生子連結候選

```bash
python3 scripts/discover_benefit_links.py
```

輸出位置：

```text
data/local/discovered_links/first_round.json
```

### 5. 下載人工核准的第一批頁面

```bash
python3 scripts/fetch_reviewed_benefit_pages.py
```

核准清單：

```text
data/benefit_discovery/death_benefit_first_batch.v0.1.json
```

### 6. 執行目前相關測試

```bash
python3 -m unittest \
  backend.tests.unit.test_import_government_oid \
  backend.tests.unit.test_benefit_catalog \
  backend.tests.unit.test_source_connector \
  backend.tests.unit.test_link_discovery \
  backend.tests.unit.test_reviewed_page_batch
```

### 7. 檢查 SQLite

```bash
sqlite3 data/local/government_oid.db
```

進入 SQLite 後可執行：

```sql
.tables
SELECT COUNT(*) FROM government_organizations WHERE active = 1;
SELECT source_id, name, connection_status FROM source_registry;
SELECT COUNT(*) FROM source_documents;
.quit
```

## 六、重要檔案位置

| 路徑 | 內容 |
| --- | --- |
| `scripts/import_government_oid.py` | OID 下載、驗證與 SQLite 匯入 |
| `backend/app/services/benefit_catalog.py` | 補助來源與證據 catalog schema |
| `scripts/init_benefit_catalog.py` | 初始化 catalog |
| `backend/app/services/source_connector.py` | 指定政府入口頁下載與同步紀錄 |
| `scripts/sync_benefit_sources.py` | 執行兩個入口頁同步 |
| `backend/app/services/link_discovery.py` | 主要內容連結抽取、去重與排序 |
| `scripts/discover_benefit_links.py` | 產生第一輪候選連結報告 |
| `data/benefit_discovery/death_benefit_first_batch.v0.1.json` | 第一批人工核准下載清單 |
| `scripts/fetch_reviewed_benefit_pages.py` | 只下載核准清單中的政府頁面 |
| `data/source_registry/initial_sources.v0.1.json` | 可審查的初始來源設定 |
| `data/benefit_discovery/death_benefit_keywords.v0.2.json` | 親人過世候選發現詞 |
| `data/evaluations/death_benefit_discovery.v0.2.json` | 固定測試案例 |
| `docs/benefit-discovery/death-benefit-discovery-v0.2.md` | 搜尋與人工審查規格 |
| `docs/decisions/0008-use-generated-sqlite-for-government-oid.md` | SQLite OID 決策 |
| `docs/decisions/0009-use-local-provenance-first-benefit-catalog.md` | 來源與證據 catalog 決策 |

## 七、哪些資料不會上傳到 GitHub

下列檔案是本機產物，已被 `.gitignore` 排除：

- `data/local/government_oid.db`
- `data/local/source_documents/` 下的原始 HTML
- `data/local/discovered_links/first_round.json`

原因是它們可以由指令重新產生，而且原始網站內容可能很大或頻繁變動。GitHub 分支會
保存程式、schema、來源設定、關鍵字、測試與本進度紀錄。協作者 clone 分支後需要執行
「第五節」的指令，才能在自己的電腦產生相同類型的本機資料。

## 八、目前還沒完成

- 71 個候選中只處理第一批 5 筆，其餘候選尚未審查或下載。
- 尚未把任何候選標記成正式補助方案。
- 尚未抽取金額、資格、期限、應備文件或申請方式。
- 尚未建立人工審查前端。
- 尚未完成全臺所有來源。
- 尚未決定 AWS 正式資料庫使用 DynamoDB、RDS 或其他服務。
- 尚未建立 SQLite 到 AWS database 的正式 migration adapter。

## 九、合作時需要注意

- `README.md`、catalog schema、關鍵字與評估案例是容易發生衝突的檔案，修改前先確認
  是否有人正在處理。
- schema、資格規則、關鍵字判定與 AI prompt 需要專案負責人審查。
- 不要把 credentials、使用者個資、`.env`、本機 SQLite 或原始大型文件提交到 Git。
- 提交前至少執行相關測試與 `git diff --check`。
- 本分支建立時，遠端 `main` 已新增 ADR-0006 與 ADR-0007，所以本功能的兩份 ADR
  使用 ADR-0008 與 ADR-0009，避免編號衝突。
