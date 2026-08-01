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

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Database | `data/local/government_oid.db` (SQLite) | TBD (DynamoDB or RDS) |
| Files affected | `scripts/import_government_oid.py`, `backend/app/services/benefit_catalog.py` | — |

### Migration Steps

1. TBD — database choice not yet decided.
2. The SQLite schema in `benefit_catalog.py` defines the contract. Any AWS
   adapter must preserve the same table relationships and constraints.

---

## Feature: Source Document Storage (HTML files)

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Storage | `data/local/source_documents/` (local folder) | S3 bucket |
| Files affected | `backend/app/services/source_connector.py` (`_write_raw_page`) | — |

### Migration Steps

1. Create an S3 bucket for raw HTML documents.
2. Replace `_write_raw_page()` file write with S3 `put_object`.
3. Update `storage_ref` in `source_documents` table to use `s3://` URIs.
4. Set `S3_BUCKET_NAME` in `.env`.

---

## Feature: LLM / Bedrock Integration

| Item | Current | AWS Target |
|------|---------|------------|
| LLM | Bedrock when `BEDROCK_MODEL_ID` is set; otherwise offline demo | Amazon Bedrock `Converse` + forced tool choice |
| Files | `backend/app/llm/bedrock.py`, `factory.py`, `config.py` | already added |
| Verified runtime | `us-west-2`, Claude Haiku 4.5 inference profile | `Converse` returned the registered `spouse_death` event ID |

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

| Behaviour | Must not change |
|-----------|-----------------|
| Failure type | `LanguageModelUnavailableError` for transport, auth, timeout, or missing credentials; `LanguageModelOutputError` when the reply is not a parseable JSON object |
| Error content | Messages must never contain `user_content` or the model's raw reply |
| Return value | `LlmResult.payload` only, never the raw text |
| Schema check | Call `validate_portable_schema()` before sending |
| Sync | Stay synchronous |

### How to turn Bedrock on today

1. Log into the competition AWS account and set region to `us-west-2`.
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

### Request shape (Converse)

| `LlmRequest` field | Converse location |
|--------------------|-------------------|
| `instruction` | `system[0].text` |
| `user_content` | `messages[0].content[0].text` (marked as data, not instructions) |
| `output_schema` | `toolConfig.tools[0].toolSpec.inputSchema.json` |
| `schema_name` | `toolSpec.name` + `toolChoice.tool.name` |
| `max_output_tokens`, `temperature` | `inferenceConfig.maxTokens`, `inferenceConfig.temperature` |

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

---

## Feature: Session Persistence

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Sessions | In-process memory, two hour expiry | TBD (DynamoDB or AgentCore Memory) |
| Files affected | `backend/app/orchestration/session_store.py`, `backend/app/main.py` | — |

The local mock is `InMemorySessionStore`: a dictionary held on the FastAPI
application instance. A restart discards every session, which ADR-0005 accepts
because the persistence choice is still open.

### What the swap has to preserve

`InMemorySessionStore` is the contract. Any AWS-backed replacement must keep the
same five methods and the same failure modes, so nothing above it changes:

| Method | Behaviour that must not change |
|--------|-------------------------------|
| `create()` | Return a new `SessionState` with a `secrets`-generated id and `expires_at` set two hours ahead |
| `get(session_id)` | Raise `SessionNotFoundError` for unknown ids and `SessionExpiredError` past the TTL, deleting the expired record |
| `save(state)` | Replace the stored state, stamp `updated_at`, and **not** extend `expires_at` |
| `delete(session_id)` | Succeed even when the session is already gone |
| `purge_expired()` | Remove expired records and return how many |

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

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Interfaces | `backend/app/orchestration/protocols.py` | unchanged — this is the contract |
| Exchange shapes | `backend/app/orchestration/data_contracts.py` | unchanged — this is the contract |
| Entitlement graph | `FixtureEntitlementGraphRepository` (hardcoded table) | SQLite repository, then TBD cloud database |
| Eligibility | `FixtureEligibilityService` (decisions passed in) | SQLite rule tables plus the deterministic rule engine |
| Evidence | `FixtureEvidenceRepository` (empty by default) | SQLite `source_documents` / `program_sources` |
| Source refresh | `LocalSourceRefreshService` (in-process list) | TBD queue (SQS or EventBridge) |

