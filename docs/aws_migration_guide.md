# AWS Migration Guide

這份文件是 local mock 與 live AWS adapter 之間的**單一遷移資訊來源**。

> **Status**: PostgreSQL adapters 已實作；本機預設使用 SQLite，部署時可用
> `DATA_STORE_BACKEND=postgresql` 切換。LLM 在設定 `BEDROCK_MODEL_ID` 時使用
> Amazon Bedrock `Converse`，否則使用離線示範。Bedrock 已於 2026-08-01 在
> `us-west-2` 驗證，見 [ADR-0016](decisions/0016-use-bedrock-only-live-llm-provider.md)。

## How to Use This Guide

When an AWS-backed path is approved and enabled, teammates should:

1. Configure credentials outside Git and fill only the required `.env` variables.
2. Follow the relevant section to swap or add adapters behind existing boundaries.
3. Test both the AWS-backed path and the retained local path.

---

## Environment Variables for Approved AWS Paths

Add only the variables required by an owner-approved integration to your local `.env`; never commit populated values:

```env
# AWS General — the verified Bedrock path uses us-west-2
AWS_REGION=us-west-2
AWS_ACCOUNT_ID=

# Data store backend selector (sqlite for local, postgresql for RDS)
DATA_STORE_BACKEND=postgresql

# RDS PostgreSQL (ACTIVE — adapters implemented)
RDS_HOST=
RDS_PORT=5432
RDS_DATABASE=
RDS_USERNAME=
RDS_PASSWORD=
RDS_SSLMODE=require

# S3 (approved document/attachment target; fill only when adapter exists)
S3_BUCKET_NAME=
S3_ATTACHMENT_PREFIX=attachments/
ATTACHMENT_STORAGE_BACKEND=local

# Bedrock (only live LLM provider). Leave empty for the offline demo.
# Verified inference profile in the competition account:
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0

# AgentCore (if used) — not required; this project has no agent loop.
# AGENTCORE_AGENT_ID=
```

---

## Feature: Data-layer Rule Engine

The accepted local architecture is SQLite behind four storage-neutral ports.
ADR-0017 selects Amazon RDS for PostgreSQL as the Hackathon shared relational
store and Amazon S3 as the document/attachment object store. This section
records the exact future swap boundary; it does not enable AWS now, and the
SQLite/local-file path remains mandatory for development and tests.

| Concern | Current local default | Local modules used or planned |
|------|--------------------------|-------------------------------|
| Canonical data | `data/local/government_oid.db` SQLite last committed state | Used: `backend/app/services/benefit_catalog.py`; active: `backend/app/adapters/sqlite/` and `backend/app/adapters/postgresql/` |
| Eligibility | Local deterministic engine over canonical Rule DSL | Used: `backend/app/rules/engine.py`; active: `backend/app/application/eligibility_service.py`, `backend/app/rules/dsl.py`, `backend/app/rules/evaluator.py` |
| Evidence/files | SQLite metadata plus `data/local/source_documents/` | Used: `backend/app/services/source_connector.py`; active: `backend/app/adapters/sqlite/evidence_repository.py`, `backend/app/adapters/postgresql/evidence_repository.py` |
| Refresh | Local committed-data-first enqueue and local worker | Active: `backend/app/adapters/sqlite/source_refresh_service.py`, `backend/app/adapters/postgresql/source_refresh_service.py` |
| Candidate extraction | Local parser and local/mock LLM only | Planned: `backend/app/curation/candidate_extractor.py`; crawler/LLM outputs remain unverified |
| Wiring | FastAPI application composition root | Active: `backend/app/application/composition.py` — switches between SQLite and PostgreSQL based on `DATA_STORE_BACKEND` |

### Future adapter swap points

PostgreSQL adapters are now implemented. The cutover procedure:

1. **Schema**: Run `scripts/migrate_sqlite_to_postgresql.py` — it creates
   all tables and copies data from SQLite to RDS in FK dependency order.
