"""Ordered, checksummed SQLite catalog migrations."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from .legacy_rule_conversion import (
    CONVERTER_VERSION,
    LegacyRuleInventory,
    persist_legacy_rule_conversion,
    prepare_legacy_rule_inventory,
)

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
_RULES_EVIDENCE_MIGRATION_ID: Final = "0004_rules_evidence"
_RULES_EVIDENCE_HELPER_IDENTITY: Final = (
    "compatibility-v1:known-source-schema:effective-at-addition:"
    "many-to-many-document-provenance:target-validation"
)
_REFRESH_COMPATIBILITY_MIGRATION_ID: Final = "0005_refresh_compatibility"
_REFRESH_COMPATIBILITY_HELPER_IDENTITY: Final = (
    "compatibility-v4:legacy-table-read-only-transition:"
    "bidirectional-rule-version-program-ownership:"
    "program-unique-active-pointer:validated-generation-immutability:"
    "fresh-active-projection-view:behavioral-current-target-validation"
)
_LEGACY_RULES_MIGRATION_ID: Final = "0006_preserve_legacy_rules"
_MVP_CATALOG_SCAFFOLD_MIGRATION_ID: Final = "0007_mvp_catalog_scaffold"
_MVP_CATALOG_IDS: Final = frozenset(
    {
        "death_registration",
        "labor_funeral_grant",
        "national_pension_funeral_grant",
        "labor_survivor_pension",
        "national_pension_survivor_pension",
        "nhi_status_change",
    }
)
_LEGACY_RULES_HELPER_IDENTITY: Final = (
    "compatibility-v2:write-lock-before-pre-rename-sha256-inventory:"
    "under-review-manifest:frozen-per-program-legacy-bridge:"
    "current-target-validation"
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
_LEGACY_SOURCE_REGISTRY_COLUMNS: Final = (
    "source_id",
    "name",
    "source_type",
    "jurisdiction_code",
    "organization_name",
    "publisher_oid",
    "base_url",
    "entry_url",
    "canonical_host",
    "official_status",
    "access_method",
    "connection_status",
    "enabled",
    "reviewed_at",
    "review_note",
    "created_at",
    "updated_at",
)
_LEGACY_SOURCE_DOCUMENT_COLUMNS: Final = (
    "document_id",
    "canonical_url",
    "title",
    "document_type",
    "jurisdiction_code",
    "publisher_name",
    "publisher_oid",
    "current_content_hash",
    "storage_ref",
    "http_status",
    "published_at",
    "source_updated_at",
    "first_seen_at",
    "last_seen_at",
    "last_changed_at",
    "retrieved_at",
    "review_status",
    "simplified_script_detected",
    "created_at",
    "updated_at",
)
_SOURCE_DOCUMENT_COLUMNS: Final = _LEGACY_SOURCE_DOCUMENT_COLUMNS + ("effective_at",)
_DOCUMENT_DISCOVERY_COLUMNS: Final = (
    "document_id",
    "source_id",
    "discovery_url",
    "discovery_method",
    "first_seen_at",
    "last_seen_at",
    "last_sync_run_id",
)


def _migration_checksum(migration_id: str, payload: bytes) -> str:
    helper_identity = {
        _PROGRAMS_FIELDS_MIGRATION_ID: _PROGRAMS_FIELDS_HELPER_IDENTITY,
        _RULES_EVIDENCE_MIGRATION_ID: _RULES_EVIDENCE_HELPER_IDENTITY,
        _REFRESH_COMPATIBILITY_MIGRATION_ID: (_REFRESH_COMPATIBILITY_HELPER_IDENTITY),
        _LEGACY_RULES_MIGRATION_ID: (
            f"{_LEGACY_RULES_HELPER_IDENTITY}:converter={CONVERTER_VERSION}"
        ),
    }.get(migration_id)
    if helper_identity is None:
        return hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(
        payload + b"\0implementation:" + helper_identity.encode()
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


def _rules_evidence_legacy_plan(connection: sqlite3.Connection) -> bool:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    source_tables = {"source_registry", "source_documents", "document_discoveries"}
    present = tables & source_tables
    if not present:
        return False
    if present != source_tables:
        raise MigrationError("legacy_schema_unsupported")

    _require_legacy_table(
        connection,
        "source_registry",
        columns=_LEGACY_SOURCE_REGISTRY_COLUMNS,
        sql_fragments=(
            "source_type IN ('reference_dataset','benefit_index','agency_site',"
            "'law_database','document_repository','other')",
            "official_status IN ('pending_review','verified_official',"
            "'confirmed_non_taiwan_government','confirmed_commercial')",
            "enabled IN (0,1)",
        ),
        indexes=frozenset(
            {
                "idx_source_registry_connection_status",
                "idx_source_registry_canonical_host",
            }
        ),
    )

    document_columns = _table_columns(connection, "source_documents")
    if document_columns not in {
        _LEGACY_SOURCE_DOCUMENT_COLUMNS,
        _SOURCE_DOCUMENT_COLUMNS,
    }:
        raise MigrationError("legacy_schema_unsupported")
    _require_legacy_table(
        connection,
        "source_documents",
        columns=document_columns,
        sql_fragments=(
            "canonical_url TEXT NOT NULL UNIQUE",
            "review_status IN ('candidate','under_review','verified','rejected',"
            "'stale','status_unknown')",
            "simplified_script_detected IN (0,1)",
        ),
        indexes=frozenset(
            {
                "idx_source_documents_review_status",
                "idx_source_documents_publisher_oid",
            }
        ),
    )
    _require_legacy_table(
        connection,
        "document_discoveries",
        columns=_DOCUMENT_DISCOVERY_COLUMNS,
        sql_fragments=(
            "PRIMARY KEY (document_id,source_id)",
            "REFERENCES source_documents (document_id)",
            "REFERENCES source_registry (source_id)",
        ),
        indexes=frozenset({"idx_document_discoveries_source_id"}),
    )
    return document_columns == _LEGACY_SOURCE_DOCUMENT_COLUMNS


_ACTIVE_PROGRAM_RULE_FIELDS_VIEW_SQL: Final = """
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
  ON active.generation_id = projection_row.generation_id;

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
"""

_LEGACY_RULE_FIELDS_READ_ONLY_SQL: Final = """
CREATE TRIGGER trg_program_rule_fields_read_only_insert
BEFORE INSERT ON program_rule_fields
BEGIN
    SELECT RAISE(ABORT, 'read-only legacy rule fields pending preservation');
END;

