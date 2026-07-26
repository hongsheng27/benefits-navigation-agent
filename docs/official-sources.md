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

尚待整理。每筆福利或行政事項來源至少記錄：

- 福利或行政事項名稱
- 發布機關
- 官方 URL
- 發布或更新日期
- 取得日期
- 適用規則與版本備註
