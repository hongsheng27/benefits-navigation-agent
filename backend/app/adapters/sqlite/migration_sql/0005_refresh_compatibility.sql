CREATE TABLE source_crawl_attempts (
    attempt_id TEXT PRIMARY KEY NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('running', 'completed', 'failed')),
    started_at TEXT NOT NULL CHECK (trim(started_at) != ''),
    completed_at TEXT,
    gap_category TEXT
        CHECK (
            gap_category IS NULL
            OR gap_category IN (
                'robots_policy',
                'login_required',
                'javascript_only',
                'broken_link',
                'scanned_attachment',
                'connection_error'
            )
        ),
    safe_error_code TEXT,
    indexed_document_count INTEGER NOT NULL DEFAULT 0
        CHECK (
            typeof(indexed_document_count) = 'integer'
            AND indexed_document_count >= 0
        ),
    CHECK (
        (
            status = 'running'
            AND completed_at IS NULL
            AND gap_category IS NULL
            AND safe_error_code IS NULL
        )
        OR
        (
            status = 'completed'
            AND completed_at IS NOT NULL
            AND trim(completed_at) != ''
            AND gap_category IS NULL
            AND safe_error_code IS NULL
        )
        OR
        (
            status = 'failed'
            AND completed_at IS NOT NULL
            AND trim(completed_at) != ''
            AND gap_category IS NOT NULL
            AND safe_error_code IS NOT NULL
            AND trim(safe_error_code) != ''
        )
    ),
    FOREIGN KEY (source_id)
        REFERENCES source_registry (source_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX idx_source_crawl_attempts_source_completed
    ON source_crawl_attempts (source_id, completed_at DESC, attempt_id);

CREATE INDEX idx_source_crawl_attempts_status_started
    ON source_crawl_attempts (status, started_at, attempt_id);

CREATE TABLE source_coverage_state (
    source_id TEXT PRIMARY KEY NOT NULL,
    crawl_status TEXT NOT NULL DEFAULT 'pending_crawl'
        CHECK (crawl_status IN ('pending_crawl', 'crawled', 'error')),
    last_successful_crawl_at TEXT,
    indexed_document_count INTEGER NOT NULL DEFAULT 0
        CHECK (
            typeof(indexed_document_count) = 'integer'
            AND indexed_document_count >= 0
        ),
    last_gap_category TEXT
        CHECK (
            last_gap_category IS NULL
            OR last_gap_category IN (
                'robots_policy',
                'login_required',
                'javascript_only',
                'broken_link',
                'scanned_attachment',
                'connection_error'
            )
        ),
    updated_revision_id TEXT,
    updated_at TEXT NOT NULL CHECK (trim(updated_at) != ''),
    CHECK (
        (
            crawl_status = 'pending_crawl'
            AND last_successful_crawl_at IS NULL
            AND indexed_document_count = 0
            AND last_gap_category IS NULL
        )
        OR
        (
            crawl_status = 'crawled'
            AND last_successful_crawl_at IS NOT NULL
            AND trim(last_successful_crawl_at) != ''
            AND last_gap_category IS NULL
        )
        OR
        (
            crawl_status = 'error'
            AND last_gap_category IS NOT NULL
            AND (
                last_successful_crawl_at IS NOT NULL
                OR indexed_document_count = 0
            )
        )
    ),
    FOREIGN KEY (source_id)
        REFERENCES source_registry (source_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (updated_revision_id)
        REFERENCES catalog_revisions (revision_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX idx_source_coverage_state_status_source
    ON source_coverage_state (crawl_status, source_id);

CREATE TABLE coverage_snapshots (
    snapshot_id TEXT PRIMARY KEY NOT NULL,
    observed_at TEXT NOT NULL CHECK (trim(observed_at) != ''),
    scope_source_ids_json TEXT NOT NULL
        CHECK (
            json_valid(scope_source_ids_json) = 1
            AND json_type(scope_source_ids_json) = 'array'
        ),
    scope_domain_tags_json TEXT NOT NULL
        CHECK (
            json_valid(scope_domain_tags_json) = 1
            AND json_type(scope_domain_tags_json) = 'array'
        ),
    scope_hash TEXT NOT NULL
        CHECK (
            length(scope_hash) = 64
            AND scope_hash NOT GLOB '*[^0-9a-f]*'
        ),
    created_revision_id TEXT,
    FOREIGN KEY (created_revision_id)
        REFERENCES catalog_revisions (revision_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX idx_coverage_snapshots_observed
    ON coverage_snapshots (observed_at DESC, snapshot_id);

CREATE INDEX idx_coverage_snapshots_scope_hash
    ON coverage_snapshots (scope_hash, observed_at DESC);

CREATE TABLE coverage_snapshot_sources (
    snapshot_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    crawl_status TEXT NOT NULL
        CHECK (crawl_status IN ('pending_crawl', 'crawled', 'error')),
    last_successful_crawl_at TEXT,
    indexed_document_count INTEGER NOT NULL DEFAULT 0
        CHECK (
            typeof(indexed_document_count) = 'integer'
            AND indexed_document_count >= 0
        ),
    domain_tags_json TEXT NOT NULL
        CHECK (
            json_valid(domain_tags_json) = 1
            AND json_type(domain_tags_json) = 'array'
        ),
    gap_category TEXT
        CHECK (
            gap_category IS NULL
            OR gap_category IN (
                'robots_policy',
                'login_required',
                'javascript_only',
                'broken_link',
                'scanned_attachment',
                'connection_error'
            )
        ),
    PRIMARY KEY (snapshot_id, source_id),
    CHECK (
        (
            crawl_status = 'pending_crawl'
            AND last_successful_crawl_at IS NULL
            AND indexed_document_count = 0
            AND gap_category IS NULL
        )
        OR
        (
            crawl_status = 'crawled'
            AND last_successful_crawl_at IS NOT NULL
            AND trim(last_successful_crawl_at) != ''
            AND gap_category IS NULL
        )
        OR
        (
            crawl_status = 'error'
            AND gap_category IS NOT NULL
            AND (
                last_successful_crawl_at IS NOT NULL
                OR indexed_document_count = 0
            )
        )
    ),
    FOREIGN KEY (snapshot_id)
        REFERENCES coverage_snapshots (snapshot_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (source_id)
        REFERENCES source_registry (source_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX idx_coverage_snapshot_sources_source_snapshot
    ON coverage_snapshot_sources (source_id, snapshot_id);

CREATE TABLE refresh_jobs (
    job_id TEXT NOT NULL CHECK (trim(job_id) != ''),
    source_id TEXT NOT NULL,
    event_id TEXT NOT NULL CHECK (trim(event_id) != ''),
    local_calendar_date TEXT NOT NULL
        CHECK (
            length(local_calendar_date) = 10
            AND date(local_calendar_date) IS NOT NULL
            AND date(local_calendar_date) = local_calendar_date
        ),
    dedup_key TEXT NOT NULL UNIQUE CHECK (trim(dedup_key) != ''),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    requested_at TEXT NOT NULL CHECK (trim(requested_at) != ''),
    started_at TEXT,
    completed_at TEXT,
    safe_error_code TEXT,
    PRIMARY KEY (job_id, source_id),
    UNIQUE (source_id, event_id, local_calendar_date),
    CHECK (
        (
            status = 'queued'
            AND started_at IS NULL
            AND completed_at IS NULL
            AND safe_error_code IS NULL
        )
        OR
        (
            status = 'running'
            AND started_at IS NOT NULL
            AND trim(started_at) != ''
            AND completed_at IS NULL
            AND safe_error_code IS NULL
        )
        OR
        (
            status = 'completed'
            AND started_at IS NOT NULL
            AND trim(started_at) != ''
            AND completed_at IS NOT NULL
            AND trim(completed_at) != ''
            AND safe_error_code IS NULL
        )
        OR
        (
            status = 'failed'
            AND completed_at IS NOT NULL
            AND trim(completed_at) != ''
            AND safe_error_code IS NOT NULL
            AND trim(safe_error_code) != ''
        )
    ),
    FOREIGN KEY (source_id)
        REFERENCES source_registry (source_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX idx_refresh_jobs_status_requested
    ON refresh_jobs (status, requested_at, job_id, source_id);

CREATE INDEX idx_refresh_jobs_event_date
    ON refresh_jobs (event_id, local_calendar_date, source_id);

CREATE TABLE compat_projection_generations (
    generation_id TEXT PRIMARY KEY NOT NULL,
    rule_version_id TEXT NOT NULL,
    program_id TEXT NOT NULL,
    converter_version TEXT NOT NULL CHECK (trim(converter_version) != ''),
    canonical_hash TEXT NOT NULL
        CHECK (
            length(canonical_hash) = 64
            AND canonical_hash NOT GLOB '*[^0-9a-f]*'
        ),
    status TEXT NOT NULL DEFAULT 'building'
        CHECK (status IN ('building', 'validated')),
    row_count INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(row_count) = 'integer' AND row_count >= 0),
    created_at TEXT NOT NULL CHECK (trim(created_at) != ''),
    validated_at TEXT,
    UNIQUE (generation_id, program_id),
    UNIQUE (generation_id, rule_version_id),
    CHECK (
        (status = 'building' AND validated_at IS NULL)
        OR
        (
            status = 'validated'
            AND validated_at IS NOT NULL
            AND trim(validated_at) != ''
        )
    ),
    FOREIGN KEY (rule_version_id)
        REFERENCES rule_versions (rule_version_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX idx_compat_projection_generations_rule_status
    ON compat_projection_generations (
        rule_version_id,
        status,
        created_at,
        generation_id
    );

CREATE TRIGGER trg_compat_projection_generations_program_insert
BEFORE INSERT ON compat_projection_generations
WHEN NOT EXISTS (
    SELECT 1
    FROM rule_versions AS rule_version
    JOIN rule_definitions AS rule_definition
      ON rule_definition.rule_id = rule_version.rule_id
    WHERE rule_version.rule_version_id = NEW.rule_version_id
      AND rule_definition.program_id = NEW.program_id
)
BEGIN
    SELECT RAISE(ABORT, 'projection generation program must own rule version');
END;

CREATE TRIGGER trg_compat_projection_generations_program_update
BEFORE UPDATE OF rule_version_id, program_id ON compat_projection_generations
WHEN NOT EXISTS (
    SELECT 1
    FROM rule_versions AS rule_version
    JOIN rule_definitions AS rule_definition
      ON rule_definition.rule_id = rule_version.rule_id
    WHERE rule_version.rule_version_id = NEW.rule_version_id
      AND rule_definition.program_id = NEW.program_id
)
BEGIN
    SELECT RAISE(ABORT, 'projection generation program must own rule version');
END;

CREATE TRIGGER trg_rule_definitions_projection_owner_update
BEFORE UPDATE OF program_id ON rule_definitions
WHEN NEW.program_id != OLD.program_id
 AND EXISTS (
     SELECT 1
     FROM rule_versions AS rule_version
     JOIN compat_projection_generations AS generation
       ON generation.rule_version_id = rule_version.rule_version_id
     WHERE rule_version.rule_id = OLD.rule_id
 )
BEGIN
    SELECT RAISE(ABORT, 'cannot change program ownership with projection generations');
END;

CREATE TRIGGER trg_rule_versions_projection_owner_update
BEFORE UPDATE OF rule_id ON rule_versions
WHEN NEW.rule_id != OLD.rule_id
 AND EXISTS (
     SELECT 1
     FROM compat_projection_generations AS generation
     WHERE generation.rule_version_id = OLD.rule_version_id
 )
BEGIN
    SELECT RAISE(ABORT, 'cannot change rule ownership with projection generations');
END;

CREATE TABLE compat_projection_rows (
    generation_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL
        CHECK (typeof(ordinal) = 'integer' AND ordinal >= 0),
    program_id TEXT NOT NULL,
    field_name TEXT NOT NULL CHECK (trim(field_name) != ''),
    field_type TEXT NOT NULL
        CHECK (
            field_type IN (
                'text',
                'integer',
                'number',
                'boolean',
                'json',
                'date'
            )
        ),
    field_value TEXT NOT NULL DEFAULT '',
    source_excerpt TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'verified', 'rejected')),
    created_at TEXT NOT NULL CHECK (trim(created_at) != ''),
    updated_at TEXT NOT NULL CHECK (trim(updated_at) != ''),
    PRIMARY KEY (generation_id, ordinal),
    UNIQUE (generation_id, field_name),
    FOREIGN KEY (generation_id, program_id)
        REFERENCES compat_projection_generations (generation_id, program_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX idx_compat_projection_rows_program_field
    ON compat_projection_rows (program_id, field_name, generation_id);

CREATE TABLE compat_projection_active (
    program_id TEXT PRIMARY KEY NOT NULL,
    rule_version_id TEXT NOT NULL UNIQUE,
    generation_id TEXT NOT NULL UNIQUE,
    activated_at TEXT NOT NULL CHECK (trim(activated_at) != ''),
    FOREIGN KEY (generation_id, rule_version_id)
        REFERENCES compat_projection_generations (
            generation_id,
            rule_version_id
        )
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (generation_id, program_id)
        REFERENCES compat_projection_generations (
            generation_id,
            program_id
        )
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TRIGGER trg_compat_projection_active_validated_insert
BEFORE INSERT ON compat_projection_active
WHEN NOT EXISTS (
    SELECT 1
    FROM compat_projection_generations AS generation
    WHERE generation.generation_id = NEW.generation_id
      AND generation.rule_version_id = NEW.rule_version_id
      AND generation.program_id = NEW.program_id
      AND generation.status = 'validated'
      AND generation.row_count = (
          SELECT COUNT(*)
          FROM compat_projection_rows AS projection_row
          WHERE projection_row.generation_id = generation.generation_id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'active projection requires validated complete generation');
END;

CREATE TRIGGER trg_compat_projection_active_validated_update
BEFORE UPDATE OF program_id, rule_version_id, generation_id
ON compat_projection_active
WHEN NOT EXISTS (
    SELECT 1
    FROM compat_projection_generations AS generation
    WHERE generation.generation_id = NEW.generation_id
      AND generation.rule_version_id = NEW.rule_version_id
      AND generation.program_id = NEW.program_id
      AND generation.status = 'validated'
      AND generation.row_count = (
          SELECT COUNT(*)
          FROM compat_projection_rows AS projection_row
          WHERE projection_row.generation_id = generation.generation_id
      )
)
BEGIN
    SELECT RAISE(ABORT, 'active projection requires validated complete generation');
END;

CREATE TRIGGER trg_compat_projection_rows_immutable_insert
BEFORE INSERT ON compat_projection_rows
WHEN EXISTS (
    SELECT 1
    FROM compat_projection_generations AS generation
    WHERE generation.generation_id = NEW.generation_id
      AND generation.status = 'validated'
)
BEGIN
    SELECT RAISE(ABORT, 'validated projection generation is immutable');
END;

CREATE TRIGGER trg_compat_projection_rows_immutable_update
BEFORE UPDATE ON compat_projection_rows
WHEN EXISTS (
    SELECT 1
    FROM compat_projection_generations AS generation
    WHERE generation.generation_id IN (OLD.generation_id, NEW.generation_id)
      AND generation.status = 'validated'
)
BEGIN
    SELECT RAISE(ABORT, 'validated projection generation is immutable');
END;

CREATE TRIGGER trg_compat_projection_rows_immutable_delete
BEFORE DELETE ON compat_projection_rows
WHEN EXISTS (
    SELECT 1
    FROM compat_projection_generations AS generation
    WHERE generation.generation_id = OLD.generation_id
      AND generation.status = 'validated'
)
BEGIN
    SELECT RAISE(ABORT, 'validated projection generation is immutable');
END;

CREATE TRIGGER trg_compat_projection_generations_immutable_update
BEFORE UPDATE ON compat_projection_generations
WHEN OLD.status = 'validated'
   OR EXISTS (
       SELECT 1
       FROM compat_projection_active AS active
       WHERE active.generation_id = OLD.generation_id
   )
BEGIN
    SELECT RAISE(ABORT, 'validated projection generation is immutable');
END;

CREATE TRIGGER trg_compat_projection_generations_immutable_delete
BEFORE DELETE ON compat_projection_generations
WHEN OLD.status = 'validated'
   OR EXISTS (
       SELECT 1
       FROM compat_projection_active AS active
       WHERE active.generation_id = OLD.generation_id
   )
BEGIN
    SELECT RAISE(ABORT, 'validated projection generation is immutable');
END;
