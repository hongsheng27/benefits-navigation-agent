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

後端拓撲已決定採用 **Modular monolith**：API、orchestration、rules、RAG、privacy
與 AWS adapters 保持清楚的模組邊界，但先組成一個可部署的 Python application，
模組之間以程式內 function call 溝通。部署平台仍待決定；未來若有實際需求，
可再把 Agent module 拆到獨立 runtime。詳見
[ADR-0001](docs/decisions/0001-backend-modular-monolith.md)。

HTTP API framework 已決定使用 **FastAPI**。FastAPI 只負責 transport、request /
response validation、routing 與 error mapping；application、orchestration、rules 與
retrieval 保持 framework-neutral。Lambda handler 不列為 MVP 必要項目，部署平台仍待決定。
詳見 [ADR-0002](docs/decisions/0002-use-fastapi-for-http-api.md)。

Frontend 已決定使用 **React、Vite、TypeScript 與 Tailwind CSS**，並以 npm 管理套件。
目前先建立單頁應用程式與 API client 邊界，不提前決定 routing、全域狀態管理、
component library 或部署平台。詳見
[ADR-0006](docs/decisions/0006-use-react-vite-typescript-tailwind.md)。

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

| Layer                     | 暫定選擇                                                                | 狀態 / 用途                                             |
| ------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------- |
| Frontend                  | React、Vite、TypeScript、Tailwind CSS                                   | **已決定**；對話、資格問題、結果與 checklist UI          |
| Backend                   | Python、Pydantic、boto3                                                 | 暫定；API、結構化資料與 AWS 整合                        |
| Backend topology          | Modular monolith                                                        | **已決定**；模組分離，單一 deployment unit              |
| API framework             | FastAPI                                                                 | **已決定**；核心 application logic 不依賴 framework     |
| LLM                       | Amazon Bedrock 上的模型                                                 | **後續決定**；chat 與 embedding model 待實測            |
| Agent orchestration       | Policy-governed hybrid                                                  | **已決定**；state machine 控制，Agent 僅限指定節點      |
| Agent SDK                 | Strands Agents + Amazon Bedrock                                         | **Trial / 可逆**；包在自有 `AgentRunner` interface 後方 |
| Agent hosting             | Amazon Bedrock AgentCore Runtime                                        | **後續決定**；先確認比賽帳號權限與現場可用性            |
| Agent tools               | `resolve_life_event`、`retrieve_official_rules`、`evaluate_eligibility` | MVP 暫定三個核心工具                                    |
| Document storage          | Amazon S3                                                               | 暫定；存放官方文件與處理後資料                          |
| RAG                       | Amazon Bedrock Knowledge Bases 或自製 retrieval                         | **後續決定**；先固定 `Retriever` interface              |
| Vector store / embeddings | 由 Bedrock Knowledge Bases 管理或自選方案                               | **後續決定**                                            |
| Entitlement graph         | JSON / Python mapping 或 DynamoDB                                       | **開賽前決定**；MVP 不使用完整 GraphRAG / Neptune       |
| Eligibility rules         | Python / JSON 規則 + Pydantic validation                                | 暫定；規則判斷必須是 deterministic                      |
| Session state boundary    | Client / server split                                                   | **已決定**；direct identifiers 留在 client              |
| Session persistence       | Memory、DynamoDB 或 AgentCore Memory                                    | **後續決定**；只保存去識別化 backend state              |
| Safety                    | Dynamic tool allowlist、輸入驗證、human-in-the-loop                     | 暫定核心機制                                            |
| Guardrails                | Amazon Bedrock Guardrails / AgentCore Policy                            | **後續決定**；依時間與帳號權限選用                      |
| Observability             | Amazon CloudWatch                                                       | 暫定；記錄狀態轉換、tool call、延遲與錯誤               |
| Deployment                | AWS Amplify、Lambda、AgentCore Runtime 的組合                           | **後續決定**；本機 vertical slice 跑通後再選            |
| Infrastructure as Code    | AWS SAM、CDK 或手動設定                                                 | **後續決定**；Hackathon 以速度為優先                    |
| Testing                   | pytest；前端測試工具待定                                                | 暫定；以 eligibility 與 end-to-end evaluation 為優先    |

## 初步檔案結構

