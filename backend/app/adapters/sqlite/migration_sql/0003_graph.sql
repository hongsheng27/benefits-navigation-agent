CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY NOT NULL,
    node_type TEXT NOT NULL
        CHECK (
            node_type IN (
                'life_event',
                'insurance_system',
                'benefit_program',
                'agency',
                'document_requirement'
            )
        ),
    display_name TEXT NOT NULL CHECK (trim(display_name) != ''),
    program_id TEXT,
    CHECK (
        (node_type = 'benefit_program' AND program_id IS NOT NULL)
        OR (node_type != 'benefit_program' AND program_id IS NULL)
    ),
    FOREIGN KEY (program_id)
        REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_nodes_program_id
    ON graph_nodes (program_id)
    WHERE program_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    edge_type TEXT NOT NULL
        CHECK (
            edge_type IN (
                'triggers',
                'belongs_to',
                'requires',
                'produces',
                'administered_by'
            )
        ),
    canonical_order INTEGER NOT NULL DEFAULT 0
        CHECK (canonical_order >= 0),
    UNIQUE (from_node_id, to_node_id, edge_type),
    FOREIGN KEY (from_node_id)
        REFERENCES graph_nodes (node_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (to_node_id)
        REFERENCES graph_nodes (node_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_from_type_order
    ON graph_edges (
        from_node_id,
        edge_type,
        canonical_order,
        to_node_id
    );

CREATE INDEX IF NOT EXISTS idx_graph_edges_to_type
    ON graph_edges (to_node_id, edge_type);

CREATE TABLE IF NOT EXISTS graph_edge_conditions (
    edge_id TEXT NOT NULL,
    condition_id TEXT NOT NULL,
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
    condition_order INTEGER NOT NULL DEFAULT 0
        CHECK (condition_order >= 0),
    PRIMARY KEY (edge_id, condition_id),
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
    FOREIGN KEY (edge_id)
        REFERENCES graph_edges (edge_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (field_id)
        REFERENCES field_registry (field_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_graph_edge_conditions_order
    ON graph_edge_conditions (edge_id, condition_order, condition_id);

CREATE TABLE IF NOT EXISTS graph_versions (
    graph_version TEXT PRIMARY KEY NOT NULL,
    revision_id TEXT NOT NULL,
    approved_by TEXT NOT NULL CHECK (trim(approved_by) != ''),
    approved_at TEXT NOT NULL CHECK (trim(approved_at) != ''),
    is_current INTEGER NOT NULL DEFAULT 0
        CHECK (is_current IN (0, 1)),
    FOREIGN KEY (revision_id)
        REFERENCES catalog_revisions (revision_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_graph_versions_current
    ON graph_versions (is_current)
    WHERE is_current = 1;
