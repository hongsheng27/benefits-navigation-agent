# AWS Migration Guide

這份文件是 local mock 與 live AWS adapter 之間的**單一遷移資訊來源**。

> **Status**: PostgreSQL adapters 已實作。本機開發繼續使用 SQLite (`DATA_STORE_BACKEND=sqlite`)；部署到 AWS 時切換為 `DATA_STORE_BACKEND=postgresql`。RDS endpoint: `database-1.c54m4aak2pcn.us-west-2.rds.amazonaws.com`。

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
AWS_REGION=us-west-2

# Data store backend selector
DATA_STORE_BACKEND=postgresql

# RDS PostgreSQL (ACTIVE — adapters implemented)
RDS_HOST=database-1.c54m4aak2pcn.us-west-2.rds.amazonaws.com
RDS_PORT=5432
RDS_DATABASE=benefits_navigation
RDS_USERNAME=benefits_admin
RDS_PASSWORD=<your-password-here>
RDS_SSLMODE=require

# S3 (approved document/attachment target; fill only when adapter exists)
S3_BUCKET_NAME=
S3_ATTACHMENT_PREFIX=attachments/
ATTACHMENT_STORAGE_BACKEND=local
```

---

## Feature: Data-layer Rule Engine

The accepted local architecture is SQLite behind four storage-neutral ports.
ADR-0014 selects Amazon RDS for PostgreSQL as the Hackathon shared relational
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

Implemented PostgreSQL adapters:
- `backend/app/adapters/postgresql/graph_repository.py` — `PgEntitlementGraphRepository`
- `backend/app/adapters/postgresql/rule_repository.py` — `PgRuleRepository`
- `backend/app/adapters/postgresql/evidence_repository.py` — `PgEvidenceRepository`
- `backend/app/adapters/postgresql/source_refresh_service.py` — `PgSourceRefreshService`
- `backend/app/adapters/postgresql/connection.py` — Connection pool management

### Environment variables for the approved RDS/S3 targets

These exact names are reserved in `.env.example`. The current code does not
consume them; keep selectors on `sqlite`/`local` until the corresponding adapter
and cutover checks exist:

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
| Entitlement graph | `FixtureEntitlementGraphRepository` (hardcoded table) | SQLite repository, then RDS PostgreSQL repository |
| Eligibility | `FixtureEligibilityService` (decisions passed in) | SQLite rule tables plus deterministic engine, then RDS PostgreSQL adapter |
| Evidence | `FixtureEvidenceRepository` (empty by default) | SQLite metadata/local objects, then RDS PostgreSQL metadata plus S3 objects |
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
3. Add PostgreSQL implementations and translated migrations behind the same
   interfaces as described in **Feature: Data-layer Rule Engine**. Switch from
   SQLite only after count/hash/reference validation and rollback checks pass;
   RDS PostgreSQL is selected, but its adapter is not implemented yet.
4. Keep the fixture implementations. They are what the workflow tests use.

### Feature: On-Demand Source Refresh Queue

| Item | Current (Local) | AWS Target |
|------|----------------|------------|
| Queue | `LocalSourceRefreshService._queue`, a Python list | TBD (SQS, EventBridge Scheduler, or Step Functions) |
| Relational jobs | SQLite `refresh_jobs` schema exists but its repository is not wired yet | RDS PostgreSQL `refresh_jobs` through the same service contract |
| Flow | `backend/app/orchestration/source_refresh.py` | unchanged |
| Dedup | Current runtime uses an in-memory set; SQLite unique keys are prepared for the future adapter | RDS unique key; queue choice remains separate |

Migration steps:

1. Replace the in-process list in `LocalSourceRefreshService` with a publisher
   behind the same protocol. Keep `CoverageScope` filtering and
   `CoverageSnapshot` arithmetic in the adapter, and keep
   `request_on_demand_refresh` returning immediately: the user's request must
   never wait for a crawl, attachment extraction, or LLM call.
2. First wire the local SQLite adapter to the prepared `refresh_jobs` unique key;
   at RDS cutover, translate the same constraint to PostgreSQL. The current
   in-memory set only works in a single process, so it remains a known runtime
   limitation until the adapter task is complete.
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

## Notes

- This file must be updated every time a new feature is added that uses a
  local mock in place of an AWS service.
- Do not create separate migration documents elsewhere in the repository.
