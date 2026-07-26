# Official Sources

## Reference datasets

### Government agency unique identification code (OID)

- Purpose: Central and local government organization registry
- Publisher: Ministry of Digital Affairs
- Dataset page: <https://data.gov.tw/dataset/7081>
- Download URL: <https://oid.nat.gov.tw/OIDWeb/GDS.csv>
- Government data quality snapshot:
  <https://quality.data.gov.tw/dq_download_csv.php?nid=7081&md5_url=19e6620647cbf3e9f46f7914498c71ca>
- License: Open Government Data License, version 1.0
- Official fields: `OrgName`, `OID`, `TEL`, `Address`, `DN`, `OrgCode`
- Dataset identifier: `A41000000G-000002`
- Retrieval date: 2026-07-25
- Local use: Build the ignored `data/local/government_oid.db` SQLite registry
  with `scripts/import_government_oid.py`
- Availability note: If the OID download host closes the request, the importer
  falls back to the official government data quality snapshot and prints the
  retrieval URL it used.
- Validation note: Treat the number actually parsed and committed by a
  successful sync run as the local database count. Do not assume the dataset
  metadata count and the OID statistics page count are identical.

## Benefit and administrative sources

### 我的 E 政府：綠色殯葬主題頁

- Purpose: 第一輪親人過世主題的地方政府服務與環保葬候選入口
- Publisher: 我的 E 政府
- Entry page: <https://www.gov.tw/News_Content_26_666371>
- Access method: Reviewed index page
- Local source ID: `my_egov`
- Reviewed date: 2026-07-26

### 臺北市殯葬管理處：參加聯合奠祭

- Purpose: 第一輪政府負擔或減免喪葬服務的正式頁面
- Publisher: 臺北市殯葬管理處
- Entry page: <https://mso.gov.taipei/cp.aspx?n=485C4E58C9A2DD7B>
- Access method: Reviewed agency page
- Local source ID: `taipei_funeral_services`
- Reviewed date: 2026-07-26

第一批經人工核准下載的 5 筆頁面記錄在
`data/benefit_discovery/death_benefit_first_batch.v0.1.json`。其中「批准下載」只表示
允許 connector 取得頁面，不表示已確認方案有效或完成資格審查。

後續每筆正式福利或行政事項來源至少記錄：

- 福利或行政事項名稱
- 發布機關
- 官方 URL
- 發布或更新日期
- 取得日期
- 適用規則與版本備註
