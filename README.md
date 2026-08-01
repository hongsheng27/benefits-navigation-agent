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

### 目前本機資料架構

目前接受的本機架構以 SQLite 作為資料策展與 runtime 的單一真相來源；ADR-0017 已選定未來 Hackathon shared target，但在替代 adapter 與 cutover validation 完成前仍維持 SQLite。FastAPI application composition root 將建立並注入 `EntitlementGraphRepository`、
`EligibilityService`、`EvidenceRepository` 與 `SourceRefreshService`；workflow／state machine
只依賴 storage-neutral contracts，不包含 SQL。Runtime 不讀 JSON，也沒有 JSON fallback。
這項架構已核准，但 schema migration、repositories、Rule DSL 與 runtime wiring 尚未完成，
不能視為目前程式已完成切換。詳見
[SQLite runtime accepted ADR-0013](docs/decisions/0013-use-sqlite-runtime-behind-repositories.md)
與 [finalized data-layer rule-engine spec](.kiro/specs/data-layer-rule-engine/requirements.md)。

依團隊規範，AWS 資源開放前不得建立 live connections，也不得提交 credentials、tokens、`.env` 或 account-specific secrets。Data-layer 目前仍使用本機 SQLite、本機檔案與本機背景工作；owner 已核准 Hackathon cutover 目標為 **Amazon RDS for PostgreSQL**（shared relational database）與 **Amazon S3**（官方文件／附件 objects），但必須先完成獨立 adapters、PostgreSQL migrations、資料驗證與 rollback 才能切換。Queue、LLM hosting 與 deployment service 仍待決策。詳見 [ADR-0017](docs/decisions/0017-target-rds-postgresql-and-s3.md)。

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
- Relevance scoring 用結構化欄位匹配做 deterministic 排序，不依賴 LLM。

### Relevance metadata（相關性排序）

相關性 metadata 只供 backend 以結構化欄位做 deterministic 候選排序，不代表資格機率、
符合程度或法定判斷，也不會影響任何 eligibility 結果。API 與 frontend 會完全省略分數、
區間、百分比及其衍生值；目前沒有核准固定數值範圍或情境別權重表。新的排序與 mapping
行為已納入 [accepted spec](.kiro/specs/data-layer-rule-engine/requirements.md)，但尚未完成
migration 與 runtime implementation。

## 暫定技術棧

| Layer                     | 暫定選擇                                                                | 狀態 / 用途                                             |
| ------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------- |
| Frontend                  | React、Vite、TypeScript、Tailwind CSS                                   | **已決定**；對話、資格問題、結果與 checklist UI          |
| Backend                   | Python、Pydantic、boto3                                                 | 暫定；API、結構化資料與 AWS 整合                        |
| Backend topology          | Modular monolith                                                        | **已決定**；模組分離，單一 deployment unit              |
| API framework             | FastAPI                                                                 | **已決定**；核心 application logic 不依賴 framework     |
| LLM                       | Amazon Bedrock Converse（Claude Haiku 4.5）                             | **已實作並實測**；未設定模型時保留離線示範              |
| Agent orchestration       | Policy-governed hybrid                                                  | **已決定**；state machine 控制，模型僅限兩個指定節點     |
| Agent SDK                 | 無 —— 不做 agent 迴圈                                                   | **已決定**；改用窄的 LLM port，見 ADR-0015              |
| Agent hosting             | Amazon Bedrock AgentCore Runtime                                        | **後續決定**；先確認比賽帳號權限與現場可用性            |
| Agent tools               | 無 —— 模型沒有工具可呼叫                                                | **已決定**；模型只做「聽懂事件」與「翻成白話」兩件事     |
| Document storage          | 本機資料夾 → Amazon S3                                                  | **AWS target 已決定**；目前 local，完成 S3 adapter/hash 驗證後 cutover |
| RAG                       | Amazon Bedrock Knowledge Bases 或自製 retrieval                         | **後續決定**；先固定 `Retriever` interface              |
| Relevance metadata        | Backend-only deterministic ordering                                     | **已核准、待完成**；無固定數值範圍，API／frontend 省略且不影響資格判斷 |
| Vector store / embeddings | 由 Bedrock Knowledge Bases 管理或自選方案                               | **後續決定**；資料量大時疊加語意搜尋                    |
| Entitlement graph / runtime storage | 本機 SQLite → Amazon RDS for PostgreSQL behind storage-neutral repositories | **local 與 AWS target 已核准、migration 待完成**；先完成 SQLite vertical slice，再以 PostgreSQL adapter cutover，見 [ADR-0013](docs/decisions/0013-use-sqlite-runtime-behind-repositories.md) 與 [ADR-0017](docs/decisions/0017-target-rds-postgresql-and-s3.md) |
| Eligibility rules         | Canonical versioned `all_of`／`any_of` Rule DSL                         | **架構已核准、implementation 待完成**；`program_rule_fields` 僅為唯讀 compatibility projection |
| Session state boundary    | Client / server split                                                   | **已決定**；direct identifiers 留在 client              |
| Session persistence       | 記憶體，不持久化                                                        | **MVP 已定**；結束即消失，保存政策見 ADR-0007           |
| Safety                    | Dynamic tool allowlist、輸入驗證、human-in-the-loop                     | 暫定核心機制                                            |
| Guardrails                | Amazon Bedrock Guardrails / AgentCore Policy                            | **後續決定**；依時間與帳號權限選用                      |
| Observability             | Amazon CloudWatch                                                       | 暫定；記錄狀態轉換、tool call、延遲與錯誤               |
| Deployment                | AWS Amplify、Lambda、AgentCore Runtime 的組合                           | **後續決定**；本機 vertical slice 跑通後再選            |
| Infrastructure as Code    | AWS SAM、CDK 或手動設定                                                 | **後續決定**；Hackathon 以速度為優先                    |
| Testing                   | pytest；前端測試工具待定                                                | **已決定**；以 eligibility 與 end-to-end evaluation 為優先 |

