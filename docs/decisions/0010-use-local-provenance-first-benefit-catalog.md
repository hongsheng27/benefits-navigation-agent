# ADR-0010: Use a Provenance-First Local Benefit Catalog

- Status: Accepted for local development and first-round ingestion
- Date: 2026-07-26

## Context

The project needs to collect government benefit resources before users ask
questions. Runtime user requests must query reviewed local data instead of
crawling the web and spending LLM tokens for every question.

The owner also needs to see which sources are registered, which connectors are
active, how many documents and candidate programs were found, and which
programs have verified official evidence. End users must be able to open the
official sources supporting each displayed program.

The existing generated SQLite database already contains the local government
OID registry. Production AWS persistence remains undecided.

## Options Considered

1. Crawl and analyze official websites during every user request.
2. Let an LLM search and classify every source page independently.
3. Build a scheduled, provenance-first local benefit catalog.
4. Select and deploy a production AWS database before local ingestion works.

## Decision

Extend the generated local SQLite database with a separate, versioned benefit
catalog schema.

The catalog separates:

- `source_registry`: reviewed source identity, access method, and connection
  status
- `source_sync_runs`: per-source ingestion counts and failures
- `source_documents`: canonical official pages or documents and current hashes
- `document_discoveries`: which registered sources discovered each document
- `benefit_programs`: canonical reviewed resources and navigation fields
- `program_sources`: evidence roles and reviewed excerpts for each program
- `program_organization_roles`: evidence-backed organization roles, with an
  optional government OID

The original OID `sync_runs` table remains OID-import-specific.
Benefit ingestion uses `source_sync_runs`; the histories must not be combined.

Seed metadata may register planned sources, but a source remains `pending`
until a connector or completed import actually works. Initializing the schema
must not claim that benefit data has been collected.

Program candidates may have incomplete classifications. A program cannot be
marked `verified` unless its purpose, program basis, delivery form, and
verification timestamp are present. Evidence and organization roles cannot be
marked `verified` without a supporting official document.

## Consequences

### Positive

- Keep web discovery and runtime user queries separate.
- Allow a future admin UI to report source and ingestion coverage.
- Preserve official citations and evidence excerpts for the user-facing UI.
- Avoid repeating LLM analysis when content hashes are unchanged.
- Link reviewed organization roles to the existing OID registry without
  treating a data publisher as the program owner.
- Keep the local schema reproducible and testable without AWS credentials.

### Negative

- Add schema and review workflow that ingestion connectors must follow.
- Require explicit migrations as catalog fields evolve.
- Keep SQLite unsuitable for shared concurrent production writes.
- Do not provide a crawler, API connector, review UI, or user-facing endpoint
  in this decision.

## Deployment Boundary

This decision does not select DynamoDB, RDS, S3 layout, a vector database, or a
deployment service. A future production adapter must preserve source IDs,
document provenance, review states, program evidence, and OID role boundaries.

The catalog must not store user sessions, direct identifiers, credentials, or
private user data.
