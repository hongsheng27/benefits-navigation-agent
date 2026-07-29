"""Ordered, checksummed SQLite catalog migrations."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

APPLICATION_VERSION: Final = "0.1.0"
SCHEMA_VERSION_KEY: Final = "data_layer_schema_version"
MIN_SUPPORTED_VERSION: Final = 0
MIGRATION_SQL_DIRECTORY: Final = Path(__file__).with_name("migration_sql")
_MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{4})_[a-z0-9_]+\.sql$")
_PROGRAMS_FIELDS_MIGRATION_ID: Final = "0002_programs_fields"
_PROGRAMS_FIELDS_HELPER_IDENTITY: Final = (
    "compatibility-v1:exact-benefit-catalog-schema:"
    "status-unknown-to-under-review:dependent-table-rebuild:target-validation"
)
_LEGACY_PROGRAM_COLUMNS: Final = (
    "program_id",
    "canonical_name",
    "summary",
    "support_purpose",
    "program_basis",
    "delivery_form",
    "jurisdiction_code",
    "program_status",
    "status_note",
    "expense_proof_requirement",
    "claimant_rule_text",
    "deadline_rule_text",
    "mutual_exclusion_text",
    "first_verified_at",
    "last_verified_at",
    "created_at",
    "updated_at",
)
_LEGACY_PROGRAM_SOURCES_COLUMNS: Final = (
    "program_id",
    "document_id",
    "evidence_role",
    "source_excerpt",
    "review_status",
    "reviewed_at",
    "created_at",
    "updated_at",
)
_LEGACY_PROGRAM_ROLES_COLUMNS: Final = (
    "role_id",
    "program_id",
    "organization_role",
    "oid",
    "organization_name",
    "evidence_document_id",
    "review_status",
    "created_at",
    "updated_at",
)
_LEGACY_RULE_FIELDS_COLUMNS: Final = (
    "program_id",
    "field_name",
    "field_type",
    "field_value",
    "source_excerpt",
    "review_status",
    "created_at",
    "updated_at",
)


def _migration_checksum(migration_id: str, payload: bytes) -> str:
    if migration_id != _PROGRAMS_FIELDS_MIGRATION_ID:
        return hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(
        payload + b"\0implementation:" + _PROGRAMS_FIELDS_HELPER_IDENTITY.encode()
    ).hexdigest()


class MigrationError(RuntimeError):
    """A migration failure whose public message contains only a safe code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Migration:
    """One immutable migration loaded from a numbered SQL file."""

    migration_id: str
    version: int
    sql: str
    checksum: str

    @classmethod
    def from_sql(cls, migration_id: str, version: int, sql: str) -> Migration:
        checksum = _migration_checksum(migration_id, sql.encode("utf-8"))
        return cls(
            migration_id=migration_id,
            version=version,
            sql=sql,
            checksum=checksum,
        )


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Safe summary returned after a migration run."""

    previous_version: int
    current_version: int
    applied_migration_ids: tuple[str, ...]


def load_migrations(directory: Path = MIGRATION_SQL_DIRECTORY) -> tuple[Migration, ...]:
    """Load migration files in strict numeric order and verify the manifest."""

    try:
        sql_paths = sorted(directory.glob("*.sql"))
    except OSError as exc:
        raise MigrationError("migration_manifest_unavailable") from exc

    migrations: list[Migration] = []
    for path in sql_paths:
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError("migration_manifest_invalid")
        try:
            payload = path.read_bytes()
            sql = payload.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise MigrationError("migration_manifest_unavailable") from exc
        migrations.append(
            Migration(
                migration_id=path.stem,
                version=int(match.group("version")),
                sql=sql,
                checksum=_migration_checksum(path.stem, payload),
            )
        )

    _validate_manifest(tuple(migrations))
    return tuple(migrations)


def _validate_manifest(migrations: tuple[Migration, ...]) -> None:
    expected_versions = tuple(range(1, len(migrations) + 1))
    actual_versions = tuple(migration.version for migration in migrations)
    if actual_versions != expected_versions:
        raise MigrationError("migration_manifest_invalid")
    if len({migration.migration_id for migration in migrations}) != len(migrations):
        raise MigrationError("migration_manifest_invalid")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _enable_foreign_keys(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()
    except sqlite3.Error as exc:
        raise MigrationError("migration_foreign_keys_unavailable") from exc
    if enabled != (1,):
        raise MigrationError("migration_foreign_keys_unavailable")


def _read_stored_version(connection: sqlite3.Connection) -> int | None:
    if not _table_exists(connection, "schema_metadata"):
        return None
    row = connection.execute(
        "SELECT value FROM schema_metadata WHERE key = ?",
        (SCHEMA_VERSION_KEY,),
    ).fetchone()
    if row is None:
        return None
    try:
        version = int(row[0])
    except (TypeError, ValueError) as exc:
        raise MigrationError("schema_version_invalid") from exc
    if version < 0:
        raise MigrationError("schema_version_invalid")
    return version


def _read_applied_migrations(connection: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(connection, "schema_migrations"):
        return {}
    try:
        rows = connection.execute(
            "SELECT migration_id, checksum FROM schema_migrations"
        ).fetchall()
    except sqlite3.Error as exc:
        raise MigrationError("migration_state_unavailable") from exc
    return {str(migration_id): str(checksum) for migration_id, checksum in rows}


def _validate_database_state(
    connection: sqlite3.Connection,
    migrations: tuple[Migration, ...],
    *,
    min_supported_version: int,
    max_supported_version: int,
) -> tuple[int, dict[str, str]]:
    known_by_id = {migration.migration_id: migration for migration in migrations}
    applied = _read_applied_migrations(connection)
    if any(migration_id not in known_by_id for migration_id in applied):
        raise MigrationError("unknown_migration")

    for migration_id, checksum in applied.items():
        if checksum != known_by_id[migration_id].checksum:
            raise MigrationError("migration_checksum_mismatch")

    applied_versions = sorted(known_by_id[item].version for item in applied)
    if applied_versions != list(range(1, len(applied_versions) + 1)):
        raise MigrationError("migration_state_invalid")

    stored_version = _read_stored_version(connection)
    current_version = stored_version if stored_version is not None else 0
    if current_version > max_supported_version:
        raise MigrationError("schema_version_unsupported")
    expected_version = applied_versions[-1] if applied_versions else 0
    if current_version != expected_version:
        raise MigrationError("migration_state_invalid")
    return current_version, applied


def _compact_sql(sql: str) -> str:
    return re.sub(r"\s+", "", sql.lower())


def _table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> tuple[str, ...]:
    quoted_name = table_name.replace('"', '""')
    rows = connection.execute(f'PRAGMA table_info("{quoted_name}")').fetchall()
    return tuple(str(row[1]) for row in rows)


def _table_sql(connection: sqlite3.Connection, table_name: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return "" if row is None or row[0] is None else _compact_sql(str(row[0]))


def _named_indexes(connection: sqlite3.Connection, table_name: str) -> set[str]:
    quoted_name = table_name.replace('"', '""')
    return {
        str(row[1])
        for row in connection.execute(f'PRAGMA index_list("{quoted_name}")')
        if not str(row[1]).startswith("sqlite_autoindex_")
    }


def _require_legacy_table(
    connection: sqlite3.Connection,
    table_name: str,
    *,
    columns: tuple[str, ...],
    sql_fragments: tuple[str, ...],
    indexes: frozenset[str],
) -> None:
    if _table_columns(connection, table_name) != columns:
        raise MigrationError("legacy_schema_unsupported")
    table_sql = _table_sql(connection, table_name)
    if any(_compact_sql(fragment) not in table_sql for fragment in sql_fragments):
        raise MigrationError("legacy_schema_unsupported")
    if _named_indexes(connection, table_name) != set(indexes):
        raise MigrationError("legacy_schema_unsupported")


def _programs_fields_legacy_plan(
    connection: sqlite3.Connection,
) -> tuple[bool, bool, bool, bool]:
    table_rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    tables = {str(row[0]) for row in table_rows}
    legacy_tables = {
        "benefit_programs",
        "program_sources",
        "program_organization_roles",
        "program_rule_fields",
    }
    reserved_tables = {f"_migration_0002_{name}" for name in legacy_tables}
    if tables & reserved_tables:
        raise MigrationError("legacy_schema_unsupported")

    has_programs = "benefit_programs" in tables
    dependent_presence = tuple(
        name in tables
        for name in (
            "program_sources",
            "program_organization_roles",
            "program_rule_fields",
        )
    )
    if not has_programs:
        if any(dependent_presence):
            raise MigrationError("legacy_schema_unsupported")
        return (False, False, False, False)

    _require_legacy_table(
        connection,
        "benefit_programs",
        columns=_LEGACY_PROGRAM_COLUMNS,
        sql_fragments=(
            "program_status IN ('candidate','under_review','verified',"
            "'rejected','stale','inactive','status_unknown')",
            "program_status != 'verified' OR",
        ),
        indexes=frozenset(
            {"idx_benefit_programs_status", "idx_benefit_programs_purpose"}
        ),
    )

    has_sources, has_roles, has_rule_fields = dependent_presence
    if has_sources:
        _require_legacy_table(
            connection,
            "program_sources",
            columns=_LEGACY_PROGRAM_SOURCES_COLUMNS,
            sql_fragments=(
                "PRIMARY KEY (program_id, document_id, evidence_role)",
                "REFERENCES benefit_programs (program_id)",
                "review_status != 'verified' OR",
            ),
            indexes=frozenset(
                {
                    "idx_program_sources_document_id",
                    "idx_program_sources_review_status",
                }
            ),
        )
    if has_roles:
        _require_legacy_table(
            connection,
            "program_organization_roles",
            columns=_LEGACY_PROGRAM_ROLES_COLUMNS,
            sql_fragments=(
                "CHECK (oid IS NOT NULL OR organization_name != '')",
                "REFERENCES benefit_programs (program_id)",
                "review_status != 'verified' OR",
            ),
            indexes=frozenset(
                {
                    "idx_program_organization_roles_program",
                    "idx_program_organization_roles_oid",
                }
            ),
        )
    if has_rule_fields:
        _require_legacy_table(
            connection,
            "program_rule_fields",
            columns=_LEGACY_RULE_FIELDS_COLUMNS,
            sql_fragments=(
                "PRIMARY KEY (program_id, field_name)",
                "REFERENCES benefit_programs (program_id)",
                "field_type IN ('text','integer','number','boolean','json','date')",
            ),
            indexes=frozenset({"idx_program_rule_fields_field_name"}),
        )

    allowed_references = {
        "program_sources",
        "program_organization_roles",
        "program_rule_fields",
    }
    for table_name in tables:
        quoted_name = table_name.replace('"', '""')
        foreign_keys = connection.execute(
            f'PRAGMA foreign_key_list("{quoted_name}")'
        ).fetchall()
        if any(str(row[2]) == "benefit_programs" for row in foreign_keys):
            if table_name not in allowed_references:
                raise MigrationError("legacy_schema_unsupported")

    return (True, has_sources, has_roles, has_rule_fields)


def _legacy_programs_prefix(
    plan: tuple[bool, bool, bool, bool],
) -> str:
    has_programs, has_sources, has_roles, has_rule_fields = plan
    if not has_programs:
        return ""
    statements = ["PRAGMA defer_foreign_keys = ON;"]
    if has_sources:
        statements.extend(
            (
                "ALTER TABLE program_sources "
                "RENAME TO _migration_0002_program_sources;",
                "DROP INDEX idx_program_sources_document_id;",
                "DROP INDEX idx_program_sources_review_status;",
            )
        )
    if has_roles:
        statements.extend(
            (
                "ALTER TABLE program_organization_roles "
                "RENAME TO _migration_0002_program_organization_roles;",
                "DROP INDEX idx_program_organization_roles_program;",
                "DROP INDEX idx_program_organization_roles_oid;",
            )
        )
    if has_rule_fields:
        statements.extend(
            (
                "ALTER TABLE program_rule_fields "
                "RENAME TO _migration_0002_program_rule_fields;",
                "DROP INDEX idx_program_rule_fields_field_name;",
            )
        )
    statements.extend(
        (
            "ALTER TABLE benefit_programs RENAME TO _migration_0002_benefit_programs;",
            "DROP INDEX idx_benefit_programs_status;",
            "DROP INDEX idx_benefit_programs_purpose;",
        )
    )
    return "\n".join(statements)


_LEGACY_PROGRAM_SOURCES_REBUILD: Final = """
CREATE TABLE program_sources (
    program_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    evidence_role TEXT NOT NULL
        CHECK (
            evidence_role IN (
                'discovery', 'overview', 'eligibility', 'application',
                'effective_period', 'organization_role', 'legal_basis'
            )
        ),
    source_excerpt TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'verified', 'rejected')),
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (program_id, document_id, evidence_role),
    CHECK (
        review_status != 'verified'
        OR (source_excerpt != '' AND reviewed_at IS NOT NULL)
    ),
    FOREIGN KEY (program_id) REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (document_id) REFERENCES source_documents (document_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);
