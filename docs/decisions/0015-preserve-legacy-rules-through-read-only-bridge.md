# ADR-0015: 以唯讀 Bridge 保存 Legacy Rule Fields

- Status: Accepted
- Date: 2026-07-29
- Complements: [ADR-0013: 在 Repository 邊界後使用 SQLite 作為 Runtime 真相來源](0013-use-sqlite-runtime-behind-repositories.md)
- Complements: [ADR-0014: 以 RDS PostgreSQL 與 S3 作為 Hackathon 資料層目標](0014-target-rds-postgresql-and-s3.md)

## 背景

現有 runtime rule reader 與 review tooling 使用 writable `program_rule_fields` table；finalized data-layer design 則要求 canonical Rule DSL 成為唯一可寫真相，`program_rule_fields` 只能是自動產生的唯讀相容投影。

Tasks 1.5 與 1.6 有一個 migration ordering 衝突：version 5 需要建立同名 compatibility view，但 legacy database 在 version 5 前仍有同名 table。SQLite 不允許 table 與 view 同名。若直接刪除或隱藏 legacy rows，目前 reader 會立即失去規則；若保留 writable table，則會繼續產生第二份真相。

Legacy rows 也沒有足夠資訊可靠重建 nested boolean semantics、operator、field registry reference 或 source reference。Converter 不得猜測這些資料，也不得把 machine-generated output 自動核准。

## 決定

1. Version 5 對 fresh database 建立只讀 `program_rule_fields` compatibility view；對 known legacy database 暫時保留同名 table，但立即以 triggers 拒絕 INSERT、UPDATE 與 DELETE。
2. Version 6 在同一 transaction 先計算 legacy schema與row SHA-256 inventory，再將 table rename為 `legacy_program_rule_fields_v1`，並以 triggers永久凍結。
3. Version 6 的 `program_rule_fields` view優先讀取active canonical compatibility generation；尚無active generation的program才讀取frozen legacy rows。
4. 每個program一旦啟用canonical generation，view不再回傳該program的legacy rows。Legacy artifact仍保留供audit與comparison使用。
5. Legacy converter只建立deterministic、可重跑且狀態為 `under_review` 的conversion manifest。它不建立不完整canonical Rule DSL，也不推定operator、nested logic、source reference或evidence。
6. Existing legacy readers可在migration window繼續讀取bridge；既有review server的legacy write endpoints將被read-only triggers拒絕。新的canonical review write path由後續task實作。
7. Compatibility cutover完成並經owner再次核准前，不移除legacy artifact或bridge fallback。

## 理由

- 保留現有讀取行為，同時立即停止legacy雙寫。
- Frozen legacy rows不再是可變真相；canonical generation可逐program安全接管。
- 不完整的legacy欄位不會被偽裝成可執行或已核准Rule DSL。
- Version 5與version 6各自都是可驗證、可rollback且可重新執行的committed state。
- 相同table、view與trigger語意可在未來PostgreSQL migration中以view、permissions與transaction重建。

## 後果

### 正面

- Migration中途停在version 5時，legacy rows仍可讀但已不可修改。
- Canonical generation切換不會讓reader看見partial rows。
- Inventory與per-program draft hashes提供人工mapping及audit基準。
- Converter、crawler、importer或LLM都不能把legacy資料自動升級為verified。

### 負面與成本

- `program_rule_fields` view在migration window含有明確的legacy fallback branch。
- Existing review server的PUT／DELETE rule-field operations在migration後會失敗，直到canonical review tooling完成。
- Legacy artifact需保留到compatibility cutover完成，增加暫時的schema與測試成本。
- PostgreSQL cutover需重建同等read-only permissions、active-generation switching與inventory validation。

## 遷移與回滾

1. 只在temporary SQLite copy先執行dry run。
2. Apply前建立獨立backup；version 5凍結legacy table。
3. Version 6 transaction內完成pre-rename inventory、rename、read-only triggers、under-review manifests與bridge view。
4. 任一步失敗時rollback回前一schema version；apply-level failure由migration CLI從backup恢復。
5. Canonical generation通過round-trip及human review後，才atomic更新active pointer。
6. Legacy fallback removal需要獨立owner-approved compatibility cutover。

## 相關文件

- [Data-layer Rule Engine design](../../.kiro/specs/data-layer-rule-engine/design.md)
- [AWS migration guide](../aws_migration_guide.md)
