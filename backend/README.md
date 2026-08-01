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
- **不做 agent 迴圈。** 模型呼叫走一個窄的 LLM port（`app/llm/port.py`），沒有
  應用程式工具迴圈；有 `BEDROCK_MODEL_ID` 就使用 Amazon Bedrock Converse，沒有才用
  離線示範。理由見 ADR-0015 與 ADR-0016。
- Raw Lambda handler 不列為 MVP 必要項目；若未來部署需要，只能作為 application
  service 前方的 thin adapter。
- 環境與套件以 **uv** 管理，Python 版本由 `.python-version` 釘在 3.13。

## Local development

需要先安裝 [uv](https://docs.astral.sh/uv/)。uv 會自行取得正確的 Python 版本，
不需要另外安裝 Python 或手動建立虛擬環境。

```bash
# 建議：從 repo 根目錄啟動（會先清掉佔埠的舊 uvicorn，再開 --reload）
make backend                              # http://127.0.0.1:8000

# 或直接：
cd backend
uv sync                                   # 建立 .venv 並依 uv.lock 安裝套件
python ../scripts/dev_backend.py          # 等同 make backend
```

不要並行開第二個 `uvicorn`：Windows 上 `--reload` 子行程常變成殭屍佔埠，
瀏覽器會打到舊程式。換埠（8001、8002…）只是暫時躲過，不是解法。

啟動後 `GET /health` 會回傳 `status` 與 `startedAt`（此行程開機時間）。
前端右上角連線狀態會變成「後端已連線」。前端預設連線至 `http://localhost:8000`。

互動式 API 文件在 `http://127.0.0.1:8000/docs`。目前可用的端點：

| 方法     | 路徑                | 用途                             |
| -------- | ------------------- | -------------------------------- |
| `GET`    | `/health`           | 存活檢查                         |
| `POST`   | `/sessions`         | 建立一次諮詢，回應含 `sessionId` |
| `POST`   | `/sessions/advance` | 送一筆輸入，推進一步             |
| `GET`    | `/sessions/current` | 查目前狀態（前端輪詢用）         |
| `DELETE` | `/sessions/current` | 立刻清除這次諮詢                 |

除了 `POST /sessions` 之外，每次呼叫都必須帶 header `X-Session-Id`。
**路徑裡沒有 session id**：它是持有即通行的憑證，放在網址會被瀏覽記錄、referrer
與伺服器日誌帶走。

> **福利資料目前仍是佔位資料。** 有設定 `BEDROCK_MODEL_ID` 時事件由 Bedrock
> 萃取，沒有才使用離線示範模型。Entitlement fixture 目前包含配偶過世四筆，以及
> 父親職災失能七筆候選方向與七個固定選項問題；沒有官方依據或金額。
> 狀態機會真的按規則推進、Case 2 答案也會做 deterministic relevance filter，
> 但**離線流程目前不會產出 `eligible`**：示範資料的治理狀態都是 `candidate`，一律回
> `needs_human_review`。
> 每個回應都帶 `implementation` 物件說明哪些能力還沒實作，前端可據此在畫面上標示。
> 未實作的能力清單見 `app/api/implementation.py`。

### 端點沒出現在 `/docs`、或改了程式卻像沒生效時

多半是**舊的 uvicorn 還佔著埠**。請用 `make backend`（或
`python scripts/dev_backend.py`）重開：腳本會先清埠再開新行程。

若仍懷疑程式本身，可跳過伺服器直接檢查 OpenAPI：

```bash
uv run python -c "from app.main import app; print(sorted(app.openapi()['paths']))"
```

也可對比 `GET /health` 的 `startedAt`：重開後時間應該變新。

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

`cd backend; uv run pytest` 目前可以正常執行：**226 個測試全部通過**（2026-07-29 於
Windows 驗證），`uv run ruff check .` 與 `uv run ruff format --check .` 也都通過。

## 已解決：SQLite 連線未關閉

曾經的問題是資料層到處使用 `with sqlite3.connect(...) as connection:`。Python 的
`sqlite3` 用 `with` 包起來只會提交或回滾交易，**不會關閉連線**，因此 Windows 上有
7 個測試以 `PermissionError: The process cannot access the file` 失敗 —— macOS 與
Linux 允許刪除還開著的檔案，Windows 不允許，所以測試的暫存目錄清理失敗。

修法是改用 `contextlib.closing` 包起來，或在 `try/finally` 裡明確呼叫 `close()`。

**2026-07-29 驗證已解決**：`backend/app` 底下沒有任何一處自己開連線（services 與
rules 以 `connection` 參數接收，由呼叫端管生命週期）；`scripts/` 的 10 處與測試的
10 處都有關閉。細節記在
[`docs/back_database_doc/README.md`](../docs/back_database_doc/README.md) 第七節。
新增資料層程式碼時請沿用同樣寫法。

## 目前實作範圍

### 已完成

| 檔案                                  | 內容                                                                                                  |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `app/main.py`                         | `create_app()` factory、CORS、router wiring、session store 建立                                       |
| `app/config.py`                       | 環境變數設定                                                                                          |
| `app/api/health.py`                   | `GET /health`                                                                                         |
| `app/api/sessions.py`                 | 四個 session 端點，只做傳輸                                                                           |
| `app/api/errors.py`                   | 錯誤轉成契約形狀，且不外洩使用者輸入                                                                  |
| `app/orchestration/state.py`          | Workflow state 的資料形狀（frozen Pydantic）                                                          |
| `app/orchestration/session_store.py`  | 記憶體 session 儲存，2 小時過期                                                                       |
| `app/orchestration/state_machine.py`  | 八個狀態的轉換、守門條件、自動推進與迴圈護欄。見 ADR-0012                                             |
| `app/orchestration/data_contracts.py` | 資料層與 workflow 之間的邊界格式（七個 dataclass、三組固定值）                                        |
| `app/orchestration/protocols.py`      | 四個資料層接口（graph、判定、證據、來源刷新）與各自的離線實作                                         |
| `app/orchestration/source_refresh.py` | on-demand refresh 的流程組裝，本機佇列、非阻塞、失敗不影響回應                                        |
| `app/orchestration/determination.py`  | 逐項判定組裝、依 `program_status` 的安全檢查、單項失敗隔離                                            |
| `app/orchestration/demo_fixtures.py`  | **示範用**資料，只有喪葬給付一項填到底。不得作為預設值。見 ADR-0014                                   |
| `app/llm/port.py`                     | 語言模型的邊界形狀、呼叫契約、以及 schema 可攜性檢查。見 ADR-0015                                     |
| `app/llm/fake.py`                     | 不連網路的模型實作，**預設值**。回登記好的答案，沒登記就拋錯                                          |
| `app/llm/bedrock.py`                  | Bedrock Converse adapter；forced tool choice 取得結構化輸出                                           |
| `app/llm/factory.py`                  | 有 `BEDROCK_MODEL_ID` 用 Bedrock，沒有才用示範實作。啟動時決定一次                                    |
| `app/llm/tasks/resolve_life_event.py` | 把一段文字對應成有順序的事件代號清單。Case 2 同時保留職災與長照；**系統唯一持有原文的地方**，用完即丟 |
| `app/orchestration/life_events.py`    | 生命事件登記表的讀取，讀 `data/life_events/events.v0.1.json`                                          |
| `app/privacy/attribute_gate.py`       | 屬性值的型別與選項驗證，不合法就拒絕整筆                                                              |
| `app/schemas/session.py`              | 對外的請求與回應形狀                                                                                  |
| `app/observability/logging.py`        | 結構化 JSON logging 與欄位 allowlist                                                                  |
| `app/rules/engine.py`                 | 通用規則引擎與相關性評分（資料層負責）                                                                |
| `app/services/`                       | benefit catalog、來源同步、連結探勘（資料層負責）                                                     |

`app/orchestration/state.py` 的設計理由見
[ADR-0011](../docs/decisions/0011-frozen-pydantic-session-workflow-state.md)。

### 佔位，之後整個刪除

| 檔案                                                             | 說明                                                                                       |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `app/api/implementation.py`                                      | 回應裡「哪些能力還沒實作」的宣告。全部實作完成後連同 `ImplementationNotice` 一起從契約移除 |
| `app/orchestration/protocols.py` 裡的 `Fixture*` / `Local*` 類別 | 四個接口的離線實作。資料層交出 SQLite 實作後，改注入參數即可換掉，介面本身保留             |

### 接上真的語言模型（Bedrock）

**不設定也能跑。** 沒有 `BEDROCK_MODEL_ID` 時後端會落回一個離線的示範實作，事件辨識一律回
`spouse_death`。所有測試都不需要金鑰也不需要網路。

要用真的模型：

1. 從 Workshop Studio 取得臨時 AWS credentials，放在**repository 根目錄**、已被
   gitignore 的 `.env`。
2. 填入已在競賽帳號 `us-west-2` 實測的 inference profile：

   ```env
   AWS_REGION=us-west-2
   BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
   ```

3. 重啟後端。啟動時會記一筆 `language_model_selected`，`model_id` 是
   `demo_fixture` 或實際的模型代號 —— **從行為上分不出來，所以看那一筆紀錄**。

正式路徑使用 boto3 `Converse`，以 forced tool choice 取得符合 schema 的輸出。若已設定
`BEDROCK_MODEL_ID`，但發生權限、模型、region、timeout、throttling 或回應格式錯誤，
後端會明確失敗，不會把離線示範結果冒充成正式模型結果。

「父親因工作事故失能且需長期照顧」案例已接成完整 backend-fixture 流程：模型回
`[occupational_injury, long_term_care_need]` 後先等使用者確認，確認後由 backend 回傳四組七題；答案寫入
session 後由 fixture repository 做 deterministic relevance filter，最後回傳最多七項
`needs_human_review` 結果。第一段描述只萃取 `event_ids`，不抽取資格 attributes，
也不讓模型判斷 eligibility。2026-08-01 的 live Bedrock 實測使用舊單數契約並回傳
`occupational_injury`；multi-event schema 需再做一次 live 驗證。福利與問題資料仍是離線
fixture，未宣稱完成正式
資格或法規審查。

接上真模型之後才會出現 `event_not_recognized` 這個錯誤（描述對應不到任何已登記的
事件）。示範實作永遠成功，所以那條路徑在沒有金鑰時測不到。

**測試不會用到真實模型，即使你設了 AWS credentials。** `tests/conftest.py` 有一個
`autouse` fixture 把 `BEDROCK_MODEL_ID` 清成空的。沒有它的話整套測試會真的打網路 —— 那會花額度、會變慢
（實測 3 秒變 46 秒），而且結果會取決於誰在跑。要驗證真實模型請用手動腳本。

### 預設跑起來為什麼每一項都是「需人工協助」

這不是壞掉。`determination.py` 規定只有資料治理狀態是 `verified`（有人真的審查過）
的方案才可以下完整結論，而離線的預設資料全部是 `candidate`（候選），所以所有項目一律
降級。理由與取捨見
[ADR-0014](../docs/decisions/0014-keep-fixture-data-out-of-verified-status.md)。

要看到「符合資格」的完整路徑，注入 `demo_fixtures` 的兩個實作：

```python
from app.orchestration.demo_fixtures import (
    DemoEntitlementGraphRepository,
    demo_eligibility_service,
)

advance(
    state,
    user_input,
    entitlement_repository=DemoEntitlementGraphRepository(),
    eligibility_service=demo_eligibility_service(),
)
```

**HTTP 端點不會注入它們**，所以從 API 跑仍然是誠實的預設行為。示範資料只走測試與
明確注入的程式碼。

### 資料層接口目前的狀態

四個接口（`EntitlementGraphRepository`、`EligibilityService`、`EvidenceRepository`、
`SourceRefreshService`）都已定義且各有不連資料庫的離線實作，所以測試不需要資料庫。
**目前沒有任何連 SQLite 的實作** —— 那是資料層要交的東西。注入點是
`state_machine.advance()` 的具名參數，換實作不用改狀態機。

已實作的安全行為：

- **資料可信程度的安全檢查**：`verified` 才做完整判定；`candidate`／`under_review`
  可以顯示但一律回 `needs_human_review`；`rejected`／`inactive` 隱藏；`stale` 暫行
  降級（待決策，非定案）。
- **單項失敗隔離**：某一項判定拋例外時只有那一項標成 `needs_human_review`，其餘照常。
- **說不出理由的「不符合」會降級**：規則引擎還不輸出結構化決定性條件，所以現階段不會
  回報任何 `ineligible`。

跨層形狀落差與待決事項記在
[`docs/back_database_doc/README.md`](../docs/back_database_doc/README.md)。

### 尚未實作

依 `AGENTS.md` 的 learn-by-building boundary，以下保留給後端負責人實作或密切審查：

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
- [`docs/back_database_doc/README.md`](../docs/back_database_doc/README.md) — 後端與資料層之間，含八個形狀落差

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
