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

互動式 API 文件在 `http://127.0.0.1:8000/docs`。目前可用的端點：

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| `GET` | `/health` | 存活檢查 |
| `POST` | `/sessions` | 建立一次諮詢，回應含 `sessionId` |
| `POST` | `/sessions/advance` | 送一筆輸入，推進一步 |
| `GET` | `/sessions/current` | 查目前狀態（前端輪詢用） |
| `DELETE` | `/sessions/current` | 立刻清除這次諮詢 |

除了 `POST /sessions` 之外，每次呼叫都必須帶 header `X-Session-Id`。
**路徑裡沒有 session id**：它是持有即通行的憑證，放在網址會被瀏覽記錄、referrer
與伺服器日誌帶走。

> **端點目前回的是佔位資料。** 不管輸入什麼文字，事件都會判定成 `spouse_death`；
> 候選項目固定四筆且全部是 `pending`；沒有任何資格判定、官方依據或金額。
> 每個回應都帶 `implementation` 物件說明哪些能力還沒實作，前端可據此在畫面上標示。
> 未實作的能力清單見 `app/api/implementation.py`。

### 端點沒出現在 `/docs` 時先檢查這個

症狀是新端點沒有列出來，看起來像 router 沒掛上。實際原因通常是**有一個舊的 uvicorn
行程還在跑並佔著 8000 埠**，載入的是還沒有那些端點的程式。父行程死掉後，子行程會
繼承監聽權，所以查詢埠的擁有者會看到一個已經不存在的 PID。

`--reload` 救不了，因為問題不是「檔案沒重載」而是「舊行程還活著」。

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Select-Object ProcessId, CreationDate, CommandLine | Format-List
```

看 `CreationDate`。比本次工作開始時間更早的就是它，用
`Stop-Process -Id <PID> -Force` 殺掉再重啟。

先確認程式本身沒問題可以用這一行，它不經過伺服器：

```bash
uv run python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
```

環境變數可複製根目錄的 `.env.example` 到根目錄 `.env`；backend 會依序讀取
`../.env` 與 `backend/.env`，後者可覆寫前者。

## Checks

在 `backend/` 目錄下執行：

```bash
uv run ruff format .          # 先排版
uv run ruff format --check .  # 確認排版
uv run ruff check .
uv run pytest
```

不需要列出個別測試檔。

```bash
uv run pytest tests/unit/test_workflow_state.py tests/unit/test_session_schemas.py \
  tests/unit/test_session_store.py tests/unit/test_loop_guardrails.py \
  tests/unit/test_field_registry.py tests/unit/test_missing_fields.py \
  tests/unit/test_rule_adapter.py tests/unit/test_determination.py \
  tests/unit/test_logging.py tests/integration
