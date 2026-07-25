# Backend

Backend 採用 Python **modular monolith**，負責 API、workflow state、Agent tools、
官方文件 retrieval、deterministic eligibility rules、隱私界線與 AWS adapters。

## 已確認方向

- 使用 **FastAPI** 作為主要 HTTP transport，負責 routing、request / response
  validation、dependency wiring 與 error mapping。
- Application services、workflow、rules、retrieval 與 Agent contracts 保持
  framework-neutral，不把 business logic 寫進 route handlers。
- 採用 policy-governed hybrid orchestration：state machine 控制狀態、允許的 tools、
  停止條件與人工確認；LLM 不直接決定福利資格。
- Strands Agents + Amazon Bedrock 先作為 `AgentRunner` 後方的可逆 trial；schemas、
  tools、rules 與 session state 不依賴 Strands-specific types。
- Raw Lambda handler 不列為 MVP 必要項目；若未來部署需要，只能作為 application
  service 前方的 thin adapter。
- 環境與套件以 **uv** 管理，Python 版本由 `.python-version` 釘在 3.13。

## Local development

需要先安裝 [uv](https://docs.astral.sh/uv/)。uv 會自行取得正確的 Python 版本，
不需要另外安裝 Python 或手動建立虛擬環境。

```bash
cd backend
uv sync                                   # 建立 .venv 並依 uv.lock 安裝套件
uv run uvicorn app.main:app --reload      # http://localhost:8000
```

啟動後 `GET /health` 會回傳 `{"status": "ok"}`，前端右上角的連線狀態會變成
「後端已連線」。前端預設連線至 `http://localhost:8000`。

環境變數可複製根目錄的 `.env.example` 到根目錄 `.env`；backend 會依序讀取
`../.env` 與 `backend/.env`，後者可覆寫前者。

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## 目前實作範圍

已建立的只有 transport 邊界與工具設定：

```text
pyproject.toml          # 相依套件、ruff 與 pytest 設定
.python-version         # 釘住 Python 3.13
app/main.py             # create_app() factory、CORS、router wiring
app/config.py           # 環境變數設定
app/api/health.py       # GET /health
tests/integration/      # health 的 smoke test
```

以下**刻意未實作**，依 `AGENTS.md` 的 learn-by-building boundary 保留給後端負責人
實作或密切審查：

- `app/schemas/` — Pydantic request / response / domain models
- `app/orchestration/` — workflow state 定義、狀態轉換與停止條件
- `app/tools/` — 三個 Agent tool 的 contracts 與實作
- `app/rules/` — deterministic eligibility rules
- `app/privacy/` — PII 偵測、去識別化與欄位 allowlist
- `app/retrieval/`、`app/services/`、`app/observability/`

`app/api/health.py` 內的 `HealthResponse` 是 transport-local 的形狀，用來對齊前端
既有的 `BackendHealth` 型別；領域 contracts 應該放在 `app/schemas/`。

## 隱私約束

實作 API、logging 與 session 時必須遵守
[ADR-0007](../docs/decisions/0007-limit-data-retention-and-egress.md)：

- 自由文字只在 `UNDERSTAND_EVENT` 接收，萃取出去識別化屬性後即丟棄，不寫入
  session、儲存或回應。
- Logs、traces 與 metrics 只記錄結構化欄位；使用者輸入的文字永遠不作為 log 欄位。

Session id 不使用 cookie，因此 CORS 未開啟 `allow_credentials`。

## 尚待驗證

- AgentCore Runtime 是否成為必要部署路徑，取決於比賽帳號權限與技術 spike。
- Bedrock model、retrieval / RAG、session persistence 與 IaC 選型尚未決定。

實作前應先確認 API、Agent tool 與 workflow state contracts，讓 frontend、backend
與 policy modules 可以平行開發。