CREATE INDEX idx_program_sources_document_id
    ON program_sources (document_id);
CREATE INDEX idx_program_sources_review_status
    ON program_sources (review_status);
INSERT INTO program_sources
SELECT * FROM _migration_0002_program_sources;
DROP TABLE _migration_0002_program_sources;
"""

_LEGACY_PROGRAM_ROLES_REBUILD: Final = """
CREATE TABLE program_organization_roles (
    role_id TEXT PRIMARY KEY,
    program_id TEXT NOT NULL,
    organization_role TEXT NOT NULL
        CHECK (
            organization_role IN (
                'program_owner', 'administrator', 'application_contact',
                'funder', 'data_publisher'
            )
        ),
    oid TEXT,
    organization_name TEXT NOT NULL DEFAULT '',
    evidence_document_id TEXT,
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'verified', 'rejected')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (oid IS NOT NULL OR organization_name != ''),
    CHECK (review_status != 'verified' OR evidence_document_id IS NOT NULL),
    FOREIGN KEY (program_id) REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (oid) REFERENCES government_organizations (oid)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (evidence_document_id) REFERENCES source_documents (document_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);
CREATE INDEX idx_program_organization_roles_program
    ON program_organization_roles (program_id);
CREATE INDEX idx_program_organization_roles_oid
    ON program_organization_roles (oid);