2. **Adapters**: Set `DATA_STORE_BACKEND=postgresql` in `.env` and provide
   `RDS_HOST`, `RDS_PASSWORD`, etc. The composition root automatically
   switches to `PgEntitlementGraphRepository`, `PgRuleRepository`,
   `PgEvidenceRepository`, and `PgSourceRefreshService`.
3. **Verify**: Start the FastAPI app and hit `/health` to confirm RDS
   connectivity. Run the integration test suite against the PostgreSQL
   backend.
4. **Rollback**: Set `DATA_STORE_BACKEND=sqlite` to revert to local SQLite.

### Feature: Case 2 database-backed consultation

The local vertical slice is implemented by
`backend/app/adapters/sqlite/migration_sql/0008_case2_database_seed.sql`.
It adds the seven Case 2 candidate programs, canonical event graph conditions,
database display names/summaries, and candidate official excerpts. It does not
create approved rules or verified citations.

The runtime paths are:

- `backend/app/adapters/sqlite/graph_repository.py` and
  `backend/app/adapters/postgresql/graph_repository.py` for candidates and
  deterministic relevance filtering.
- `backend/app/adapters/sqlite/evidence_repository.py` and
  `backend/app/adapters/postgresql/evidence_repository.py` for two distinct
  evidence paths: display-only candidates and verified eligibility evidence.
- `frontend/src/components/alt/RelatedProvisionsPanel.tsx` consumes backend
  citations in live mode. The old frontend fixture remains enabled only in
  demo mode, so there is no live mock code to remove at RDS cutover.

When RDS access becomes available:

1. Confirm a network path to the private RDS endpoint (team VPN, approved
   bastion/SSH tunnel, or an app host inside the VPC). `RDS_HOST` and database
   credentials alone cannot cross a private VPC boundary.
2. Fill the untracked `.env` variables shown below. Do not put their values in
   this guide, chat screenshots, commits, or shell history shared with others.
3. Before copying the SQLite seed, inspect the existing RDS rows. The teammate
   ingestion uses legacy event IDs, so the PostgreSQL graph adapter translates
   `occupational_injury -> work_injury` and
   `long_term_care_need -> long_term_care` only when canonical nodes are absent.
4. Verify that RDS has graph edges from those event nodes to benefit-program
   nodes, and that `program_evidence_links`, `evidence_excerpts`, and
   `source_documents` join to the returned program IDs. Existing program UUIDs
   are supported because the API now returns database `displayName` and
   `summary` instead of requiring frontend ID mappings.
5. Set `DATA_STORE_BACKEND=postgresql`, restart FastAPI, then run the Case 2
   flow. A successful candidate-data run still returns
   `needs_human_review`; it must not return `eligible` until rules and evidence
   have human-approved status.
6. If RDS lacks Case 2 graph/evidence rows, port migration 0008 as a separate,
   reviewed PostgreSQL seed. Do not mark imported rows verified and do not
   overwrite teammate-owned rows merely to match local IDs.
7. Roll back by setting `DATA_STORE_BACKEND=sqlite` and restarting FastAPI.

Required `.env` names for this feature:

```env
DATA_STORE_BACKEND=postgresql
RDS_HOST=
RDS_PORT=5432
RDS_DATABASE=
RDS_USERNAME=
RDS_PASSWORD=
RDS_SSLMODE=require
```

Implemented PostgreSQL adapters:
- `backend/app/adapters/postgresql/graph_repository.py` — `PgEntitlementGraphRepository`
- `backend/app/adapters/postgresql/rule_repository.py` — `PgRuleRepository`
- `backend/app/adapters/postgresql/evidence_repository.py` — `PgEvidenceRepository`
- `backend/app/adapters/postgresql/source_refresh_service.py` — `PgSourceRefreshService`
- `backend/app/adapters/postgresql/connection.py` — Connection pool management

### Environment variables for the approved RDS/S3 targets

These exact names are reserved in `.env.example`. The composition root consumes
the database selector and RDS variables now. Keep selectors on `sqlite`/`local`
until the corresponding database and object-storage cutover checks pass:

