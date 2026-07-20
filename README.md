# 接住 — Benefits Navigation Agent

「接住」是一個以人生事件為入口、重視隱私與政策依據的福利導航 Agent，
預計參加 2026 Taiwan Generative AI Application Hackathon 創意交流組。

> 本專案目前仍在規劃期。以下技術棧分為「暫定」與「待決策」，不是最終實作承諾。

## 問題

面臨重大人生事件的人，往往不知道有哪些相關福利、由哪個政府機關負責、
是否符合資格，以及申請時需要準備哪些文件。

## 解法與主要功能

使用者以自然語言描述人生事件後，系統將：

1. 辨識人生事件與去識別化的資格屬性。
2. 展開可能相關、且可能跨機關的福利與行政事項。
3. 只追問判斷資格所需的缺漏資訊。
4. 檢索官方政府文件與規則。
5. 以確定性規則判斷資格，不讓 LLM 自行決定是否符合資格。
6. 產生附官方來源、申請順序與文件需求的行動清單。
7. 在重要操作前要求使用者確認，必要時轉介人工協助。

## 暫定架構

```text
React Web UI
    ↓
Backend API
    ↓
Policy-governed State Machine
    ├── Event / profile extraction (LLM)
    ├── Curated entitlement graph
    ├── Official-document RAG
    ├── Deterministic eligibility rule engine
    ├── Grounded explanation (LLM)
    └── Human confirmation / escalation
    ↓
AWS deployment, logging and observability
```

預計流程狀態：

```text
UNDERSTAND_EVENT
  → RESOLVE_ENTITLEMENTS
  → COLLECT_MISSING_FIELDS
  → RETRIEVE_RULES
  → EVALUATE_ELIGIBILITY
  → EXPLAIN_RESULT
  → CONFIRM
  → COMPLETE
```

架構原則：

- Workflow / state machine 控制流程、安全界線、停止條件與人工確認。
- LLM 負責自然語言理解、挑選下一個必要問題及白話解釋。
- Rule engine 負責資格判斷。
- RAG 只使用官方文件，回答需保留來源。
- Entitlement graph 只描述福利與機關的關聯；MVP 不做完整 GraphRAG。
- Agent 只能呼叫目前狀態允許的工具，並限制最大迭代次數。

## 暫定技術棧

| Layer | 暫定選擇 | 狀態 / 用途 |
| --- | --- | --- |
| Frontend | React、Vite、TypeScript、Tailwind CSS | 暫定；對話、資格問題、結果與 checklist UI |
| Backend | Python、Pydantic、boto3 | 暫定；API、結構化資料與 AWS 整合 |
| API framework | FastAPI 或 AWS Lambda handler | **待決策** |
| LLM | Amazon Bedrock 上的模型 | 暫定使用 Bedrock；模型尚未決定 |
| Agent orchestration | 自製 state machine；Strands Agents 為候選 | **待決策**；傾向混合方案 |
| Agent hosting | Amazon Bedrock AgentCore Runtime | 暫定；需確認比賽帳號權限與現場可用性 |
| Agent tools | `resolve_life_event`、`retrieve_official_rules`、`evaluate_eligibility` | MVP 暫定三個核心工具 |
| Document storage | Amazon S3 | 暫定；存放官方文件與處理後資料 |
| RAG | Amazon Bedrock Knowledge Bases 或自製 retrieval | **待決策** |
| Vector store / embeddings | 由 Bedrock Knowledge Bases 管理或自選方案 | **待決策** |
| Entitlement graph | JSON / Python mapping 或 DynamoDB | **待決策**；不使用完整 GraphRAG / Neptune 作為 MVP 前提 |
| Eligibility rules | Python / JSON 規則 + Pydantic validation | 暫定；規則判斷必須是 deterministic |
| Session / application data | DynamoDB | 選用；只有跨請求狀態需要保存時才加入 |
| Safety | Dynamic tool allowlist、輸入驗證、human-in-the-loop | 暫定核心機制 |
| Guardrails | Amazon Bedrock Guardrails / AgentCore Policy | 選用；依時間與帳號權限決定 |
| Observability | Amazon CloudWatch | 暫定；記錄狀態轉換、tool call、延遲與錯誤 |
| Deployment | AWS Amplify、Lambda、AgentCore Runtime 的組合 | **待決策** |
| Infrastructure as Code | AWS SAM、CDK 或手動設定 | **待決策**；Hackathon 以速度為優先 |
| Testing | pytest；前端測試工具待定 | 暫定；以 eligibility 與 end-to-end evaluation 為優先 |

## Agent Orchestration：尚未定案

目前考慮三種方式：

1. **自製 state machine**：控制力、可測試性最高，適合資格與隱私流程；需要自行撰寫 orchestration。
2. **Strands Agents 主導 agent loop**：tool calling 開發較快，但執行順序較不確定。
3. **混合方案（目前較傾向）**：自製 state machine 作為外層控制，Strands 只用在事件理解、下一題選擇與 grounded explanation 等節點。

無論採用哪一種方案，LLM / Agent 都不直接決定福利資格，也不能繞過狀態檢查、
PII 邊界或人工確認。

## 待決策清單

- [ ] 純自製 state machine，或 state machine + Strands Agents。
- [ ] AgentCore Runtime 是否列為 MVP 必要元件，或先以 Lambda 執行。
- [ ] Bedrock 使用的 chat model 與 embedding model。
- [ ] 使用 Bedrock Knowledge Bases，或自行實作小型 RAG pipeline。
- [ ] Entitlement graph 儲存在程式內、JSON，還是 DynamoDB。
- [ ] Backend 採 FastAPI、Lambda handler，或兩者搭配。
- [ ] 前端部署至 Amplify，或使用其他靜態網站方案。
- [ ] 是否需要 DynamoDB 保存 session，以及保存哪些去識別化欄位。
- [ ] 是否加入 Bedrock Guardrails、AgentCore Policy、AgentCore Gateway 或 Memory。
- [ ] IaC 使用 SAM、CDK，還是 Hackathon 期間先手動建立資源。
- [ ] 官方文件的最終清單、更新日期、切分方式與 citation 格式。
- [ ] Demo 是否只完成喪偶情境，或再加入一個較淺的人生事件。
- [ ] 團隊分工、GitHub Issues、branch 與 pull request 流程。

技術選型原則：能在有限時間內完成穩定 demo、保留官方依據、可測試，且能清楚說明
AI 與確定性程式各自負責什麼；不以使用最多 AWS 服務為目標。

## MVP 情境

配偶死亡：

1. 死亡登記
2. 喪葬給付
3. 遺屬年金
4. 全民健康保險身分變更

預計準備 8–12 份官方文件，以及約 8–10 個正常、邊界與不符合資格的測試案例。

## 隱私界線

姓名、身分證字號、地址與聯絡方式等真實個資原則上保留在使用者裝置；
雲端只接收資格判斷需要的去識別化屬性。實際欄位與保存政策仍待逐項確認。

## 專案狀態

Planning and architecture phase。尚未開始鎖定最終技術選型。
