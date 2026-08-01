# AWS Migration Guide

This is the **single source of truth** for transitioning from local mock
implementations to live AWS services on August 1st.

> **Status**: Most features still run on local mocks (SQLite, local files).
> The live LLM path is **Amazon Bedrock `Converse`** when `BEDROCK_MODEL_ID` is
> set; otherwise the backend uses the offline demo. The competition account was
> verified in `us-west-2` on 2026-08-01. See
> [ADR-0016](decisions/0016-use-bedrock-only-live-llm-provider.md).

## How to Use This Guide

On August 1st, teammates should:

1. Set up AWS credentials and fill in `.env` variables listed below.
2. Follow each section to swap local mocks for live services.
3. Test each feature after switching.

---

## Environment Variables Needed on August 1st

Add these to your `.env` file when AWS access is available:

```env
# AWS General — the verified Bedrock path uses us-west-2
AWS_REGION=us-west-2
AWS_ACCOUNT_ID=

# S3 (document storage) — keep buckets private (Block Public Access)
# S3_BUCKET_NAME=

# Database (if migrating from SQLite)
# DATABASE_URL=

# Bedrock (only live LLM provider). Leave empty for the offline demo.
# Verified inference profile in the competition account:
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0

# AgentCore (if used) — not required; this project has no agent loop.
# AGENTCORE_AGENT_ID=
```

---

## Feature: Government OID & Benefit Catalog Database

| Item           | Current (Local)                                                               | AWS Target            |
| -------------- | ----------------------------------------------------------------------------- | --------------------- |
| Database       | `data/local/government_oid.db` (SQLite)                                       | TBD (DynamoDB or RDS) |
| Files affected | `scripts/import_government_oid.py`, `backend/app/services/benefit_catalog.py` | —                     |

### Migration Steps

1. TBD — database choice not yet decided.
2. The SQLite schema in `benefit_catalog.py` defines the contract. Any AWS
   adapter must preserve the same table relationships and constraints.

---

## Feature: Source Document Storage (HTML files)

| Item           | Current (Local)                                                | AWS Target |
| -------------- | -------------------------------------------------------------- | ---------- |
| Storage        | `data/local/source_documents/` (local folder)                  | S3 bucket  |
| Files affected | `backend/app/services/source_connector.py` (`_write_raw_page`) | —          |

### Migration Steps

1. Create an S3 bucket for raw HTML documents.
2. Replace `_write_raw_page()` file write with S3 `put_object`.
3. Update `storage_ref` in `source_documents` table to use `s3://` URIs.
4. Set `S3_BUCKET_NAME` in `.env`.

---

## Feature: LLM / Bedrock Integration

| Item             | Current                                                         | AWS Target                                                                                                                                                                         |
| ---------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LLM              | Bedrock when `BEDROCK_MODEL_ID` is set; otherwise offline demo  | Amazon Bedrock `Converse` + forced tool choice                                                                                                                                     |
| Files            | `backend/app/llm/bedrock.py`, `factory.py`, `config.py`         | already added                                                                                                                                                                      |
| Verified runtime | `us-west-2` and `us-east-1`, Claude Haiku 4.5 inference profile | `Converse` returned the registered `spouse_death` event ID; the us-east-1 run on 2026-08-01 also returned `applicant_jurisdiction` and `children_count` through forced tool choice |

**There is no `AgentRunner`.** ADR-0015 replaced it with a narrow port that has
no tool loop, because both model tasks are single request/response and giving a
model a free tool loop would open a path for it to influence eligibility.
Forced tool choice here is only a **structured-output vehicle**: one tool whose
`inputSchema.json` is our JSON Schema, and `toolChoice` forces that single tool.
The model cannot call application tools.

### Competition constraints that this feature must obey

- Regions: `us-east-1` or `us-west-2` (default `us-east-1`).
- Bedrock throughput: keep under **1 request per second**. The adapter enforces
  a ≥1.05s gap between calls in-process.
- Enable only the foundation model(s) you will call — do not open every model.
- Never commit AWS keys. Use the AWS credential chain / local `.env` (gitignored).
- Do not send prohibited data categories to AWS (PII, health, etc.). The product
  already strips direct identifiers before model calls; keep it that way.

### What the swap has to preserve

`LanguageModelPort` is the contract. It has one method:

