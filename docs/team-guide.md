# 團隊工作規範

這份文件只放每天會用到的東西。決策背景在
[ADR](decisions/README.md)，commit 格式細節在
[CONTRIBUTING.md](../CONTRIBUTING.md)，這裡不重複。

## 開工

需要先安裝 [uv](https://docs.astral.sh/uv/) 與 Node.js 22.12 以上。不需要自己裝
Python，uv 會取得正確的版本。

**前端**

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

**後端**

```bash
cd backend
uv sync                                 # 自動取得 Python 3.13、建立 .venv、安裝套件
uv run uvicorn app.main:app --reload    # http://localhost:8000
```

環境變數複製根目錄 `.env.example` 到根目錄 `.env`。後端會依序讀取 `../.env` 與
`backend/.env`；前端讀 `frontend/.env.local` 或根目錄的 `VITE_` 變數。

兩邊都啟動後，前端右上角會顯示「後端已連線」。

## 每天的循環

```text
改東西  →  跑檢查  →  commit
```

**提交前一定要跑過**：

```bash
make format    # 先排版
make check     # 前後端全部檢查
```

只想跑單邊：`make check-frontend` 或 `make check-backend`。

沒跑過就不要說「檢查通過」。

### Windows 沒有 make

兩個選擇，擇一即可。

裝一次就跟大家一樣：

```powershell
winget install ezwinports.make
```

或直接打底下的指令，效果相同：

```bash
cd frontend
npm run format && npm run format:check && npm run lint && npm run typecheck && npm test
```

```bash
cd backend
uv run ruff format . && uv run ruff format --check . && uv run ruff check . && uv run pytest
```

> 這兩段是 `Makefile` 內容的展開。改動檢查流程時兩邊要一起更新。

### 排版由工具決定，不要手動對齊

前端用 **Prettier**，後端用 **ruff format**。兩邊都是 88 字元寬。

排版**不是個人偏好**——四個人不同編輯器產生的縮排差異，會變成純排版的 merge
conflict，在現場最浪費時間。`make check` 會擋下沒排版的檔案。

另外請在編輯器裝 **EditorConfig** 外掛（VS Code、JetBrains、Kiro 都支援）。
根目錄的 `.editorconfig` 會統一縮排、換行字元與檔尾空行。

**Commit** 使用 Conventional Commit 格式，型別與 scope 見
[CONTRIBUTING.md](../CONTRIBUTING.md)：

```text
feat(rules): add survivor pension eligibility conditions

- Add age and dependent-child conditions
- Add golden cases for the ineligible boundary
```

一個 commit 一件事。不要把前端、後端、資料混在同一個 commit。

## PR 怎麼合併

每個 PR 都會收到 Codex 自動 review。可以按 merge 的條件：

1. 本機跑過 `make check`，把結果寫進 PR 描述。
2. 如果 Codex review 提出 blocking 項目，先處理完再 merge。

兩條都滿足後，**可以自己 merge 自己的 PR**，不用等別人按或等待固定的
review verdict。

Review 只會因為三條紅線擋人：**secrets／PII／LLM 做資格判定**。
其他都只是提醒，不會卡你。

給 AI reviewer 與 coding agent 的規則本體在 [AGENTS.md](../AGENTS.md)，
不用背，agent 會照做。

## 三條隱私紅線

這三條已經定案（[ADR-0007](decisions/0007-limit-data-retention-and-egress.md)），
寫程式時直接遵守，不需要重新討論：

**1. 使用者打的字不能進 log。**

後端一律使用 `log_event`，不要用 `print` 或 `logging.info`：

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

只有 `ALLOWED_FIELDS` 內的欄位會被接受，其他直接丟出
`DisallowedLogFieldError`。這是刻意的：寫錯要在跑測試時就發現，不是上線後。

記錄例外時用 `exc_info=True`，**不要**把例外訊息當欄位傳進去 —— Pydantic 的
`ValidationError` 會把違規的輸入值寫進訊息裡。

```python
try:
    ...
except ValueError:
    log_event("extraction_failed", level=logging.ERROR,
              session_id=session_id, exc_info=True)
```

**2. 原始自由文字用完即丟。**

`UNDERSTAND_EVENT` 萃取出去識別化屬性之後，原文就不能再寫進 session、資料庫或
回應。後續每個步驟吃的都是結構化屬性，沒有一步需要回頭看原文。

**3. 前端不加第三方 runtime 套件。**

不要引入 analytics、error reporting（Sentry 等）、字型 CDN 或 tag manager。這類
服務通常會擷取表單內容與 DOM 快照。目前 runtime 依賴只有 `react` 與 `react-dom`。

build-time 與開發用的套件不受限制。

## 什麼不能自己決定

以下情況先開 issue 或討論，達成共識後補一份
[ADR](decisions/README.md)，不要直接改：

- 換框架、加新的 AWS 服務、改變部署方式
- 擴充 log 的欄位 allowlist（等於一次隱私決定）
- 開始接收姓名、身分證字號等 direct identifiers
- 改變 LLM 與規則引擎的職責分界

最後一項是底線：**資格判定只能由 rule engine 產生**，LLM 不得決定或覆寫。
理由見 [產品定位](positioning.md)。

## 提案時先問自己四題

新功能、新技術、demo 腳本都適用（出自[產品定位](positioning.md)）：

1. 它強化了哪一項與通用聊天模型的差異？
2. 移除 LLM 之後，這個功能還成立嗎？
3. 它是否需要開始接收 direct identifiers？
4. 它在 demo 上看得見嗎？

四題都答不出來的，優先級往後排。

## 常見錯誤

| 錯誤 | 正確做法 |
|---|---|
| `print(f"收到: {text}")` | `log_event("message_received", session_id=...)` |
| `log_event("failed", error=str(exc))` | `log_event("failed", exc_info=True)` |
| 把原文存進 session 方便 debug | 只存萃取後的屬性；靠 `extracted_field_names` 追查 |
| 為了查 bug 裝 Sentry | 用結構化 log 的 `session_id` 串起整條軌跡 |
| 在 route handler 裡寫判斷邏輯 | route 只做 transport；邏輯放對應模組 |
| 直接改別人負責的模組 | 先講一聲，避免衝突與重工 |

## 分工與檔案邊界

| 成員 | 主要負責 | 主要動到 |
|---|---|---|
| A（Will） | Technical Lead、Agent Platform / AWS | `app/observability/`、`app/services/`、Agent 執行邊界、整合 |
| B | Privacy, Safety & AI Experience | `frontend/`、`app/privacy/` |
| C | Backend Workflow / Agent Tooling | `app/api/`、`app/schemas/`、`app/orchestration/`、`app/tools/` |
| D | Policy Intelligence / Evaluation | `data/`、`app/rules/`、`app/retrieval/`、`docs/official-sources.md` |

要動別人的模組先講一聲。共用的 contract（API schema、tool 介面）改動前要對齊。

## 文件在哪

| 想知道 | 看 |
|---|---|
| 這個產品為什麼存在、跟 ChatGPT 差在哪 | [positioning.md](positioning.md) |
| 模組責任與資料流 | [architecture.md](architecture.md) |
| 某個技術為什麼這樣選 | [decisions/](decisions/README.md) |
| Commit 格式與 scope | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| 後端怎麼跑、實作到哪 | [backend/README.md](../backend/README.md) |
| 前端怎麼跑 | [frontend/README.md](../frontend/README.md) |
| AI coding agent 的規則 | [AGENTS.md](../AGENTS.md) |