### What the swap has to preserve

The four `Protocol` classes in `protocols.py` are the contract. Any SQLite or
cloud adapter must keep the same method names and the same return types:

| Interface | Methods that must not change |
|-----------|------------------------------|
| `EntitlementGraphRepository` | `expand_from_event`, `get_prerequisites`, `get_produces`, `get_programs_by_system` |
| `EligibilityService` | `get_required_fields`, `evaluate`, `evaluate_many` |
| `EvidenceRepository` | `get_citations` |
| `SourceRefreshService` | `get_coverage_status`, `request_on_demand_refresh` |

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
   Every seam is already a named parameter, so no other file changes.
2. Add the SQLite adapters in the data layer, mapping `program_id` to `item_id`
   and decoding stored JSON into the `data_contracts` dataclasses.
3. Only after the database choice is settled, add a cloud adapter behind the
   same interfaces.
4. Keep the fixture implementations. They are what the workflow tests use.

### Feature: On-Demand Source Refresh Queue

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Queue | `LocalSourceRefreshService._queue`, a Python list | TBD (SQS, EventBridge Scheduler, or Step Functions) |
| Flow | `backend/app/orchestration/source_refresh.py` | unchanged |
| Dedup | in-memory set keyed by `source_id + event_id + date` | must move to shared storage |

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

| Concern | Local mock now | Target |
|---|---|---|
| Agency directory UI | `frontend/src/mocks/agencies.ts` via `frontend/src/api/agencyClient.ts` | `GET /agencies` backed by SQLite / RDS source registry |
| Case tracking UI | `frontend/src/mocks/trackedCases.ts` via `frontend/src/api/trackingClient.ts` | `GET /cases` (or equivalent) persisted session/case store |

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

## Conversational attribute collection (T21b-style)

| Concern | Local now | Target |
|---|---|---|
| Chat turn API | `attribute_chat_turn` on `POST /sessions/advance` + `collect_attributes` task | Same; Bedrock when `BEDROCK_MODEL_ID` set |
| Jurisdiction filter | `applicant_jurisdiction` + `jurisdiction_items.py` fixtures | Entitlement graph rows with `jurisdiction_code` |
| MCQ fallback | Frontend `AttributeChatPanel` → `QuestionGroupList` | Keep as offline / low-confidence path |

Reuse `BEDROCK_MODEL_ID` / AWS credentials above. No new frontend env required.

---

## Frontend post-consult panels (related law + application guide)

| Concern | Local mock now | Target |
|---|---|---|
| Related provisions UI | `frontend/src/mocks/relatedProvisions.ts` (from `data/benefit_discovery/extracted_candidates.v0.1.json`) | Session / item `citations` with real excerpts via `official_citations` |
| Application guide UI | `frontend/src/mocks/applicationGuides.ts` | Backend `action_plan` (or equivalent) per life event / item |
| Copilot chat | `POST /sessions/current/explain` via `frontend/src/api/explainClient.ts` + stub fallback (`copilotStub.ts`) | Same endpoint; Bedrock when `BEDROCK_MODEL_ID` is set |

### What to change

1. **Related provisions**
   - Stop hard-coding excerpts in `relatedProvisions.ts` once
     `PendingCapability.official_citations` is implemented.
   - Prefer `ItemView.citations` / evidence repository text; keep the panel UI
     (`RelatedProvisionsPanel`, `PostConsultPanel`) and only swap the data loader.
   - Do not let the model invent article numbers; ground on retrieved excerpts.
   - The explain request already sends `references[]` (title / body / sourceUrl).

2. **Application guide**
   - Replace `getApplicationGuide()` fixture with backend action-plan payload
     when `action_plan` leaves the pending list.
   - Keep step → documents → agency shape close to
     `frontend/src/types/postConsult.ts` so the panel can stay thin.

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

## Notes

- This file must be updated every time a new feature is added that uses a
  local mock in place of an AWS service.
- Do not create separate migration documents elsewhere in the repository.