```env
AWS_REGION=
DATA_STORE_BACKEND=sqlite
RDS_HOST=
RDS_PORT=5432
RDS_DATABASE=
RDS_USERNAME=
RDS_PASSWORD=
RDS_SSLMODE=require
ATTACHMENT_STORAGE_BACKEND=local
S3_BUCKET_NAME=
S3_ATTACHMENT_PREFIX=attachments/
```

Use the AWS credential provider chain or an assigned IAM role; do not add
`AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` values to tracked files. On
cutover, change `DATA_STORE_BACKEND=postgresql` and
`ATTACHMENT_STORAGE_BACKEND=s3` only after database/object validation succeeds.

### Coverage, refresh, and legacy-rule migration boundary

SQLite migrations `0005_refresh_compatibility` and
`0006_preserve_legacy_rules` add local coverage snapshots, per-source refresh
jobs, compatibility generations, SHA-256 legacy inventories, under-review
conversion manifests, and the read-only legacy bridge. They do not enable a
queue, network crawler, AWS SDK, or PostgreSQL connection.

For the approved RDS PostgreSQL target:

1. Translate these tables with `TIMESTAMPTZ`, `JSONB`, explicit numeric types,
   equivalent FKs/checks, and a transaction-safe unique constraint on
   `(source_id, event_id, local_calendar_date)`.
2. Recreate the `program_rule_fields` bridge with PostgreSQL view permissions
   that reject DML. Preserve `legacy_program_rule_fields_v1` and both SHA-256
   fingerprints until the separately approved compatibility cutover.
3. Replace only the future SQLite refresh repository in
   `backend/app/adapters/sqlite/source_refresh_service.py` with a PostgreSQL
   implementation behind `SourceRefreshService`; do not put SQL or AWS types in
   Workflow. The current in-memory implementation remains the default until
   that repository task is complete.
4. Keep queue publishing separate from relational dedup. No queue service has
   been selected, so do not add an AWS SDK publisher or queue environment
   variable in this batch.
5. Use the existing `DATA_STORE_BACKEND`, `RDS_HOST`, `RDS_PORT`,
   `RDS_DATABASE`, `RDS_USERNAME`, `RDS_PASSWORD`, and `RDS_SSLMODE` variables.
   No additional AWS variables are required by migrations 0005/0006.

---

## Feature: Source Documents and Attachments

| Item | Current (Local) | Approved AWS Target |
|------|----------------|---------------------|
| Object storage | `data/local/source_documents/` and future local attachment files | Amazon S3 |
| Relational metadata | SQLite `source_documents` and `document_attachments` | Amazon RDS for PostgreSQL |
| Local code to replace behind an adapter | `backend/app/services/source_connector.py` (`_write_raw_page`); future `backend/app/curation/attachments.py` local writer | S3 object adapter using AWS SDK `put_object` / `get_object` |

### Migration Steps

1. Keep `_write_raw_page()` and future local attachment writes active until the
   S3 adapter and rollback path pass tests; do not add a live S3 call to the
   default local profile.
2. Add the AWS SDK calls inside the object-storage adapter, not the workflow,
   crawler, rule engine, or repository contracts. At cutover, disable the local
   writer only in the `s3` profile rather than deleting the local test path.
3. Store opaque S3 object keys in `storage_ref`, not absolute paths,
   presigned URLs, bucket names, or `s3://` URIs. Attachment rows set
   `storage_backend='s3'`; source-document rows have no per-row backend and are
   resolved by the globally selected object adapter.
4. Source documents must switch as one validated batch: upload every object,
   compare each content hash, update all references transactionally, and only
   then change the object-adapter selector. Do not run a mixed local/S3 source-
   document mode. Attachments may migrate per row because their schema records
   `storage_backend`; preserve missing, extraction-failed, and scanned-document
   gaps instead of marking them extracted or verified.