INSERT INTO program_organization_roles
SELECT * FROM _migration_0002_program_organization_roles;
DROP TABLE _migration_0002_program_organization_roles;
"""

_LEGACY_RULE_FIELDS_REBUILD: Final = """
CREATE TABLE program_rule_fields (
    program_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    field_type TEXT NOT NULL DEFAULT 'text'
        CHECK (field_type IN ('text','integer','number','boolean','json','date')),
    field_value TEXT NOT NULL DEFAULT '',
    source_excerpt TEXT NOT NULL DEFAULT '',
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'verified', 'rejected')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (program_id, field_name),
    FOREIGN KEY (program_id) REFERENCES benefit_programs (program_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);
CREATE INDEX idx_program_rule_fields_field_name
    ON program_rule_fields (field_name);
INSERT INTO program_rule_fields
SELECT * FROM _migration_0002_program_rule_fields;
DROP TABLE _migration_0002_program_rule_fields;
"""


def _legacy_programs_suffix(
    plan: tuple[bool, bool, bool, bool],
) -> str:
    has_programs, has_sources, has_roles, has_rule_fields = plan
    if not has_programs:
        return ""
    statements = [
        """
INSERT INTO benefit_programs (
    program_id, canonical_name, summary, support_purpose, program_basis,
    delivery_form, jurisdiction_code, program_status, status_note,
    expense_proof_requirement, claimant_rule_text, deadline_rule_text,
    mutual_exclusion_text, first_verified_at, last_verified_at,
    amount_min, amount_max, amount_period, amount_currency,
    current_revision_id, created_at, updated_at
)
SELECT
    program_id, canonical_name, summary, support_purpose, program_basis,
    delivery_form, jurisdiction_code,
    CASE
        WHEN program_status = 'status_unknown' THEN 'under_review'
        ELSE program_status
    END,
    status_note, expense_proof_requirement, claimant_rule_text,
    deadline_rule_text, mutual_exclusion_text, first_verified_at,
    last_verified_at, NULL, NULL, NULL, NULL, NULL, created_at, updated_at
