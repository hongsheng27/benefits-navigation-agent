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
                'candidate',
                'under_review',
                'verified',
                'stale',
                'rejected',
                'inactive'
            )
        ),
    status_note TEXT NOT NULL DEFAULT '',
    expense_proof_requirement TEXT NOT NULL DEFAULT 'unknown',
    claimant_rule_text TEXT NOT NULL DEFAULT '',
    deadline_rule_text TEXT NOT NULL DEFAULT '',
    mutual_exclusion_text TEXT NOT NULL DEFAULT '',
    first_verified_at TEXT,
    last_verified_at TEXT,
    amount_min NUMERIC,
    amount_max NUMERIC,
    amount_period TEXT,
    amount_currency TEXT,
    current_revision_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (
            amount_min IS NULL
            AND amount_max IS NULL
            AND amount_period IS NULL
            AND amount_currency IS NULL
        )
        OR
        (
            amount_min IS NOT NULL
            AND amount_max IS NOT NULL
            AND amount_period IS NOT NULL
            AND amount_currency IS NOT NULL
            AND typeof(amount_min) IN ('integer', 'real')
            AND typeof(amount_max) IN ('integer', 'real')
            AND amount_min <= amount_max
        )
    ),
    FOREIGN KEY (current_revision_id)
        REFERENCES catalog_revisions (revision_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_benefit_programs_status_program
    ON benefit_programs (program_status, program_id);

CREATE TABLE IF NOT EXISTS program_status_history (
    history_id TEXT PRIMARY KEY NOT NULL,
    program_id TEXT NOT NULL,
    from_status TEXT NOT NULL
        CHECK (
            from_status IN (
                'candidate',
                'under_review',
                'verified',
                'stale',
                'rejected',
                'inactive',
                'status_unknown'
            )
        ),
    to_status TEXT NOT NULL
        CHECK (
            to_status IN (
                'candidate',
                'under_review',
                'verified',
                'stale',
                'rejected',
                'inactive'
            )
        ),
    actor_type TEXT NOT NULL
        CHECK (actor_type IN ('human_reviewer', 'migration')),
    reviewer_ref TEXT NOT NULL CHECK (reviewer_ref != ''),
    reviewed_at TEXT NOT NULL CHECK (reviewed_at != ''),
    approved_version TEXT NOT NULL CHECK (approved_version != ''),
    CHECK (
        (
            actor_type = 'migration'
            AND from_status = 'status_unknown'
            AND to_status = 'under_review'
        )
        OR
        (
            actor_type = 'human_reviewer'
            AND (
                (from_status = 'candidate' AND to_status IN (
                    'under_review', 'verified', 'rejected', 'inactive'
                ))
                OR (from_status = 'under_review' AND to_status IN (
                    'verified', 'rejected', 'inactive'
                ))
                OR (from_status = 'stale' AND to_status IN (
                    'verified', 'rejected', 'inactive'
                ))
                OR (from_status = 'verified' AND to_status IN (
                    'stale', 'inactive'
                ))
            )
        )
    ),
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_program_status_history_program_reviewed
    ON program_status_history (program_id, reviewed_at, history_id);

CREATE TRIGGER IF NOT EXISTS trg_program_status_history_protected_actor
BEFORE INSERT ON program_status_history
WHEN NEW.to_status IN ('verified', 'rejected', 'inactive')
 AND NEW.actor_type != 'human_reviewer'
BEGIN
    SELECT RAISE(ABORT, 'protected program status requires human reviewer');
END;

CREATE TABLE IF NOT EXISTS review_approvals (
    approval_id TEXT PRIMARY KEY NOT NULL,
    artifact_type TEXT NOT NULL
        CHECK (
            artifact_type IN (
                'program',
                'rule_dsl',
                'citation',
                'source_excerpt'
            )
        ),
    artifact_id TEXT NOT NULL CHECK (artifact_id != ''),
    artifact_version TEXT NOT NULL CHECK (artifact_version != ''),
    reviewer_ref TEXT NOT NULL CHECK (reviewer_ref != ''),
    reviewed_at TEXT NOT NULL CHECK (reviewed_at != ''),
    decision TEXT NOT NULL
        CHECK (decision IN ('approved', 'rejected'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_review_approvals_approved_artifact_version
    ON review_approvals (artifact_type, artifact_id, artifact_version)
    WHERE decision = 'approved';

CREATE INDEX IF NOT EXISTS idx_review_approvals_artifact
    ON review_approvals (artifact_type, artifact_id, artifact_version, reviewed_at);

CREATE TABLE IF NOT EXISTS field_registry (
    field_id TEXT PRIMARY KEY NOT NULL,
    data_type TEXT NOT NULL
        CHECK (
            data_type IN (
                'text',
                'integer',
                'number',
                'boolean',
                'date',
                'enum'
            )
        ),
    prompt_label TEXT NOT NULL CHECK (prompt_label != ''),
    why_needed TEXT NOT NULL CHECK (why_needed != ''),
    pii_classification TEXT NOT NULL
        CHECK (
            pii_classification IN (
                'none',
                'eligibility_sensitive',
                'direct_identifier'
            )
        ),
    active INTEGER NOT NULL DEFAULT 1
        CHECK (active IN (0, 1))
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
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_field_allowed_values_order
    ON field_allowed_values (field_id, canonical_order, value);
