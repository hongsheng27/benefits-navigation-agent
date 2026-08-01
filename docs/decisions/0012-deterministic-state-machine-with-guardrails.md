# ADR-0012: Deterministic State Machine with Loop Guardrails

- Status: Accepted
- Date: 2026-07-28

## Decision

The workflow is driven by a deterministic state machine in
`backend/app/orchestration/state_machine.py`. All flow rules are declared in
three lookup tables rather than scattered across handler functions:

1. **ALLOWED_INPUTS** — which input kinds each state accepts (empty set means
   auto-advance, no user interaction needed).
2. **ENTRY_GUARDS** — conditions that must hold before entering a state; when
   not met the state is skipped.
3. **NOMINAL_PATH** — the default next state in a straight-through run.

When user input is processed, the engine auto-advances through all states that
do not require user interaction, stopping only at the next state that has
allowed inputs. This means a single API call can traverse multiple internal
states.

The collect → retrieve → evaluate loop is protected by two guardrails today:

- **Iteration limit** (6): if iterations reach the cap with unsettled items,
  `exit_reason` is set to `LOOP_LIMIT_REACHED`.
- **Must-make-progress**: after the first iteration, if neither item statuses
  nor attribute count changed compared to before the user's input, `exit_reason`
  is set to `NO_PROGRESS`.

Two more guardrails (no-evidence → human review, no-re-evaluation of settled
items) will be added when the retrieval and evaluation steps have real content.

Field readiness is determined by the field registry: an item is ready for
evaluation when all fields declared in `used_by` for that item have been
answered.

---

# ADR-0012：具有迴圈護欄的確定性狀態機

- 狀態：已接受
- 日期：2026-07-28

## 決定

Workflow 由 `backend/app/orchestration/state_machine.py` 裡的確定性狀態機驅動。
所有流程規則宣告在三張查詢表裡，不散在各個處理函式中：

1. **ALLOWED_INPUTS** — 每個狀態接受哪些輸入種類（空集合代表自動推進，不等使用者）。
2. **ENTRY_GUARDS** — 進入某個狀態之前的守門條件；不滿足就跳過。
3. **NOMINAL_PATH** — 正常路徑的下一步。

處理使用者輸入後，引擎會自動推進經過所有不需要使用者的狀態，直到停在下一個有
`ALLOWED_INPUTS` 的狀態。所以前端一次 API 呼叫可以走過多個內部狀態。

「追問 → 檢索 → 判定」的迴圈目前有兩道護欄：

- **迭代上限**（6 圈）：到達上限且仍有未定案項目時，設
  `exit_reason = LOOP_LIMIT_REACHED`。
- **必須有進展**：第一圈之後，如果「項目狀態」和「屬性數量」都沒有變化，設
  `exit_reason = NO_PROGRESS`。

另外兩道護欄（找不到依據就標人工協助、已定案不重跑）會在檢索與判定有真正內容時加入。

項目是否就緒由欄位登記表決定：當一個項目在 `used_by` 裡宣告的所有欄位都被回答了，
它就可以送去判定。