以下 MVP 骨架已建立在 repository 中。原則是讓四位組員可以分別處理前端、
Agent / backend、RAG / 政府文件與規則 / evaluation，並降低互相修改同一檔案的機會。
目前多數檔案只是 package marker 或職責說明，尚不代表功能已完成。

```text
.
├── README.md
├── .env.example                    # 所需環境變數名稱，不放真實密鑰
├── .gitignore
├── frontend/
│   └── src/
│       ├── api/                    # Backend API client
│       ├── components/             # 對話、問題卡、福利結果、來源與 checklist
│       ├── pages/                  # 主要頁面
│       ├── types/                  # 前後端共用資料形狀的 TypeScript 版本
│       └── ...                     # 選定套件版本後再初始化 React app
├── backend/
│   ├── README.md
│   ├── app/
│   │   ├── main.py                 # FastAPI application 入口
│   │   ├── api/                    # Session、message、result endpoints
│   │   ├── schemas/                # Pydantic request / response / domain models
│   │   ├── orchestration/
│   │   │   ├── state.py            # Workflow state 定義
│   │   │   ├── state_machine.py    # 狀態轉換與停止條件
│   │   │   ├── agent_runner.py     # Framework-neutral AgentRunner interface
│   │   │   └── strands_agent.py    # Trial：StrandsAgentRunner adapter
│   │   ├── tools/
│   │   │   ├── resolve_life_event.py
│   │   │   ├── retrieve_official_rules.py
│   │   │   └── evaluate_eligibility.py
│   │   ├── retrieval/              # 文件切分、metadata filter、citation 組裝
│   │   ├── rules/                  # Deterministic eligibility rulesｓ
│   │   ├── privacy/                # PII 偵測、去識別化與欄位 allowlist
│   │   ├── services/               # Bedrock、S3、DynamoDB 等 AWS adapters
│   │   └── observability/          # Structured logging、trace 與 metrics
│   └── tests/
│       ├── unit/                   # Rules、state transitions、privacy tests
│       └── integration/            # Tool、RAG 與 API integration tests
├── data/
│   ├── benefits/                   # 福利定義、負責機關與所需欄位
│   ├── entitlement_graph/          # 跨福利 / 機關的 curated relations
│   ├── document_metadata/          # 官方來源 URL、發布機關、日期與版本Ｐ
│   └── evaluations/                # 正常、邊界與不符合資格的測試案例
├── scripts/
│   ├── ingest_documents.py         # 官方文件清理、切分與匯入
│   ├── validate_rules.py           # 規則與資料 schema 檢查
│   └── run_evaluation.py           # 批次執行 evaluation cases
├── infra/                          # SAM / CDK；選型確定後再建立內容
├── docs/
│   ├── architecture.md             # 完整架構與資料流程
│   ├── decisions/                  # Architecture Decision Records (ADR)
│   └── official-sources.md         # MVP 採用的政府文件清單
└── tmp/                            # 本機 PDF 提取 / 測試產物，不作為正式資料來源
```

選用功能如 DynamoDB、Guardrails 與 IaC，等選型確定後再補。大型原始 PDF
和處理產物原則上放 S3 或本機 `tmp/`，Git 只保存來源 metadata、可審查的規則與小型
evaluation fixtures。

## Agent Orchestration：已定案

採用 **policy-governed hybrid**：整體是可預測的 workflow，只有需要語意彈性的
節點使用受限制的 Agent 行為。

- **State machine** 擁有目前狀態、狀態轉換、tool allowlist、停止條件、錯誤處理與人工確認的控制權。
- **Agent / LLM** 只負責人生事件理解、去識別化欄位提取、建議下一個必要問題與 grounded explanation。
- **Deterministic rule engine** 擁有 `eligible`、`ineligible`、`needs_information` 與 `needs_human_review` 的資格判斷權。

Agent 不能直接決定福利資格，也不能繞過狀態檢查、PII 邊界或人工確認。
Bounded agentic steps 暫定以 **Strands Agents + Amazon Bedrock** 實作，但只能透過
自有 `AgentRunner` interface 接入；state machine、schemas、tools、rules 與 session state
不得依賴 Strands-specific types。若 spike 無法穩定限制 tools、產生結構化輸出或清楚
除錯，則改用 direct Bedrock implementation。詳見
[ADR-0003](docs/decisions/0003-policy-governed-hybrid-orchestration.md)。
實作選型與退出條件詳見
[ADR-0004](docs/decisions/0004-trial-strands-agent-runner.md)。