CREATE TRIGGER trg_program_rule_fields_read_only_update
BEFORE UPDATE ON program_rule_fields
BEGIN
    SELECT RAISE(ABORT, 'read-only legacy rule fields pending preservation');
END;

CREATE TRIGGER trg_program_rule_fields_read_only_delete
BEFORE DELETE ON program_rule_fields
BEGIN
    SELECT RAISE(ABORT, 'read-only legacy rule fields pending preservation');
END;
"""


def _program_rule_fields_object_type(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        "SELECT type FROM sqlite_master WHERE name = 'program_rule_fields'"
    ).fetchone()
    return None if row is None else str(row[0])


def _require_supported_legacy_rule_fields(connection: sqlite3.Connection) -> None:
    _require_legacy_table(
        connection,
        "program_rule_fields",
        columns=_LEGACY_RULE_FIELDS_COLUMNS,
        sql_fragments=(
            "field_type IN ('text','integer','number','boolean','json','date')",
            "review_status IN ('pending','verified','rejected')",
            "PRIMARY KEY (program_id,field_name)",
            "REFERENCES benefit_programs (program_id)",
        ),
        indexes=frozenset({"idx_program_rule_fields_field_name"}),
    )


def _refresh_compatibility_legacy_plan(connection: sqlite3.Connection) -> str:
    object_type = _program_rule_fields_object_type(connection)
    if object_type is None:
        return "fresh"
    if object_type == "table":
        _require_supported_legacy_rule_fields(connection)
        return "legacy"
    raise MigrationError("legacy_schema_unsupported")


def _refresh_compatibility_suffix(plan: str) -> str:
    if plan == "fresh":
        return _ACTIVE_PROGRAM_RULE_FIELDS_VIEW_SQL
    if plan == "legacy":
        return _LEGACY_RULE_FIELDS_READ_ONLY_SQL
    raise MigrationError("legacy_schema_unsupported")


def _legacy_rules_preservation_plan(connection: sqlite3.Connection) -> str:
    if _table_exists(connection, "legacy_program_rule_fields_v1"):
        raise MigrationError("legacy_schema_unsupported")
    object_type = _program_rule_fields_object_type(connection)
    if object_type == "table":
        _require_supported_legacy_rule_fields(connection)
        return "legacy"
    if object_type == "view":
        columns = _table_columns(connection, "program_rule_fields")
        if columns != _LEGACY_RULE_FIELDS_COLUMNS:
            raise MigrationError("legacy_schema_unsupported")
        return "fresh"
    raise MigrationError("legacy_schema_unsupported")


def _legacy_rules_prefix(plan: str) -> str:
    drop_triggers = """
DROP TRIGGER trg_program_rule_fields_read_only_insert;
DROP TRIGGER trg_program_rule_fields_read_only_update;
DROP TRIGGER trg_program_rule_fields_read_only_delete;
"""
    if plan == "legacy":
        return (
            f"{drop_triggers}\n"
            "ALTER TABLE program_rule_fields "
            "RENAME TO legacy_program_rule_fields_v1;"
        )
    if plan == "fresh":
        return f"{drop_triggers}\nDROP VIEW program_rule_fields;"
    raise MigrationError("legacy_schema_unsupported")


def _migration_script(
    connection: sqlite3.Connection,
    migration: Migration,
) -> str:
    if migration.migration_id == _PROGRAMS_FIELDS_MIGRATION_ID:
        plan = _programs_fields_legacy_plan(connection)
        prefix = _legacy_programs_prefix(plan)
        suffix = _legacy_programs_suffix(plan)
        return f"{prefix}\n{migration.sql}\n{suffix}\n"
    if migration.migration_id == _RULES_EVIDENCE_MIGRATION_ID:
        add_effective_at = _rules_evidence_legacy_plan(connection)
        prefix = (
            "ALTER TABLE source_documents ADD COLUMN effective_at TEXT;"
            if add_effective_at
            else ""
        )
        return f"{prefix}\n{migration.sql}\n"
    if migration.migration_id == _REFRESH_COMPATIBILITY_MIGRATION_ID:
        plan = _refresh_compatibility_legacy_plan(connection)
        suffix = _refresh_compatibility_suffix(plan)
        return f"{migration.sql}\n{suffix}\n"
    if migration.migration_id == _LEGACY_RULES_MIGRATION_ID:
        plan = _legacy_rules_preservation_plan(connection)
        prefix = _legacy_rules_prefix(plan)
        return f"{prefix}\n{migration.sql}\n"
    return f"{migration.sql}\n"


def _execute_script_in_current_transaction(
    connection: sqlite3.Connection,
    script: str,
) -> None:
    """Execute complete SQLite statements without executescript's implicit commit."""

    buffer: list[str] = []
    for character in script:
        buffer.append(character)
        if character != ";":
            continue
        statement = "".join(buffer)
        if sqlite3.complete_statement(statement):
            connection.execute(statement)
            buffer.clear()
    if "".join(buffer).strip():
        raise MigrationError("migration_script_invalid")