5. Set `AWS_REGION`, `S3_BUCKET_NAME`, `S3_ATTACHMENT_PREFIX`, and
   `ATTACHMENT_STORAGE_BACKEND=s3` in the untracked `.env` only after document
   batch validation, attachment validation, IAM policy, and rollback checks are
   ready.

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

These are the seams the workflow uses to reach the data layer. Every interface keeps an offline implementation so the workflow test suite runs without SQLite or live AWS.

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Interfaces | `backend/app/orchestration/protocols.py` | unchanged — this is the contract |
| Exchange shapes | `backend/app/orchestration/data_contracts.py` | unchanged — this is the contract |
| Entitlement graph | `FixtureEntitlementGraphRepository` (hardcoded table) | SQLite repository, then RDS PostgreSQL repository |
| Eligibility | `FixtureEligibilityService` (decisions passed in) | SQLite rule tables plus deterministic engine, then RDS PostgreSQL adapter |
| Evidence | `FixtureEvidenceRepository` (empty by default) | SQLite metadata/local objects, then RDS PostgreSQL metadata plus S3 objects |
| Source refresh | `LocalSourceRefreshService` (in-process list) | TBD queue (SQS or EventBridge) |

### Case 2 occupational-injury fixture

`FixtureEntitlementGraphRepository` currently contains the seven Case 2
candidate directions and deterministic relevance predicates. The seven
question fields live in `data/eligibility_fields/fields.v0.1.json`. This is a
backend-driven local vertical slice, but it is still mock policy data: retained
items remain `candidate` and the workflow reports `needs_human_review`.

Now that the SQLite runtime adapters are available:

1. Keep the Case 2 tuple and `_care_item_is_relevant` predicates in
   `backend/app/orchestration/protocols.py` only for explicitly injected tests;
   production startup now injects database repositories from the composition root.
2. As the next data task, insert equivalent `occupational_injury` graph nodes, program nodes, field
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

The Protocol classes in `protocols.py` are the integration baseline. Contract changes require owner alignment and coordinated updates to implementations, consumers, tests, and this guide:

| Interface | Required operations |
|-----------|---------------------|
| `EntitlementGraphRepository` | `expand_from_event`, `get_prerequisites`, `get_produces`, `get_programs_by_system` |
| `EligibilityService` | `get_required_fields`, `evaluate`, `evaluate_many` |
| `EvidenceRepository` | `get_citations`, plus source-reference citation lookup approved by the data-layer alignment |
| `SourceRefreshService` | `get_coverage_status(CoverageScope) -> CoverageSnapshot`；`request_on_demand_refresh(RefreshRequest(event_id, source_ids, requested_at)) -> RefreshReceipt(job_id, accepted, deduplicated)` |

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

1. Keep dependency construction in `backend/app/application/composition.py`;
   routes pass the selected repositories into `state_machine.advance()` without
   changing the external API contract.
2. Keep SQLite as the local default. Its adapters map database rows into the
   frozen `data_contracts` types before returning to workflow code.
3. PostgreSQL implementations and translated migrations now exist behind the
   same interfaces. Switch only after count/hash/reference validation and
   rollback checks pass.
4. Keep fixture implementations for explicit isolated tests. Do not use them as
   an implicit runtime fallback when database content is missing.

### Feature: On-Demand Source Refresh Queue

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Queue | `LocalSourceRefreshService._queue`, a Python list | TBD (SQS, EventBridge Scheduler, or Step Functions) |
| Relational jobs | SQLite `refresh_jobs` through `SqliteSourceRefreshService` | RDS PostgreSQL `refresh_jobs` through the same service contract |
| Flow | `backend/app/orchestration/source_refresh.py` | unchanged |
| Dedup | Current runtime uses an in-memory set; SQLite unique keys are prepared for the future adapter | RDS unique key; queue choice remains separate |

Migration steps:

1. Replace the in-process list in `LocalSourceRefreshService` with a publisher
   behind the same protocol. Keep `CoverageScope` filtering and
   `CoverageSnapshot` arithmetic in the adapter, and keep
   `request_on_demand_refresh` returning immediately: the user's request must
   never wait for a crawl, attachment extraction, or LLM call.
