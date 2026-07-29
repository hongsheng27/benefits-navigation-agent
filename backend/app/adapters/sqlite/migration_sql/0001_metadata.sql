CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    applied_at TEXT NOT NULL,
    application_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_revisions (
    revision_id TEXT PRIMARY KEY,
    committed_at TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    description_code TEXT NOT NULL
);