def _validate_graph_target(connection: sqlite3.Connection) -> None:
    required_tables = {
        "graph_nodes",
        "graph_edges",
        "graph_edge_conditions",
        "graph_versions",
    }
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if not required_tables.issubset(tables):
        raise MigrationError("migration_target_invalid")

    expected_tables = {
        "graph_nodes": (
            ("node_id", "node_type", "display_name", "program_id"),
            (
                "node_id TEXT PRIMARY KEY NOT NULL",
                "node_type IN ('life_event','insurance_system','benefit_program',"
                "'agency','document_requirement')",
                "trim(display_name) != ''",
                "node_type = 'benefit_program' AND program_id IS NOT NULL",
                "node_type != 'benefit_program' AND program_id IS NULL",
                "REFERENCES benefit_programs (program_id)",
            ),
        ),
        "graph_edges": (
            (
                "edge_id",
                "from_node_id",
                "to_node_id",
                "edge_type",
                "canonical_order",
            ),
            (
                "edge_id TEXT PRIMARY KEY NOT NULL",
                "edge_type IN ('triggers','belongs_to','requires','produces',"
                "'administered_by')",
                "canonical_order >= 0",
                "UNIQUE (from_node_id, to_node_id, edge_type)",
                "REFERENCES graph_nodes (node_id)",
            ),
        ),
        "graph_edge_conditions": (
            (
                "edge_id",
                "condition_id",
                "field_id",
                "operator",
                "expected_value_type",
                "expected_value_json",
                "condition_order",
            ),
            (
                "PRIMARY KEY (edge_id, condition_id)",
                "trim(operator) != ''",
                "expected_value_type IN ('string','integer','number','boolean','null')",
                "json_valid(expected_value_json) = 0",
                "json_type(expected_value_json) = 'integer'",
                "json_type(expected_value_json) IN ('integer', 'real')",
                "json_type(expected_value_json) IN ('true', 'false')",
                "condition_order >= 0",
                "REFERENCES graph_edges (edge_id)",
                "REFERENCES field_registry (field_id)",
            ),
        ),
        "graph_versions": (
            (
                "graph_version",
                "revision_id",
                "approved_by",
                "approved_at",
                "is_current",
            ),
            (
                "graph_version TEXT PRIMARY KEY NOT NULL",
                "trim(approved_by) != ''",
                "trim(approved_at) != ''",
                "is_current IN (0, 1)",
                "REFERENCES catalog_revisions (revision_id)",
            ),
        ),
    }
    for table_name, (columns, sql_fragments) in expected_tables.items():
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

    require_index(
        "graph_nodes",
        "uq_graph_nodes_program_id",
        columns=("program_id",),
        unique=True,
        partial=True,
        sql_fragments=("WHERE program_id IS NOT NULL",),
    )
    require_index(
        "graph_edges",
        "idx_graph_edges_from_type_order",
        columns=("from_node_id", "edge_type", "canonical_order", "to_node_id"),
    )
    require_index(
        "graph_edges",
        "idx_graph_edges_to_type",
        columns=("to_node_id", "edge_type"),
    )
    require_index(
        "graph_edge_conditions",
        "idx_graph_edge_conditions_order",
        columns=("edge_id", "condition_order", "condition_id"),
    )
    require_index(
        "graph_versions",
        "uq_graph_versions_current",
        columns=("is_current",),
        unique=True,
        partial=True,
        sql_fragments=("WHERE is_current = 1",),
    )

    required_foreign_keys = {
        (
            "graph_nodes",
            "program_id",
            "benefit_programs",
            "program_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "graph_edges",
            "from_node_id",
            "graph_nodes",
            "node_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "graph_edges",
            "to_node_id",
            "graph_nodes",
            "node_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "graph_edge_conditions",
            "edge_id",
            "graph_edges",
            "edge_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "graph_edge_conditions",
            "field_id",
            "field_registry",
            "field_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "graph_versions",
            "revision_id",
            "catalog_revisions",
            "revision_id",
            "CASCADE",
            "RESTRICT",
        ),
    }
    actual_foreign_keys: set[tuple[str, str, str, str, str, str]] = set()
    for table_name in required_tables:
        quoted_table = table_name.replace('"', '""')
        for row in connection.execute(f'PRAGMA foreign_key_list("{quoted_table}")'):
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
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise MigrationError("migration_target_invalid")


