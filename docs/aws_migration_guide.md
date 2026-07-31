# AWS Migration Guide

This is the **single source of truth** for transitioning from local mock
implementations to live AWS services on August 1st.

> **Status**: All features currently run on local mocks (SQLite, local files,
> `FakeLanguageModel`). The LLM layer will use Gemini over plain HTTP as an
> interim real-model path until Bedrock account access is confirmed; see
> [ADR-0015](decisions/0015-narrow-llm-port-instead-of-agent-loop.md).

## How to Use This Guide

On August 1st, teammates should:

1. Set up AWS credentials and fill in `.env` variables listed below.
2. Follow each section to swap local mocks for live services.
3. Test each feature after switching.

---

## Environment Variables Needed on August 1st

Add these to your `.env` file when AWS access is available:

```env
# AWS General
AWS_REGION=ap-northeast-1
AWS_ACCOUNT_ID=

# S3 (document storage)
# S3_BUCKET_NAME=

# Database (if migrating from SQLite)
# DATABASE_URL=

# Bedrock (LLM)
# BEDROCK_MODEL_ID=

# Gemini (interim LLM before Bedrock access is confirmed).
# Not an AWS variable, listed here so the LLM setup lives in one place.
# Leave empty and the backend falls back to the offline FakeLanguageModel
# instead of failing to start.
# GEMINI_API_KEY=
# GEMINI_MODEL_ID=

# AgentCore (if used)
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

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| LLM | `FakeLanguageModel` (offline, fixed answers) | Amazon Bedrock Converse API |
| Interim | Gemini over plain HTTP (team's own key) | — |
| Files affected | `backend/app/llm/port.py`, `backend/app/llm/fake.py`, `backend/app/llm/gemini.py` | add `backend/app/llm/bedrock.py` |

**There is no `AgentRunner`.** ADR-0015 replaced it with a narrow port that has
no tool loop, because both model tasks are single request/response and giving a
model tool access would open a path for it to influence eligibility.
An earlier version of this section referred to an `AgentRunner` in
`backend/app/orchestration/`; that interface was never built and will not be.

### What the swap has to preserve

`LanguageModelPort` is the contract. It has one method:

```python
def generate_structured(self, request: LlmRequest) -> LlmResult: ...
```

A Bedrock-backed replacement must keep the same signature and the same failure
modes, so nothing above it changes:

| Behaviour | Must not change |
|-----------|-----------------|
| Failure type | `LanguageModelUnavailableError` for transport, auth, timeout, or missing credentials; `LanguageModelOutputError` when the reply is not a parseable JSON object |
| Error content | Messages must never contain `user_content` or the model's raw reply. Those reach logs and error responses, which ADR-0007 forbids |
| Return value | `LlmResult.payload` only, never the raw text |
| Schema check | Call `validate_portable_schema()` before sending |
| Sync | Stay synchronous. The endpoints and `state_machine.advance()` are sync; an async port would force the whole chain to change |

### Migration Steps

1. Add `boto3` to `backend/pyproject.toml` dependencies (currently not
   installed).
2. Create `backend/app/llm/bedrock.py` with a `BedrockLanguageModel` class
   implementing `LanguageModelPort`. **Do not modify `port.py`.**
3. Map `LlmRequest` onto the Converse API request:

   | `LlmRequest` field | Converse API location |
   |--------------------|-----------------------|
   | `instruction`, `user_content` | `messages[].content[].text` (separate text blocks) |
   | `output_schema` | `outputConfig.textFormat.structure.jsonSchema.schema` — **must be `json.dumps()`-ed into a string**, unlike Gemini which takes an object |
   | `schema_name` | `outputConfig.textFormat.structure.jsonSchema.name` |
   | `max_output_tokens`, `temperature` | `inferenceConfig` |

4. Map the vendor stop reason onto `FinishReason`. Unknown values go to
   `OTHER` — do not guess a meaning.
5. Set `BEDROCK_MODEL_ID` and `AWS_REGION` in `.env`.
6. Switch the injected default. The call sites pass the port as a named
   parameter, so this is a one-line change at composition time, not a change to
   the state machine.
7. Keep `FakeLanguageModel` as the default for tests. Tests must not require
   network access or credentials after the migration.

### Do not remove the Gemini adapter on migration day

Keep `gemini.py` until Bedrock is confirmed working end to end. It is the only
proven real-model path, and losing it would leave no fallback if the account,
model access, or region turns out to be a problem mid-demo.

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

Sending user text to Gemini is an egress change recorded in ADR-0015. Moving to
Bedrock changes who receives the text, not whether it is sent. The three
structural rules stay the same either way: model-returned attributes go through
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

## Notes

- This file must be updated every time a new feature is added that uses a
  local mock in place of an AWS service.
- Do not create separate migration documents elsewhere in the repository.
