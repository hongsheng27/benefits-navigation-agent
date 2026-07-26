"""SQLite schema and small data helpers for the local benefit catalog.

The catalog is a local/demo adapter. Its records keep storage-neutral IDs and
explicit provenance so a future AWS adapter can preserve the same boundaries.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CATALOG_SCHEMA_VERSION = "1"

SOURCE_TYPES = (
    "reference_dataset",
    "benefit_index",
    "agency_site",
    "law_database",
    "document_repository",
    "other",
)
OFFICIAL_STATUSES = (
    "pending_review",
    "verified_official",
    "confirmed_non_taiwan_government",
    "confirmed_commercial",
)
ACCESS_METHODS = (
    "api",
    "download_file",
    "sitemap",
    "rss",
    "index_page",
    "targeted_crawl",
    "manual_seed",
)
CONNECTION_STATUSES = (
    "pending",
    "active",
    "degraded",
    "failed",
    "paused",
)


@dataclass(frozen=True)
class SourceSeed:
    source_id: str
    name: str
    source_type: str
    jurisdiction_code: str
    organization_name: str
    publisher_oid: str | None
    base_url: str
    entry_url: str
    canonical_host: str
    official_status: str
    access_method: str
    connection_status: str
    enabled: bool
    reviewed_at: str | None
    review_note: str


@dataclass(frozen=True)
class CatalogSummary:
    source_count: int
    source_status_counts: dict[str, int]
    source_sync_run_count: int
    document_count: int
    candidate_program_count: int
    verified_program_count: int
    pending_evidence_count: int


@dataclass(frozen=True)
class RegisteredSourceStatus:
    source_id: str
    name: str
    source_type: str
    access_method: str
    connection_status: str
    document_count: int
    candidate_program_count: int
    verified_program_count: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def initialize_catalog_schema(connection: sqlite3.Connection) -> None:
    """Create benefit catalog tables without inserting source or program data."""

    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS source_registry (
            source_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL
                CHECK (source_type IN ({_sql_values(SOURCE_TYPES)})),
            jurisdiction_code TEXT NOT NULL DEFAULT '',
            organization_name TEXT NOT NULL DEFAULT '',
            publisher_oid TEXT,
            base_url TEXT NOT NULL,
            entry_url TEXT NOT NULL,
            canonical_host TEXT NOT NULL,
            official_status TEXT NOT NULL
                CHECK (official_status IN ({_sql_values(OFFICIAL_STATUSES)})),
            access_method TEXT NOT NULL
                CHECK (access_method IN ({_sql_values(ACCESS_METHODS)})),
            connection_status TEXT NOT NULL
                CHECK (
                    connection_status IN (
                        {_sql_values(CONNECTION_STATUSES)}
                    )
                ),
            enabled INTEGER NOT NULL DEFAULT 1
                CHECK (enabled IN (0, 1)),
            reviewed_at TEXT,
            review_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (publisher_oid)
                REFERENCES government_organizations (oid)
                ON UPDATE CASCADE
                ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_source_registry_connection_status
            ON source_registry (connection_status);

        CREATE INDEX IF NOT EXISTS idx_source_registry_canonical_host
            ON source_registry (canonical_host);

        CREATE TABLE IF NOT EXISTS source_sync_runs (
            sync_run_id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL
                CHECK (
                    status IN (
                        'running',
                        'completed',
                        'partial',
                        'failed'
                    )
                ),
            source_cursor TEXT,
            source_version TEXT,
            discovered_document_count INTEGER NOT NULL DEFAULT 0
                CHECK (discovered_document_count >= 0),
            fetched_document_count INTEGER NOT NULL DEFAULT 0
                CHECK (fetched_document_count >= 0),
            unchanged_document_count INTEGER NOT NULL DEFAULT 0
                CHECK (unchanged_document_count >= 0),
            changed_document_count INTEGER NOT NULL DEFAULT 0
                CHECK (changed_document_count >= 0),
            parse_failed_count INTEGER NOT NULL DEFAULT 0
                CHECK (parse_failed_count >= 0),
            candidate_count INTEGER NOT NULL DEFAULT 0
                CHECK (candidate_count >= 0),
            error_message TEXT,
            FOREIGN KEY (source_id)
                REFERENCES source_registry (source_id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_source_sync_runs_source_started
            ON source_sync_runs (source_id, started_at DESC);

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
            FOREIGN KEY (publisher_oid)
                REFERENCES government_organizations (oid)
                ON UPDATE CASCADE
                ON DELETE RESTRICT
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
                ON DELETE RESTRICT,
            FOREIGN KEY (last_sync_run_id)
                REFERENCES source_sync_runs (sync_run_id)
                ON UPDATE CASCADE
                ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_document_discoveries_source_id
            ON document_discoveries (source_id);

        CREATE TABLE IF NOT EXISTS benefit_programs (
            program_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            support_purpose TEXT
                CHECK (
                    support_purpose IS NULL
                    OR support_purpose IN (
                        'funeral_cost',
                        'one_time_death_support',
                        'survivor_livelihood'
                    )
                ),
            program_basis TEXT
                CHECK (
                    program_basis IS NULL
                    OR program_basis IN (
                        'government_subsidy_or_relief',
                        'social_assistance',
                        'social_insurance',
                        'survivor_pension_or_pension',
                        'legal_compensation',
                        'employer_statutory_payment',
                        'other_or_unknown'
                    )
                ),
            delivery_form TEXT
                CHECK (
                    delivery_form IS NULL
                    OR delivery_form IN (
                        'cash_once',
                        'cash_recurring',
                        'reimbursement',
                        'fee_waiver',
                        'service_or_in_kind',
                        'unknown'
                    )
                ),
            jurisdiction_code TEXT NOT NULL DEFAULT '',
            program_status TEXT NOT NULL DEFAULT 'candidate'
                CHECK (
                    program_status IN (
                        'candidate',
                        'under_review',
                        'verified',
                        'rejected',
                        'stale',
                        'inactive',
                        'status_unknown'
                    )
                ),
            status_note TEXT NOT NULL DEFAULT '',
            expense_proof_requirement TEXT NOT NULL DEFAULT 'unknown'
                CHECK (
                    expense_proof_requirement IN (
                        'required',
                        'not_required',
                        'conditional',
                        'unknown'
                    )
                ),
            claimant_rule_text TEXT NOT NULL DEFAULT '',
            deadline_rule_text TEXT NOT NULL DEFAULT '',
            mutual_exclusion_text TEXT NOT NULL DEFAULT '',
            first_verified_at TEXT,
            last_verified_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (
                program_status != 'verified'
                OR (
                    support_purpose IS NOT NULL
                    AND program_basis IS NOT NULL
                    AND delivery_form IS NOT NULL
                    AND last_verified_at IS NOT NULL
                )
            )
        );

        CREATE INDEX IF NOT EXISTS idx_benefit_programs_status
            ON benefit_programs (program_status);

        CREATE INDEX IF NOT EXISTS idx_benefit_programs_purpose
            ON benefit_programs (support_purpose);

        CREATE TABLE IF NOT EXISTS program_sources (
            program_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
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
            source_excerpt TEXT NOT NULL DEFAULT '',
            review_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (
                    review_status IN (
                        'pending',
                        'verified',
                        'rejected'
                    )
                ),
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (program_id, document_id, evidence_role),
            CHECK (
                review_status != 'verified'
                OR (
                    source_excerpt != ''
                    AND reviewed_at IS NOT NULL
                )
            ),
            FOREIGN KEY (program_id)
                REFERENCES benefit_programs (program_id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (document_id)
                REFERENCES source_documents (document_id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_program_sources_document_id
            ON program_sources (document_id);

        CREATE INDEX IF NOT EXISTS idx_program_sources_review_status
            ON program_sources (review_status);

        CREATE TABLE IF NOT EXISTS program_organization_roles (
            role_id TEXT PRIMARY KEY,
            program_id TEXT NOT NULL,
            organization_role TEXT NOT NULL
                CHECK (
                    organization_role IN (
                        'program_owner',
                        'administrator',
                        'application_contact',
                        'funder',
                        'data_publisher'
                    )
                ),
            oid TEXT,
            organization_name TEXT NOT NULL DEFAULT '',
            evidence_document_id TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (
                    review_status IN (
                        'pending',
                        'verified',
                        'rejected'
                    )
                ),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (oid IS NOT NULL OR organization_name != ''),
            CHECK (
                review_status != 'verified'
                OR evidence_document_id IS NOT NULL
            ),
            FOREIGN KEY (program_id)
                REFERENCES benefit_programs (program_id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (oid)
                REFERENCES government_organizations (oid)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (evidence_document_id)
                REFERENCES source_documents (document_id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_program_organization_roles_program
            ON program_organization_roles (program_id);

        CREATE INDEX IF NOT EXISTS idx_program_organization_roles_oid
            ON program_organization_roles (oid);
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO schema_metadata (key, value)
        VALUES ('benefit_catalog_schema_version', ?)
        """,
        (CATALOG_SCHEMA_VERSION,),
    )
    stored_version = connection.execute(
        """
        SELECT value
        FROM schema_metadata
        WHERE key = 'benefit_catalog_schema_version'
        """
    ).fetchone()
    if stored_version is None or stored_version[0] != CATALOG_SCHEMA_VERSION:
        raise RuntimeError(
            "Unsupported benefit catalog schema version: "
            f"{stored_version[0] if stored_version else 'missing'}"
        )
    connection.commit()


