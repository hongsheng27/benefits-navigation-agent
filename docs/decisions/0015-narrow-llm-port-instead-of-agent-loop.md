# ADR-0015: Use a Narrow LLM Port Instead of an Agent Loop

- Status: Accepted
- Date: 2026-07-30
- Relates to: ADR-0003, ADR-0004, ADR-0007

## Context

ADR-0004 planned an `AgentRunner` interface implemented with Strands Agents over
Amazon Bedrock: a bounded agent loop that can select and call tools.

Two model-driven tasks actually exist in this system:

1. `UNDERSTAND_EVENT` — turn one free-text description into a life event code and
   de-identified attributes.
2. `EXPLAIN_RESULT` — restate already-settled determinations in plain language.

Both are single request, single response. Retrieval and eligibility evaluation
between them are deterministic and are not model decisions.

A Bedrock account with model access is not yet confirmed, so the first working
implementation will use the team's own Gemini key.

## Decision

Implement a project-owned **narrow LLM port** rather than an agent loop.

The port takes one instruction, one piece of user content, and a JSON Schema
describing the required answer. It returns parsed structured output. It has no
tool registry, no loop, and no conversation history.

```
app/llm/
├── port.py     LanguageModelPort protocol and boundary shapes
├── fake.py     FakeLanguageModel, fixed answers, no network
├── gemini.py   GeminiLanguageModel, direct HTTP, the only module importing httpx
└── tasks/      resolve_life_event.py, explain_result.py
```

Three constraints are enforced structurally, not by convention:

- Attributes returned by the model pass through the same privacy gate as answers
  submitted by a user. The model gets no exemption.
- The raw text is sent to the model but never stored, logged, or returned. This
  completes the deferred free-text discard work.
- The explanation task returns text only. Its return type has no status field,
  so it cannot alter a determination even if prompted to.

Requests carry no conversation history. Each call is independent.

### Vendor access: direct HTTP, not the vendor SDK

Gemini is called over plain HTTP with `httpx` rather than through the
`google-genai` SDK.

The deciding reason is auditability of egress. This project sends user-written
text to a third party, which ADR-0007 constrains. With a hand-written request,
the exact payload leaving the process is visible in one function and reviewable
in a diff. With an SDK, establishing what is actually transmitted requires
reading someone else's code, and a later SDK version can change it silently.

Secondary reasons: only one endpoint is needed, and the SDK's dependency tree is
large relative to that need.

### Schemas must stay inside the Bedrock-supported subset

Bedrock supports only a subset of JSON Schema Draft 2020-12. The following are
**not** available and must not be used anywhere in this project, including while
only Gemini is wired up:

- `minimum`, `maximum`, `multipleOf`
- `minLength`, `maxLength`
- recursive schemas
- external `$ref`
- `additionalProperties` set to anything other than `false`

`enum` is supported, and closed code lists are what this project actually needs.

Writing a schema that Gemini accepts but Bedrock rejects would surface as a 400
error on the day of the switch, and every schema would need redesigning at once.

## Rationale

Giving a model the ability to call tools would create a path by which it could
influence eligibility, which ADR-0003 forbids. Removing the loop removes the
path; no prompt or guardrail is needed to defend a capability that does not
exist.

ADR-0004 already permits this: it states that direct calls may be used for
single-call structured tasks that do not benefit from an agent loop. This is
that case, not a reversal.

Comparing the two vendor APIs showed the shapes are close enough that the port
does not have to paper over a large gap. Both take role-tagged text messages,
both constrain output with JSON Schema, and both keep inference settings in a
separate block. The differences are field naming, whether the schema is passed
as a string, and authentication.

## Consequences

- The two LLM tasks can be developed and tested with no network and no API key,
  because the default injected implementation is the fake one.
- Switching vendors touches one file. Prompts live in `tasks/` and are not
  restated in any adapter.
- Authentication does not transfer. Gemini uses an API key header; Bedrock
  requires SigV4 request signing and will realistically use `boto3`. The
  hand-written HTTP work is Gemini-specific; the payload understanding and the
  schema discipline carry over.
- Sending user text to Google is a real change to the egress boundary described
  in ADR-0007. It is acceptable for demonstration input, and is recorded here
  rather than left implicit. If the project later handles input from real users
  in distress, this decision must be revisited before that happens.
- Google's API surface is changing: a May 2026 migration guide replaces
  `response_mime_type` with a `response_format` field in the newer Interactions
  API. That guide covers a different endpoint than `generateContent`, but the
  churn is real, and the adapter pins an API version for this reason.
- If multi-turn interaction is later required, a loop must be added
  deliberately. This decision does not leave room for one to appear by accident.
- The stub files in `app/tools/` are leftovers from the agent-loop design. In
  particular `evaluate_eligibility.py` describes something that must never be a
  model-callable tool. They need to be repurposed or removed.

## References