```python
def generate_structured(self, request: LlmRequest) -> LlmResult: ...
```

| Behaviour     | Must not change                                                                                                                                                |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Failure type  | `LanguageModelUnavailableError` for transport, auth, timeout, or missing credentials; `LanguageModelOutputError` when the reply is not a parseable JSON object |
| Error content | Messages must never contain `user_content` or the model's raw reply                                                                                            |
| Return value  | `LlmResult.payload` only, never the raw text                                                                                                                   |
| Schema check  | Call `validate_portable_schema()` before sending                                                                                                               |
| Sync          | Stay synchronous                                                                                                                                               |

### How to turn Bedrock on today

1. Log into the competition AWS account and set region to `us-west-2` — the team
   default, matching `config.py` and `.env.example`. `us-east-1` is also verified
   and works, but do not mix them across teammates.

   Confirm you are in the right account first with `aws sts get-caller-identity`.
   The competition identity is `WSParticipantRole/Participant`. A laptop with
   several profiles in `~/.aws/credentials` will otherwise happily run the whole
   verification against the wrong account.

2. Configure the temporary Workshop Studio credentials via the normal AWS chain
   or a local gitignored `.env` file. Never copy credentials into tracked files.
3. Use the inference profile that was successfully tested with Converse.
4. In repository-root `.env`:

   ```env
   AWS_REGION=us-west-2
   BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
   ```

5. Restart the backend. Startup logs should show
   `language_model_selected` with your Bedrock model id.
6. If the venue needs the offline contingency, explicitly clear
   `BEDROCK_MODEL_ID` and restart the backend. A Bedrock failure during a request
   does not silently switch providers.

### First-time Anthropic enablement can block Converse

The Bedrock "Model access" console page has been retired: serverless foundation
models enable themselves on first invocation. Anthropic models are the exception
noted on that page — a first-time account may still have to submit use case
details, and until the enablement has propagated `Converse` fails with:

```text
ResourceNotFoundException: Model use case details have not been submitted for
this account. Fill out the Anthropic use case details form before using the
model. If you have already filled out the form, try again in 15 minutes.
```

**The competition account does not have this problem.** On 2026-08-01 the
`WSParticipantRole` credentials ran `Converse` in `us-east-1` successfully on the
first attempt, both plain text and with forced tool choice.

The error above was observed in a separate personal account, where single calls
succeeded and then reverted to it — which is what a still-propagating enablement
looks like. Recorded here only so the error is recognisable: it is neither an IAM
problem nor a wrong model ID, and opening the model once in the console
Playground is the documented way to trigger enablement.

**Do not debug the request shape while this error is showing.** Wait and retry.
If it persists, check the other note on the retired page: for models served
through AWS Marketplace, a principal with Marketplace permissions has to invoke
the model once to enable it account-wide.

### Request shape (Converse)

| `LlmRequest` field                 | Converse location                                                |
| ---------------------------------- | ---------------------------------------------------------------- |
| `instruction`                      | `system[0].text`                                                 |
| `user_content`                     | `messages[0].content[0].text` (marked as data, not instructions) |
| `output_schema`                    | `toolConfig.tools[0].toolSpec.inputSchema.json`                  |
| `schema_name`                      | `toolSpec.name` + `toolChoice.tool.name`                         |
| `max_output_tokens`, `temperature` | `inferenceConfig.maxTokens`, `inferenceConfig.temperature`       |

Gemini has been removed from the runtime, configuration, dependency list, and
active documentation. Bedrock is the only live provider; the local fixture is
the deliberate offline contingency.

### The JSON Schema subset is a hard constraint, already enforced

Bedrock supports only a subset of JSON Schema Draft 2020-12. `port.py` enforces
this at runtime with `validate_portable_schema()`, and the offline fake enforces
it too, so violations surface during local development rather than on migration
day.

Not available: `minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`,
recursive schemas, external `$ref`, and `additionalProperties` set to anything
other than `false`. `enum` is available and is what this project actually needs.

If a schema needs to change, keep it inside the allowlist in
`port.ALLOWED_SCHEMA_KEYWORDS` rather than widening the allowlist.

### Privacy note that survives the migration

Sending user text to Bedrock is an external egress. The three structural rules
remain: model-returned attributes go through
the same privacy gate as user-submitted answers, the raw text is never stored or
logged, and the explanation task's return type has no status field so it cannot
alter a determination.

