# ADR-0016: Use Bedrock as the Only Live LLM Provider

- Status: Accepted
- Date: 2026-08-01
- Supersedes: the Gemini provider and fallback parts of ADR-0015
- Retains: the narrow LLM port decision in ADR-0015

## Context

ADR-0015 introduced a narrow `LanguageModelPort` and used Gemini while the
competition Bedrock account was unverified. The competition requires AWS, and
the temporary Workshop Studio session has now been tested in `us-west-2`.

On 2026-08-01 the account successfully called Bedrock Converse with the
inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0`. A forced tool
choice returned the registered `spouse_death` event ID. This verifies the real
model invocation path, not only model discovery.

## Decision

Amazon Bedrock Converse is the only live LLM provider.

- When `BEDROCK_MODEL_ID` is present, build `BedrockLanguageModel`.
- When it is absent, use the offline demo fixture.
- When Bedrock fails at runtime, return the existing safe model error. Do not
  silently switch to the fixture or another live provider.
- Remove the Gemini adapter, configuration, factory branch, tests, environment
  variables, and runtime HTTP dependency.

The Bedrock adapter continues to enforce the existing safety boundary:

- Validate the portable JSON Schema before calling AWS.
- Use Converse forced tool choice only as a structured-output mechanism.
- Send no conversation history.
- Never log `user_content` or include it in errors.
- Never expose the model's raw response in errors.
- Keep calls below one request per second.
- Do not let model output set or modify eligibility status.

## Rationale

Bedrock satisfies the competition's AWS requirement and has been proven in the
actual account. Keeping a second live provider would add configuration, egress,
failure, and testing paths without improving the competition deployment.

The offline fixture remains useful for development, automated tests, and a
deliberate no-network demo. Making that choice at startup keeps it visible. A
runtime fallback would be misleading because the application could present a
fixed demo answer as if it came from the configured live model.

## Consequences

- The live provider selection is `Bedrock -> explicit failure`; there is no
  live-provider fallback chain.
- The startup selection is `BEDROCK_MODEL_ID -> Bedrock`, otherwise offline
  demo.
- Developers need AWS temporary credentials, `AWS_REGION=us-west-2`, and the
  verified inference profile to test the live path.
- Automated tests remain offline and require no AWS credentials.
- ADR-0015 remains authoritative for the narrow port, privacy boundary, and the
  rule that LLMs do not determine eligibility. Its Gemini implementation and
  fallback details are superseded by this ADR.

---

# ADR-0016：Bedrock 是唯一的 live LLM provider

- 狀態：已接受
- 日期：2026-08-01
- 取代：ADR-0015 中 Gemini provider 與 fallback 的部分
- 保留：ADR-0015 的窄 LLM port 決策

## 背景

ADR-0015 建立窄的 `LanguageModelPort`，並在競賽 Bedrock 帳號尚未驗證時先使用 Gemini。
競賽要求使用 AWS，而 Workshop Studio 的臨時 session 現在已在 `us-west-2` 實測完成。

2026-08-01 已用 inference profile
`us.anthropic.claude-haiku-4-5-20251001-v1:0` 成功呼叫 Bedrock Converse，並以 forced
tool choice 取得登記表中的 `spouse_death` 事件代號。這驗證的是實際模型呼叫，不只是
列出模型。

## 決定

Amazon Bedrock Converse 是唯一的 live LLM provider。

- 有 `BEDROCK_MODEL_ID` 時建立 `BedrockLanguageModel`。
- 沒有時使用 offline demo fixture。
- Bedrock 執行中失敗時回傳既有的安全模型錯誤，不偷偷切換 fixture 或其他 live provider。
- 移除 Gemini adapter、設定、factory 分支、測試、環境變數與 runtime HTTP 依賴。

Bedrock adapter 繼續維持既有安全邊界：呼叫前驗證可攜 schema、forced tool choice 只用來
取得結構化輸出、不傳對話歷史、不記錄 `user_content`、錯誤不包含模型原始回應、維持每秒
少於一次呼叫，而且模型輸出不能回傳或修改資格狀態。

## 理由

Bedrock 符合競賽 AWS 要求，而且已在實際帳號證明可用。保留第二個 live provider 只會增加
設定、資料外送、錯誤與測試路徑，對競賽部署沒有實質幫助。

Offline fixture 仍適合本機開發、自動測試與明確選擇的無網路 demo。啟動時決定 provider
讓這個選擇可見；runtime fallback 反而可能把固定示範答案冒充成正式模型結果。

## 後果

- Live provider 路徑是 `Bedrock -> 明確失敗`，沒有 live-provider fallback chain。
- 啟動時的選擇是 `BEDROCK_MODEL_ID -> Bedrock`，否則 offline demo。
- Live 測試需要 AWS 臨時 credentials、`AWS_REGION=us-west-2` 與已驗證的 inference profile。
- 自動測試維持離線，不需要 AWS credentials。
- ADR-0015 仍負責窄 port、隱私邊界與 LLM 不判定資格的決策；其中 Gemini 實作與 fallback
  說明由本 ADR 取代。
