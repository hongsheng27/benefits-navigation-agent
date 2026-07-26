# ADR-0008: Use Generated SQLite for the Local Government OID Registry

- Status: Accepted for local development and demo
- Date: 2026-07-25

## Context

The project needs a queryable registry containing every organization in the
Ministry of Digital Affairs government OID dataset. The registry will later
gain project-owned tags, benefit relationships, and refresh history.

The AWS deployment target and production persistence service remain
undecided. Selecting DynamoDB now would require AWS permissions, key and index
design, infrastructure configuration, and deployment decisions that are
outside this data-ingestion slice.

The official dataset is small enough for a local file database and is primarily
reference data. It can be rebuilt from the official CSV instead of being
treated as irreplaceable application state.

## Options Considered

1. Commit the official CSV or a generated database to Git.
2. Build a generated local SQLite database.
3. Create and populate DynamoDB immediately.
4. Store all records and tags in one JSON file.

## Decision

Build a generated SQLite database at `data/local/government_oid.db` for local
development and the initial demo.

The generated database remains ignored by Git. The repository stores the
importer, schema, tests, source metadata, and rebuild instructions instead of
the generated database.

The schema separates:

- `government_organizations`: official OID fields and active status
- `tags`: project-owned reusable tags
- `organization_tags`: many-to-many organization and tag relationships
- `sync_runs`: source checksums, counts, status, and refresh history
- `schema_metadata`: the local schema version

OID is the stable organization key. Official refreshes update only official
organization fields. They must not overwrite project-owned tags or
relationships. Records missing from a later official snapshot are marked
inactive instead of being deleted.

CSV parsing produces a storage-neutral `AgencyRecord` before the SQLite adapter
writes data. A future DynamoDB adapter should consume the same normalized
record contract and preserve the same ownership boundaries.

## Consequences

### Positive

- Provide a queryable local database without external services or credentials.
- Keep the official-data refresh reproducible and reviewable.
- Preserve tags and relationships across official source refreshes.
- Record import counts and failures for debugging and data review.
- Retain a migration path to an AWS-managed data store.

### Negative

- Require each developer or deployment pipeline to build the local database.
- Do not provide shared concurrent writes across application instances.
- Require a separate AWS storage adapter if the deployed application needs
  shared or mutable organization data.
- Require explicit schema migrations when the version changes.

## Deployment Boundary

This decision does not select the production session database, entitlement
graph store, or AWS deployment target.

For a read-only demo, the generated SQLite file may be packaged with a
container or used as a deployment-time artifact. If the application needs
shared updates or horizontal scaling, migrate the normalized records and
relationships to DynamoDB or another agreed persistent service through a new
ADR.

SQLite must not store user sessions, direct identifiers, credentials, or
private user data.
