"""Migrate data from local SQLite to RDS PostgreSQL.

Usage:
    python scripts/migrate_sqlite_to_postgresql.py

Reads connection info from environment variables (or .env file):
    RDS_HOST, RDS_PORT, RDS_DATABASE, RDS_USERNAME, RDS_PASSWORD, RDS_SSLMODE

The script:
1. Connects to the local SQLite database (data/local/government_oid.db).
2. Connects to PostgreSQL (RDS).
3. Runs the PostgreSQL schema migration if tables don't exist.
4. Copies all data from SQLite in FK dependency order.
5. Verifies row counts match.

This script is idempotent: it uses INSERT ... ON CONFLICT DO NOTHING,
so re-running it won't duplicate data.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

# Allow importing from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[0] / ".." / "backend"))

try:
    import psycopg
except ImportError:
    print("ERROR: psycopg not installed. Run: pip install 'psycopg[binary]'")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[1]
SQLITE_DB_PATH = REPO_ROOT / "data" / "local" / "government_oid.db"
MIGRATION_SQL_PATH = (
    REPO_ROOT / "backend" / "app" / "adapters" / "postgresql"
    / "migration_sql" / "0001_full_schema.sql"
)

# Tables to migrate in FK dependency order.
# Each entry: (table_name, list_of_columns, boolean_columns_to_convert)
# boolean_columns_to_convert: SQLite stores 0/1, PostgreSQL needs True/False
MIGRATION_ORDER: list[tuple[str, list[str], list[str]]] = [
    # From OID database
    ("government_organizations", [
        "oid", "org_name", "org_code", "tel", "address", "dn",
        "active", "source_url", "source_record_hash",
        "source_updated_at", "first_seen_at", "last_seen_at",
    ], ["active"]),

    # Metadata tables
    ("schema_metadata", ["key", "value"], []),
    ("catalog_revisions", ["revision_id", "committed_at", "actor_ref", "description_code"], []),

    # Field registry
    ("field_registry", [
        "field_id", "data_type", "prompt_label", "why_needed",
        "pii_classification", "active",
    ], ["active"]),
    ("field_allowed_values", ["field_id", "value", "canonical_order"], []),

    # Programs
    ("benefit_programs", [
        "program_id", "canonical_name", "summary", "support_purpose",
        "program_basis", "delivery_form", "jurisdiction_code",
        "program_status", "status_note", "expense_proof_requirement",
        "claimant_rule_text", "deadline_rule_text", "mutual_exclusion_text",
        "first_verified_at", "last_verified_at", "amount_min", "amount_max",
        "amount_period", "amount_currency", "current_revision_id",
        "created_at", "updated_at",
    ], []),
    ("program_status_history", [
        "history_id", "program_id", "from_status", "to_status",
        "actor_type", "reviewer_ref", "reviewed_at", "approved_version",
    ], []),
    ("review_approvals", [
        "approval_id", "artifact_type", "artifact_id",
        "artifact_version", "reviewer_ref", "reviewed_at", "decision",
    ], []),

    # Graph
    ("graph_nodes", ["node_id", "node_type", "display_name", "program_id"], []),
    ("graph_edges", [
        "edge_id", "from_node_id", "to_node_id", "edge_type", "canonical_order",
    ], []),
    ("graph_edge_conditions", [
        "edge_id", "condition_id", "field_id", "operator",
        "expected_value_type", "expected_value_json", "condition_order",
    ], []),
    ("graph_versions", [
        "graph_version", "revision_id", "approved_by", "approved_at", "is_current",
    ], ["is_current"]),

    # Sources
    ("source_registry", [
        "source_id", "name", "source_type", "jurisdiction_code",
        "organization_name", "publisher_oid", "base_url", "entry_url",
        "canonical_host", "official_status", "access_method",
        "connection_status", "enabled", "reviewed_at", "review_note",
        "created_at", "updated_at",
    ], ["enabled"]),
    ("source_documents", [
        "document_id", "canonical_url", "title", "document_type",
        "jurisdiction_code", "publisher_name", "publisher_oid",
        "current_content_hash", "storage_ref", "http_status",
        "published_at", "source_updated_at", "first_seen_at",
        "last_seen_at", "last_changed_at", "retrieved_at",
        "review_status", "simplified_script_detected",
        "created_at", "updated_at", "effective_at",
    ], ["simplified_script_detected"]),
    ("document_discoveries", [
        "document_id", "source_id", "discovery_url", "discovery_method",
        "first_seen_at", "last_seen_at", "last_sync_run_id",
    ], []),
    ("source_domain_tags", ["source_id", "domain_tag"], []),

    # Rules
    ("rule_definitions", ["rule_id", "program_id"], []),
    ("rule_versions", [
        "rule_version_id", "rule_id", "version", "dsl_version",
        "approval_status", "is_current", "root_node_id",
        "created_at", "approved_by", "approved_at",
    ], ["is_current"]),
    ("rule_nodes", [
        "node_id", "rule_version_id", "parent_node_id",
        "node_type", "child_order",
    ], []),
    ("rule_conditions", [
        "condition_id", "node_id", "field_id", "operator",
        "expected_value_type", "expected_value_json",
        "label", "source_reference",
    ], []),
    ("rule_required_fields", [
        "rule_version_id", "field_id", "canonical_order",
    ], []),
    ("rule_version_source_refs", ["rule_version_id", "source_reference"], []),
    ("approved_amounts", [
        "rule_version_id", "amount_min", "amount_max",
        "amount_period", "amount_currency", "source_reference",
    ], []),

    # Evidence
    ("evidence_excerpts", [
        "evidence_id", "document_id", "excerpt", "review_status",
        "reviewer_ref", "reviewed_at", "created_at", "updated_at",
    ], []),
    ("program_evidence_links", [
        "program_id", "evidence_id", "evidence_role",
        "review_status", "reviewer_ref", "reviewed_at",
    ], []),
    ("source_reference_evidence", [
        "rule_version_id", "source_reference", "evidence_id",
    ], []),
    ("document_attachments", [
        "attachment_id", "document_id", "filename", "media_type",
        "source_url", "storage_backend", "storage_ref", "content_hash",
        "extraction_status", "extraction_method", "extracted_at",
        "review_status", "reviewer_ref", "reviewed_at",
        "created_at", "updated_at",
    ], []),

    # Coverage & Refresh
    ("source_coverage_state", [
        "source_id", "crawl_status", "last_successful_crawl_at",
        "indexed_document_count", "last_gap_category",
        "updated_revision_id", "updated_at",
    ], []),
    ("refresh_jobs", [
        "job_id", "source_id", "event_id", "local_calendar_date",
        "dedup_key", "status", "requested_at", "started_at",
        "completed_at", "safe_error_code",
    ], []),
]


def load_env() -> None:
    """Load .env file if it exists."""
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and value:
                    os.environ.setdefault(key, value)


def get_pg_conninfo() -> str:
    """Build PostgreSQL connection string from environment."""
    host = os.environ.get("RDS_HOST", "")
    port = os.environ.get("RDS_PORT", "5432")
    database = os.environ.get("RDS_DATABASE", "benefits_navigation")
    username = os.environ.get("RDS_USERNAME", "benefits_admin")
    password = os.environ.get("RDS_PASSWORD", "")
    sslmode = os.environ.get("RDS_SSLMODE", "require")

    if not host:
        print("ERROR: RDS_HOST not set. Configure it in .env or environment.")
        sys.exit(1)
    if not password:
        print("ERROR: RDS_PASSWORD not set. Configure it in .env or environment.")
        sys.exit(1)

    return (
        f"host={host} port={port} dbname={database} "
        f"user={username} password={password} sslmode={sslmode}"
    )


def table_exists(pg_conn: psycopg.Connection, table_name: str) -> bool:
    """Check if a table exists in PostgreSQL."""
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            )
            """,
            (table_name,),
        )
        row = cur.fetchone()
        return row[0] if row else False


