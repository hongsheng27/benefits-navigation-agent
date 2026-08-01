CREATE TABLE IF NOT EXISTS source_registry (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL
        CHECK (
            source_type IN (
                'reference_dataset',
                'benefit_index',
                'agency_site',
                'law_database',
                'document_repository',
                'other'
            )
        ),
    jurisdiction_code TEXT NOT NULL DEFAULT '',
    organization_name TEXT NOT NULL DEFAULT '',
    publisher_oid TEXT,
    base_url TEXT NOT NULL,
    entry_url TEXT NOT NULL,
    canonical_host TEXT NOT NULL,
    official_status TEXT NOT NULL
        CHECK (
            official_status IN (
                'pending_review',
                'verified_official',
                'confirmed_non_taiwan_government',
                'confirmed_commercial'
            )
        ),
    access_method TEXT NOT NULL
        CHECK (
            access_method IN (
                'api',
                'download_file',
                'sitemap',
                'rss',
                'index_page',
                'targeted_crawl',
                'manual_seed'
            )
        ),
    connection_status TEXT NOT NULL
        CHECK (
            connection_status IN (
                'pending',
                'active',
                'degraded',
                'failed',
                'paused'
            )
        ),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    reviewed_at TEXT,
    review_note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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
        CHECK (
            document_type IN (
                'benefit_page',
                'application_page',
                'legal_text',
                'news',
                'statistics',
                'budget',
                'procurement',
                'index',
                'other'
            )
        ),
    jurisdiction_code TEXT NOT NULL DEFAULT '',
    publisher_name TEXT NOT NULL DEFAULT '',
    publisher_oid TEXT,
    current_content_hash TEXT,
    storage_ref TEXT,
    http_status INTEGER,
    published_at TEXT,
    source_updated_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_changed_at TEXT,
    retrieved_at TEXT,
    review_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (
            review_status IN (
                'candidate',
                'under_review',
                'verified',
                'rejected',
                'stale',
                'status_unknown'
            )
        ),
    simplified_script_detected INTEGER NOT NULL DEFAULT 0
        CHECK (simplified_script_detected IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    effective_at TEXT
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
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_sync_run_id TEXT,
    PRIMARY KEY (document_id, source_id),
    FOREIGN KEY (document_id)
        REFERENCES source_documents (document_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (source_id)
        REFERENCES source_registry (source_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_document_discoveries_source_id
    ON document_discoveries (source_id);

CREATE TABLE IF NOT EXISTS source_domain_tags (
    source_id TEXT NOT NULL,
    domain_tag TEXT NOT NULL CHECK (trim(domain_tag) != ''),
    PRIMARY KEY (source_id, domain_tag),
    FOREIGN KEY (source_id)
        REFERENCES source_registry (source_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_source_domain_tags_tag_source
    ON source_domain_tags (domain_tag, source_id);

CREATE TABLE IF NOT EXISTS rule_definitions (
    rule_id TEXT PRIMARY KEY NOT NULL,
    program_id TEXT NOT NULL UNIQUE,
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS rule_versions (
    rule_version_id TEXT PRIMARY KEY NOT NULL,
    rule_id TEXT NOT NULL,
    version TEXT NOT NULL CHECK (trim(version) != ''),
    dsl_version TEXT NOT NULL CHECK (trim(dsl_version) != ''),
    approval_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (
            approval_status IN (
                'candidate',
                'under_review',
                'approved',
                'rejected'
            )
        ),
    is_current INTEGER NOT NULL DEFAULT 0 CHECK (is_current IN (0, 1)),
    root_node_id TEXT,
    created_at TEXT NOT NULL CHECK (trim(created_at) != ''),
    approved_by TEXT,
    approved_at TEXT,
    UNIQUE (rule_id, version),
    CHECK (
        (
            approval_status = 'approved'
            AND root_node_id IS NOT NULL
            AND approved_by IS NOT NULL
            AND trim(approved_by) != ''
            AND approved_at IS NOT NULL
            AND trim(approved_at) != ''
        )
        OR
        (
            approval_status != 'approved'
            AND is_current = 0
            AND approved_by IS NULL
            AND approved_at IS NULL
        )
    ),
    FOREIGN KEY (rule_id)
        REFERENCES rule_definitions (rule_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (root_node_id, rule_version_id)
        REFERENCES rule_nodes (node_id, rule_version_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_versions_current_approved
    ON rule_versions (rule_id)
    WHERE is_current = 1 AND approval_status = 'approved';

CREATE INDEX IF NOT EXISTS idx_rule_versions_rule_status_version
    ON rule_versions (rule_id, approval_status, version);

CREATE TABLE IF NOT EXISTS rule_nodes (
    node_id TEXT PRIMARY KEY NOT NULL,
    rule_version_id TEXT NOT NULL,
    parent_node_id TEXT,
    node_type TEXT NOT NULL
        CHECK (node_type IN ('all_of', 'any_of', 'condition')),
    child_order INTEGER NOT NULL DEFAULT 0 CHECK (child_order >= 0),
    UNIQUE (node_id, rule_version_id),
    UNIQUE (rule_version_id, parent_node_id, child_order),
    FOREIGN KEY (rule_version_id)
        REFERENCES rule_versions (rule_version_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (parent_node_id, rule_version_id)
        REFERENCES rule_nodes (node_id, rule_version_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rule_nodes_root_per_version
    ON rule_nodes (rule_version_id)
    WHERE parent_node_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_rule_nodes_parent_order
    ON rule_nodes (rule_version_id, parent_node_id, child_order, node_id);

CREATE TABLE IF NOT EXISTS rule_conditions (
    condition_id TEXT PRIMARY KEY NOT NULL,
    node_id TEXT NOT NULL UNIQUE,
    field_id TEXT NOT NULL,
    operator TEXT NOT NULL CHECK (trim(operator) != ''),
    expected_value_type TEXT NOT NULL
        CHECK (
            expected_value_type IN (
                'string',
                'integer',
                'number',
                'boolean',
                'null'
            )
        ),
    expected_value_json TEXT NOT NULL,
    label TEXT NOT NULL CHECK (trim(label) != ''),
    source_reference TEXT NOT NULL CHECK (trim(source_reference) != ''),
    CHECK (
        CASE
            WHEN json_valid(expected_value_json) = 0 THEN 0
            WHEN expected_value_type = 'string'
                THEN json_type(expected_value_json) = 'text'
            WHEN expected_value_type = 'integer'
                THEN json_type(expected_value_json) = 'integer'
            WHEN expected_value_type = 'number'
                THEN json_type(expected_value_json) IN ('integer', 'real')
            WHEN expected_value_type = 'boolean'
                THEN json_type(expected_value_json) IN ('true', 'false')
            WHEN expected_value_type = 'null'
                THEN json_type(expected_value_json) = 'null'
            ELSE 0
        END
    ),
    FOREIGN KEY (node_id)
        REFERENCES rule_nodes (node_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (field_id)
        REFERENCES field_registry (field_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_rule_conditions_field_id
    ON rule_conditions (field_id, condition_id);

CREATE TABLE IF NOT EXISTS rule_required_fields (
    rule_version_id TEXT NOT NULL,
    field_id TEXT NOT NULL,
    canonical_order INTEGER NOT NULL CHECK (canonical_order >= 0),
    PRIMARY KEY (rule_version_id, field_id),
    UNIQUE (rule_version_id, canonical_order),
    FOREIGN KEY (rule_version_id)
        REFERENCES rule_versions (rule_version_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (field_id)
        REFERENCES field_registry (field_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_rule_required_fields_order
    ON rule_required_fields (rule_version_id, canonical_order, field_id);

CREATE TABLE IF NOT EXISTS rule_version_source_refs (
    rule_version_id TEXT NOT NULL,
    source_reference TEXT NOT NULL CHECK (trim(source_reference) != ''),
    PRIMARY KEY (rule_version_id, source_reference),
    FOREIGN KEY (rule_version_id)
        REFERENCES rule_versions (rule_version_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS approved_amounts (
    rule_version_id TEXT PRIMARY KEY NOT NULL,
    amount_min NUMERIC NOT NULL,
    amount_max NUMERIC NOT NULL,
    amount_period TEXT NOT NULL CHECK (trim(amount_period) != ''),
    amount_currency TEXT NOT NULL CHECK (trim(amount_currency) != ''),
    source_reference TEXT NOT NULL CHECK (trim(source_reference) != ''),
    CHECK (typeof(amount_min) IN ('integer', 'real')),
    CHECK (typeof(amount_max) IN ('integer', 'real')),
    CHECK (amount_min <= amount_max),
    FOREIGN KEY (rule_version_id)
        REFERENCES rule_versions (rule_version_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (rule_version_id, source_reference)
        REFERENCES rule_version_source_refs (
            rule_version_id,
            source_reference
        )
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS evidence_excerpts (
    evidence_id TEXT PRIMARY KEY NOT NULL,
    document_id TEXT NOT NULL,
    excerpt TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (
            review_status IN (
                'candidate',
                'under_review',
                'verified',
                'rejected'
            )
        ),
    reviewer_ref TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        review_status != 'verified'
        OR (
            trim(excerpt) != ''
            AND reviewer_ref IS NOT NULL
            AND trim(reviewer_ref) != ''
            AND reviewed_at IS NOT NULL
            AND trim(reviewed_at) != ''
        )
    ),
    FOREIGN KEY (document_id)
        REFERENCES source_documents (document_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_evidence_excerpts_document_status
    ON evidence_excerpts (document_id, review_status, evidence_id);

CREATE TABLE IF NOT EXISTS program_evidence_links (
    program_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    evidence_role TEXT NOT NULL
        CHECK (
            evidence_role IN (
                'discovery',
                'overview',
                'eligibility',
                'application',
                'effective_period',
                'organization_role',
                'legal_basis'
            )
        ),
    review_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (
            review_status IN (
                'candidate',
                'under_review',
                'verified',
                'rejected'
            )
        ),
    reviewer_ref TEXT,
    reviewed_at TEXT,
    PRIMARY KEY (program_id, evidence_id, evidence_role),
    CHECK (
        review_status != 'verified'
        OR (
            reviewer_ref IS NOT NULL
            AND trim(reviewer_ref) != ''
            AND reviewed_at IS NOT NULL
            AND trim(reviewed_at) != ''
        )
    ),
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_excerpts (evidence_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_program_evidence_links_evidence_status
    ON program_evidence_links (evidence_id, review_status, program_id);

CREATE TABLE IF NOT EXISTS source_reference_evidence (
    rule_version_id TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (rule_version_id, source_reference, evidence_id),
    FOREIGN KEY (rule_version_id, source_reference)
        REFERENCES rule_version_source_refs (
            rule_version_id,
            source_reference
        )
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (evidence_id)
        REFERENCES evidence_excerpts (evidence_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_source_reference_evidence_evidence
    ON source_reference_evidence (evidence_id, rule_version_id, source_reference);

CREATE TABLE IF NOT EXISTS document_attachments (
    attachment_id TEXT PRIMARY KEY NOT NULL,
    document_id TEXT NOT NULL,
    filename TEXT NOT NULL CHECK (trim(filename) != ''),
    media_type TEXT NOT NULL CHECK (trim(media_type) != ''),
    source_url TEXT NOT NULL CHECK (trim(source_url) != ''),
    storage_backend TEXT
        CHECK (storage_backend IS NULL OR storage_backend IN ('local', 's3')),
    storage_ref TEXT,
    content_hash TEXT,
    extraction_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            extraction_status IN (
                'pending',
                'extracted',
                'failed',
                'not_applicable'
            )
        ),
    extraction_method TEXT,
    extracted_at TEXT,
    review_status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (
            review_status IN (
                'candidate',
                'under_review',
                'verified',
                'rejected'
            )
        ),
    reviewer_ref TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (
            storage_backend IS NULL
            AND storage_ref IS NULL
            AND content_hash IS NULL
        )
        OR
        (
            storage_backend IS NOT NULL
            AND storage_ref IS NOT NULL
            AND trim(storage_ref) != ''
            AND content_hash IS NOT NULL
            AND trim(content_hash) != ''
        )
    ),
    CHECK (
        extraction_status != 'extracted'
        OR (
            storage_ref IS NOT NULL
            AND extraction_method IS NOT NULL
            AND trim(extraction_method) != ''
            AND extracted_at IS NOT NULL
            AND trim(extracted_at) != ''
        )
    ),
    CHECK (
        review_status != 'verified'
        OR (
            storage_ref IS NOT NULL
            AND content_hash IS NOT NULL
            AND reviewer_ref IS NOT NULL
            AND trim(reviewer_ref) != ''
            AND reviewed_at IS NOT NULL
            AND trim(reviewed_at) != ''
        )
    ),
    FOREIGN KEY (document_id)
        REFERENCES source_documents (document_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_document_attachments_document_status
    ON document_attachments (document_id, review_status, attachment_id);

CREATE INDEX IF NOT EXISTS idx_document_attachments_extraction_status
    ON document_attachments (extraction_status, attachment_id);

CREATE TRIGGER IF NOT EXISTS trg_evidence_excerpts_verified_source_insert
BEFORE INSERT ON evidence_excerpts
WHEN NEW.review_status = 'verified'
 AND NOT EXISTS (
    SELECT 1
    FROM source_documents AS document
    JOIN document_discoveries AS discovery
      ON discovery.document_id = document.document_id
    JOIN source_registry AS source
      ON source.source_id = discovery.source_id
    WHERE document.document_id = NEW.document_id
      AND document.review_status = 'verified'
      AND source.official_status = 'verified_official'
      AND source.enabled = 1
 )
BEGIN
    SELECT RAISE(ABORT, 'verified evidence requires verified official source');
END;

CREATE TRIGGER IF NOT EXISTS trg_evidence_excerpts_verified_source_update
BEFORE UPDATE OF document_id, review_status ON evidence_excerpts
WHEN NEW.review_status = 'verified'
 AND NOT EXISTS (
    SELECT 1
    FROM source_documents AS document
    JOIN document_discoveries AS discovery
      ON discovery.document_id = document.document_id
    JOIN source_registry AS source
      ON source.source_id = discovery.source_id
    WHERE document.document_id = NEW.document_id
      AND document.review_status = 'verified'
      AND source.official_status = 'verified_official'
      AND source.enabled = 1
 )
BEGIN
    SELECT RAISE(ABORT, 'verified evidence requires verified official source');
END;

CREATE TRIGGER IF NOT EXISTS trg_program_evidence_links_verified_insert
BEFORE INSERT ON program_evidence_links
WHEN NEW.review_status = 'verified'
 AND NOT EXISTS (
    SELECT 1
    FROM evidence_excerpts AS evidence
    WHERE evidence.evidence_id = NEW.evidence_id
      AND evidence.review_status = 'verified'
 )
BEGIN
    SELECT RAISE(ABORT, 'verified program link requires verified evidence');
END;

CREATE TRIGGER IF NOT EXISTS trg_program_evidence_links_verified_update
BEFORE UPDATE OF evidence_id, review_status ON program_evidence_links
WHEN NEW.review_status = 'verified'
 AND NOT EXISTS (
    SELECT 1
    FROM evidence_excerpts AS evidence
    WHERE evidence.evidence_id = NEW.evidence_id
      AND evidence.review_status = 'verified'
 )
BEGIN
    SELECT RAISE(ABORT, 'verified program link requires verified evidence');
END;
