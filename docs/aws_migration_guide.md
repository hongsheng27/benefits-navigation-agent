# AWS Migration Guide

This is the **single source of truth** for transitioning from local mock
implementations to live AWS services on August 1st.

> **Status**: All features currently run on local mocks (SQLite, local files).
> No AWS connections are active or required until the hackathon starts.

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
| Sessions | Not yet implemented | TBD (DynamoDB or AgentCore Memory) |

### Migration Steps

1. TBD — session persistence approach not yet decided.

---

## Notes

- This file must be updated every time a new feature is added that uses a
  local mock in place of an AWS service.
- Do not create separate migration documents elsewhere in the repository.