## 四人初步分工

每位成員負責一個可獨立展示的部分，同時透過共同 contracts 串成完整流程。角色會在
第一次架構會議確認後調整。

| 成員 | 角色 | 主要負責 |
| --- | --- | --- |
| **成員 A**<br>（Will） | Technical Lead、Agent Platform / AWS | Strands agent loop、Bedrock、AgentCore spike、Agent 執行邊界、observability 與最終整合 |
| **成員 B** | Privacy, Safety & AI Experience | React 使用流程、human-in-the-loop、PII masking、資格結果、引用與 Privacy Demo |
| **成員 C** | Backend Workflow / Agent Tooling | FastAPI、Pydantic contracts、state machine、session、Agent tools 與 backend tests |
| **成員 D** | Policy Intelligence / Evaluation | 官方來源、eligibility rules、retrieval data、citations、golden cases 與 evaluation |

共同實作前會先對齊 API / tool contracts、PII boundary、MVP 官方資料與 integration
checkpoints。請每位成員確認想負責的角色、希望獲得的技術經驗，以及目前看到的工作量
或技術風險。

## 已確認的工程方向

- Backend 採用 modular monolith 與 FastAPI。
- Frontend 採用 React、Vite、TypeScript 與 Tailwind CSS，並使用 npm 管理套件。
- 採用 policy-governed hybrid：state machine 控制流程，Agent 僅在指定節點推理。
- Bounded agentic steps 試用 Strands Agents + Bedrock，並透過自有 `AgentRunner` 接入。
- 採用 client / server split state；direct identifiers 留在 client。

Bedrock model、retrieval、session persistence、AgentCore 與 deployment 細節將由技術驗證
逐步確定；已接受的共同工程決策記錄在 [Architecture Decision Records](docs/decisions/README.md)。

技術選型原則：能在有限時間內完成穩定 demo、保留官方依據、可測試，且能清楚說明
AI 與確定性程式各自負責什麼；不以使用最多 AWS 服務為目標。

## MVP 情境

配偶死亡：

1. 死亡登記
2. 喪葬給付
3. 遺屬年金
4. 全民健康保險身分變更

預計準備 8–12 份官方文件，以及約 8–10 個正常、邊界與不符合資格的測試案例。

四個項目目前都保留；實作深度會依官方資料品質與 Hackathon 時間調整。

### 候選案例提案：家人突發重病後的照護導航

> 此案例仍在構想階段，尚未取代目前的 MVP。

聚焦家人突發重病後，主要照顧者如何跨醫院、長照、社福、身障與照顧者支持系統，找到
出院準備到返家初期的下一步。候選輸出包含聯絡窗口、7 / 30 / 90 天行動、缺少的評估或
文件、辦理順序、官方來源與人工轉介。系統只提供導航，不做醫療建議，也不取代醫師、
護理師、社工、照管人員或政府承辦人。

## 未來方向

- 擴展更多人生事件，並將單次 `LifeEvent` 演進為持續更新的 `CareJourney`。
- 擴充跨機關 entitlement graph；資料規模與多跳需求增加後再評估 GraphRAG / Neptune。
- 視需要加入 Bedrock Knowledge Bases、persistent session、AgentCore 進階服務與 Guardrails。
- 加強進階 PII detection、authentication、streaming 與可重建的 AWS infrastructure。

## 隱私界線

採用 **client / server split state**：

- 姓名、身分證字號、地址、電話與 email 等 direct identifiers 留在使用者裝置。
- Client 在傳輸前提示、偵測並遮罩明顯 PII，只送 sanitized text 與 allowlisted eligibility attributes。
- Backend 使用不含個資的 random `session_id`，並擁有 authoritative workflow state。
- Backend 只保存人生事件、資格所需的去識別化屬性、缺漏欄位、candidate benefit IDs 與判斷結果。
- Backend 仍執行輸入驗證與 defense-in-depth redaction，避免 PII 進入 logs、model prompts 或 traces。
- Client 傳入的 workflow state 不視為可信，狀態轉換由 backend 驗證。

Session persistence 技術、精確欄位、保存期限與刪除政策仍待決定。詳見
[ADR-0005](docs/decisions/0005-split-client-server-session-state.md)。

## 專案狀態

Planning and architecture phase。尚未開始鎖定最終技術選型。