### Case 2: multi-event recognition

The father-occupational-disability Case 2 reuses this exact Bedrock path. There
is no local-to-AWS code swap and no new environment variable:

- Local/offline: `demo_language_model()` remains the explicit fixture selected
  only when `BEDROCK_MODEL_ID` is empty.
- AWS/live: `backend/app/llm/tasks/resolve_life_event.py` sends the fictional
  description through `LanguageModelPort` and Bedrock Converse forced tool
  choice, returning one to five ordered registered IDs in `event_ids`.
- Configuration: keep using `AWS_REGION`, `AWS_DEFAULT_REGION`, and
  `BEDROCK_MODEL_ID` documented above.

The event registry retains all existing event IDs. The Case 2 output contract is
`{"event_ids":["occupational_injury","long_term_care_need"]}`: occupational
injury remains primary, while the explicit long-term-care need is preserved.
Disability-service wording, childcare, and reduced hours do not automatically
add `disability_onset` or `caregiver_burden`, and none of these IDs is an
eligibility conclusion.

The API exposes the ordered list as `lifeEvents` and temporarily retains
`lifeEvent` as the first ID for consumers that still accept only one event. An
AWS-backed session store must persist both fields until those consumers migrate;
it must not silently discard secondary IDs.

Live verification on 2026-08-01 used the fictional Case 2 description with the
configured Bedrock model before the multi-event contract was introduced. After
this schema change, repeat live verification and expect both registered IDs;
local tests validate the contract without making a network call.

The five-event upper bound was then verified live on 2026-08-01 with the same
fictional Case 2 description plus a spouse-death sentence. Bedrock returned
`occupational_injury`, `long_term_care_need`, `caregiver_burden`,
`childcare_hardship`, and `spouse_death`; the session accepted all five instead
of mapping the response to `event_not_recognized`.

---

## Feature: Session Persistence

| Item           | Current (Local)                                                     | AWS Target                         |
| -------------- | ------------------------------------------------------------------- | ---------------------------------- |
| Sessions       | In-process memory, two hour expiry                                  | TBD (DynamoDB or AgentCore Memory) |
| Files affected | `backend/app/orchestration/session_store.py`, `backend/app/main.py` | —                                  |

The local mock is `InMemorySessionStore`: a dictionary held on the FastAPI
application instance. A restart discards every session, which ADR-0005 accepts
because the persistence choice is still open.

The frontend intentionally keeps `sessionId` in memory only. Reloading the page
or leaving and re-entering consultation starts a new frontend session and does
not call `/sessions/current` to restore an abandoned one. Replacing the backend
store with an AWS service must not silently re-enable browser persistence;
cross-reload recovery requires a separate privacy and product decision.

### What the swap has to preserve

`InMemorySessionStore` is the contract. Any AWS-backed replacement must keep the
same five methods and the same failure modes, so nothing above it changes:

| Method               | Behaviour that must not change                                                                                   |
| -------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `create()`           | Return a new `SessionState` with a `secrets`-generated id and `expires_at` set two hours ahead                   |
| `get(session_id)`    | Raise `SessionNotFoundError` for unknown ids and `SessionExpiredError` past the TTL, deleting the expired record |
| `save(state)`        | Replace the stored state, stamp `updated_at`, and **not** extend `expires_at`                                    |
| `delete(session_id)` | Succeed even when the session is already gone                                                                    |
| `purge_expired()`    | Remove expired records and return how many                                                                       |

Two constraints carry over from ADR-0005 and ADR-0007 and must survive the swap:

- The stored record holds no direct identifiers and no free text. Do not add
  fields while migrating.
- `session_id` is a bearer credential. Keep it out of URLs, table scan logs, and
  any exported metrics.

### Migration Steps

1. Decide between DynamoDB and AgentCore Memory. Not yet decided.
2. Add a store class that implements the five methods above, for example
   `DynamoDbSessionStore`, in the same module.
3. Use the service's native expiry (DynamoDB TTL) so records disappear without a
   scheduled job, matching the current read-time deletion.
4. Swap the single construction site in `backend/app/main.py`:
   `app.state.session_store = InMemorySessionStore()`.
5. Keep `InMemorySessionStore` for tests. `backend/tests/unit/test_session_store.py`
   injects a fake clock and must keep passing without AWS access.
6. Fill in the environment variables below.