### 技術棧名詞白話說明

以下補充說明技術棧表格中各項的實際功能，特別是標示「後續決定」的部分：

| 項目 | 白話說明 |
| --- | --- |
| **LLM** | 讓系統能「聽懂」使用者的話、產生白話回答的 AI 模型。目前使用 AWS Bedrock Converse 與 Claude Haiku 4.5，已在競賽帳號 `us-west-2` 實測。未設定模型時才使用離線示範。 |
| **Agent SDK** | **不用了。** 原本打算用 Strands 做一個「會自己決定下一步」的 agent。後來判定不做 — 我們只有兩個問一次答一次的任務，而讓模型能自己呼叫功能會開出一條它可以影響資格判定的路。見 ADR-0015。 |
| **Agent hosting (AgentCore)** | 讓 Agent 跑在 AWS 上面（不是跑在你的電腦）。是否用要看比賽帳號有沒有開放權限。 |
| **Document storage (S3)** | 官方 HTML、PDF 與附件物件的已核准 AWS target。目前仍使用本機資料夾；完成 S3 adapter、hash 驗證與 rollback 後才 cutover，database 只保存 metadata 與 opaque object key。 |
| **RAG (Knowledge Bases)** | 語意搜尋 — 讓系統用「意思相近」來找資料，不只靠關鍵字。資料量少時用 SQL + 評分就夠，量大時才需要。 |
| **Vector store / embeddings** | RAG 的底層技術。把文字轉成數字向量，比較向量距離來判斷「意思接不接近」。需要 embedding model；是否接 Bedrock 與底層 storage 仍待驗證。 |
| **Guardrails** | AI 的安全圍欄 — 防止 AI 輸出個資、亂下結論、回答無關問題。目前靠 state machine 控制；AWS Guardrails 是否採用仍待決策。 |
| **Observability (CloudWatch)** | 系統監控 — 記錄狀態轉換、tool 呼叫、回應時間與錯誤。CloudWatch 是候選方案，實際服務仍待 deployment 決策。 |
| **Deployment** | 怎麼讓別人使用系統。目前可在 owner 核准後驗證 AWS 路徑，但 Amplify、Lambda、AgentCore Runtime 或其他 production 組合尚未選定。 |
| **Infrastructure as Code** | 用程式碼一鍵建立 AWS 資源（S3 bucket、Lambda、資料庫等），不用手動去 console 點。Hackathon 趕時間可能先手動，之後再補。 |
| **Session persistence** | 使用者跟系統的對話狀態要不要存起來。MVP 決定不存 — 關掉就消失，避免處理個資保存問題。 |

## 初步檔案結構

以下是目前 repository 的實際結構。原則是讓四位組員可以分別處理前端、
Agent / backend、RAG / 政府文件與規則 / evaluation，並降低互相修改同一檔案的機會。

