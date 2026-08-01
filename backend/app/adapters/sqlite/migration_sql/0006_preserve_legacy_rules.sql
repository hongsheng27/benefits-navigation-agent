CREATE TABLE IF NOT EXISTS legacy_program_rule_fields_v1 (
    program_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_type TEXT NOT NULL DEFAULT 'text'
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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (program_id, field_name),
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_program_rule_fields_field_name
    ON legacy_program_rule_fields_v1 (field_name);

CREATE TABLE legacy_rule_migration_inventory (
    inventory_id TEXT PRIMARY KEY NOT NULL,
    source_table_name TEXT NOT NULL
        CHECK (source_table_name = 'program_rule_fields'),
    source_schema_sha256 TEXT NOT NULL
        CHECK (
            length(source_schema_sha256) = 64
            AND source_schema_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
    source_rows_sha256 TEXT NOT NULL
        CHECK (
            length(source_rows_sha256) = 64
            AND source_rows_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
    row_count INTEGER NOT NULL
        CHECK (typeof(row_count) = 'integer' AND row_count >= 0),
    converter_version TEXT NOT NULL CHECK (trim(converter_version) != ''),
    captured_at TEXT NOT NULL CHECK (trim(captured_at) != ''),
    UNIQUE (
        source_schema_sha256,
        source_rows_sha256,
        converter_version
    )
);

CREATE TABLE legacy_rule_conversion_drafts (
    draft_id TEXT PRIMARY KEY NOT NULL,
    inventory_id TEXT NOT NULL,
    program_id TEXT NOT NULL,
    converter_version TEXT NOT NULL CHECK (trim(converter_version) != ''),
    conversion_status TEXT NOT NULL
        CHECK (conversion_status IN ('candidate', 'under_review')),
    reason_code TEXT NOT NULL CHECK (trim(reason_code) != ''),
    source_row_count INTEGER NOT NULL
        CHECK (typeof(source_row_count) = 'integer' AND source_row_count > 0),
    source_rows_sha256 TEXT NOT NULL
        CHECK (
            length(source_rows_sha256) = 64
            AND source_rows_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
    created_at TEXT NOT NULL CHECK (trim(created_at) != ''),
    UNIQUE (inventory_id, program_id),
    FOREIGN KEY (inventory_id)
        REFERENCES legacy_rule_migration_inventory (inventory_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX idx_legacy_rule_conversion_drafts_status_program
    ON legacy_rule_conversion_drafts (
        conversion_status,
        program_id,
        draft_id
    );

CREATE TRIGGER trg_legacy_program_rule_fields_read_only_insert
BEFORE INSERT ON legacy_program_rule_fields_v1
BEGIN
    SELECT RAISE(ABORT, 'read-only preserved legacy rule fields');
END;

CREATE TRIGGER trg_legacy_program_rule_fields_read_only_update
BEFORE UPDATE ON legacy_program_rule_fields_v1
BEGIN
    SELECT RAISE(ABORT, 'read-only preserved legacy rule fields');
END;

CREATE TRIGGER trg_legacy_program_rule_fields_read_only_delete
BEFORE DELETE ON legacy_program_rule_fields_v1
BEGIN
    SELECT RAISE(ABORT, 'read-only preserved legacy rule fields');
END;

CREATE VIEW program_rule_fields AS
SELECT
    projection_row.program_id AS program_id,
    projection_row.field_name AS field_name,
    projection_row.field_type AS field_type,
    projection_row.field_value AS field_value,
    projection_row.source_excerpt AS source_excerpt,
    projection_row.review_status AS review_status,
    projection_row.created_at AS created_at,
    projection_row.updated_at AS updated_at
FROM compat_projection_rows AS projection_row
JOIN compat_projection_active AS active
  ON active.generation_id = projection_row.generation_id
UNION ALL
SELECT
    legacy.program_id AS program_id,
    legacy.field_name AS field_name,
    legacy.field_type AS field_type,
    legacy.field_value AS field_value,
    legacy.source_excerpt AS source_excerpt,
    legacy.review_status AS review_status,
    legacy.created_at AS created_at,
    legacy.updated_at AS updated_at
FROM legacy_program_rule_fields_v1 AS legacy
WHERE NOT EXISTS (
    SELECT 1
    FROM compat_projection_active AS active
    JOIN compat_projection_generations AS generation
      ON generation.generation_id = active.generation_id
     AND generation.rule_version_id = active.rule_version_id
    WHERE generation.program_id = legacy.program_id
);

CREATE TRIGGER trg_program_rule_fields_read_only_insert
INSTEAD OF INSERT ON program_rule_fields
BEGIN
    SELECT RAISE(ABORT, 'read-only compatibility projection');
END;

CREATE TRIGGER trg_program_rule_fields_read_only_update
INSTEAD OF UPDATE ON program_rule_fields
BEGIN
    SELECT RAISE(ABORT, 'read-only compatibility projection');
END;

CREATE TRIGGER trg_program_rule_fields_read_only_delete
INSTEAD OF DELETE ON program_rule_fields
BEGIN
    SELECT RAISE(ABORT, 'read-only compatibility projection');
END;