def _validate_rules_evidence_target(connection: sqlite3.Connection) -> None:
    required_tables = {
        "source_registry",
        "source_documents",
        "document_discoveries",
        "source_domain_tags",
        "rule_definitions",
        "rule_versions",
        "rule_nodes",
        "rule_conditions",
        "rule_required_fields",
        "rule_version_source_refs",
        "approved_amounts",
        "evidence_excerpts",
        "program_evidence_links",
        "source_reference_evidence",
        "document_attachments",
    }
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    if not required_tables.issubset(tables):
        raise MigrationError("migration_target_invalid")

    expected_tables = {
        "source_registry": (
            _LEGACY_SOURCE_REGISTRY_COLUMNS,
            (
                "source_id TEXT PRIMARY KEY",
                "official_status IN ('pending_review','verified_official',"
                "'confirmed_non_taiwan_government','confirmed_commercial')",
                "enabled IN (0,1)",
            ),
        ),
        "source_documents": (
            _SOURCE_DOCUMENT_COLUMNS,
            (
                "document_id TEXT PRIMARY KEY",
                "canonical_url TEXT NOT NULL UNIQUE",
                "review_status IN ('candidate','under_review','verified','rejected',"
                "'stale','status_unknown')",
                "simplified_script_detected IN (0,1)",
            ),
        ),
        "document_discoveries": (
            _DOCUMENT_DISCOVERY_COLUMNS,
            (
                "PRIMARY KEY (document_id,source_id)",
                "REFERENCES source_documents (document_id)",
                "REFERENCES source_registry (source_id)",
            ),
        ),
        "source_domain_tags": (
            ("source_id", "domain_tag"),
            (
                "PRIMARY KEY (source_id,domain_tag)",
                "trim(domain_tag) != ''",
                "REFERENCES source_registry (source_id)",
            ),
        ),
        "rule_definitions": (
            ("rule_id", "program_id"),
            (
                "rule_id TEXT PRIMARY KEY NOT NULL",
                "program_id TEXT NOT NULL UNIQUE",
                "REFERENCES benefit_programs (program_id)",
            ),
        ),
        "rule_versions": (
            (
                "rule_version_id",
                "rule_id",
                "version",
                "dsl_version",
                "approval_status",
                "is_current",
                "root_node_id",
                "created_at",
                "approved_by",
                "approved_at",
            ),
            (
                "rule_version_id TEXT PRIMARY KEY NOT NULL",
                "approval_status IN ('candidate','under_review','approved','rejected')",
                "is_current IN (0,1)",
                "approval_status = 'approved'",
                "approval_status != 'approved' AND is_current = 0",
                "UNIQUE (rule_id,version)",
                "REFERENCES rule_definitions (rule_id)",
                "REFERENCES rule_nodes (node_id,rule_version_id)",
                "DEFERRABLE INITIALLY DEFERRED",
            ),
        ),
        "rule_nodes": (
            (
                "node_id",
                "rule_version_id",
                "parent_node_id",
                "node_type",
                "child_order",
            ),
            (
                "node_type IN ('all_of','any_of','condition')",
                "child_order >= 0",
                "UNIQUE (rule_version_id,parent_node_id,child_order)",
                "REFERENCES rule_versions (rule_version_id)",
                "REFERENCES rule_nodes (node_id,rule_version_id)",
            ),
        ),
        "rule_conditions": (
            (
                "condition_id",
                "node_id",
                "field_id",
                "operator",
                "expected_value_type",
                "expected_value_json",
                "label",
                "source_reference",
            ),
            (
                "condition_id TEXT PRIMARY KEY NOT NULL",
                "node_id TEXT NOT NULL UNIQUE",
                "trim(operator) != ''",
                "expected_value_type IN ('string','integer','number','boolean','null')",
                "json_valid(expected_value_json) = 0",
                "json_type(expected_value_json) IN ('true','false')",
                "REFERENCES rule_nodes (node_id)",
                "REFERENCES field_registry (field_id)",
            ),
        ),
        "rule_required_fields": (
            ("rule_version_id", "field_id", "canonical_order"),
            (
                "PRIMARY KEY (rule_version_id,field_id)",
                "UNIQUE (rule_version_id,canonical_order)",
                "canonical_order >= 0",
                "REFERENCES rule_versions (rule_version_id)",
                "REFERENCES field_registry (field_id)",
            ),
        ),
        "rule_version_source_refs": (
            ("rule_version_id", "source_reference"),
            (
                "PRIMARY KEY (rule_version_id,source_reference)",
                "trim(source_reference) != ''",
                "REFERENCES rule_versions (rule_version_id)",
            ),
        ),
        "approved_amounts": (
            (
                "rule_version_id",
                "amount_min",
                "amount_max",
                "amount_period",
                "amount_currency",
                "source_reference",
            ),
            (
                "rule_version_id TEXT PRIMARY KEY NOT NULL",
                "typeof(amount_min) IN ('integer','real')",
                "typeof(amount_max) IN ('integer','real')",
                "amount_min <= amount_max",
                "REFERENCES rule_versions (rule_version_id)",
                (
                    "REFERENCES rule_version_source_refs "
                    "(rule_version_id,source_reference)"
                ),
            ),
        ),
        "evidence_excerpts": (
            (
                "evidence_id",
                "document_id",
                "excerpt",
                "review_status",
                "reviewer_ref",
                "reviewed_at",
                "created_at",
                "updated_at",
            ),
            (
                "evidence_id TEXT PRIMARY KEY NOT NULL",
                "review_status IN ('candidate','under_review','verified','rejected')",
                "review_status != 'verified'",
                "trim(excerpt) != ''",
                "REFERENCES source_documents (document_id)",
            ),
        ),
        "program_evidence_links": (
            (
                "program_id",
                "evidence_id",
                "evidence_role",
                "review_status",
                "reviewer_ref",
                "reviewed_at",
            ),
            (
                "PRIMARY KEY (program_id,evidence_id,evidence_role)",
                "review_status IN ('candidate','under_review','verified','rejected')",
                "review_status != 'verified'",
                "REFERENCES benefit_programs (program_id)",
                "REFERENCES evidence_excerpts (evidence_id)",
            ),
        ),
        "source_reference_evidence": (
            ("rule_version_id", "source_reference", "evidence_id"),
            (
                "PRIMARY KEY (rule_version_id,source_reference,evidence_id)",
                "REFERENCES rule_version_source_refs "
                "(rule_version_id,source_reference)",
                "REFERENCES evidence_excerpts (evidence_id)",
            ),
        ),
        "document_attachments": (
            (
                "attachment_id",
                "document_id",
                "filename",
                "media_type",
                "source_url",
                "storage_backend",
                "storage_ref",
                "content_hash",
                "extraction_status",
                "extraction_method",
                "extracted_at",
                "review_status",
                "reviewer_ref",
                "reviewed_at",
                "created_at",
                "updated_at",
            ),
            (
                "attachment_id TEXT PRIMARY KEY NOT NULL",
                "storage_backend IS NULL OR storage_backend IN ('local','s3')",
                "extraction_status IN ('pending','extracted','failed',"
                "'not_applicable')",
                "review_status IN ('candidate','under_review','verified','rejected')",
                "extraction_status != 'extracted'",
                "review_status != 'verified'",
                "REFERENCES source_documents (document_id)",
            ),
        ),
    }
    for table_name, (columns, sql_fragments) in expected_tables.items():
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

    indexes = (
        (
            "source_registry",
            "idx_source_registry_connection_status",
            ("connection_status",),
            False,
            False,
            (),
        ),
        (
            "source_registry",
            "idx_source_registry_canonical_host",
            ("canonical_host",),
            False,
            False,
            (),
        ),
        (
            "source_documents",
            "idx_source_documents_review_status",
            ("review_status",),
            False,
            False,
            (),
        ),
        (
            "source_documents",
            "idx_source_documents_publisher_oid",
            ("publisher_oid",),
            False,
            False,
            (),
        ),
        (
            "document_discoveries",
            "idx_document_discoveries_source_id",
            ("source_id",),
            False,
            False,
            (),
        ),
        (
            "source_domain_tags",
            "idx_source_domain_tags_tag_source",
            ("domain_tag", "source_id"),
            False,
            False,
            (),
        ),
        (
            "rule_versions",
            "uq_rule_versions_current_approved",
            ("rule_id",),
            True,
            True,
            ("WHERE is_current = 1 AND approval_status = 'approved'",),
        ),
        (
            "rule_versions",
            "idx_rule_versions_rule_status_version",
            ("rule_id", "approval_status", "version"),
            False,
            False,
            (),
        ),
        (
            "rule_nodes",
            "uq_rule_nodes_root_per_version",
            ("rule_version_id",),
            True,
            True,
            ("WHERE parent_node_id IS NULL",),
        ),
        (
            "rule_nodes",
            "idx_rule_nodes_parent_order",
            ("rule_version_id", "parent_node_id", "child_order", "node_id"),
            False,
            False,
            (),
        ),
        (
            "rule_conditions",
            "idx_rule_conditions_field_id",
            ("field_id", "condition_id"),
            False,
            False,
            (),
        ),
        (
            "rule_required_fields",
            "idx_rule_required_fields_order",
            ("rule_version_id", "canonical_order", "field_id"),
            False,
            False,
            (),
        ),
        (
            "evidence_excerpts",
            "idx_evidence_excerpts_document_status",
            ("document_id", "review_status", "evidence_id"),
            False,
            False,
            (),
        ),
        (
            "program_evidence_links",
            "idx_program_evidence_links_evidence_status",
            ("evidence_id", "review_status", "program_id"),
            False,
            False,
            (),
        ),
        (
            "source_reference_evidence",
            "idx_source_reference_evidence_evidence",
            ("evidence_id", "rule_version_id", "source_reference"),
            False,
            False,
            (),
        ),
        (
            "document_attachments",
            "idx_document_attachments_document_status",
            ("document_id", "review_status", "attachment_id"),
            False,
            False,
            (),
        ),
        (
            "document_attachments",
            "idx_document_attachments_extraction_status",
            ("extraction_status", "attachment_id"),
            False,
            False,
            (),
        ),
    )
    for table_name, index_name, columns, unique, partial, fragments in indexes:
        require_index(
            table_name,
            index_name,
            columns=columns,
            unique=unique,
            partial=partial,
            sql_fragments=fragments,
        )

    required_foreign_keys = {
        (
            "document_discoveries",
            "document_id",
            "source_documents",
            "document_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "document_discoveries",
            "source_id",
            "source_registry",
            "source_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "source_domain_tags",
            "source_id",
            "source_registry",
            "source_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "rule_definitions",
            "program_id",
            "benefit_programs",
            "program_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "rule_versions",
            "rule_id",
            "rule_definitions",
            "rule_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "rule_versions",
            "root_node_id",
            "rule_nodes",
            "node_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "rule_nodes",
            "rule_version_id",
            "rule_versions",
            "rule_version_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "rule_nodes",
            "parent_node_id",
            "rule_nodes",
            "node_id",
            "CASCADE",
            "RESTRICT",
        ),
        ("rule_conditions", "node_id", "rule_nodes", "node_id", "CASCADE", "RESTRICT"),
        (
            "rule_conditions",
            "field_id",
            "field_registry",
            "field_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "rule_required_fields",
            "rule_version_id",
            "rule_versions",
            "rule_version_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "rule_required_fields",
            "field_id",
            "field_registry",
            "field_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "rule_version_source_refs",
            "rule_version_id",
            "rule_versions",
            "rule_version_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "approved_amounts",
            "rule_version_id",
            "rule_versions",
            "rule_version_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "approved_amounts",
            "source_reference",
            "rule_version_source_refs",
            "source_reference",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "evidence_excerpts",
            "document_id",
            "source_documents",
            "document_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "program_evidence_links",
            "program_id",
            "benefit_programs",
            "program_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "program_evidence_links",
            "evidence_id",
            "evidence_excerpts",
            "evidence_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "source_reference_evidence",
            "source_reference",
            "rule_version_source_refs",
            "source_reference",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "source_reference_evidence",
            "evidence_id",
            "evidence_excerpts",
            "evidence_id",
            "CASCADE",
            "RESTRICT",
        ),
        (
            "document_attachments",
            "document_id",
            "source_documents",
            "document_id",
            "CASCADE",
            "RESTRICT",
        ),
    }
    actual_foreign_keys: set[tuple[str, str, str, str, str, str]] = set()
    for table_name in required_tables:
        quoted_table = table_name.replace('"', '""')
        for row in connection.execute(f'PRAGMA foreign_key_list("{quoted_table}")'):
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

    required_triggers = {
        "trg_evidence_excerpts_verified_source_insert": (
            "beforeinserton evidence_excerpts",
            "verified evidence requires verified official source",
        ),
        "trg_evidence_excerpts_verified_source_update": (
            "beforeupdateof document_id, review_statuson evidence_excerpts",
            "verified evidence requires verified official source",
        ),
        "trg_program_evidence_links_verified_insert": (
            "beforeinserton program_evidence_links",
            "verified program link requires verified evidence",
        ),
        "trg_program_evidence_links_verified_update": (
            "beforeupdateof evidence_id, review_statuson program_evidence_links",
            "verified program link requires verified evidence",
        ),
    }
    for trigger_name, fragments in required_triggers.items():
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger_name,),
        ).fetchone()
        trigger_sql = "" if row is None or row[0] is None else _compact_sql(str(row[0]))
        if any(_compact_sql(fragment) not in trigger_sql for fragment in fragments):
            raise MigrationError("migration_target_invalid")

    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise MigrationError("migration_target_invalid")