```text
.
├── README.md                           # 專案總覽、架構、技術棧
├── AGENTS.md                           # AI agent 行為規範（含 AWS 時程限制）
├── CONTRIBUTING.md                     # Commit 格式與協作慣例
├── .env.example                        # 所需環境變數名稱，不放真實密鑰
├── .gitignore
│
├── frontend/                           # React 前端
│   └── src/
│       ├── api/
│       │   └── client.ts              # Backend API client（目前只有健康檢查）
│       ├── components/                 # 對話、問題卡、福利結果、來源與 checklist
│       ├── pages/
│       │   └── HomePage.tsx           # 人生事件輸入頁
│       └── types/
│           └── session.ts             # 對外契約的 TypeScript 版本
│
├── backend/                            # Python 後端（FastAPI modular monolith）
│   ├── app/
│   │   ├── main.py                     # FastAPI application 入口
│   │   ├── config.py                   # 環境變數設定
│   │   ├── api/
│   │   │   ├── health.py              # GET /health
│   │   │   ├── sessions.py            # 四個 session 端點（只做傳輸）
│   │   │   ├── errors.py              # 錯誤轉成契約形狀，不外洩使用者輸入
│   │   │   └── implementation.py      # 宣告哪些能力還沒實作（之後移除）
│   │   ├── schemas/
│   │   │   └── session.py             # 對外的請求與回應形狀
│   │   ├── orchestration/
│   │   │   ├── state.py               # Workflow state 的資料形狀
│   │   │   ├── session_store.py       # 記憶體 session 儲存，2 小時過期
│   │   │   ├── field_registry.py      # 欄位登記表讀取與驗證
│   │   │   ├── missing_fields.py      # 缺漏欄位計算與主題分組
│   │   │   ├── rule_adapter.py        # 規則引擎結果 → CandidateItem
│   │   │   ├── determination.py       # 逐項判定組裝（目前為 stub）
│   │   │   └── state_machine.py       # 狀態轉換、守門條件、自動推進、迴圈護欄
│   │   ├── tools/
│   │   │   ├── resolve_life_event.py      # Tool：辨識人生事件
│   │   │   ├── retrieve_official_rules.py # Tool：檢索官方規則
│   │   │   └── evaluate_eligibility.py    # Tool：呼叫 Rule Engine 判斷資格
│   │   ├── rules/
│   │   │   └── engine.py              # 通用規則引擎（讀 DB 結構化欄位做判斷）
│   │   ├── retrieval/                  # 文件切分、metadata filter、citation 組裝
│   │   ├── privacy/                    # PII 偵測、去識別化與欄位 allowlist
│   │   ├── services/
│   │   │   ├── benefit_catalog.py     # SQLite schema 定義與 catalog helpers
│   │   │   ├── source_connector.py    # 官方頁面下載與同步紀錄
│   │   │   └── link_discovery.py      # 從 HTML 找出子連結、排序候選
│   │   └── observability/
│   │       └── logging.py             # Structured logging
│   └── tests/
│       ├── unit/                       # 規則、狀態轉換、隱私、來源連接器測試
│       └── integration/                # Tool、RAG 與 API integration tests
│
├── data/
│   ├── benefit_discovery/              # 候選發現流程的設定與產出
│   │   ├── death_benefit_first_batch.v0.1.json   # 人工核准的第一批頁面清單
│   │   ├── death_benefit_keywords.v0.2.json      # 候選排序關鍵字
│   │   └── extracted_candidates.v0.1.json        # 抽取後的結構化候選（供人工審查）
│   ├── source_registry/                # 來源白名單設定
│   │   └── initial_sources.v0.1.json   # 初始登記的官方來源
│   ├── evaluations/                    # 正常、邊界與不符合資格的測試案例
│   └── local/                          # 本機產物（不進 Git）
│       ├── government_oid.db           # SQLite 資料庫（所有資料表都在這）
│       ├── source_documents/           # 下載的官方 HTML 檔案
│       └── discovered_links/           # 候選連結 JSON
│
├── scripts/
│   ├── import_government_oid.py        # 下載並匯入政府機關 OID 到 SQLite
│   ├── init_benefit_catalog.py         # 建立 catalog 所有資料表
│   ├── sync_benefit_sources.py         # 同步指定入口頁（下載 HTML）
│   ├── discover_benefit_links.py       # 從入口頁產生子連結候選清單
│   ├── fetch_reviewed_benefit_pages.py # 只下載人工核准的政府頁面
│   ├── extract_benefit_candidates.py   # 從 HTML 解析結構化候選資料
│   ├── load_candidates_to_db.py        # 把候選寫入 benefit_programs 表
│   ├── review_benefit_status.py        # CLI：列出待審查方案與缺少欄位
│   ├── review_server.py                # 啟動本機審查網頁介面（FastAPI + HTML）
│   └── review_ui.html                  # 審查介面前端（瀏覽、編輯、Verify）
│
├── docs/
│   ├── architecture-overview.html      # 視覺化架構與資料庫說明
│   ├── aws_migration_guide.md          # AWS 遷移集中指南（唯一來源）
│   ├── official-sources.md             # MVP 採用的政府文件清單
│   ├── decisions/                      # Architecture Decision Records (ADR)
│   └── benefit-discovery/              # 搜尋與人工審查規格
│
├── record/                             # 進度紀錄（含日期）
├── infra/                              # SAM / CDK；選型確定後再建立內容
└── tmp/                                # 本機暫存，不作為正式資料來源
```