def _require_string(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Source seed field '{field}' must be a non-empty string.")
    return value.strip()


def _optional_string(record: dict[str, Any], field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Source seed field '{field}' must be a string or null.")
    normalized = value.strip()
    return normalized or None


def load_source_seeds(seed_path: Path) -> tuple[SourceSeed, ...]:
    """Load and validate reviewable source metadata from JSON."""

    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise ValueError("Source seed JSON must contain a 'sources' list.")

    seeds: list[SourceSeed] = []
    seen_source_ids: set[str] = set()
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise ValueError("Every source seed must be an object.")
        source_id = _require_string(raw_source, "source_id")
        if source_id in seen_source_ids:
            raise ValueError(f"Duplicate source_id in seed file: {source_id}")
        seen_source_ids.add(source_id)

        source_type = _require_string(raw_source, "source_type")
        official_status = _require_string(raw_source, "official_status")
        access_method = _require_string(raw_source, "access_method")
        connection_status = _require_string(raw_source, "connection_status")
        if source_type not in SOURCE_TYPES:
            raise ValueError(f"Unsupported source_type: {source_type}")
        if official_status not in OFFICIAL_STATUSES:
            raise ValueError(f"Unsupported official_status: {official_status}")
        if access_method not in ACCESS_METHODS:
            raise ValueError(f"Unsupported access_method: {access_method}")
        if connection_status not in CONNECTION_STATUSES:
            raise ValueError(
                f"Unsupported connection_status: {connection_status}"
            )

        enabled = raw_source.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("Source seed field 'enabled' must be a boolean.")

        seeds.append(
            SourceSeed(
                source_id=source_id,
                name=_require_string(raw_source, "name"),
                source_type=source_type,
                jurisdiction_code=_require_string(
                    raw_source,
                    "jurisdiction_code",
                ),
                organization_name=_require_string(
                    raw_source,
                    "organization_name",
                ),
                publisher_oid=_optional_string(raw_source, "publisher_oid"),
                base_url=_require_string(raw_source, "base_url"),
                entry_url=_require_string(raw_source, "entry_url"),
                canonical_host=_require_string(raw_source, "canonical_host"),
                official_status=official_status,
                access_method=access_method,
                connection_status=connection_status,
                enabled=enabled,
                reviewed_at=_optional_string(raw_source, "reviewed_at"),
                review_note=(
                    _optional_string(raw_source, "review_note") or ""
                ),
            )
        )
    return tuple(seeds)


def seed_source_registry(
    connection: sqlite3.Connection,
    seeds: tuple[SourceSeed, ...],
) -> int:
    """Refresh reviewed metadata without overwriting later runtime status."""

    now = utc_now()
    inserted_count = 0
    for seed in seeds:
        existing = connection.execute(
            "SELECT 1 FROM source_registry WHERE source_id = ?",
            (seed.source_id,),
        ).fetchone()
        values = (
            seed.name,
            seed.source_type,
            seed.jurisdiction_code,
            seed.organization_name,
            seed.publisher_oid,
            seed.base_url,
            seed.entry_url,
            seed.canonical_host,
            seed.official_status,
            seed.access_method,
            seed.reviewed_at,
            seed.review_note,
        )
        if existing is None:
            connection.execute(
                """
                INSERT INTO source_registry (
                    source_id,
                    name,
                    source_type,
                    jurisdiction_code,
                    organization_name,
                    publisher_oid,
                    base_url,
                    entry_url,
                    canonical_host,
                    official_status,
                    access_method,
                    connection_status,
                    enabled,
                    reviewed_at,
                    review_note,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    seed.source_id,
                    *values[:10],
                    seed.connection_status,
                    int(seed.enabled),
                    *values[10:],
                    now,
                    now,
                ),
            )
            inserted_count += 1
        else:
            connection.execute(
                """
                UPDATE source_registry
                SET
                    name = ?,
                    source_type = ?,
                    jurisdiction_code = ?,
                    organization_name = ?,
                    publisher_oid = ?,
                    base_url = ?,
                    entry_url = ?,
                    canonical_host = ?,
                    official_status = ?,
                    access_method = ?,
                    reviewed_at = ?,
                    review_note = ?,
                    updated_at = ?
                WHERE source_id = ?
                """,
                (*values, now, seed.source_id),
            )
    connection.commit()
    return inserted_count


def mark_oid_source_active_when_imported(
    connection: sqlite3.Connection,
) -> bool:
    """Reflect a completed OID import without claiming other connectors work."""

    completed_sync = connection.execute(
        """
        SELECT 1
        FROM sync_runs
        WHERE status = 'completed'
        LIMIT 1
        """
    ).fetchone()
    if completed_sync is None:
        return False

    cursor = connection.execute(
        """
        UPDATE source_registry
        SET connection_status = 'active', updated_at = ?
        WHERE source_id = 'government_oid_dataset'
          AND connection_status != 'active'
        """,
        (utc_now(),),
    )
    connection.commit()
    return cursor.rowcount > 0


def get_catalog_summary(connection: sqlite3.Connection) -> CatalogSummary:
    """Return counts suitable for a future read-only admin status endpoint."""

    source_status_counts = {
        status: 0 for status in CONNECTION_STATUSES
    }
    for status, count in connection.execute(
        """
        SELECT connection_status, COUNT(*)
        FROM source_registry
        GROUP BY connection_status
        """
    ):
        source_status_counts[status] = count

    def scalar(query: str) -> int:
        row = connection.execute(query).fetchone()
        return int(row[0] if row else 0)

    return CatalogSummary(
        source_count=sum(source_status_counts.values()),
        source_status_counts=source_status_counts,
        source_sync_run_count=scalar("SELECT COUNT(*) FROM source_sync_runs"),
        document_count=scalar("SELECT COUNT(*) FROM source_documents"),
        candidate_program_count=scalar(
            """
            SELECT COUNT(*)
            FROM benefit_programs
            WHERE program_status IN (
                'candidate',
                'under_review',
                'status_unknown'
            )
            """
        ),
        verified_program_count=scalar(
            """
            SELECT COUNT(*)
            FROM benefit_programs
            WHERE program_status = 'verified'
            """
        ),
        pending_evidence_count=scalar(
            """
            SELECT COUNT(*)
            FROM program_sources
            WHERE review_status = 'pending'
            """
        ),
    )


def get_registered_source_statuses(
    connection: sqlite3.Connection,
) -> tuple[RegisteredSourceStatus, ...]:
    """Return one admin-facing coverage row per registered source."""

    rows = connection.execute(
        """
        SELECT
            source.source_id,
            source.name,
            source.source_type,
            source.access_method,
            source.connection_status,
            COUNT(DISTINCT discovery.document_id) AS document_count,
            COUNT(
                DISTINCT CASE
                    WHEN program.program_status IN (
                        'candidate',
                        'under_review',
                        'status_unknown'
                    )
                    THEN program.program_id
                END
            ) AS candidate_program_count,
            COUNT(
                DISTINCT CASE
                    WHEN program.program_status = 'verified'
                    THEN program.program_id
                END
            ) AS verified_program_count
        FROM source_registry AS source
        LEFT JOIN document_discoveries AS discovery
            ON discovery.source_id = source.source_id
        LEFT JOIN program_sources AS evidence
            ON evidence.document_id = discovery.document_id
        LEFT JOIN benefit_programs AS program
            ON program.program_id = evidence.program_id
        GROUP BY
            source.source_id,
            source.name,
            source.source_type,
            source.access_method,
            source.connection_status
        ORDER BY source.name, source.source_id
        """
    ).fetchall()
    return tuple(
        RegisteredSourceStatus(
            source_id=row[0],
            name=row[1],
            source_type=row[2],
            access_method=row[3],
            connection_status=row[4],
            document_count=row[5],
            candidate_program_count=row[6],
            verified_program_count=row[7],
        )
        for row in rows
    )