FROM _migration_0002_benefit_programs;

INSERT INTO program_status_history (
    history_id, program_id, from_status, to_status, actor_type,
    reviewer_ref, reviewed_at, approved_version
)
SELECT
    'migration-0002:' || program_id,
    program_id,
    'status_unknown',
    'under_review',
    'migration',
    'migration:0002_programs_fields',
    updated_at,
    '0002'
FROM _migration_0002_benefit_programs
WHERE program_status = 'status_unknown';
"""
    ]
    if has_sources:
        statements.append(_LEGACY_PROGRAM_SOURCES_REBUILD)
    if has_roles:
        statements.append(_LEGACY_PROGRAM_ROLES_REBUILD)
    if has_rule_fields:
        statements.append(_LEGACY_RULE_FIELDS_REBUILD)
    statements.append("DROP TABLE _migration_0002_benefit_programs;")
    return "\n".join(statements)


def _validate_programs_fields_target(connection: sqlite3.Connection) -> None:
    required_tables = {
        "benefit_programs",
        "program_status_history",
        "review_approvals",
        "field_registry",
        "field_allowed_values",
    }
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if not required_tables.issubset(tables):
        raise MigrationError("migration_target_invalid")

    def require_table(
        table_name: str,
        *,
        columns: tuple[str, ...],
        sql_fragments: tuple[str, ...],
    ) -> None:
        if _table_columns(connection, table_name) != columns:
            raise MigrationError("migration_target_invalid")
        table_sql = _table_sql(connection, table_name)
        if any(_compact_sql(fragment) not in table_sql for fragment in sql_fragments):
            raise MigrationError("migration_target_invalid")

    def require_index(
        table_name: str,
        index_name: str,
        *,
        columns: tuple[str, ...],
        unique: bool = False,
        partial: bool = False,
        sql_fragments: tuple[str, ...] = (),
    ) -> None:
        quoted_table = table_name.replace('"', '""')
        index_row = next(
            (
                row
                for row in connection.execute(f'PRAGMA index_list("{quoted_table}")')
                if str(row[1]) == index_name
            ),
            None,
        )
        if (
            index_row is None
            or bool(index_row[2]) is not unique
            or bool(index_row[4]) is not partial
        ):
            raise MigrationError("migration_target_invalid")
        quoted_index = index_name.replace('"', '""')
        actual_columns = tuple(
            str(row[2])
            for row in connection.execute(f'PRAGMA index_info("{quoted_index}")')
        )
        if actual_columns != columns:
            raise MigrationError("migration_target_invalid")
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).fetchone()
        index_sql = "" if row is None or row[0] is None else _compact_sql(str(row[0]))
        if any(_compact_sql(fragment) not in index_sql for fragment in sql_fragments):
            raise MigrationError("migration_target_invalid")

    expected_program_columns = _LEGACY_PROGRAM_COLUMNS[:-2] + (
        "amount_min",
        "amount_max",
        "amount_period",
        "amount_currency",
        "current_revision_id",
        "created_at",
        "updated_at",
    )
    require_table(
        "benefit_programs",
        columns=expected_program_columns,
        sql_fragments=(
            "program_id TEXT PRIMARY KEY NOT NULL",
            "program_status IN ('candidate','under_review','verified','stale',"
            "'rejected','inactive')",
            "amount_min IS NULL AND amount_max IS NULL AND amount_period IS NULL "
            "AND amount_currency IS NULL",
            "amount_min IS NOT NULL AND amount_max IS NOT NULL "
            "AND amount_period IS NOT NULL AND amount_currency IS NOT NULL",
            "typeof(amount_min) IN ('integer','real')",
            "typeof(amount_max) IN ('integer','real')",
            "amount_min <= amount_max",
            "REFERENCES catalog_revisions (revision_id)",
        ),
    )
    require_table(
        "program_status_history",
        columns=(
            "history_id",
            "program_id",
            "from_status",
            "to_status",
            "actor_type",
            "reviewer_ref",
            "reviewed_at",
            "approved_version",
        ),
        sql_fragments=(
            "history_id TEXT PRIMARY KEY NOT NULL",
            "from_status IN ('candidate','under_review','verified','stale',"
            "'rejected','inactive','status_unknown')",
            "to_status IN ('candidate','under_review','verified','stale',"
            "'rejected','inactive')",
            "actor_type IN ('human_reviewer','migration')",
            "reviewer_ref != ''",
            "reviewed_at != ''",
            "approved_version != ''",
            "actor_type = 'migration' AND from_status = 'status_unknown' "
            "AND to_status = 'under_review'",
            "from_status = 'verified' AND to_status IN ('stale','inactive')",
            "REFERENCES benefit_programs (program_id)",
        ),
    )
    require_table(
        "review_approvals",
        columns=(
            "approval_id",
            "artifact_type",
            "artifact_id",
            "artifact_version",
            "reviewer_ref",
            "reviewed_at",
            "decision",
        ),
        sql_fragments=(
            "approval_id TEXT PRIMARY KEY NOT NULL",
            "artifact_type IN ('program','rule_dsl','citation','source_excerpt')",
            "artifact_id != ''",
            "artifact_version != ''",
            "reviewer_ref != ''",
            "reviewed_at != ''",
            "decision IN ('approved','rejected')",
        ),
    )
    require_table(
        "field_registry",
        columns=(
            "field_id",
            "data_type",
            "prompt_label",
            "why_needed",
            "pii_classification",
            "active",
        ),
        sql_fragments=(
            "field_id TEXT PRIMARY KEY NOT NULL",
            "data_type IN ('text','integer','number','boolean','date','enum')",
            "prompt_label != ''",
            "why_needed != ''",
            "pii_classification IN "
            "('none','eligibility_sensitive','direct_identifier')",
            "active IN (0,1)",
        ),
    )
    require_table(
        "field_allowed_values",
        columns=("field_id", "value", "canonical_order"),
        sql_fragments=(
            "canonical_order >= 0",
            "PRIMARY KEY (field_id,value)",
            "UNIQUE (field_id,canonical_order)",
            "REFERENCES field_registry (field_id)",
        ),
    )

    require_index(
        "benefit_programs",
        "idx_benefit_programs_status_program",
        columns=("program_status", "program_id"),
    )
    require_index(
        "program_status_history",
        "idx_program_status_history_program_reviewed",
        columns=("program_id", "reviewed_at", "history_id"),
    )
    require_index(
        "review_approvals",
        "uq_review_approvals_approved_artifact_version",
        columns=("artifact_type", "artifact_id", "artifact_version"),
        unique=True,
        partial=True,
        sql_fragments=("WHERE decision = 'approved'",),
    )
    require_index(
        "review_approvals",
        "idx_review_approvals_artifact",
        columns=("artifact_type", "artifact_id", "artifact_version", "reviewed_at"),
    )
    require_index(
        "field_registry",
        "idx_field_registry_active_field",
        columns=("active", "field_id"),
    )
    require_index(
        "field_allowed_values",
        "idx_field_allowed_values_order",
        columns=("field_id", "canonical_order", "value"),
    )

    required_foreign_keys = {
        (
            "benefit_programs",
            "current_revision_id",
            "catalog_revisions",
            "revision_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "program_status_history",
            "program_id",
            "benefit_programs",
            "program_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "field_allowed_values",
            "field_id",
            "field_registry",
            "field_id",
            "CASCADE",
            "RESTRICT",
        ),
    }
    actual_foreign_keys: set[tuple[str, str, str, str, str, str]] = set()
    for table_name in required_tables:
        for row in connection.execute(f'PRAGMA foreign_key_list("{table_name}")'):
            actual_foreign_keys.add(
                (
                    table_name,
                    str(row[3]),
                    str(row[2]),
                    str(row[4]),
                    str(row[5]),
                    str(row[6]),
                )
            )
    if not required_foreign_keys.issubset(actual_foreign_keys):
        raise MigrationError("migration_target_invalid")

    trigger = connection.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'trigger'
          AND name = 'trg_program_status_history_protected_actor'
        """
    ).fetchone()
    trigger_sql = (
        "" if trigger is None or trigger[0] is None else _compact_sql(str(trigger[0]))
    )
    required_trigger_fragments = (
        "beforeinsertonprogram_status_history",
        "whennew.to_statusin('verified','rejected','inactive')and"
        "new.actor_type!='human_reviewer'",
        "raise(abort,'protectedprogramstatusrequireshumanreviewer')",
    )
    if any(fragment not in trigger_sql for fragment in required_trigger_fragments):
        raise MigrationError("migration_target_invalid")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise MigrationError("migration_target_invalid")