`data/local/` 下的 SQLite、HTML 與 JSON 不進 Git，可由 `scripts/` 中的指令重建。
Git 保存的是程式碼、schema、設定、關鍵字、測試案例與進度紀錄。

## 本機政府機關 OID registry

數位發展部的政府機關 OID 官方 CSV 可匯入為本機 SQLite reference database：

```bash
python3 scripts/import_government_oid.py
```

預設輸出為 `data/local/government_oid.db`。`data/local/` 與 `*.db` 已被 Git
忽略；repository 保存可重建的 importer、schema、測試與官方來源 metadata，不保存
產生後的 database。

Importer 會先讀取 OID 官方下載網址；若該主機暫時關閉連線，會自動改用政府資料開放
平臺提供的官方 quality snapshot，並在執行結果顯示實際 retrieval URL。

本機 schema 將官方機關資料、project-owned tags、機關與標籤關聯、同步紀錄分開。
官方資料更新只更新官方欄位；既有標籤不會被覆寫。OID 消失時先標記為 inactive，
不直接刪除相關資料。

若官方網站暫時無法下載，也可以先取得官方 `GDS.csv`，再執行：

```bash
python3 scripts/import_government_oid.py --source-file /path/to/GDS.csv
```

政府 OID 匯入資料本身可由核准的 importer 與官方來源重新產生；但 accepted target 同時把人工策展
catalog 與 runtime 最近一次成功 commit 的完整 SQLite 狀態視為 canonical truth，不再把整個
SQLite 僅視為可重建 reference store。Runtime 透過 storage-neutral adapters 取用資料；owner 已核准 shared-write AWS target 為 RDS PostgreSQL，實際替換仍須完成 PostgreSQL adapter、migration、驗證與 rollback，不會讓 Workflow 接觸 database-specific shape。
這個 catalog 不存放使用者 session、直接識別資料、raw user text 或 credentials；上述架構已核准，
schema migration 與 runtime wiring 尚未完成。詳見
[SQLite runtime accepted ADR-0013](docs/decisions/0013-use-sqlite-runtime-behind-repositories.md)
與 [ADR-0009](docs/decisions/0009-use-generated-sqlite-for-government-oid.md)。

## 本機補助來源與方案 catalog

在 OID registry 匯入完成後，可初始化同一個本機 SQLite 檔案中的來源與方案 catalog：

```bash
python3 scripts/init_benefit_catalog.py
```

初始化程式會建立來源登記、來源同步、官方文件、補助方案、方案證據與機關角色等
資料表，並輸出目前已登記來源、連線狀態、候選方案及已確認方案數量。初始來源 metadata
保存在 `data/source_registry/initial_sources.v0.1.json`，重跑指令不會覆寫之後由同步流程
更新的連線狀態。

初始登記不等於已完成對接。只有存在成功 OID import 紀錄時，OID 來源才會標為
`active`。目前可用下列指令同步「我的 E 政府」與「臺北市殯葬管理處」已審核的入口
頁面：

```bash
python3 scripts/sync_benefit_sources.py
```

這個指令目前只下載這兩個指定頁面並記錄網址、標題、抓取時間、內容雜湊與同步結果；
不會展開子連結、爬完整網站、呼叫 AI 或建立正式補助方案。

完成入口頁同步後，可從已下載的 HTML 主要內容區列出子連結候選：

```bash
python3 scripts/discover_benefit_links.py
```

候選清單預設輸出到 `data/local/discovered_links/first_round.json`。這一步只解析已下載的
入口頁，不下載候選子頁；關鍵字只用來排序，沒有命中關鍵字的主要內容連結仍會保留給
人工檢查。

人工核准第一批候選後，可執行：

```bash
python3 scripts/fetch_reviewed_benefit_pages.py
```

這個指令只處理
`data/benefit_discovery/death_benefit_first_batch.v0.1.json` 中標示為
`approved_for_fetch` 的 HTTPS 臺灣政府網址，不接受任意網址、不展開下一層連結，也
不呼叫 AI。完成下載仍不代表方案已通過正式審查。

