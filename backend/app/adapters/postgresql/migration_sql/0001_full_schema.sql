-- PostgreSQL schema migration: consolidated from SQLite migrations 0001-0007.
-- Translates: TEXT datetimes → TIMESTAMPTZ, INTEGER booleans → BOOLEAN,
-- json_valid/json_type checks → JSONB columns, SQLite triggers → PostgreSQL equivalents.

-- ============================================================
-- 0001: Metadata
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    checksum TEXT NOT NULL CHECK (length(checksum) = 64),
    applied_at TIMESTAMPTZ NOT NULL,
    application_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_revisions (
    revision_id TEXT PRIMARY KEY,
    committed_at TIMESTAMPTZ NOT NULL,
    actor_ref TEXT NOT NULL,
    description_code TEXT NOT NULL
);

-- ============================================================
-- 0002: Programs and Fields
-- ============================================================

CREATE TABLE IF NOT EXISTS benefit_programs (
    program_id TEXT PRIMARY KEY NOT NULL,
    canonical_name TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    support_purpose TEXT,
    program_basis TEXT,
    delivery_form TEXT,
    jurisdiction_code TEXT NOT NULL DEFAULT '',
    program_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (
            program_status IN (
                'candidate', 'under_review', 'verified',
                'stale', 'rejected', 'inactive'
            )
        ),
    status_note TEXT NOT NULL DEFAULT '',
    expense_proof_requirement TEXT NOT NULL DEFAULT 'unknown',
    claimant_rule_text TEXT NOT NULL DEFAULT '',
    deadline_rule_text TEXT NOT NULL DEFAULT '',
    mutual_exclusion_text TEXT NOT NULL DEFAULT '',
    first_verified_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    amount_min NUMERIC,
    amount_max NUMERIC,
    amount_period TEXT,
    amount_currency TEXT,
    current_revision_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (amount_min IS NULL AND amount_max IS NULL
         AND amount_period IS NULL AND amount_currency IS NULL)
        OR
        (amount_min IS NOT NULL AND amount_max IS NOT NULL
         AND amount_period IS NOT NULL AND amount_currency IS NOT NULL
         AND amount_min <= amount_max)
    ),
    FOREIGN KEY (current_revision_id)
        REFERENCES catalog_revisions (revision_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_benefit_programs_status_program
    ON benefit_programs (program_status, program_id);

CREATE TABLE IF NOT EXISTS program_status_history (
    history_id TEXT PRIMARY KEY NOT NULL,
    program_id TEXT NOT NULL,
    from_status TEXT NOT NULL
        CHECK (from_status IN (
            'candidate', 'under_review', 'verified',
            'stale', 'rejected', 'inactive', 'status_unknown'
        )),
    to_status TEXT NOT NULL
        CHECK (to_status IN (
            'candidate', 'under_review', 'verified',
            'stale', 'rejected', 'inactive'
        )),
    actor_type TEXT NOT NULL CHECK (actor_type IN ('human_reviewer', 'migration')),
    reviewer_ref TEXT NOT NULL CHECK (reviewer_ref != ''),
    reviewed_at TIMESTAMPTZ NOT NULL,
    approved_version TEXT NOT NULL CHECK (approved_version != ''),
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_program_status_history_program_reviewed
    ON program_status_history (program_id, reviewed_at, history_id);

CREATE TABLE IF NOT EXISTS review_approvals (
    approval_id TEXT PRIMARY KEY NOT NULL,
    artifact_type TEXT NOT NULL
        CHECK (artifact_type IN ('program', 'rule_dsl', 'citation', 'source_excerpt')),
    artifact_id TEXT NOT NULL CHECK (artifact_id != ''),
    artifact_version TEXT NOT NULL CHECK (artifact_version != ''),
    reviewer_ref TEXT NOT NULL CHECK (reviewer_ref != ''),
    reviewed_at TIMESTAMPTZ NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_review_approvals_approved_artifact_version
    ON review_approvals (artifact_type, artifact_id, artifact_version)
    WHERE decision = 'approved';

CREATE TABLE IF NOT EXISTS field_registry (
    field_id TEXT PRIMARY KEY NOT NULL,
    data_type TEXT NOT NULL
        CHECK (data_type IN ('text', 'integer', 'number', 'boolean', 'date', 'enum')),
    prompt_label TEXT NOT NULL CHECK (prompt_label != ''),
    why_needed TEXT NOT NULL CHECK (why_needed != ''),
    pii_classification TEXT NOT NULL
        CHECK (pii_classification IN ('none', 'eligibility_sensitive', 'direct_identifier')),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_field_registry_active_field
    ON field_registry (active, field_id);

CREATE TABLE IF NOT EXISTS field_allowed_values (
    field_id TEXT NOT NULL,
    value TEXT NOT NULL,
    canonical_order INTEGER NOT NULL CHECK (canonical_order >= 0),
    PRIMARY KEY (field_id, value),
    UNIQUE (field_id, canonical_order),
    FOREIGN KEY (field_id)
        REFERENCES field_registry (field_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================
-- 0003: Graph
-- ============================================================

CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY NOT NULL,
    node_type TEXT NOT NULL
        CHECK (node_type IN (
            'life_event', 'insurance_system', 'benefit_program',
            'agency', 'document_requirement'
        )),
    display_name TEXT NOT NULL CHECK (trim(display_name) != ''),
    program_id TEXT,
    CHECK (
        (node_type = 'benefit_program' AND program_id IS NOT NULL)
        OR (node_type != 'benefit_program' AND program_id IS NULL)
    ),
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_nodes_program_id
    ON graph_nodes (program_id) WHERE program_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    edge_type TEXT NOT NULL
        CHECK (edge_type IN ('triggers', 'belongs_to', 'requires', 'produces', 'administered_by')),
    canonical_order INTEGER NOT NULL DEFAULT 0 CHECK (canonical_order >= 0),
    UNIQUE (from_node_id, to_node_id, edge_type),
    FOREIGN KEY (from_node_id) REFERENCES graph_nodes (node_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (to_node_id) REFERENCES graph_nodes (node_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_from_type_order
    ON graph_edges (from_node_id, edge_type, canonical_order, to_node_id);

CREATE INDEX IF NOT EXISTS idx_graph_edges_to_type
    ON graph_edges (to_node_id, edge_type);

CREATE TABLE IF NOT EXISTS graph_edge_conditions (
    edge_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    operator TEXT NOT NULL CHECK (trim(operator) != ''),
    expected_value_type TEXT NOT NULL
        CHECK (expected_value_type IN ('string', 'integer', 'number', 'boolean', 'null')),
    expected_value_json JSONB NOT NULL,
    condition_order INTEGER NOT NULL DEFAULT 0 CHECK (condition_order >= 0),
    PRIMARY KEY (edge_id, condition_id),
    FOREIGN KEY (edge_id) REFERENCES graph_edges (edge_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (field_id) REFERENCES field_registry (field_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_graph_edge_conditions_order
    ON graph_edge_conditions (edge_id, condition_order, condition_id);

CREATE TABLE IF NOT EXISTS graph_versions (
    graph_version TEXT PRIMARY KEY NOT NULL,
    revision_id TEXT NOT NULL,
    approved_by TEXT NOT NULL CHECK (trim(approved_by) != ''),
    approved_at TIMESTAMPTZ NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (revision_id) REFERENCES catalog_revisions (revision_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_versions_current
    ON graph_versions (is_current) WHERE is_current = TRUE;

-- ============================================================
-- 0004: Rules and Evidence
-- ============================================================

CREATE TABLE IF NOT EXISTS source_registry (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL
        CHECK (source_type IN (
            'reference_dataset', 'benefit_index', 'agency_site',
            'law_database', 'document_repository', 'other'
        )),
    jurisdiction_code TEXT NOT NULL DEFAULT '',
    organization_name TEXT NOT NULL DEFAULT '',
    publisher_oid TEXT,
    base_url TEXT NOT NULL,
    entry_url TEXT NOT NULL,
    canonical_host TEXT NOT NULL,
    official_status TEXT NOT NULL
        CHECK (official_status IN (
            'pending_review', 'verified_official',
            'confirmed_non_taiwan_government', 'confirmed_commercial'
        )),
    access_method TEXT NOT NULL
        CHECK (access_method IN (
            'api', 'download_file', 'sitemap', 'rss',
            'index_page', 'targeted_crawl', 'manual_seed'
        )),
    connection_status TEXT NOT NULL
        CHECK (connection_status IN ('pending', 'active', 'degraded', 'failed', 'paused')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    reviewed_at TIMESTAMPTZ,
    review_note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_registry_connection_status
    ON source_registry (connection_status);

CREATE INDEX IF NOT EXISTS idx_source_registry_canonical_host
    ON source_registry (canonical_host);

CREATE TABLE IF NOT EXISTS source_documents (
    document_id TEXT PRIMARY KEY,
    canonical_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    document_type TEXT NOT NULL DEFAULT 'other'
        CHECK (document_type IN (
            'benefit_page', 'application_page', 'legal_text', 'news',
            'statistics', 'budget', 'procurement', 'index', 'other'
        )),
    jurisdiction_code TEXT NOT NULL DEFAULT '',
    publisher_name TEXT NOT NULL DEFAULT '',
    publisher_oid TEXT,
    current_content_hash TEXT,
    storage_ref TEXT,
    http_status INTEGER,
    published_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_changed_at TIMESTAMPTZ,
    retrieved_at TIMESTAMPTZ,
    review_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (review_status IN (
            'candidate', 'under_review', 'verified',
            'rejected', 'stale', 'status_unknown'
        )),
    simplified_script_detected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    effective_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_source_documents_review_status
    ON source_documents (review_status);

CREATE INDEX IF NOT EXISTS idx_source_documents_publisher_oid
    ON source_documents (publisher_oid);

CREATE TABLE IF NOT EXISTS document_discoveries (
    document_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    discovery_url TEXT NOT NULL DEFAULT '',
    discovery_method TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_sync_run_id TEXT,
    PRIMARY KEY (document_id, source_id),
    FOREIGN KEY (document_id) REFERENCES source_documents (document_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (source_id) REFERENCES source_registry (source_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_document_discoveries_source_id
    ON document_discoveries (source_id);

CREATE TABLE IF NOT EXISTS source_domain_tags (
    source_id TEXT NOT NULL,
    domain_tag TEXT NOT NULL CHECK (trim(domain_tag) != ''),
    PRIMARY KEY (source_id, domain_tag),
    FOREIGN KEY (source_id) REFERENCES source_registry (source_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_source_domain_tags_tag_source
    ON source_domain_tags (domain_tag, source_id);

CREATE TABLE IF NOT EXISTS rule_definitions (
    rule_id TEXT PRIMARY KEY NOT NULL,
    program_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (program_id) REFERENCES benefit_programs (program_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS rule_versions (
    rule_version_id TEXT PRIMARY KEY NOT NULL,
    rule_id TEXT NOT NULL,
    version TEXT NOT NULL CHECK (trim(version) != ''),
    dsl_version TEXT NOT NULL CHECK (trim(dsl_version) != ''),
    approval_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (approval_status IN ('candidate', 'under_review', 'approved', 'rejected')),
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    root_node_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    UNIQUE (rule_id, version),
    CHECK (
        (approval_status = 'approved'
         AND root_node_id IS NOT NULL
         AND approved_by IS NOT NULL AND trim(approved_by) != ''
         AND approved_at IS NOT NULL)
        OR
        (approval_status != 'approved'
         AND is_current = FALSE
         AND approved_by IS NULL AND approved_at IS NULL)
    ),
    FOREIGN KEY (rule_id) REFERENCES rule_definitions (rule_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_versions_current_approved
    ON rule_versions (rule_id) WHERE is_current = TRUE AND approval_status = 'approved';

CREATE INDEX IF NOT EXISTS idx_rule_versions_rule_status_version
    ON rule_versions (rule_id, approval_status, version);

CREATE TABLE IF NOT EXISTS rule_nodes (
    node_id TEXT PRIMARY KEY NOT NULL,
    rule_version_id TEXT NOT NULL,
    parent_node_id TEXT,
    node_type TEXT NOT NULL CHECK (node_type IN ('all_of', 'any_of', 'condition')),
    child_order INTEGER NOT NULL DEFAULT 0 CHECK (child_order >= 0),
    UNIQUE (node_id, rule_version_id),
    UNIQUE (rule_version_id, parent_node_id, child_order),
    FOREIGN KEY (rule_version_id) REFERENCES rule_versions (rule_version_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (parent_node_id) REFERENCES rule_nodes (node_id) ON UPDATE CASCADE ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_nodes_root_per_version
    ON rule_nodes (rule_version_id) WHERE parent_node_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_rule_nodes_parent_order
    ON rule_nodes (rule_version_id, parent_node_id, child_order, node_id);

CREATE TABLE IF NOT EXISTS rule_conditions (
    condition_id TEXT PRIMARY KEY NOT NULL,
    node_id TEXT NOT NULL UNIQUE,
    field_id TEXT NOT NULL,
    operator TEXT NOT NULL CHECK (trim(operator) != ''),
    expected_value_type TEXT NOT NULL
        CHECK (expected_value_type IN ('string', 'integer', 'number', 'boolean', 'null')),
    expected_value_json JSONB NOT NULL,
    label TEXT NOT NULL CHECK (trim(label) != ''),
    source_reference TEXT NOT NULL CHECK (trim(source_reference) != ''),
    FOREIGN KEY (node_id) REFERENCES rule_nodes (node_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (field_id) REFERENCES field_registry (field_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_rule_conditions_field_id
    ON rule_conditions (field_id, condition_id);

CREATE TABLE IF NOT EXISTS rule_required_fields (
    rule_version_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    canonical_order INTEGER NOT NULL CHECK (canonical_order >= 0),
    PRIMARY KEY (rule_version_id, field_id),
    UNIQUE (rule_version_id, canonical_order),
    FOREIGN KEY (rule_version_id) REFERENCES rule_versions (rule_version_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (field_id) REFERENCES field_registry (field_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS rule_version_source_refs (
    rule_version_id TEXT NOT NULL,
    source_reference TEXT NOT NULL CHECK (trim(source_reference) != ''),
    PRIMARY KEY (rule_version_id, source_reference),
    FOREIGN KEY (rule_version_id) REFERENCES rule_versions (rule_version_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS approved_amounts (
    rule_version_id TEXT PRIMARY KEY NOT NULL,
    amount_min NUMERIC NOT NULL,
    amount_max NUMERIC NOT NULL,
    amount_period TEXT NOT NULL CHECK (trim(amount_period) != ''),
    amount_currency TEXT NOT NULL CHECK (trim(amount_currency) != ''),
    source_reference TEXT NOT NULL CHECK (trim(source_reference) != ''),
    CHECK (amount_min <= amount_max),
    FOREIGN KEY (rule_version_id) REFERENCES rule_versions (rule_version_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS evidence_excerpts (
    evidence_id TEXT PRIMARY KEY NOT NULL,
    document_id TEXT NOT NULL,
    excerpt TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (review_status IN ('candidate', 'under_review', 'verified', 'rejected')),
    reviewer_ref TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (
        review_status != 'verified'
        OR (trim(excerpt) != '' AND reviewer_ref IS NOT NULL
            AND trim(reviewer_ref) != '' AND reviewed_at IS NOT NULL)
    ),
    FOREIGN KEY (document_id) REFERENCES source_documents (document_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_evidence_excerpts_document_status
    ON evidence_excerpts (document_id, review_status, evidence_id);

CREATE TABLE IF NOT EXISTS program_evidence_links (
    program_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    evidence_role TEXT NOT NULL
        CHECK (evidence_role IN (
            'discovery', 'overview', 'eligibility', 'application',
            'effective_period', 'organization_role', 'legal_basis'
        )),
    review_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (review_status IN ('candidate', 'under_review', 'verified', 'rejected')),
    reviewer_ref TEXT,
    reviewed_at TIMESTAMPTZ,
    PRIMARY KEY (program_id, evidence_id, evidence_role),
    CHECK (
        review_status != 'verified'
        OR (reviewer_ref IS NOT NULL AND trim(reviewer_ref) != '' AND reviewed_at IS NOT NULL)
    ),
    FOREIGN KEY (program_id) REFERENCES benefit_programs (program_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id) REFERENCES evidence_excerpts (evidence_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_program_evidence_links_evidence_status
    ON program_evidence_links (evidence_id, review_status, program_id);

CREATE TABLE IF NOT EXISTS source_reference_evidence (
    rule_version_id TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (rule_version_id, source_reference, evidence_id),
    FOREIGN KEY (rule_version_id, source_reference)
        REFERENCES rule_version_source_refs (rule_version_id, source_reference)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id) REFERENCES evidence_excerpts (evidence_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_source_reference_evidence_evidence
    ON source_reference_evidence (evidence_id, rule_version_id, source_reference);

CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id TEXT PRIMARY KEY NOT NULL,
    document_id TEXT NOT NULL,
    filename TEXT NOT NULL CHECK (trim(filename) != ''),
    media_type TEXT NOT NULL CHECK (trim(media_type) != ''),
    source_url TEXT NOT NULL CHECK (trim(source_url) != ''),
    storage_backend TEXT CHECK (storage_backend IS NULL OR storage_backend IN ('local', 's3')),
    storage_ref TEXT,
    content_hash TEXT,
    extraction_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (extraction_status IN ('pending', 'extracted', 'failed', 'not_applicable')),
    extraction_method TEXT,
    extracted_at TIMESTAMPTZ,
    review_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (review_status IN ('candidate', 'under_review', 'verified', 'rejected')),
    reviewer_ref TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (storage_backend IS NULL AND storage_ref IS NULL AND content_hash IS NULL)
        OR (storage_backend IS NOT NULL AND storage_ref IS NOT NULL
            AND trim(storage_ref) != '' AND content_hash IS NOT NULL AND trim(content_hash) != '')
    ),
    FOREIGN KEY (document_id) REFERENCES source_documents (document_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_document_attachments_document_status
    ON document_attachments (document_id, review_status, attachment_id);

-- ============================================================
-- 0005: Refresh and Coverage
-- ============================================================

CREATE TABLE IF NOT EXISTS source_coverage_state (
    source_id TEXT PRIMARY KEY NOT NULL,
    crawl_status TEXT NOT NULL DEFAULT 'pending_crawl'
        CHECK (crawl_status IN ('pending_crawl', 'crawled', 'error')),
    last_successful_crawl_at TIMESTAMPTZ,
    indexed_document_count INTEGER NOT NULL DEFAULT 0 CHECK (indexed_document_count >= 0),
    last_gap_category TEXT
        CHECK (last_gap_category IS NULL OR last_gap_category IN (
            'robots_policy', 'login_required', 'javascript_only',
            'broken_link', 'scanned_attachment', 'connection_error'
        )),
    updated_revision_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (source_id) REFERENCES source_registry (source_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (updated_revision_id) REFERENCES catalog_revisions (revision_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_source_coverage_state_status_source
    ON source_coverage_state (crawl_status, source_id);

CREATE TABLE IF NOT EXISTS refresh_jobs (
    job_id TEXT NOT NULL CHECK (trim(job_id) != ''),
    source_id TEXT NOT NULL,
    event_id TEXT NOT NULL CHECK (trim(event_id) != ''),
    local_calendar_date DATE NOT NULL,
    dedup_key TEXT NOT NULL UNIQUE CHECK (trim(dedup_key) != ''),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    requested_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    safe_error_code TEXT,
    PRIMARY KEY (job_id, source_id),
    UNIQUE (source_id, event_id, local_calendar_date),
    FOREIGN KEY (source_id) REFERENCES source_registry (source_id) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_refresh_jobs_status_requested
    ON refresh_jobs (status, requested_at, job_id, source_id);

CREATE INDEX IF NOT EXISTS idx_refresh_jobs_event_date
    ON refresh_jobs (event_id, local_calendar_date, source_id);

-- ============================================================
-- Government Organizations (from OID importer)
-- ============================================================

CREATE TABLE IF NOT EXISTS government_organizations (
    oid TEXT PRIMARY KEY,
    org_name TEXT NOT NULL,
    org_code TEXT NOT NULL DEFAULT '',
    tel TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    dn TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    source_url TEXT NOT NULL,
    source_record_hash TEXT NOT NULL,
    source_updated_at TIMESTAMPTZ,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_government_organizations_org_name
    ON government_organizations (org_name);

CREATE INDEX IF NOT EXISTS idx_government_organizations_org_code
    ON government_organizations (org_code);

-- ============================================================
-- Record schema version
-- ============================================================

INSERT INTO schema_metadata (key, value)
VALUES ('data_layer_schema_version', '7')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

INSERT INTO schema_metadata (key, value)
VALUES ('postgresql_migration_applied_at', NOW()::TEXT)
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