def _require_target_table(
    connection: sqlite3.Connection,
    table_name: str,
    *,
    columns: tuple[str, ...],
    sql_fragments: tuple[str, ...],
    indexes: frozenset[str],
) -> None:
    if _table_columns(connection, table_name) != columns:
        raise MigrationError("migration_target_invalid")
    table_sql = _table_sql(connection, table_name)
    if any(_compact_sql(fragment) not in table_sql for fragment in sql_fragments):
        raise MigrationError("migration_target_invalid")
    if _named_indexes(connection, table_name) != set(indexes):
        raise MigrationError("migration_target_invalid")


def _require_trigger(
    connection: sqlite3.Connection,
    trigger_name: str,
    *fragments: str,
) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
        (trigger_name,),
    ).fetchone()
    trigger_sql = "" if row is None or row[0] is None else _compact_sql(str(row[0]))
    if any(_compact_sql(fragment) not in trigger_sql for fragment in fragments):
        raise MigrationError("migration_target_invalid")


def _validate_program_rule_fields_read_only(
    connection: sqlite3.Connection,
    *,
    require_legacy_bridge: bool,
) -> None:
    object_type = _program_rule_fields_object_type(connection)
    if object_type == "table" and not require_legacy_bridge:
        try:
            _require_supported_legacy_rule_fields(connection)
        except MigrationError as exc:
            raise MigrationError("migration_target_invalid") from exc
        trigger_prefixes = ("before insert", "before update", "before delete")
    elif object_type == "view":
        if _table_columns(connection, "program_rule_fields") != (
            _LEGACY_RULE_FIELDS_COLUMNS
        ):
            raise MigrationError("migration_target_invalid")
        view_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'view' AND name = ?",
            ("program_rule_fields",),
        ).fetchone()
        view_sql = (
            ""
            if view_row is None or view_row[0] is None
            else _compact_sql(str(view_row[0]))
        )
        required_view_fragments = [
            "from compat_projection_rows as projection_row",
            "join compat_projection_active as active",
        ]
        if require_legacy_bridge:
            required_view_fragments.extend(
                (
                    "union all",
                    "from legacy_program_rule_fields_v1 as legacy",
                    "where not exists",
                    "where generation.program_id = legacy.program_id",
                )
            )
        if any(
            _compact_sql(fragment) not in view_sql
            for fragment in required_view_fragments
        ):
            raise MigrationError("migration_target_invalid")
        trigger_prefixes = (
            "instead of insert",
            "instead of update",
            "instead of delete",
        )
    else:
        raise MigrationError("migration_target_invalid")

    for action, trigger_name in zip(
        trigger_prefixes,
        (
            "trg_program_rule_fields_read_only_insert",
            "trg_program_rule_fields_read_only_update",
            "trg_program_rule_fields_read_only_delete",
        ),
        strict=True,
    ):
        _require_trigger(
            connection,
            trigger_name,
            f"{action} on program_rule_fields",
            "raise(abort,",
        )