```

資料層的測試從 **repository 根目錄**算起：

```python
from backend.app.services.benefit_catalog import ...
from scripts.init_benefit_catalog import initialize_database
```

因此 `pyproject.toml` 的 `pythonpath` 兩個目錄都收：

```toml
pythonpath = [".", ".."]
```

這是繞過而非根治。**兩種慣例應該統一成一種**，但那要改動多個測試檔，尚未處理。

## 已知問題：SQLite 連線未關閉

資料層到處使用 `with sqlite3.connect(...) as connection:`。Python 的 `sqlite3` 用
`with` 包起來只會提交或回滾交易，**不會關閉連線**。

已回報的影響：**Windows 上有 7 個測試失敗**，錯誤是 `PermissionError: The process
cannot access the file`——macOS 與 Linux 允許刪除還開著的檔案，Windows 不允許，
所以測試的暫存目錄清理失敗。（此現象在 `pythonpath` 修正後尚未於 Windows 複驗。）

修法是改用 `contextlib.closing` 包起來，或明確呼叫 `close()`。屬於資料層的程式碼，
尚未有人處理。

## 目前實作範圍

### 已完成

| 檔案 | 內容 |
| --- | --- |
| `app/main.py` | `create_app()` factory、CORS、router wiring、session store 建立 |
| `app/config.py` | 環境變數設定 |
| `app/api/health.py` | `GET /health` |
| `app/api/sessions.py` | 四個 session 端點，只做傳輸 |
| `app/api/errors.py` | 錯誤轉成契約形狀，且不外洩使用者輸入 |
| `app/orchestration/state.py` | Workflow state 的資料形狀（frozen Pydantic） |
| `app/orchestration/session_store.py` | 記憶體 session 儲存，2 小時過期 |
| `app/schemas/session.py` | 對外的請求與回應形狀 |
| `app/observability/logging.py` | 結構化 JSON logging 與欄位 allowlist |
| `app/rules/engine.py` | 通用規則引擎與相關性評分（資料層負責） |
| `app/services/` | benefit catalog、來源同步、連結探勘（資料層負責） |

`app/orchestration/state.py` 的設計理由見
[ADR-0011](../docs/decisions/0011-frozen-pydantic-session-workflow-state.md)。

### 佔位，之後整個刪除

| 檔案 | 說明 |
| --- | --- |
| `app/api/implementation.py` | 回應裡「哪些能力還沒實作」的宣告。全部實作完成後連同 `ImplementationNotice` 一起從契約移除 |
| `app/orchestration/determination.py` | 逐項判定組裝。目前是 stub：湊齊欄位標 `eligible`，接上 SQLite 後換掉 |

### 尚未實作

依 `AGENTS.md` 的 learn-by-building boundary，以下保留給後端負責人實作或密切審查：

- `app/orchestration/state_machine.py` — 八個狀態的轉換、守門條件、迴圈四道護欄
- `app/orchestration/agent_runner.py` — framework-neutral 的 LLM 呼叫介面（未建立）
- `app/tools/` — 三個 Agent tool 的 contracts 與實作
- `app/privacy/` — PII 偵測、去識別化與屬性 allowlist
- `app/retrieval/` — 文件切分、metadata filter、citation 組裝
- 欄位登記表 — 決定要問哪些資格欄位、型別與選項

`app/api/health.py` 內的 `HealthResponse` 是 transport-local 的形狀，用來對齊前端
既有的 `BackendHealth` 型別；領域 contracts 放在 `app/schemas/`。

## 對外契約與跨組協調

對外契約定義在 `app/schemas/session.py`，前端那一半在
`../frontend/src/types/session.ts`。**兩邊手寫維護**，由
`tests/unit/test_session_schemas.py` 檢查是否走鐘 —— 那個測試會直接讀取前端的
型別檔案，比對欄位名稱、列舉的值與文字長度常數。

改契約的流程：改兩邊 → 跑該測試 → 前端跑 `npm run typecheck` → 在溝通文件留紀錄。

兩份溝通文件記錄已定案的約定與待確認事項，開始接手前請先讀：

- [`docs/front_back_doc/README.md`](../docs/front_back_doc/README.md) — 前後端之間
- [`docs/back_database_doc/README.md`](../docs/back_database_doc/README.md) — 後端與資料層之間，含五個形狀落差

### 兩個容易誤會的命名慣例

- **線路上的欄位名是 camelCase**（`itemId`），Python 內部維持 snake_case。
  由 Pydantic 的 alias generator 轉換。
- **列舉的值保持 snake_case**（`needs_information`），因為那是資料內容不是欄位名稱。
  改的時候不要一起換。

## AWS 相關

8 月 1 日前**不得建立實際的 AWS 連線**，只能用本機模擬。目前後端連 `boto3` 都沒有
安裝，所以在沒有網路與雲端帳號的環境也能完整運作。

新增任何未來會需要 AWS 服務的功能時，**必須在同一個任務內**更新
[`docs/aws_migration_guide.md`](../docs/aws_migration_guide.md)。那份指南是遷移說明
的唯一來源，不要把遷移步驟寫在別的檔案裡。

`app/orchestration/session_store.py` 是目前唯一有登記在那份指南裡的後端功能。

## 隱私約束

實作 API、logging 與 session 時必須遵守
[ADR-0007](../docs/decisions/0007-limit-data-retention-and-egress.md)：

- 自由文字只在 `UNDERSTAND_EVENT` 接收，萃取出去識別化屬性後即丟棄，不寫入
  session、儲存或回應。
- Logs、traces 與 metrics 只記錄結構化欄位；使用者輸入的文字永遠不作為 log 欄位。

第二條由 `app/observability/logging.py` 在程式層強制。請一律使用 `log_event`，
不要直接呼叫 `print` 或 `logging.info`：

```python
from app.observability.logging import log_event

log_event(
    "state_transitioned",
    session_id=session_id,
    state="UNDERSTAND_EVENT",
    next_state="RESOLVE_ENTITLEMENTS",
    duration_ms=elapsed_ms,
)
```

只有 `ALLOWED_FIELDS` 內的欄位會被接受，其餘直接丟出 `DisallowedLogFieldError`。
記錄例外時使用 `exc_info=True` 並且**不要**傳入例外訊息 —— Pydantic 的
`ValidationError` 會把違規的輸入值寫進訊息裡，那正是我們丟棄的文字。formatter
只保留例外類別與 stack frames。

新增欄位等同於一次隱私決定，需先確認該欄位的值不可能包含使用者輸入的內容。

Session id 不使用 cookie，因此 CORS 未開啟 `allow_credentials`。

## 尚待驗證

- AgentCore Runtime 是否成為必要部署路徑，取決於比賽帳號權限與技術 spike。
- Bedrock model、retrieval / RAG、session persistence 與 IaC 選型尚未決定。

實作前應先確認 API、Agent tool 與 workflow state contracts，讓 frontend、backend
與 policy modules 可以平行開發。