- [Bedrock structured outputs](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html)
- [Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)
- [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini Interactions API breaking changes, May 2026](https://ai.google.dev/gemini-api/docs/interactions-breaking-changes-may-2026)

---

# ADR-0015：改用窄的 LLM port，不做 agent 迴圈

- 狀態：已接受
- 日期：2026-07-30
- 相關：ADR-0003、ADR-0004、ADR-0007

## 背景

ADR-0004 規劃的是 `AgentRunner` 介面，用 Strands Agents 搭配 Amazon Bedrock 實作 ——
一個有界限的 agent 迴圈，模型可以自己選擇並呼叫工具。

這個系統實際上只有兩個由模型驅動的工作：

1. `UNDERSTAND_EVENT` —— 把一段自由文字變成生命事件代號與去識別化屬性。
2. `EXPLAIN_RESULT` —— 把**已經定案**的判定結果換成白話。

兩者都是問一次、答一次。中間的檢索與資格判定是確定性的，不是模型的決定。

比賽的 Bedrock 帳號權限尚未確認，所以第一個可運作的實作會用團隊自己的 Gemini 金鑰。

## 決定

實作一個由本專案擁有的**窄 LLM port**，不做 agent 迴圈。

Port 接收一段指示、一段使用者內容、以及一份描述答案格式的 JSON Schema，回傳解析好的
結構化結果。它**沒有**工具登記表、沒有迴圈、沒有對話歷史。

```
app/llm/
├── port.py     LanguageModelPort 協定與請求／回應的邊界形狀
├── fake.py     FakeLanguageModel，固定答案，不連網路
├── gemini.py   GeminiLanguageModel，直接打 HTTP，唯一 import httpx 的模組
└── tasks/      resolve_life_event.py、explain_result.py
```

三條約束用結構強制，不靠慣例：

- 模型回來的屬性，走**與使用者直接送答案完全相同**的隱私閘門。模型不享有豁免。
- 原文會送給模型，但不寫入 state、不寫入紀錄檔、不回傳前端。這也**完成了先前延後的
  原文丟棄工作**。
- 解釋任務的回傳型別**只有文字**，沒有 status 欄位，所以即使 prompt 被繞過，
  它也沒有地方可以改變判定。

請求不帶對話歷史，每次呼叫獨立。

### 廠商存取：直接打 HTTP，不用廠商 SDK

呼叫 Gemini 用 `httpx` 直接發 HTTP 請求，不使用 `google-genai` SDK。

決定性的理由是**資料外送的可稽核性**。本專案會把使用者寫的文字送到第三方，而 ADR-0007
對此有限制。自己寫請求的話，離開這個行程的完整內容在一個函式裡看得完，而且任何改動都
會出現在 diff 上。用 SDK 的話，要確認實際送出什麼得去讀別人的程式碼，而且之後版本更新
可能悄悄改掉它。

次要理由：我們只需要一個端點，而 SDK 的依賴樹相對於這個需求過大。

### Schema 一律限制在 Bedrock 支援的子集內

Bedrock 只支援 JSON Schema Draft 2020-12 的一個子集。以下**不可用**，即使目前只接
Gemini 也不可用：

- `minimum`、`maximum`、`multipleOf`
- `minLength`、`maxLength`
- 遞迴 schema
- 外部 `$ref`
- `additionalProperties` 設成 `false` 以外的值

`enum` 支援，而封閉的代號清單正是本專案真正需要的東西。

寫出「Gemini 接受但 Bedrock 拒絕」的 schema，會在切換的那天變成 400 錯誤，
而且每一份 schema 都要同時重新設計。

## 理由

給模型呼叫工具的能力，等於開出一條它可以影響資格判定的路，而 ADR-0003 明文禁止。
移除迴圈就移除那條路 —— 不存在的能力不需要用 prompt 或護欄去防守。

ADR-0004 本身就允許這樣做：它寫明「單次結構化任務不需要 agent 迴圈時，可以直接呼叫」。
這正是那種情況，不是推翻它。

比較兩邊的 API 之後確認形狀足夠接近，port 不需要去彌補一個很大的落差：兩邊都用帶
role 的文字訊息、都用 JSON Schema 限制輸出、都把推論設定放在獨立區塊。差別只在欄位
命名、schema 是否要字串化、以及認證方式。

## 後果

- 兩個 LLM 任務可以在**沒有網路、沒有金鑰**的情況下開發與測試，因為預設注入的是假實作。
- 換廠商只動一個檔案。Prompt 放在 `tasks/`，不會在任何 adapter 裡重述一次。
- **認證方式不會延續。** Gemini 用 API 金鑰放 header；Bedrock 需要 SigV4 請求簽章，
  實務上會用 `boto3`。手寫 HTTP 這件事是 Gemini 專屬的；延續下來的是對請求內容的理解
  與 schema 的紀律。
- 把使用者文字送到 Google，是對 ADR-0007 所描述的外送邊界的**實質變更**。用在示範
  輸入上是可接受的，而且記在這裡而不是留成默契。**如果之後要處理真實使用者
  （處於人生低谷的人）的輸入，必須在那之前重新檢視這個決定。**
- Google 的 API 正在變動：2026 年 5 月的一份遷移說明在較新的 Interactions API 裡用
  `response_format` 取代 `response_mime_type`。那份說明針對的端點與 `generateContent`
  不同，但變動是真的，所以 adapter 會釘住 API 版本。
- 如果之後需要多輪互動，必須**刻意**加上迴圈。這個決定不留任何讓迴圈自己冒出來的空間。
- `app/tools/` 底下的空殼檔案是 agent 迴圈設計的遺留物。其中
  `evaluate_eligibility.py` 描述的東西**絕對不能**成為模型可呼叫的工具。
  那三個檔案需要重新安排或刪除。