Catalog 與原本 OID 專用的 `sync_runs` 分開，使用 `source_sync_runs` 保存福利來源的同步
狀態。方案只有在分類、驗證時間及官方證據齊全後才能標為 `verified`；機關角色也必須
附來源文件，不能把資料發布機關直接視為補助主管機關。詳見
[ADR-0010](docs/decisions/0010-use-local-provenance-first-benefit-catalog.md)。

## Agent Orchestration：已定案

採用 **policy-governed hybrid**：整體是可預測的 workflow，只有需要語意彈性的
節點使用受限制的 Agent 行為。

- **State machine** 擁有目前狀態、狀態轉換、tool allowlist、停止條件、錯誤處理與人工確認的控制權。
- **Agent / LLM** 只負責人生事件理解、去識別化欄位提取、建議下一個必要問題與 grounded explanation。
- **Deterministic rule engine** 擁有 `eligible`、`ineligible`、`needs_information` 與 `needs_human_review` 的資格判斷權。

Agent 不能直接決定福利資格，也不能繞過狀態檢查、PII 邊界或人工確認。詳見
[ADR-0003](docs/decisions/0003-policy-governed-hybrid-orchestration.md)。

**沒有 agent 迴圈，模型也沒有工具可以呼叫。** 原本規劃用 Strands 做一個受限制的
agent 迴圈（[ADR-0004](docs/decisions/0004-trial-strands-agent-runner.md)），
2026-07-30 改為一個窄的 LLM port
（[ADR-0015](docs/decisions/0015-narrow-llm-port-instead-of-agent-loop.md)）。理由是
系統裡只有兩個模型任務、兩個都是單次問答；而給模型工具就是開出一條它可以影響資格判定
的路，**不存在的能力不需要用 prompt 或護欄去防守**。

模型呼叫關在 `backend/app/llm/` 底下：`port.py` 定形狀、`bedrock.py` 透過 boto3
`Converse` 呼叫正式模型、`fake.py` 讓測試與離線示範不需要網路。設定
`BEDROCK_MODEL_ID` 時只走 Bedrock；沒有設定時才使用離線示範。Bedrock 執行中失敗會
明確回錯，不會偷偷改用示範結果。詳見
[ADR-0016](docs/decisions/0016-use-bedrock-only-live-llm-provider.md) 與
[AWS 遷移指南](docs/aws_migration_guide.md)。

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
- 已接受 SQLite runtime behind storage-neutral repositories：SQLite 是目前本機 curation／runtime
  單一真相，FastAPI composition root 注入四個 ports，workflow 不含 SQL，runtime 無 JSON fallback；
  migration 與 wiring 尚未完成。
- 已核准 Hackathon AWS data-layer target：shared relational data 使用 Amazon RDS for PostgreSQL，官方文件與附件 objects 使用 Amazon S3；完成 adapters、migration、validation 與 rollback 前仍維持 local path。
- Relevance metadata 只供 backend deterministic ordering，沒有核准固定數值範圍，API／frontend
  完全省略，且永不影響 eligibility；新 mapping 尚未完成。

Bedrock model、retrieval、AgentCore、queue 與 deployment 細節仍待技術驗證與獨立決策。RDS PostgreSQL 與 S3 已是 owner-approved Hackathon data-layer targets，但 AWS 資源開放前不得建立 live connection；之後任何 credentials、tokens、`.env` 與 account-specific secrets 仍不得提交。已接受的共同工程決策記錄在
[Architecture Decision Records](docs/decisions/README.md)。

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
- Backend 完成屬性萃取後即丟棄原始自由文字，不寫入 session、儲存或回應。
- Logs、traces 與 metrics 只記錄結構化欄位；使用者輸入的文字永遠不作為 log 欄位。
- Frontend 不載入 analytics、error reporting 等第三方 runtime 依賴。
- Client 傳入的 workflow state 不視為可信，狀態轉換由 backend 驗證。

Session persistence 技術、精確欄位、保存期限與刪除政策仍待決定。詳見
[ADR-0005](docs/decisions/0005-split-client-server-session-state.md) 與
[ADR-0007](docs/decisions/0007-limit-data-retention-and-egress.md)。

## 專案狀態

決賽為 **8/1–8/2 現場 30 小時開發**。架構方向與隱私邊界已定案，目前重心在
補齊 `data/` 內容、完成 SQLite runtime migration 的實作準備，以及依 owner 核准驗證 Bedrock
權限與整合路徑；任何 live AWS 使用都不得提交 credentials 或 account-specific secrets。

比賽條件、MVP 範圍與交付分工見 [hackathon-plan.md](docs/hackathon-plan.md)。
