---
inclusion: auto
---

# Hackathon AWS Constraints (Auto-loaded)

2026 Taiwan Generative AI Application Hackathon 使用規範與限制。
以競賽期間實際環境或公告為最終依據。

## 一般性使用規範

1. **S3 禁止公開存取** — 必須透過 S3 Block Public Access 或 Bucket Policy 限制。
2. **禁止敏感資料** — 不得在 AWS 帳戶中使用/匯入任何：個人資料、受管制資料、
   財務資訊、種族/民族/政治/宗教/哲學/工會/性取向/性生活資訊、基因資料、
   生物識別資料、健康資料、付款處理資料、惡意程式碼。
3. **EC2 Security Group** — 禁止對外完全開放。
4. **RDS / EMR** — 禁止啟用公開存取。
5. **資源節約** — 僅啟動工作必要的執行個體數量，避免浪費。
6. **指定區域** — 以 `us-east-1` 與 `us-west-2` 作為部署主要區域。
7. **支援服務** — 僅限 `docs/hackathon-aws-services-reference.md` 列出之服務。
8. **禁止提交機密** — 上傳 GitHub 或公開儲存庫前確認未包含 AWS Access Keys、
   API Tokens、資料庫密碼等。使用 `.gitignore` 與環境變數管理。
9. **Kiro 資料夾須公開** — `/.kiro` 資料夾不得加入 `.gitignore`，須展示
   specs、hooks、steering 使用情況。

## Amazon Bedrock 規範

- 請求限制：每秒 1 個請求以下（RPS/TPS）。
- 僅申請當前專案直接相關之模型存取權，不得大量啟用所有模型。
- 定期檢閱並撤銷不再使用的模型存取權。

## Amazon EC2 & SageMaker AI 規範

- 可用執行個體類型與限額見 `docs/hackathon-aws-services-reference.md`。
- 限制可能依實際情況調整，以競賽期間環境為準。
- **不建議**在 AWS 平台進行大規模模型訓練。

## EC2 vCPU 限額摘要

| 類型 | vCPU 限額 |
|------|-----------|
| Standard (A, C, D, H, I, M, R, T, Z) | 256 |
| HPC | 192 |
| DL | 96 |
| F | 64 |
| Inf | 8 |
| Trn | 8 |
| G and VT | 0 |
| P | 0 |
| High Memory | 0 |
| X | 0 |

## 對本專案的影響

- 部署區域鎖定 `us-east-1` 或 `us-west-2`。
- 不可使用 GPU (G/P) 執行個體做推論或訓練 — 必須使用 Bedrock managed models。
- Bedrock 呼叫需加 rate limiter（< 1 RPS）。
- RDS PostgreSQL（ADR-0014 目標）可用，但須確認不啟用公開存取。
- S3 可用於文件儲存，須確保 Block Public Access 啟用。
