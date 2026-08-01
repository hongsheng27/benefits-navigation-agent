# ADR-0011: Use Frozen Pydantic Models for Session Workflow State

- Status: Accepted
- Date: 2026-07-26

> 中文版在本文件後半段：[以 frozen Pydantic 模型表達 session workflow state](#adr-0011以-frozen-pydantic-模型表達-session-workflow-state)

## Context

ADR-0003 puts a state machine in charge of the workflow, and ADR-0005 makes the
backend the authoritative owner of de-identified session state. Neither ADR says
what that state looks like in code.

The shape has to be settled before anything else in the backend can proceed. The
transport contract in `app.schemas` is a projection of it, the state machine
reads and rewrites it, and the rule engine writes decisions into it. Three
modules and two other contributors are blocked while it is undefined.

The shape also has to carry two constraints that are easy to lose. ADR-0007
discards free text after extraction, so no field may invite prose. ADR-0005
keeps direct identifiers on the client, so no field may hold identity data.
Stating those rules in prose has already proven insufficient elsewhere in this
repository, which is why `app.observability.logging` enforces its field
allowlist in code rather than in documentation.

## Options Considered

1. Standard-library dataclasses, keeping orchestration free of third-party types.
2. Mutable Pydantic models, letting each step assign to the fields it changes.
3. Frozen Pydantic models, where every step produces a new state object.

A related choice applied to item status: a single flat enumeration covering both
rule outcomes and item lifecycle, or a nested shape separating "settled" from the
four decision values.

## Decision

Adopt option 3, expressed as six rules.

### 1. Pydantic, not dataclasses

Session state is serialized and projected into API responses. Pydantic supplies
both directions of that conversion, including enum and datetime handling, and the
project already depends on it through FastAPI and `pydantic-settings`. Requiring
a second declaration style would add hand-written conversion code between
`app.orchestration` and `app.schemas`.

The framework-neutrality rule in the backend README was considered and judged not
to apply: it exists to keep business logic independent of the web framework, and
Pydantic is a validation library rather than a framework.

### 2. Frozen models

`frozen=True` blocks attribute reassignment, so a transition cannot mutate the
state it was handed. `state_machine.py` becomes the only place where workflow
state changes, and every change is a new object.

The limitation is recorded rather than hidden: freezing prevents rebinding a
field, not mutating the object a field points at. Sequence fields use `tuple`;
the attribute map keeps `dict` and is treated as read-only by convention.

### 3. No field may hold user text or direct identifiers

`SessionState` has no `text`, `description`, `raw_input`, or `note`, and no field
for a name, national ID, address, phone, or email. `extra="forbid"` rejects
unknown fields, and a unit test scans field names for markers of prose and
identity data. Legitimate exceptions are listed by name in the test with a stated
reason, so relaxing the check requires an explicit edit.

### 4. Status is per item, using one flat enumeration

Each `CandidateItem` carries its own status. A session routinely holds several
eligible items alongside an unresolved one, and the result screen groups the list
by status.

`ItemStatus` has six values. `RULE_ENGINE_STATUSES` names the four the rule
engine may return, so the constraint that the engine does not own item lifecycle
remains checkable while consumers still read a single field.

### 5. Session-level exits are separate from item-level review

`ExitReason` covers the five cases that stop a whole session. Two documented
blocked cases are item-level instead and set `NEEDS_HUMAN_REVIEW` on the affected
item while the rest of the session continues: no official evidence was found, and
a rule could not name the condition behind an ineligible result.

### 6. Transition history lives in logs, not in state

`log_event` already accepts `state`, `next_state`, `transition`, and `guard`, and
no transition depends on reading the history. Duplicating it in state would store
the same facts twice.

## Amendment 1: An item carries a structured amount (2026-07-26)

The first version of `CandidateItem` had nowhere to put money, so an eligible
result could be produced but the figure could not reach the screen.

Options: mirror the rule engine's `amount` plus `amount_label`; store a single
`amount` with a currency; or store bounds, period, and currency.

**Decision: bounds, period, and currency.** `CandidateItem` gains `amount_min`,
`amount_max`, `amount_period`, and `amount_currency`, plus an `AmountPeriod`
enumeration for one-time, monthly, and annual payments.

- Two bounds, because the catalog already treats `min_amount` and `max_amount` as
  separate fields. A fixed amount repeats the same value in both.
- No `amount_label`, because display text belongs to the frontend under the same
  split used for question wording.
- `amount_period` is part of the shape, because "5,000" and "5,000 per month"
  cannot be told apart from the number alone.
- Administrative items normally leave the whole group empty.

The adapter around the rule engine must map its single `amount` onto both bounds
and source the period from the rule fields.

## Consequences

### Positive

- Unblocks the transport contract, the state machine, and the rule engine, which
  three separate tasks depend on.
- Makes two privacy rules structural rather than advisory, and testable.
- Confines workflow state changes to one module, so an unexpected state can be
  traced to a single file.
- Keeps a single declaration style across the backend.
- Allows several items to be eligible at once, matching the result screen.

### Negative

- Every change needs `model_copy(update=...)`, which is more verbose than
  assignment, and nested updates require rebuilding the enclosing state.
- Adds a second place where a Pydantic `ValidationError` can be raised, and such
  a message may quote the offending value. Three rules in the module docstring
  keep it contained: state is never built directly from client input, a failure
  here is a programming error and is allowed to crash, and callers log the
  exception type only.
- Diverges in letter from ADR-0005, which lists transition history as
  backend-owned state. It remains backend-owned, in logs rather than in state.
  The divergence is recorded in code but ADR-0005 is not amended.
- The flat status enumeration does not prevent the rule engine from returning a
  lifecycle value at the type level; the constraint is enforced by the
  `RULE_ENGINE_STATUSES` check instead.

## Non-decisions

This ADR does not decide:

- The transport contract in `app.schemas` or the matching frontend types
- Transition rules, guards, loop caps, or retry caps
- Where session state is stored, or how long it is kept
- How mutually exclusive benefits are represented, which is deferred to the rule
  engine because the exclusion sets depend on unreviewed official documents
- Whether the action plan is stored or derived on demand
- How question groups are formed or counted
- How transient retrieval and model failures are marked
- Whether a state schema version is needed, which depends on persistence

---

# ADR-0011：以 frozen Pydantic 模型表達 session workflow state

- 狀態：已接受
- 日期：2026-07-26

> English version is in the first half of this document:
> [Use Frozen Pydantic Models for Session Workflow State](#adr-0011-use-frozen-pydantic-models-for-session-workflow-state)

## 背景

ADR-0003 讓 state machine 控制整個流程，ADR-0005 則讓後端成為去識別化 session
state 的權威擁有者。但兩份 ADR 都沒有說這份 state 在程式裡長什麼樣。

這個形狀必須先定案，後端其他工作才能往下走。`app.schemas` 的對外契約是它的投影、
state machine 讀取並改寫它、規則引擎把判定結果寫進它。形狀沒定之前，三個模組與
另外兩位貢獻者都被卡住。

這個形狀還必須承載兩項容易流失的約束。ADR-0007 規定自由文字抽取後即丟棄，所以
不能有任何欄位誘使人塞入句子。ADR-0005 規定直接識別資料留在使用者裝置，所以不能
有任何欄位存放身分資料。把這些規則寫成文字說明在本 repository 已經證實不夠 ——
這正是 `app.observability.logging` 選擇用程式而不是文件來強制欄位 allowlist 的原因。

## 候選方案

1. **標準庫 dataclass**，讓 orchestration 不依賴第三方型別。
2. **可變的 Pydantic 模型**，每一步直接對它要改的欄位賦值。
3. **frozen Pydantic 模型**，每一步都產生一個新的 state 物件。

另有一項相關選擇，適用於項目狀態：用**一層扁平的列舉**同時涵蓋規則結果與項目
生命週期，或用**兩層結構**把「是否已定案」與四種判定值分開。

## 決定

採用方案 3，並拆成六條規則。

### 1. 用 Pydantic，不用 dataclass

Session state 需要序列化，也需要投影成 API 回應。Pydantic 提供這兩個方向的轉換，
包含列舉與時間的處理，而專案已經透過 FastAPI 與 `pydantic-settings` 依賴它。多引入
一種宣告方式，會在 `app.orchestration` 與 `app.schemas` 之間產生需要手寫的轉換程式。

Backend README 的 framework-neutral 原則已納入考量，判定為不適用：那條原則存在的
目的是讓業務邏輯不依賴 web framework，而 Pydantic 是驗證套件，不是 framework。

### 2. 模型設為 frozen

`frozen=True` 讓欄位不能重新賦值，所以狀態轉換無法修改傳進來的那份 state。
`state_machine.py` 因此成為唯一會改變 workflow state 的地方，而每一次改變都是一個
新物件。

限制被記錄下來而非隱藏：frozen 只擋住「重新綁定欄位」，不擋「修改欄位指向的物件」。
序列欄位使用 `tuple`；屬性對照表保留 `dict`，以約定方式視為唯讀。

### 3. 任何欄位都不得存放使用者文字或直接識別資料

`SessionState` 沒有 `text`、`description`、`raw_input`、`note`，也沒有姓名、身分證
字號、地址、電話或 email 的欄位。`extra="forbid"` 會拒絕未知欄位，並有一個單元測試
掃描欄位名稱中代表文字與身分資料的片段。正當的例外在測試中逐一列名並附上理由，
因此放寬檢查必須是一次明確的修改。

### 4. 狀態屬於單一項目，使用一層扁平列舉

每個 `CandidateItem` 帶自己的狀態。一次諮詢很常同時存在數個符合的項目與一個尚未
定案的項目，結果畫面就是把這份清單按狀態分區。

`ItemStatus` 有六個值。`RULE_ENGINE_STATUSES` 指出規則引擎唯一允許回傳的四個，
讓「規則引擎不擁有項目生命週期」這條約束仍然可被檢查，同時使用端只需要讀一個欄位。

### 5. 整次諮詢的出口與單一項目的人工協助分開

`ExitReason` 涵蓋五種會讓整次諮詢停止的情況。另有兩種已記錄的「走不下去」屬於項目
層級，只把受影響的項目標成 `NEEDS_HUMAN_REVIEW`，其餘項目照常進行：找不到官方
依據，以及規則無法指出造成「不符合」的條件。

### 6. 轉換歷程記在紀錄檔，不放在 state

`log_event` 已經接受 `state`、`next_state`、`transition` 與 `guard`，而目前沒有任何
轉換需要讀取歷程。在 state 裡再存一份等於把同一件事記錄兩次。

## 修訂一：項目帶結構化的金額（2026-07-26）

`CandidateItem` 的第一版沒有地方放金額，會出現「判定為符合但金額傳不到畫面」的情況。

候選方案：照抄規則引擎的 `amount` 加 `amount_label`；存單一 `amount` 加幣別；
或存上下界、發放性質與幣別。

**決定：存上下界、發放性質與幣別。** `CandidateItem` 新增 `amount_min`、
`amount_max`、`amount_period`、`amount_currency`，並新增 `AmountPeriod` 列舉，
涵蓋一次性、按月與按年。

- 用兩個上下界，因為 catalog 本來就把 `min_amount` 與 `max_amount` 當成兩個欄位。
  單一固定金額時兩者填相同的值。
- 不放 `amount_label`，因為給人看的文字屬於前端，與問題文案沿用同一條分界。
- `amount_period` 屬於形狀的一部分，因為「5,000 元」與「每月 5,000 元」無法只從
  數字分辨。
- 行政事項通常整組金額欄位留空。

包裝規則引擎的轉接層必須把它的單一 `amount` 映射到兩個上下界，並從規則欄位取得
發放性質。

## 後果

### 正面

- 解開對外契約、state machine 與規則引擎的阻塞，這三項是分開的任務。
- 讓兩條隱私規則從「宣示」變成「結構」，並且可被測試。
- 把 workflow state 的改變限制在單一模組，出現非預期狀態時可追到單一檔案。
- 後端維持單一種宣告方式。
- 允許多個項目同時符合，與結果畫面一致。

### 負面

- 每次改動都要用 `model_copy(update=...)`，比直接賦值囉唆，嵌套更新還需要重建外層
  state。
- 多了一個可能拋出 Pydantic `ValidationError` 的地方，而那個訊息可能引用不合法的
  原始值。模組 docstring 用三條規則圍住它：state 永不由前端資料直接建立、這裡的
  失敗屬於程式錯誤且允許直接中斷、呼叫端只記錄例外類別。
- 在文字上偏離 ADR-0005，該 ADR 把轉換歷程列為後端擁有的 state。它仍然由後端擁有，
  只是放在紀錄檔而不是 state。此偏離已記錄在程式中，但未修改 ADR-0005。
- 扁平的狀態列舉無法在型別層面阻止規則引擎回傳生命週期值；該約束改由
  `RULE_ENGINE_STATUSES` 的檢查強制。

## 未決事項

本 ADR 不決定：

- `app.schemas` 的對外契約，以及對應的前端型別
- 狀態轉換規則、守門條件、迴圈上限與重試上限
- session state 存放在哪裡、保存多久
- 互斥福利如何表達 —— 延後到規則引擎，因為互斥組合取決於尚未審核的官方文件
- 辦理清單是儲存下來還是需要時即時推導
- 問題分組如何形成與計數
- 檢索與模型的暫時性失敗如何標記
- 是否需要 state schema 版本 —— 取決於持久化方案

---

## Reference

- [ADR-0003: Use Policy-Governed Hybrid Orchestration](0003-policy-governed-hybrid-orchestration.md)
- [ADR-0005: Split Client and Server Session State](0005-split-client-server-session-state.md)
- [ADR-0007: Limit Data Retention and Egress](0007-limit-data-retention-and-egress.md)
- [ADR-0010: Use a Provenance-First Local Benefit Catalog](0010-use-local-provenance-first-benefit-catalog.md)