def run_schema_migration(pg_conn: psycopg.Connection) -> None:
    """Run the PostgreSQL schema DDL if not already applied."""
    if table_exists(pg_conn, "schema_metadata"):
        print("  Schema already exists, skipping DDL.")
        return

    print("  Running schema migration...")
    ddl = MIGRATION_SQL_PATH.read_text(encoding="utf-8")
    with pg_conn.cursor() as cur:
        cur.execute(ddl)
    pg_conn.commit()
    print("  Schema migration complete.")


def sqlite_table_exists(sqlite_conn: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists in the SQLite database."""
    row = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def convert_row(row: tuple, columns: list[str], boolean_cols: list[str]) -> tuple:
    """Convert a SQLite row for PostgreSQL insertion.

    - Boolean columns: 0/1 → False/True
    - JSONB columns (expected_value_json): keep as string, psycopg handles it
    """
    result = list(row)
    for i, col in enumerate(columns):
        if col in boolean_cols and result[i] is not None:
            result[i] = bool(result[i])
    return tuple(result)


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: psycopg.Connection,
    table_name: str,
    columns: list[str],
    boolean_cols: list[str],
) -> int:
    """Migrate one table from SQLite to PostgreSQL. Returns row count."""
    if not sqlite_table_exists(sqlite_conn, table_name):
        return 0

    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    # For JSONB columns, cast explicitly
    value_exprs = []
    for col in columns:
        if col == "expected_value_json":
            value_exprs.append("%s::JSONB")
        elif col == "local_calendar_date":
            value_exprs.append("%s::DATE")
        else:
            value_exprs.append("%s")
    placeholders = ", ".join(value_exprs)

    # Build ON CONFLICT clause based on table
    # Use DO NOTHING for idempotency
    insert_sql = (
        f"INSERT INTO {table_name} ({col_list}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT DO NOTHING"
    )

    rows = sqlite_conn.execute(f"SELECT {col_list} FROM {table_name}").fetchall()
    if not rows:
        return 0

    count = 0
    with pg_conn.cursor() as cur:
        for row in rows:
            converted = convert_row(row, columns, boolean_cols)
            try:
                cur.execute(insert_sql, converted)
                if cur.rowcount > 0:
                    count += 1
            except Exception as exc:
                print(f"    WARNING: Failed to insert row in {table_name}: {exc}")
                pg_conn.rollback()
                # Try to continue with next row
                continue

    pg_conn.commit()
    return count


def verify_counts(
    sqlite_conn: sqlite3.Connection,
    pg_conn: psycopg.Connection,
    table_name: str,
) -> tuple[int, int]:
    """Return (sqlite_count, pg_count) for a table."""
    sqlite_count = 0
    if sqlite_table_exists(sqlite_conn, table_name):
        row = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        sqlite_count = row[0] if row else 0

    pg_count = 0
    with pg_conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        row = cur.fetchone()
        pg_count = row[0] if row else 0

    return sqlite_count, pg_count


def main() -> None:
    load_env()

    print("=" * 60)
    print("SQLite → PostgreSQL Migration")
    print("=" * 60)

    # Check SQLite exists
    if not SQLITE_DB_PATH.exists():
        print(f"ERROR: SQLite database not found at {SQLITE_DB_PATH}")
        print("Run the OID importer first: python scripts/import_government_oid.py")
        sys.exit(1)

    # Connect to SQLite
    print(f"\n[1/4] Connecting to SQLite: {SQLITE_DB_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_conn.execute("PRAGMA foreign_keys = ON")

    # Connect to PostgreSQL
    conninfo = get_pg_conninfo()
    print(f"\n[2/4] Connecting to PostgreSQL...")
    try:
        pg_conn = psycopg.connect(conninfo, autocommit=False)
        print("  Connected successfully.")
    except Exception as exc:
        print(f"ERROR: Cannot connect to PostgreSQL: {exc}")
        sqlite_conn.close()
        sys.exit(1)

    # Run schema
    print("\n[3/4] Ensuring schema exists...")
    try:
        run_schema_migration(pg_conn)
    except Exception as exc:
        print(f"ERROR: Schema migration failed: {exc}")
        pg_conn.close()
        sqlite_conn.close()
        sys.exit(1)

    # Migrate data
    print("\n[4/4] Migrating data...")
    total_migrated = 0
    results: list[tuple[str, int, int, int]] = []

    for table_name, columns, boolean_cols in MIGRATION_ORDER:
        inserted = migrate_table(sqlite_conn, pg_conn, table_name, columns, boolean_cols)
        sqlite_count, pg_count = verify_counts(sqlite_conn, pg_conn, table_name)
        results.append((table_name, sqlite_count, pg_count, inserted))
        total_migrated += inserted
        if inserted > 0:
            print(f"  {table_name}: +{inserted} rows (SQLite={sqlite_count}, PG={pg_count})")
        elif sqlite_count > 0:
            print(f"  {table_name}: already synced (SQLite={sqlite_count}, PG={pg_count})")

    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"{'Table':<35} {'SQLite':>8} {'PG':>8} {'New':>6}")
    print("-" * 60)
    mismatches = []
    for table_name, sqlite_count, pg_count, inserted in results:
        if sqlite_count > 0 or pg_count > 0:
            marker = " !" if sqlite_count != pg_count else ""
            print(f"{table_name:<35} {sqlite_count:>8} {pg_count:>8} {inserted:>6}{marker}")
            if sqlite_count != pg_count:
                mismatches.append(table_name)

    print("-" * 60)
    print(f"Total new rows inserted: {total_migrated}")

    if mismatches:
        print(f"\nWARNING: Row count mismatch in: {', '.join(mismatches)}")
        print("This may be expected if some rows were already migrated previously.")
    else:
        print("\nAll table row counts match between SQLite and PostgreSQL.")

    # Cleanup
    pg_conn.close()
    sqlite_conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