2. Preserve the SQLite and PostgreSQL `refresh_jobs` unique keys when replacing
   the current publisher. The in-memory worker itself only works in one process,
   so shared delivery remains a known limitation until a queue is selected.
3. Keep failures non-blocking. `refresh_after_response` swallows the error,
   logs the exception class only, and returns the coverage that was already
   read. That behaviour is required, not incidental.

### Environment variables

The queue contract-alignment change requires **no additional AWS environment
variables**. The approved RDS PostgreSQL/S3 names are listed earlier and remain
unused by the current local implementation. Queue and shared dedup-store
services remain `TBD-after-ADR`; when selected, add their exact variable names
here and in `.env.example` in the same migration batch rather than inventing
generic placeholders.

### Settled decision: `stale` behaviour

Owner selected Option B. A `stale` program remains visible so the API can show a
warning, but it never runs full deterministic evaluation and always returns
`needs_human_review`. Cloud adapters must preserve this gate; refresh success
must not silently promote stale data or bypass human review. The canonical
runtime constant and behavior live in `backend/app/orchestration/determination.py`.

---

## Feature: Curation Pipeline (Structural Crawl, Attachments, Classification)

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Page fetching | `LocalFixtureFetcher` reads from local fixture files, zero network | Live HTTP fetcher (or AWS Lambda for scheduled crawls) |
| Structural crawl | `StructuralCrawler` with fixture fetcher | Same crawler logic with live fetcher; consider AWS Step Functions for orchestration |
| Attachment storage | `AttachmentService` with `LocalExtractionHandler`, metadata only | S3 for binary storage, Textract or custom Lambda for extraction |
| Classification | `LocalKeywordClassifier` (heuristic keywords, zero LLM) | Amazon Bedrock classifier (LLM-based) |
| Candidate extraction | `CandidateExtractor` with local classifier | Same extractor with Bedrock classifier |
| Review transitions | `ReviewService` with in-memory persistence | RDS PostgreSQL persistence behind `ReviewPersistence` protocol |
| Pipeline orchestration | `CurationPipeline` with all local components | Same pipeline with live components injected |

### Local code to remove or disable at cutover

| Local module | What to replace | AWS insertion point |
|-------------|-----------------|---------------------|
| `backend/app/curation/fetchers.py` → `LocalFixtureFetcher` | Swap to a live HTTP fetcher behind `FetcherPort` | New `LiveHttpFetcher` class implementing `FetcherPort` |
| `backend/app/curation/attachments.py` → `LocalExtractionHandler` | Swap to Textract/Lambda handler behind `ExtractionHandler` | New handler implementing `ExtractionHandler` protocol |
| `backend/app/curation/classifier.py` → `LocalKeywordClassifier` | Swap to Bedrock classifier behind `ClassifierPort` | New `BedrockClassifier` implementing `ClassifierPort` |
| `backend/app/curation/pipeline.py` → constructor defaults | Change default component construction in composition root | `backend/app/application/composition.py` |

### Key invariants that must survive the swap

- Discovered pages and machine outputs stay `candidate` or `under_review` — never `verified`
- Protected transitions (→ verified) require `human_reviewer` actor type with complete artifacts
- `FORBIDDEN_ACTORS` (crawler, llm, importer, converter, exporter, migration) are blocked from verified
- Pipeline stage failures do not corrupt prior committed state
- Gaps (robots, login, JS-only, broken links, failed extractions) are preserved honestly

### Environment variables (TBD-after-ADR)

No curation-specific AWS environment variables are consumed yet. When live
network, Bedrock, or Textract is approved, add exact variable names here:

```env
# Curation pipeline (TBD-after-ADR)
# CURATION_FETCHER_BACKEND=local
# CURATION_CLASSIFIER_BACKEND=local
# CURATION_EXTRACTION_BACKEND=local
# BEDROCK_CLASSIFIER_MODEL_ID=
# TEXTRACT_ENDPOINT=
```

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