### Environment variables

```env
# Session persistence (fill in on August 1st)
# SESSION_TABLE_NAME=
# SESSION_TTL_HOURS=2
```

### Known limitation of the local mock

The store lives in one process, so it does not work across processes. Running
more than one instance today would send a request to a process that has never
seen that `session_id`. This disappears once a shared store is in place, and is
the main reason to do this migration rather than leave the mock in production.

---

## Feature: Storage-Neutral Data Layer Interfaces

These are the seams the workflow uses to reach the data layer. Until August 1st
every one of them has an offline implementation that needs no database at all,
which is why the workflow test suite runs without SQLite.

| Item              | Current (Local)                                       | AWS Target                                            |
| ----------------- | ----------------------------------------------------- | ----------------------------------------------------- |
| Interfaces        | `backend/app/orchestration/protocols.py`              | unchanged — this is the contract                      |
| Exchange shapes   | `backend/app/orchestration/data_contracts.py`         | unchanged — this is the contract                      |
| Entitlement graph | `FixtureEntitlementGraphRepository` (hardcoded table) | SQLite repository, then TBD cloud database            |
| Eligibility       | `FixtureEligibilityService` (decisions passed in)     | SQLite rule tables plus the deterministic rule engine |
| Evidence          | `FixtureEvidenceRepository` (empty by default)        | SQLite `source_documents` / `program_sources`         |
| Source refresh    | `LocalSourceRefreshService` (in-process list)         | TBD queue (SQS or EventBridge)                        |

### Case 2 occupational-injury fixture

`FixtureEntitlementGraphRepository` currently contains the seven Case 2
candidate directions and deterministic relevance predicates. The seven
question fields live in `data/eligibility_fields/fields.v0.1.json`. This is a
backend-driven local vertical slice, but it is still mock policy data: retained
items remain `candidate` and the workflow reports `needs_human_review`.

When the SQLite runtime branch is available:

1. Remove the Case 2 item tuple and `_care_item_is_relevant` predicates from
   `backend/app/orchestration/protocols.py`; keep the fixture implementation for
   isolated tests, but load its test data explicitly rather than treating it as
   runtime truth.
2. Insert equivalent `occupational_injury` graph nodes, program nodes, field
   requirements and conditional edges through the SQLite migration/seed path.
3. Keep the answer-time `expand_from_event(event_id, attributes)` call in
   `state_machine.py`. It is the storage-neutral point that makes updated
   answers filter the graph.
4. Do not promote the migrated Case 2 programs or citations to `verified`.
   Human review of the Rule DSL and official excerpts is required first.
5. For the RDS cutover, migrate the same rows to PostgreSQL and inject the RDS
   adapter at the application composition root. No frontend environment
   variable is required for this feature.

### What the swap has to preserve

The four `Protocol` classes in `protocols.py` are the contract. Any SQLite or
cloud adapter must keep the same method names and the same return types:

| Interface                    | Methods that must not change                                                       |
| ---------------------------- | ---------------------------------------------------------------------------------- |
| `EntitlementGraphRepository` | `expand_from_event`, `get_prerequisites`, `get_produces`, `get_programs_by_system` |
| `EligibilityService`         | `get_required_fields`, `evaluate`, `evaluate_many`                                 |
| `EvidenceRepository`         | `get_citations`                                                                    |
| `SourceRefreshService`       | `get_coverage_status`, `request_on_demand_refresh`                                 |

Three constraints carry over and must survive the swap:

- Return the frozen dataclasses from `data_contracts.py`. Never return
  `sqlite3.Row`, a SQL tuple, or an undecoded `metadata_json` blob. This is what
  keeps table renames from reaching the workflow.
- `StructuredReason.actual` may travel back to the user who asked. It must never
  reach a log, trace, metric, exception message, or persisted audit event. The
  allowlist in `backend/app/observability/logging.py` has no field that can hold
  it, and `backend/tests/unit/test_logging.py` asserts that.
- Crawler and LLM output stays in `candidate` or `under_review`. Promotion to
  `verified` is a human review step, never an automatic one.

### Migration Steps

1. Replace the construction sites in `backend/app/orchestration/state_machine.py`
   (`advance()` builds the defaults) with the data layer's SQLite repositories.
   Every seam is already a named parameter; keep the API contract unchanged.