def _migration_script(
    connection: sqlite3.Connection,
    migration: Migration,
) -> str:
    if migration.migration_id != _PROGRAMS_FIELDS_MIGRATION_ID:
        return f"BEGIN IMMEDIATE;\n{migration.sql}\n"
    plan = _programs_fields_legacy_plan(connection)
    prefix = _legacy_programs_prefix(plan)
    suffix = _legacy_programs_suffix(plan)
    return f"BEGIN IMMEDIATE;\n{prefix}\n{migration.sql}\n{suffix}\n"


def _validate_migration_target(
    connection: sqlite3.Connection,
    migration: Migration,
) -> None:
    if migration.migration_id == _PROGRAMS_FIELDS_MIGRATION_ID:
        _validate_programs_fields_target(connection)


def _apply_migration(
    connection: sqlite3.Connection,
    migration: Migration,
    *,
    application_version: str,
) -> None:
    try:
        connection.executescript(_migration_script(connection, migration))
        _validate_migration_target(connection, migration)
        connection.execute(
            """
            INSERT INTO schema_migrations (
                migration_id,
                checksum,
                applied_at,
                application_version
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                migration.migration_id,
                migration.checksum,
                datetime.now(UTC).isoformat(),
                application_version,
            ),
        )
        connection.execute(
            """
            INSERT INTO schema_metadata (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SCHEMA_VERSION_KEY, str(migration.version)),
        )
        connection.commit()
    except MigrationError:
        try:
            connection.rollback()
        except sqlite3.Error as rollback_error:
            raise MigrationError("migration_rollback_failed") from rollback_error
        raise
    except Exception as exc:
        try:
            connection.rollback()
        except sqlite3.Error as rollback_error:
            raise MigrationError("migration_rollback_failed") from rollback_error
        raise MigrationError("migration_failed") from exc


