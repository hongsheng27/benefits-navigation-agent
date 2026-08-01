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

## 中央部會官方來源接點

以下 32 個中央政府機關已在 `data/source_registry/initial_sources.v0.1.json` 註冊為
`agency_site` 類型來源，並與 `government_oid.db` 的 OID 完成對應。目前 `entry_url`
指向各機關首頁，尚未設定特定福利頁 connector；待人工審查後再更新 `reviewed_at`
並指定實際入口頁。

### 15 部

| source_id | 機關名稱 | OID | 官方網站 |
|-----------|----------|-----|----------|
| `moi` | 內政部 | `2.16.886.101.20003.20001` | <https://www.moi.gov.tw/> |
| `mofa` | 外交部 | `2.16.886.101.20003.20002` | <https://www.mofa.gov.tw/> |
| `mnd` | 國防部 | `2.16.886.101.20003.20003` | <https://www.mnd.gov.tw/> |
| `mof` | 財政部 | `2.16.886.101.20003.20004` | <https://www.mof.gov.tw/> |
| `moe` | 教育部 | `2.16.886.101.20003.20005` | <https://www.edu.tw/> |
| `moj` | 法務部 | `2.16.886.101.20003.20006` | <https://www.moj.gov.tw/> |
| `moea` | 經濟部 | `2.16.886.101.20003.20007` | <https://www.moea.gov.tw/> |
| `motc` | 交通部 | `2.16.886.101.20003.20008` | <https://www.motc.gov.tw/> |
| `mol` | 勞動部 | `2.16.886.101.20003.20063` | <https://www.mol.gov.tw/> |
| `moa` | 農業部 | `2.16.886.101.20003.20064` | <https://www.moa.gov.tw/> |
| `mohw` | 衛生福利部 | `2.16.886.101.20003.20065` | <https://www.mohw.gov.tw/> |
| `moenv` | 環境部 | `2.16.886.101.20003.20083` | <https://www.moenv.gov.tw/> |
| `moc` | 文化部 | `2.16.886.101.20003.20067` | <https://www.moc.gov.tw/> |
| `moda` | 數位發展部 | `2.16.886.101.20003.20082` | <https://moda.gov.tw/> |
| `mosa` | 運動部 | `2.16.886.101.20003.20086` | <https://www.sports.gov.tw/> |

### 10 委員會

| source_id | 機關名稱 | OID | 官方網站 |
|-----------|----------|-----|----------|
| `ndc` | 國家發展委員會 | `2.16.886.101.20003.20069` | <https://www.ndc.gov.tw/> |
| `nstc` | 國家科學及技術委員會 | `2.16.886.101.20003.20081` | <https://www.nstc.gov.tw/> |
| `mac` | 大陸委員會 | `2.16.886.101.20003.20033` | <https://www.mac.gov.tw/> |
| `fsc` | 金融監督管理委員會 | `2.16.886.101.20003.20052` | <https://www.fsc.gov.tw/> |
| `oac` | 海洋委員會 | `2.16.886.101.20003.20070` | <https://www.oac.gov.tw/> |
| `ocac` | 僑務委員會 | `2.16.886.101.20003.20010` | <https://www.ocac.gov.tw/> |
| `vac` | 國軍退除役官兵輔導委員會 | `2.16.886.101.20003.20016` | <https://www.vac.gov.tw/> |
| `cip` | 原住民族委員會 | `2.16.886.101.20003.20036` | <https://www.cip.gov.tw/> |
| `hakka` | 客家委員會 | `2.16.886.101.20003.20043` | <https://www.hakka.gov.tw/> |
| `pcc` | 行政院公共工程委員會 | `2.16.886.101.20003.20035` | <https://www.pcc.gov.tw/> |

### 2 總處

| source_id | 機關名稱 | OID | 官方網站 |
|-----------|----------|-----|----------|
| `dgbas` | 行政院主計總處 | `2.16.886.101.20003.20071` | <https://www.dgbas.gov.tw/> |
| `dgpa` | 行政院人事行政總處 | `2.16.886.101.20003.20072` | <https://www.dgpa.gov.tw/> |

### 中央銀行與故宮博物院

| source_id | 機關名稱 | OID | 官方網站 |
|-----------|----------|-----|----------|
| `cbc` | 中央銀行 | `2.16.886.101.20003.20025` | <https://www.cbc.gov.tw/> |
| `npm` | 國立故宮博物院 | `2.16.886.101.20003.20018` | <https://www.npm.gov.tw/> |

### 3 獨立機關

| source_id | 機關名稱 | OID | 官方網站 |
|-----------|----------|-----|----------|
| `cec` | 中央選舉委員會 | `2.16.886.101.20003.20026` | <https://www.cec.gov.tw/> |
| `ftc` | 公平交易委員會 | `2.16.886.101.20003.20034` | <https://www.ftc.gov.tw/> |
| `ncc` | 國家通訊傳播委員會 | `2.16.886.101.20003.20056` | <https://www.ncc.gov.tw/> |

### URL 驗證備註

- 多數機關官網回應 HTTP 200。
- 經濟部、環境部、國發會、陸委會、通傳會回應 HTTP 403，但經 web_fetch 確認
  為 WAF 擋 script（非瀏覽器 User-Agent），實際網站內容可正常取得。
- 運動部使用 `www.sports.gov.tw`（非 `www.sa.gov.tw`，後者為全民運動署）。
- 所有 `publisher_oid` 皆已比對 `government_oid.db` 確認存在。