2. Add the SQLite adapters in the data layer, mapping `program_id` to `item_id`
   and decoding stored JSON into the `data_contracts` dataclasses.
3. Only after the database choice is settled, add a cloud adapter behind the
   same interfaces.
4. Keep the fixture implementations. They are what the workflow tests use.

### Feature: On-Demand Source Refresh Queue

| Item  | Current (Local)                                      | AWS Target                                          |
| ----- | ---------------------------------------------------- | --------------------------------------------------- |
| Queue | `LocalSourceRefreshService._queue`, a Python list    | TBD (SQS, EventBridge Scheduler, or Step Functions) |
| Flow  | `backend/app/orchestration/source_refresh.py`        | unchanged                                           |
| Dedup | in-memory set keyed by `source_id + event_id + date` | must move to shared storage                         |

Migration steps:

1. Remove the in-process list in `LocalSourceRefreshService` and publish a
   message instead. Keep `request_on_demand_refresh` returning immediately: the
   user's request must never wait for a crawl, attachment extraction, or LLM
   call.
2. Move the same-day dedup key to shared storage. The in-memory set only works
   in a single process, so today two workers would trigger the same source
   twice on the same day.
3. Keep failures non-blocking. `refresh_after_response` swallows the error,
   logs the exception class only, and returns the coverage that was already
   read. That behaviour is required, not incidental.

### Environment variables

```env
# Data layer (fill in on August 1st)
# ENTITLEMENT_DB_URL=
# SOURCE_REFRESH_QUEUE_URL=
# SOURCE_REFRESH_DEDUP_TABLE=
```

### Open decision recorded here on purpose: `stale` behaviour

`stale` programs currently return `needs_human_review`. This is a **provisional**
choice, not a settled decision. Section 12 of
`tmp/sqlite-runtime-alignment-proposal.md` lists it as a joint decision that
neither side may make silently, with two options:

- Option A: serve the last-verified snapshot with an explicit warning.
- Option B: always downgrade to `needs_human_review`.

The backend took the safer end of the range for now, because treating expired
data as current is the failure mode that sends someone to a counter for nothing.
Once the owners decide, change `_STALE_FALLBACK_STATUS` in
`backend/app/orchestration/determination.py` — that is the only place it lives.
Do not read the current behaviour as Option B having been chosen.

---

## Frontend agency directory and case tracking

| Concern             | Local mock now                                                                | Target                                                    |
| ------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------- |
| Agency directory UI | `frontend/src/mocks/agencies.ts` via `frontend/src/api/agencyClient.ts`       | `GET /agencies` backed by SQLite / RDS source registry    |
| Case tracking UI    | `frontend/src/mocks/trackedCases.ts` via `frontend/src/api/trackingClient.ts` | `GET /cases` (or equivalent) persisted session/case store |

### What to change

1. **Agencies**
   - Implement backend `GET /agencies` returning
     `{ agencies: AgencyDirectoryItem[], isMock: false }` shaped like
     `frontend/src/types/agency.ts`.
   - Seed / join from `data/source_registry` and related benefit tables.
   - In `.env` / frontend env: set `VITE_USE_AGENCY_MOCK=false` so
     `listAgencies()` stops short-circuiting to mock.
   - Optional: `VITE_AGENCIES_API_PATH=/agencies` if the path differs.

2. **Case tracking**
   - Implement backend list endpoint for saved consult cases.
   - Shape responses like `frontend/src/types/tracking.ts`.
   - Default client already tries the API and falls back to mock on failure;
     set `VITE_USE_CASE_TRACKING_MOCK=true` only when you want to force mock.

### Environment variables

```env
# Frontend — agency directory / case tracking (fill when APIs exist)
# VITE_USE_AGENCY_MOCK=false
# VITE_AGENCIES_API_PATH=/agencies
# VITE_USE_CASE_TRACKING_MOCK=false
# VITE_CASES_API_PATH=/cases
```

---

## Multi life-event confirmation

| Concern | Local now | Target |
|---|---|---|
| Resolve step | `resolve_life_event` returns up to 5 `event_ids` | Same schema on Bedrock |
| Extras | Deterministic co-occurrence (`life_event_selection.py`) adds 3 candidates | Optional graph-based relatedness |
| Expand | Union of `expand_from_event` per confirmed event | Entitlement graph multi-root expand |
| Cap | App enforces max 5 confirmed events (Bedrock schema has no `maxItems`) | Keep app-side cap |