def _validate_projection_ownership_behavior(
    connection: sqlite3.Connection,
) -> None:
    token_row = connection.execute("SELECT lower(hex(randomblob(16)))").fetchone()
    if token_row is None:
        raise MigrationError("migration_target_invalid")
    token = str(token_row[0])
    program_a = f"__projection_owner_a_{token}"
    program_b = f"__projection_owner_b_{token}"
    program_c = f"__projection_owner_c_{token}"
    rule_a = f"__projection_rule_a_{token}"
    rule_b = f"__projection_rule_b_{token}"
    version_a = f"__projection_version_a_{token}"
    version_b = f"__projection_version_b_{token}"
    generation_id = f"__projection_generation_{token}"
    timestamp = "2000-01-01T00:00:00+00:00"

    def require_rejection(sql: str, parameters: tuple[object, ...]) -> None:
        try:
            connection.execute(sql, parameters)
        except sqlite3.IntegrityError:
            return
        raise MigrationError("migration_target_invalid")

    connection.execute("SAVEPOINT validate_projection_ownership")
    try:
        connection.executemany(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                (program_a, "Synthetic ownership A", timestamp, timestamp),
                (program_b, "Synthetic ownership B", timestamp, timestamp),
                (program_c, "Synthetic ownership C", timestamp, timestamp),
            ),
        )
        connection.executemany(
            "INSERT INTO rule_definitions VALUES (?, ?)",
            ((rule_a, program_a), (rule_b, program_b)),
        )
        connection.executemany(
            """
            INSERT INTO rule_versions (
                rule_version_id, rule_id, version, dsl_version,
                approval_status, is_current, created_at
            ) VALUES (?, ?, '1', 'validation', 'candidate', 0, ?)
            """,
            ((version_a, rule_a, timestamp), (version_b, rule_b, timestamp)),
        )
        require_rejection(
            """
            INSERT INTO compat_projection_generations (
                generation_id, rule_version_id, program_id,
                converter_version, canonical_hash, created_at
            ) VALUES (?, ?, ?, 'validation', ?, ?)
            """,
            (
                f"{generation_id}_invalid",
                version_a,
                program_b,
                "a" * 64,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO compat_projection_generations (
                generation_id, rule_version_id, program_id,
                converter_version, canonical_hash, created_at
            ) VALUES (?, ?, ?, 'validation', ?, ?)
            """,
            (generation_id, version_a, program_a, "b" * 64, timestamp),
        )
        require_rejection(
            """
            UPDATE compat_projection_generations
            SET program_id = ?
            WHERE generation_id = ?
            """,
            (program_b, generation_id),
        )
        require_rejection(
            "UPDATE rule_definitions SET program_id = ? WHERE rule_id = ?",
            (program_c, rule_a),
        )
        require_rejection(
            "UPDATE rule_versions SET rule_id = ? WHERE rule_version_id = ?",
            (rule_b, version_a),
        )
    finally:
        connection.execute("ROLLBACK TO validate_projection_ownership")
        connection.execute("RELEASE validate_projection_ownership")


def _validate_refresh_compatibility_target(
    connection: sqlite3.Connection,
) -> None:
    expected_tables = {
        "source_crawl_attempts": (
            (
                "attempt_id",
                "source_id",
                "status",
                "started_at",
                "completed_at",
                "gap_category",
                "safe_error_code",
                "indexed_document_count",
            ),
            (
                "attempt_id TEXT PRIMARY KEY NOT NULL",
                "status IN ('running','completed','failed')",
                "indexed_document_count >= 0",
                "REFERENCES source_registry (source_id)",
            ),
            frozenset(
                {
                    "idx_source_crawl_attempts_source_completed",
                    "idx_source_crawl_attempts_status_started",
                }
            ),
        ),
        "source_coverage_state": (
            (
                "source_id",
                "crawl_status",
                "last_successful_crawl_at",
                "indexed_document_count",
                "last_gap_category",
                "updated_revision_id",
                "updated_at",
            ),
            (
                "source_id TEXT PRIMARY KEY NOT NULL",
                "crawl_status IN ('pending_crawl','crawled','error')",
                "indexed_document_count >= 0",
                "REFERENCES source_registry (source_id)",
                "REFERENCES catalog_revisions (revision_id)",
            ),
            frozenset({"idx_source_coverage_state_status_source"}),
        ),
        "coverage_snapshots": (
            (
                "snapshot_id",
                "observed_at",
                "scope_source_ids_json",
                "scope_domain_tags_json",
                "scope_hash",
                "created_revision_id",
            ),
            (
                "snapshot_id TEXT PRIMARY KEY NOT NULL",
                "json_type(scope_source_ids_json) = 'array'",
                "json_type(scope_domain_tags_json) = 'array'",
                "length(scope_hash) = 64",
                "REFERENCES catalog_revisions (revision_id)",
            ),
            frozenset(
                {
                    "idx_coverage_snapshots_observed",
                    "idx_coverage_snapshots_scope_hash",
                }
            ),
        ),
        "coverage_snapshot_sources": (
            (
                "snapshot_id",
                "source_id",
                "crawl_status",
                "last_successful_crawl_at",
                "indexed_document_count",
                "domain_tags_json",
                "gap_category",
            ),
            (
                "PRIMARY KEY (snapshot_id,source_id)",
                "crawl_status IN ('pending_crawl','crawled','error')",
                "json_type(domain_tags_json) = 'array'",
                "indexed_document_count >= 0",
                "REFERENCES coverage_snapshots (snapshot_id)",
                "REFERENCES source_registry (source_id)",
            ),
            frozenset({"idx_coverage_snapshot_sources_source_snapshot"}),
        ),
        "refresh_jobs": (
            (
                "job_id",
                "source_id",
                "event_id",
                "local_calendar_date",
                "dedup_key",
                "status",
                "requested_at",
                "started_at",
                "completed_at",
                "safe_error_code",
            ),
            (
                "PRIMARY KEY (job_id,source_id)",
                "UNIQUE (source_id,event_id,local_calendar_date)",
                "status IN ('queued','running','completed','failed')",
                "date(local_calendar_date) = local_calendar_date",
                "REFERENCES source_registry (source_id)",
            ),
            frozenset(
                {
                    "idx_refresh_jobs_status_requested",
                    "idx_refresh_jobs_event_date",
                }
            ),
        ),
        "compat_projection_generations": (
            (
                "generation_id",
                "rule_version_id",
                "program_id",
                "converter_version",
                "canonical_hash",
                "status",
                "row_count",
                "created_at",
                "validated_at",
            ),
            (
                "generation_id TEXT PRIMARY KEY NOT NULL",
                "status IN ('building','validated')",
                "row_count >= 0",
                "REFERENCES rule_versions (rule_version_id)",
                "REFERENCES benefit_programs (program_id)",
            ),
            frozenset({"idx_compat_projection_generations_rule_status"}),
        ),
        "compat_projection_rows": (
            (
                "generation_id",
                "ordinal",
                "program_id",
                "field_name",
                "field_type",
                "field_value",
                "source_excerpt",
                "review_status",
                "created_at",
                "updated_at",
            ),
            (
                "PRIMARY KEY (generation_id,ordinal)",
                "UNIQUE (generation_id,field_name)",
                "ordinal >= 0",
                "REFERENCES compat_projection_generations (generation_id,program_id)",
            ),
            frozenset({"idx_compat_projection_rows_program_field"}),
        ),
        "compat_projection_active": (
            ("program_id", "rule_version_id", "generation_id", "activated_at"),
            (
                "program_id TEXT PRIMARY KEY NOT NULL",
                "rule_version_id TEXT NOT NULL UNIQUE",
                "generation_id TEXT NOT NULL UNIQUE",
                (
                    "REFERENCES compat_projection_generations "
                    "(generation_id,rule_version_id)"
                ),
                ("REFERENCES compat_projection_generations (generation_id,program_id)"),
            ),
            frozenset(),
        ),
    }
    for table_name, (columns, fragments, indexes) in expected_tables.items():
        if not _table_exists(connection, table_name):
            raise MigrationError("migration_target_invalid")
        _require_target_table(
            connection,
            table_name,
            columns=columns,
            sql_fragments=fragments,
            indexes=indexes,
        )

    for trigger_name, action in (
        ("trg_compat_projection_generations_program_insert", "insert"),
        ("trg_compat_projection_generations_program_update", "update of"),
    ):
        _require_trigger(
            connection,
            trigger_name,
            f"before {action}",
            "join rule_definitions as rule_definition",
            "rule_definition.program_id = new.program_id",
            "projection generation program must own rule version",
        )

    _require_trigger(
        connection,
        "trg_rule_definitions_projection_owner_update",
        "before update of program_id on rule_definitions",
        "join compat_projection_generations as generation",
        "new.program_id != old.program_id",
        "cannot change program ownership with projection generations",
    )
    _require_trigger(
        connection,
        "trg_rule_versions_projection_owner_update",
        "before update of rule_id on rule_versions",
        "from compat_projection_generations as generation",
        "new.rule_id != old.rule_id",
        "cannot change rule ownership with projection generations",
    )

    _require_trigger(
        connection,
        "trg_compat_projection_active_validated_insert",
        "before insert on compat_projection_active",
        "generation.program_id = new.program_id",
        "generation.status = 'validated'",
        "count(*)",
    )
    _require_trigger(
        connection,
        "trg_compat_projection_active_validated_update",
        (
            "before update of program_id, rule_version_id, generation_id "
            "on compat_projection_active"
        ),
        "generation.program_id = new.program_id",
        "generation.status = 'validated'",
        "count(*)",
    )
    for action in ("insert", "update", "delete"):
        _require_trigger(
            connection,
            f"trg_compat_projection_rows_immutable_{action}",
            f"before {action} on compat_projection_rows",
            "generation.status = 'validated'",
            "validated projection generation is immutable",
        )
    for action in ("update", "delete"):
        _require_trigger(
            connection,
            f"trg_compat_projection_generations_immutable_{action}",
            f"before {action} on compat_projection_generations",
            "old.status = 'validated'",
            "from compat_projection_active as active",
            "validated projection generation is immutable",
        )
    _validate_projection_ownership_behavior(connection)
    _validate_program_rule_fields_read_only(
        connection,
        require_legacy_bridge=False,
    )
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise MigrationError("migration_target_invalid")


def _validate_legacy_bridge_behavior(connection: sqlite3.Connection) -> None:
    token_row = connection.execute("SELECT lower(hex(randomblob(16)))").fetchone()
    if token_row is None:
        raise MigrationError("migration_target_invalid")
    token = str(token_row[0])
    program_a = f"__bridge_validation_a_{token}"
    program_b = f"__bridge_validation_b_{token}"
    rule_id = f"__bridge_validation_rule_{token}"
    rule_version_id = f"__bridge_validation_version_{token}"
    generation_id = f"__bridge_validation_generation_{token}"
    timestamp = "2000-01-01T00:00:00+00:00"

    connection.execute("SAVEPOINT validate_legacy_bridge")
    try:
        for action in ("insert", "update", "delete"):
            connection.execute(
                f"DROP TRIGGER trg_legacy_program_rule_fields_read_only_{action}"
            )
        connection.executemany(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                (program_a, "Synthetic validation A", timestamp, timestamp),
                (program_b, "Synthetic validation B", timestamp, timestamp),
            ),
        )
        connection.executemany(
            """
            INSERT INTO legacy_program_rule_fields_v1 (
                program_id, field_name, field_type, field_value,
                source_excerpt, review_status, created_at, updated_at
            ) VALUES (?, 'legacy-field', 'text', 'legacy', '', 'pending', ?, ?)
            """,
            (
                (program_a, timestamp, timestamp),
                (program_b, timestamp, timestamp),
            ),
        )
        connection.execute(
            "INSERT INTO rule_definitions VALUES (?, ?)",
            (rule_id, program_a),
        )
        connection.execute(
            """
            INSERT INTO rule_versions (
                rule_version_id, rule_id, version, dsl_version,
                approval_status, is_current, created_at
            ) VALUES (?, ?, '1', 'validation', 'candidate', 0, ?)
            """,
            (rule_version_id, rule_id, timestamp),
        )
        connection.execute(
            """
            INSERT INTO compat_projection_generations (
                generation_id, rule_version_id, program_id,
                converter_version, canonical_hash, status,
                row_count, created_at, validated_at
            ) VALUES (?, ?, ?, 'validation', ?, 'building', 1, ?, NULL)
            """,
            (generation_id, rule_version_id, program_a, "a" * 64, timestamp),
        )
        connection.execute(
            """
            INSERT INTO compat_projection_rows (
                generation_id, ordinal, program_id, field_name,
                field_type, field_value, source_excerpt,
                review_status, created_at, updated_at
            ) VALUES (?, 0, ?, 'canonical-field', 'text', 'canonical',
                      '', 'pending', ?, ?)
            """,
            (generation_id, program_a, timestamp, timestamp),
        )
        connection.execute(
            """
            UPDATE compat_projection_generations
            SET status = 'validated', validated_at = ?
            WHERE generation_id = ?
            """,
            (timestamp, generation_id),
        )
        connection.execute(
            """
            INSERT INTO compat_projection_active (
                program_id, rule_version_id, generation_id, activated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (program_a, rule_version_id, generation_id, timestamp),
        )
        visible_rows = connection.execute(
            """
            SELECT program_id, field_name, field_value
            FROM program_rule_fields
            WHERE program_id IN (?, ?)
            ORDER BY program_id, field_name
            """,
            (program_a, program_b),
        ).fetchall()
        if visible_rows != [
            (program_a, "canonical-field", "canonical"),
            (program_b, "legacy-field", "legacy"),
        ]:
            raise MigrationError("migration_target_invalid")
    finally:
        connection.execute("ROLLBACK TO validate_legacy_bridge")
        connection.execute("RELEASE validate_legacy_bridge")


def _validate_legacy_rules_target(connection: sqlite3.Connection) -> None:
    _validate_refresh_compatibility_target(connection)
    _require_target_table(
        connection,
        "legacy_program_rule_fields_v1",
        columns=_LEGACY_RULE_FIELDS_COLUMNS,
        sql_fragments=(
            "field_type IN ('text','integer','number','boolean','json','date')",
            "review_status IN ('pending','verified','rejected')",
            "PRIMARY KEY (program_id,field_name)",
            "REFERENCES benefit_programs (program_id)",
        ),
        indexes=frozenset({"idx_program_rule_fields_field_name"}),
    )
    _require_target_table(
        connection,
        "legacy_rule_migration_inventory",
        columns=(
            "inventory_id",
            "source_table_name",
            "source_schema_sha256",
            "source_rows_sha256",
            "row_count",
            "converter_version",
            "captured_at",
        ),
        sql_fragments=(
            "inventory_id TEXT PRIMARY KEY NOT NULL",
            "source_table_name = 'program_rule_fields'",
            "length(source_schema_sha256) = 64",
            "length(source_rows_sha256) = 64",
            "row_count >= 0",
        ),
        indexes=frozenset(),
    )
    _require_target_table(
        connection,
        "legacy_rule_conversion_drafts",
        columns=(
            "draft_id",
            "inventory_id",
            "program_id",
            "converter_version",
            "conversion_status",
            "reason_code",
            "source_row_count",
            "source_rows_sha256",
            "created_at",
        ),
        sql_fragments=(
            "draft_id TEXT PRIMARY KEY NOT NULL",
            "conversion_status IN ('candidate','under_review')",
            "source_row_count > 0",
            "REFERENCES legacy_rule_migration_inventory (inventory_id)",
            "REFERENCES benefit_programs (program_id)",
        ),
        indexes=frozenset({"idx_legacy_rule_conversion_drafts_status_program"}),
    )
    for action in ("insert", "update", "delete"):
        _require_trigger(
            connection,
            f"trg_legacy_program_rule_fields_read_only_{action}",
            f"before {action} on legacy_program_rule_fields_v1",
            "read-only preserved legacy rule fields",
        )
    _validate_program_rule_fields_read_only(
        connection,
        require_legacy_bridge=True,
    )
    _validate_legacy_bridge_behavior(connection)
    invalid_draft = connection.execute(
        """
        SELECT 1
        FROM legacy_rule_conversion_drafts
        WHERE conversion_status NOT IN ('candidate', 'under_review')
        LIMIT 1
        """
    ).fetchone()
    if invalid_draft is not None:
        raise MigrationError("migration_target_invalid")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise MigrationError("migration_target_invalid")


def _validate_mvp_catalog_scaffold_target(
    connection: sqlite3.Connection,
) -> None:
    """Validate that exactly the 6 MVP IDs exist with safe defaults."""
    rows = connection.execute(
        """
        SELECT program_id, program_status, amount_min, amount_max,
               amount_period, amount_currency
        FROM benefit_programs
        WHERE program_id IN (?, ?, ?, ?, ?, ?)
        """,
        tuple(sorted(_MVP_CATALOG_IDS)),
    ).fetchall()
    found_ids = {str(row[0]) for row in rows}
    if found_ids != _MVP_CATALOG_IDS:
        raise MigrationError("migration_target_invalid")
    for row in rows:
        status = str(row[1])
        if status not in ("candidate", "under_review"):
            raise MigrationError("migration_target_invalid")
        if any(row[i] is not None for i in range(2, 6)):
            raise MigrationError("migration_target_invalid")


def _validate_migration_target(
    connection: sqlite3.Connection,
    migration: Migration,
) -> None:
    if migration.migration_id == _PROGRAMS_FIELDS_MIGRATION_ID:
        _validate_programs_fields_target(connection)
    elif migration.migration_id == "0003_graph":
        _validate_graph_target(connection)
    elif migration.migration_id == _RULES_EVIDENCE_MIGRATION_ID:
        _validate_rules_evidence_target(connection)
    elif migration.migration_id == _REFRESH_COMPATIBILITY_MIGRATION_ID:
        _validate_refresh_compatibility_target(connection)
    elif migration.migration_id == _LEGACY_RULES_MIGRATION_ID:
        _validate_legacy_rules_target(connection)
    elif migration.migration_id == _MVP_CATALOG_SCAFFOLD_MIGRATION_ID:
        _validate_mvp_catalog_scaffold_target(connection)


def _apply_migration(
    connection: sqlite3.Connection,
    migration: Migration,
    *,
    application_version: str,
) -> None:
    try:
        connection.execute("BEGIN IMMEDIATE")
        script = _migration_script(connection, migration)
        legacy_inventory: LegacyRuleInventory | None = None
        if migration.migration_id == _LEGACY_RULES_MIGRATION_ID:
            legacy_inventory = prepare_legacy_rule_inventory(connection)
        applied_at = datetime.now(UTC).isoformat()

        _execute_script_in_current_transaction(connection, script)
        if migration.migration_id == _LEGACY_RULES_MIGRATION_ID:
            persist_legacy_rule_conversion(
                connection,
                legacy_inventory,
                captured_at=applied_at,
            )
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
                applied_at,
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
        for migration in migration_set:
            if migration.version > current_version:
                break
            _validate_migration_target(connection, migration)
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
