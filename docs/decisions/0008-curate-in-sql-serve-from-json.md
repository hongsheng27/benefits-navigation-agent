# ADR-0008: Curate in SQL, Serve from JSON

- Status: Accepted
- Date: 2026-07-26

## Context

Benefit data is not written by hand. A scraping and review interface produces
candidate records that move through `candidate` → `pending` → `verified`, with
evidence excerpts and source URLs attached. Reviewing that queue needs ad-hoc
queries: how many are pending, which records are missing an exclusion clause,
which county a record belongs to.

At runtime the system needs the opposite properties. The dataset is small
(single digits to low tens of benefits for the MVP), it is read-only, every
record must be reviewable before it can affect an eligibility answer, and the
live demo must survive a network or credential failure on site.

These are two different activities with conflicting requirements, and treating
them as one storage problem forces a bad compromise either way.

## Options Considered

1. Keep everything in Git as JSON, including the curation queue.
2. Keep everything in SQL, and have the runtime query the database.
3. Curate in SQL, export verified records to JSON, and serve only from JSON.

Option 1 makes the review queue unworkable — a JSON file cannot answer "how
many are still pending". Option 2 puts a database on the critical path of the
demo and removes code review from the step that decides eligibility.

## Decision

Adopt option 3.

### 1. SQL is the curation workspace

The scraping output, review status, edits, and verification workflow live in
SQL. This side may be queried freely and is not part of the deployed system.

### 2. Verified records are exported to JSON under `data/`

Only records marked `verified` are exported. The export is what the repository
tracks, so `git log` becomes the audit trail for anything that can influence an
answer, and a change to an eligibility condition arrives as a reviewable diff.

### 3. The runtime reads JSON only, never SQL

The application loads `data/` into memory at startup. It holds no database
connection.

Consequences of this that are deliberate: the demo runs with no network, no
credentials, and no external service; and every record the system serves has
been signed off by a person.

### 4. Rules are declarative data, not code

Eligibility conditions are expressed as JSON with a `rule_id`, a `version`, a
source URL, a `retrieved_at` date, and labelled conditions. The rule engine
executes them; it does not embed specific thresholds.

Changing a threshold is a data edit plus a version bump, reviewable as a diff,
with no code change and no redeploy.

### 5. Retrieval at runtime is in-memory

Exact lookups (by county, purpose, benefit id, provision id) are dictionary and
list operations over the loaded data. Semantic search, used only to map a vague
user description onto a benefit, is a dot product against a preloaded vector
array. At this dataset size neither warrants an index or a vector database.

## Consequences

### Positive

- Curation keeps the query power it needs without putting a database in the
  serving path.
- Everything that can change an eligibility answer passes through code review.
- The demo is unaffected by network, credential, or service failures.
- Rule changes are diffs with a version and a source, which is what makes the
  "citable and auditable" product claim true rather than aspirational.

### Negative

- The export step is a manual gate; a verified record does not reach the
  runtime until someone runs it.
- Two representations of the same record exist, so the export must be the only
  way data crosses over.
- Reloading data requires restarting the process.

## Non-decisions

This ADR does not decide:

- The SQL engine or the schema of the curation workspace
- Whether the export runs as a script, a CI step, or by hand
- Whether the eventual production system keeps this split

## Reference

- [ADR-0005: Split Client and Server Session State](0005-split-client-server-session-state.md)
- [ADR-0007: Limit Data Retention and Egress](0007-limit-data-retention-and-egress.md)
- [Data model and file formats](../data-model.md)