No new environment variables.

---

## Conversational attribute collection (T21b-style)

| Concern             | Local now                                                                     | Target                                          |
| ------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------- |
| Chat turn API       | `attribute_chat_turn` on `POST /sessions/advance` + `collect_attributes` task | Same; Bedrock when `BEDROCK_MODEL_ID` set       |
| Jurisdiction filter | `applicant_jurisdiction` + `jurisdiction_items.py` fixtures                   | Entitlement graph rows with `jurisdiction_code` |
| MCQ fallback        | Frontend `AttributeChatPanel` → `QuestionGroupList`                           | Keep as offline / low-confidence path           |

Reuse `BEDROCK_MODEL_ID` / AWS credentials above. No new frontend env required.

---

## Frontend post-consult panels (related law + application guide)

| Concern               | Local mock now                                                                                              | Target                                                                 |
| --------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Related provisions UI | `frontend/src/mocks/relatedProvisions.ts` filtered by result `itemId` + life event (no cross-event funeral fallback) | Session / item `citations` with real excerpts via `official_citations` |
| Application guide UI  | `frontend/src/mocks/applicationGuides.ts` per life event (`null` when unknown; never fall back to spouse-death) | Backend `action_plan` (or equivalent) per life event / item            |
| Copilot chat          | `POST /sessions/current/explain` via `frontend/src/api/explainClient.ts` + stub fallback (`copilotStub.ts`) | Same endpoint; Bedrock when `BEDROCK_MODEL_ID` is set                  |

### What to change

1. **Related provisions**
   - Stop hard-coding excerpts in `relatedProvisions.ts` once
     `PendingCapability.official_citations` is implemented.
   - Prefer `ItemView.citations` / evidence repository text; keep the panel UI
     (`RelatedProvisionsPanel`, `PostConsultPanel`) and only swap the data loader.
   - Keep the frontend filter contract: match by `itemId` / life event; **no hit =
     empty list**; never fall back to another event’s funeral package.
   - Do not let the model invent article numbers; ground on retrieved excerpts.
   - The explain request already sends `references[]` (title / body / sourceUrl).

2. **Application guide**
   - Replace `getApplicationGuide()` fixture with backend action-plan payload
     when `action_plan` leaves the pending list.
   - Keep step → documents → agency shape close to
     `frontend/src/types/postConsult.ts` so the panel can stay thin.
   - Unknown life events must stay empty / `null`, not reuse spouse-death steps.

3. **Copilot (already wired)**
   - Live path: `answer_with_references` task → Bedrock Converse when
     `BEDROCK_MODEL_ID` is set; otherwise offline demo model answer.
   - Frontend: `askCopilot()` posts question + panel references; on
     `explanation_unavailable` falls back to `copilotStub`.
   - Prompt forbids eligibility determination.
   - Force stub only when debugging UI without backend:

```env
# Frontend — post-consult Copilot
# VITE_USE_POST_CONSULT_COPILOT_MOCK=true
```

### Files

- Backend: `backend/app/llm/tasks/answer_with_references.py`,
  `backend/app/api/sessions.py` (`POST /sessions/current/explain`)
- Frontend: `frontend/src/api/explainClient.ts`, `frontend/src/lib/askCopilot.ts`
- Stub fallback: `frontend/src/lib/copilotStub.ts`

---

## Feature: Deployment and Hosting

| Item           | Current (Local)                                                                                         | AWS Target                                        |
| -------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Frontend       | `npm run dev` on `localhost:5173`                                                                       | S3 bucket + CloudFront                            |
| Backend        | `uvicorn` on `localhost:8000`                                                                           | One ECS Fargate task, or Lambda + Mangum          |
| TLS            | none                                                                                                    | CloudFront default `*.cloudfront.net` certificate |
| Files affected | `frontend/vite.config.ts`, `frontend/src/api/client.ts`, `backend/app/main.py`, `backend/app/config.py` | —                                                 |

### AWS App Runner is blocked by a Service Control Policy

Tested on 2026-08-01 with the `WSParticipantRole` credentials rather than read
off the organiser's spreadsheet:

```text
AccessDeniedException: ... not authorized to perform: apprunner:ListServices
... because no service control policy allows the apprunner:ListServices action
```