def run_migrations(
    connection: sqlite3.Connection,
    *,
    migrations: tuple[Migration, ...] | None = None,
    application_version: str = APPLICATION_VERSION,
    min_supported_version: int = MIN_SUPPORTED_VERSION,
    max_supported_version: int | None = None,
) -> MigrationResult:
    """Apply pending migrations in order on an existing connection."""

    migration_set = load_migrations() if migrations is None else migrations
    _validate_manifest(migration_set)
    latest_version = migration_set[-1].version if migration_set else 0
    supported_max = (
        latest_version if max_supported_version is None else max_supported_version
    )
    if min_supported_version < 0 or supported_max < min_supported_version:
        raise MigrationError("schema_version_configuration_invalid")

    _enable_foreign_keys(connection)
    try:
        previous_version, applied = _validate_database_state(
            connection,
            migration_set,
            min_supported_version=min_supported_version,
            max_supported_version=supported_max,
        )
        applied_ids: list[str] = []
        for migration in migration_set:
            if migration.migration_id in applied:
                continue
            if migration.version > supported_max:
                break
            _apply_migration(
                connection,
                migration,
                application_version=application_version,
            )
            applied_ids.append(migration.migration_id)
        current_version, _ = _validate_database_state(
            connection,
            migration_set,
            min_supported_version=min_supported_version,
            max_supported_version=supported_max,
        )
    except MigrationError:
        raise
    except sqlite3.Error as exc:
        raise MigrationError("migration_state_unavailable") from exc

    if current_version < min_supported_version:
        raise MigrationError("schema_version_unsupported")
    return MigrationResult(
        previous_version=previous_version,
        current_version=current_version,
        applied_migration_ids=tuple(applied_ids),
    )


def migrate_database(
    database_path: Path,
    *,
    migrations: tuple[Migration, ...] | None = None,
    application_version: str = APPLICATION_VERSION,
) -> MigrationResult:
    """Open, migrate, and explicitly close a SQLite database."""

    try:
        connection = sqlite3.connect(database_path)
    except (OSError, sqlite3.Error) as exc:
        raise MigrationError("sqlite_unavailable") from exc

    result: MigrationResult | None = None
    failure: BaseException | None = None
    try:
        result = run_migrations(
            connection,
            migrations=migrations,
            application_version=application_version,
        )
    except BaseException as exc:
        failure = exc
    try:
        connection.close()
    except sqlite3.Error as exc:
        raise MigrationError("migration_close_failed") from exc
    if failure is not None:
        raise failure
    if result is None:
        raise MigrationError("migration_failed")
    return result
