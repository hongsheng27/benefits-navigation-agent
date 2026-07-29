# AWS Migration Guide

這份文件是 local mock 與 live AWS adapter 之間的**單一遷移資訊來源**。

> **Status**: 目前功能仍以 local mocks（SQLite、本機檔案）運作。依團隊規範可在 owner 核准後使用 live AWS 進行準備與驗證，但不得提交 credentials 或 account-specific secrets，且不得因 AWS integration 破壞 local test path。

## How to Use This Guide

When an AWS-backed path is approved and enabled, teammates should:

1. Configure credentials outside Git and fill only the required `.env` variables.
2. Follow the relevant section to swap or add adapters behind existing boundaries.
3. Test both the AWS-backed path and the retained local path.

---

## Environment Variables for Approved AWS Paths

Add only the variables required by an owner-approved integration to your local `.env`; never commit populated values:

```env
# AWS General
AWS_REGION=ap-northeast-1
AWS_ACCOUNT_ID=

# S3 (document storage)
# S3_BUCKET_NAME=

# Data-layer service-specific variables are intentionally not named yet.
# Define them only after a future service-selection ADR and owner approval.

# Bedrock (LLM)
# BEDROCK_MODEL_ID=

# AgentCore (if used)
# AGENTCORE_AGENT_ID=
```

---

## Feature: Data-layer Rule Engine

The accepted local architecture is SQLite behind four storage-neutral ports.
This section records future swap boundaries only; it does **not** select a
production AWS database, queue, object store, LLM service, or deployment
service, and it does not authorize changing the local path now.

| Concern | Current local default | Local modules used or planned |
|------|--------------------------|-------------------------------|
| Canonical data | `data/local/government_oid.db` SQLite last committed state | Used: `backend/app/services/benefit_catalog.py`; planned: `backend/app/adapters/sqlite/` and migrations |
| Eligibility | Local deterministic engine over canonical Rule DSL | Used: `backend/app/rules/engine.py`; planned: `backend/app/application/eligibility_service.py`, `backend/app/rules/dsl.py`, `backend/app/rules/evaluator.py` |
| Evidence/files | SQLite metadata plus `data/local/source_documents/` | Used: `backend/app/services/source_connector.py`; planned: `backend/app/adapters/sqlite/evidence_repository.py` |
| Refresh | Local committed-data-first enqueue and local worker | Planned: `backend/app/adapters/sqlite/source_refresh_service.py`, `backend/app/curation/local_worker.py` |
| Candidate extraction | Local parser and local/mock LLM only | Planned: `backend/app/curation/candidate_extractor.py`; crawler/LLM outputs remain unverified |
| Wiring | FastAPI application composition root | Planned: `backend/app/application/composition.py`; workflow/state machine receive injected ports |

### Future adapter swap points

A later, separately approved migration may replace only these infrastructure
implementations while preserving the shared contracts:

1. Replace the SQLite implementations of `EntitlementGraphRepository`,
   `EligibilityService`, `EvidenceRepository`, and `SourceRefreshService` with
   implementations for the selected services.
2. Replace local document writes behind the evidence/storage adapter; do not
   change workflow or Rule DSL semantics.
3. Replace the local refresh worker behind `SourceRefreshService`; preserve
   current-data-first responses and same-day deduplication.
4. Replace the local/mock LLM client only behind the candidate-extraction
   boundary; it must still never verify data or decide eligibility.
5. Change construction only in the FastAPI composition root. Workflow and state
   machine must not receive service-specific SDK types, table names, or URLs.

The SQLite adapters, local files, local background job, and local/mock LLM remain the default data-layer path until an owner-approved service-selection ADR and adapter migration replaces a boundary. Enabling an unrelated AWS integration does not implicitly replace these paths.

### Environment variables after a future service decision

Currently required shared baseline name already used by this repository:

```env
AWS_REGION=
```

Service-specific environment variable names are **TBD-after-ADR**. Do not add a
placeholder such as a table, queue, bucket, endpoint, or database URL until an
owner-approved service-selection ADR defines the exact service and exact names.
At that time, update this section and `.env.example` in the same approved batch.

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
| LLM | Not yet implemented | Amazon Bedrock |
| Files affected | TBD (agent runner, orchestration) | — |

### Migration Steps

1. TBD — model selection not yet decided.
2. The `AgentRunner` interface in `backend/app/orchestration/` will wrap
   Bedrock calls. Local development may use stubs or a local model.

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

These are the seams the workflow uses to reach the data layer. Every interface keeps an offline implementation so the workflow test suite runs without SQLite or live AWS.

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Interfaces | `backend/app/orchestration/protocols.py` | unchanged — this is the contract |
| Exchange shapes | `backend/app/orchestration/data_contracts.py` | unchanged — this is the contract |
| Entitlement graph | `FixtureEntitlementGraphRepository` (hardcoded table) | SQLite repository, then TBD cloud database |
| Eligibility | `FixtureEligibilityService` (decisions passed in) | SQLite rule tables plus the deterministic rule engine |
| Evidence | `FixtureEvidenceRepository` (empty by default) | SQLite `source_documents` / `program_sources` |
| Source refresh | `LocalSourceRefreshService` (in-process list) | TBD queue (SQS or EventBridge) |

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

1. Replace the in-process list in `LocalSourceRefreshService` with a publisher
   behind the same protocol. Keep `CoverageScope` filtering and
   `CoverageSnapshot` arithmetic in the adapter, and keep
   `request_on_demand_refresh` returning immediately: the user's request must
   never wait for a crawl, attachment extraction, or LLM call.
2. Move the same-day dedup key to shared storage. The in-memory set only works
   in a single process, so today two workers would trigger the same source
   twice on the same day.
3. Keep failures non-blocking. `refresh_after_response` swallows the error,
   logs the exception class only, and returns the coverage that was already
   read. That behaviour is required, not incidental.

### Environment variables

This contract-alignment change requires **no AWS environment variables**. The
current implementation remains local and uses no AWS SDK or API connection.
Queue, dedup-store, or cloud-database names remain `TBD-after-ADR`; once an
owner-approved service-selection ADR exists, add the exact environment variable
names here and in `.env.example` in that same migration batch rather than
inventing generic placeholders now.

### Settled decision: `stale` behaviour

Owner selected Option B. A `stale` program remains visible so the API can show a
warning, but it never runs full deterministic evaluation and always returns
`needs_human_review`. Cloud adapters must preserve this gate; refresh success
must not silently promote stale data or bypass human review. The canonical
runtime constant and behavior live in `backend/app/orchestration/determination.py`.

---

## Notes

- This file must be updated every time a new feature is added that uses a
  local mock in place of an AWS service.
- Do not create separate migration documents elsewhere in the repository.