The organiser's list (`Supported AWS Services List 20260722.xlsx`) is therefore
**enforced by an SCP**, not advisory. An SCP denial cannot be overridden by any
IAM policy, so App Runner is out however convenient it looks.

Do not treat the spreadsheet as authoritative in either direction, though. It
lists IAM _actions_, and `bedrock:Converse` does not appear in it even though
Converse works — because Converse is authorised by `bedrock:InvokeModel` and no
`bedrock:Converse` action exists. **When it matters, make the call and read the
error.** A read-only `list-*` or `describe-*` is enough to tell an SCP denial
from a missing permission.

Verified available with real calls in the competition account (2026-08-01):

| Service                | Call used                      | Result    |
| ---------------------- | ------------------------------ | --------- |
| `ecs`                  | `list-clusters`                | available |
| `ecr`                  | `describe-repositories`        | available |
| `logs`                 | `describe-log-groups`          | available |
| `elasticloadbalancing` | `describe-load-balancers`      | available |
| `dynamodb`             | `list-tables`                  | available |
| `iam`                  | `list-roles`                   | available |
| `s3`                   | bucket created, policy applied | available |
| `cloudfront`           | distribution and OAC created   | available |

A successful `list-*` proves read access, not create access. The S3 and
CloudFront rows are stronger because resources were actually created.

### Target shape: one CloudFront distribution

Serve the static bundle and the API through a single distribution:

- default behaviour → S3 origin (the `frontend/dist` upload)
- `/sessions*` and `/health` → the backend origin

This solves three problems at once rather than one. CloudFront supplies HTTPS on
its default domain, and an HTTPS page cannot call a plain-HTTP backend. The
frontend and API become same-origin, so **CORS configuration is no longer needed
at all**. And `VITE_API_BASE_URL` can stay empty.

### Four things to handle before the first deploy

1. **`VITE_API_BASE_URL` is a build-time value.** `api/client.ts` reads
   `import.meta.env.VITE_API_BASE_URL` and falls back to
   `http://localhost:8000`. Vite inlines it during `npm run build`, so changing
   the variable after deploying does nothing. `vite.config.ts` sets `envDir` to
   the repository root, so the value belongs in the root `.env`, not
   `frontend/.env`.

2. **The routers have no `/api` prefix.** `main.py` mounts the health and
   sessions routers at `/health` and `/sessions`. Either point the CloudFront
   behaviours at those paths or give FastAPI a `root_path`. Do one, not half of
   each.

3. **The SPA needs a fallback.** With client-side routing across
   `ProductHomePage`, `AgenciesPage`, and `TrackedCasesPage`, CloudFront has to
   map 403/404 to `/index.html`, or reloading any non-root URL returns 404.

4. **Leave the AWS credential variables empty.** `config.py` copies
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN` from
   `.env` into `os.environ` for boto3. That is right for Workshop Studio
   credentials on a laptop and wrong in a deployed task: leave them empty and let
   boto3 use the task or execution role. No code change is needed, because boto3
   falls back to the role when the variables are absent. Workshop credentials
   expire, so baking them into an image guarantees a broken demo later.

### Session state constrains the backend choice

`InMemorySessionStore` lives on the FastAPI application instance. One
long-lived process — a single Fargate task, EC2, or Lightsail instance — keeps it
working with no code change. Lambda does not: each execution environment has its
own memory, so sessions would be lost between requests. Choosing Lambda means
doing the work in "Feature: Session Persistence" first.

Suggested order: deploy one Fargate task with no code change, and treat session
persistence as separate work rather than a prerequisite.

### AgentCore is not required

`bedrock-agentcore` is fully available in the supported-services list
(`CreateAgentRuntime`, `CreateAgentRuntimeEndpoint`, `CreateMemory`,
`CreateGateway`), but ADR-0015 removed the agent loop, so AgentCore Runtime has
nothing to host that a plain container does not. Treat it as optional, and only
after a repeatable local end-to-end run exists.

### Environment variables

```env
# Deployment (fill in once the platform is chosen)
# VITE_API_BASE_URL=    # empty when served through one CloudFront distribution
#
# In deployed environments leave AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and
# AWS_SESSION_TOKEN empty and rely on the task or execution role.
```

---

## Notes

- This file must be updated every time a new feature is added that uses a
  local mock in place of an AWS service.
- Do not create separate migration documents elsewhere in the repository.
