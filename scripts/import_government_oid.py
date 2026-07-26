"""Build a local SQLite registry from the official government OID CSV.

The SQLite database is a reproducible local/demo artifact. It is deliberately
kept under ``data/local/`` so it is not committed to Git or treated as the
project's final AWS persistence choice.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sqlite3
import ssl
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = REPO_ROOT / "data" / "local" / "government_oid.db"
DEFAULT_SOURCE_URL = "https://oid.nat.gov.tw/OIDWeb/GDS.csv"
OFFICIAL_QUALITY_SNAPSHOT_URL = (
    "https://quality.data.gov.tw/dq_download_csv.php"
    "?nid=7081&md5_url=19e6620647cbf3e9f46f7914498c71ca"
)
REQUIRED_COLUMNS = ("OrgName", "OID", "TEL", "Address", "DN", "OrgCode")
SCHEMA_VERSION = "1"
OID_PATTERN = re.compile(r"^\d+(?:\.\d+)+$")


@dataclass(frozen=True)
class AgencyRecord:
    """Storage-neutral representation of one official OID record."""

    oid: str
    org_name: str
    org_code: str
    tel: str
    address: str
    dn: str


@dataclass(frozen=True)
class ParseResult:
    records: tuple[AgencyRecord, ...]
    source_record_count: int
    invalid_count: int
    duplicate_count: int


@dataclass(frozen=True)
class ImportSummary:
    run_id: str
    source_record_count: int
    valid_record_count: int
    invalid_count: int
    duplicate_count: int
    inserted_count: int
    updated_count: int
    unchanged_count: int
    deactivated_count: int
    active_count: int
    database_total_count: int


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def normalize_text(value: str | None) -> str:
    return (value or "").strip()


def record_hash(record: AgencyRecord) -> str:
    canonical_record = {
        "address": record.address,
        "dn": record.dn,
        "oid": record.oid,
        "org_code": record.org_code,
        "org_name": record.org_name,
        "tel": record.tel,
    }
    payload = json.dumps(
        canonical_record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_official_csv(csv_bytes: bytes) -> ParseResult:
    """Parse and validate the official UTF-8 CSV without choosing a database."""

    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("The OID CSV does not contain a header row.")

    normalized_headers = tuple(normalize_text(name) for name in reader.fieldnames)
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(normalized_headers))
    if missing_columns:
        raise ValueError(
            "The OID CSV is missing required columns: "
            + ", ".join(missing_columns)
        )

    records_by_oid: dict[str, AgencyRecord] = {}
    source_record_count = 0
    invalid_count = 0
    duplicate_count = 0

    for raw_row in reader:
        row = {
            normalize_text(key): normalize_text(value)
            for key, value in raw_row.items()
            if key is not None
        }
        if not any(row.values()):
            continue

        source_record_count += 1
        oid = row.get("OID", "")
        org_name = row.get("OrgName", "")
        if not oid or not org_name or not OID_PATTERN.fullmatch(oid):
            invalid_count += 1
            continue

        record = AgencyRecord(
            oid=oid,
            org_name=org_name,
            org_code=row.get("OrgCode", ""),
            tel=row.get("TEL", ""),
            address=row.get("Address", ""),
            dn=row.get("DN", ""),
        )
        existing = records_by_oid.get(oid)
        if existing is not None:
            duplicate_count += 1
            if existing != record:
                raise ValueError(f"Conflicting rows found for OID {oid}.")
            continue

        records_by_oid[oid] = record

    if not records_by_oid:
        raise ValueError("The OID CSV does not contain any valid records.")

    return ParseResult(
        records=tuple(records_by_oid.values()),
        source_record_count=source_record_count,
        invalid_count=invalid_count,
        duplicate_count=duplicate_count,
    )


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the versioned SQLite schema without adding application data."""

    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS government_organizations (
            oid TEXT PRIMARY KEY,
            org_name TEXT NOT NULL,
            org_code TEXT NOT NULL DEFAULT '',
            tel TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            dn TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            source_url TEXT NOT NULL,
            source_record_hash TEXT NOT NULL,
            source_updated_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_government_organizations_org_name
            ON government_organizations (org_name);

        CREATE INDEX IF NOT EXISTS idx_government_organizations_org_code
            ON government_organizations (org_code);

        CREATE TABLE IF NOT EXISTS tags (
            tag_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS organization_tags (
            oid TEXT NOT NULL,
            tag_id TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (oid, tag_id),
            FOREIGN KEY (oid)
                REFERENCES government_organizations (oid)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (tag_id)
                REFERENCES tags (tag_id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_organization_tags_tag_id
            ON organization_tags (tag_id);

        CREATE TABLE IF NOT EXISTS sync_runs (
            run_id TEXT PRIMARY KEY,
            source_url TEXT NOT NULL,
            source_modified_at TEXT,
            source_checksum TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            source_record_count INTEGER NOT NULL DEFAULT 0,
            valid_record_count INTEGER NOT NULL DEFAULT 0,
            invalid_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            updated_count INTEGER NOT NULL DEFAULT 0,
            unchanged_count INTEGER NOT NULL DEFAULT 0,
            deactivated_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error_message TEXT
        );
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO schema_metadata (key, value)
        VALUES ('schema_version', ?)
        """,
        (SCHEMA_VERSION,),
    )
    stored_version = connection.execute(
        "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
    ).fetchone()
    if stored_version is None or stored_version[0] != SCHEMA_VERSION:
        raise RuntimeError(
            "Unsupported government OID database schema version: "
            f"{stored_version[0] if stored_version else 'missing'}"
        )
    connection.commit()


def import_into_sqlite(
    parse_result: ParseResult,
    database_path: Path,
    *,
    source_url: str,
    source_checksum: str,
    source_modified_at: str | None = None,
) -> ImportSummary:
    """Atomically refresh official fields while preserving tags and history."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    run_id = str(uuid.uuid4())
    started_at = utc_now()

    try:
        initialize_schema(connection)
        connection.execute(
            """
            INSERT INTO sync_runs (
                run_id,
                source_url,
                source_modified_at,
                source_checksum,
                started_at,
                source_record_count,
                valid_record_count,
                invalid_count,
                duplicate_count,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            (
                run_id,
                source_url,
                source_modified_at,
                source_checksum,
                started_at,
                parse_result.source_record_count,
                len(parse_result.records),
                parse_result.invalid_count,
                parse_result.duplicate_count,
            ),
        )
        connection.commit()
        connection.execute("BEGIN")
        connection.execute(
            "CREATE TEMP TABLE seen_oids (oid TEXT PRIMARY KEY)"
        )

        inserted_count = 0
        updated_count = 0
        unchanged_count = 0
        seen_at = utc_now()

        for record in parse_result.records:
            current_hash = record_hash(record)
            existing = connection.execute(
                """
                SELECT source_record_hash, active
                FROM government_organizations
                WHERE oid = ?
                """,
                (record.oid,),
            ).fetchone()

            if existing is None:
                connection.execute(
                    """
                    INSERT INTO government_organizations (
                        oid,
                        org_name,
                        org_code,
                        tel,
                        address,
                        dn,
                        active,
                        source_url,
                        source_record_hash,
                        source_updated_at,
                        first_seen_at,
                        last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.oid,
                        record.org_name,
                        record.org_code,
                        record.tel,
                        record.address,
                        record.dn,
                        source_url,
                        current_hash,
                        source_modified_at,
                        seen_at,
                        seen_at,
                    ),
                )
                inserted_count += 1
            elif existing[0] != current_hash or existing[1] != 1:
                connection.execute(
                    """
                    UPDATE government_organizations
                    SET
                        org_name = ?,
                        org_code = ?,
                        tel = ?,
                        address = ?,
                        dn = ?,
                        active = 1,
                        source_url = ?,
                        source_record_hash = ?,
                        source_updated_at = ?,
                        last_seen_at = ?
                    WHERE oid = ?
                    """,
                    (
                        record.org_name,
                        record.org_code,
                        record.tel,
                        record.address,
                        record.dn,
                        source_url,
                        current_hash,
                        source_modified_at,
                        seen_at,
                        record.oid,
                    ),
                )
                updated_count += 1
            else:
                connection.execute(
                    """
                    UPDATE government_organizations
                    SET
                        source_url = ?,
                        source_updated_at = ?,
                        last_seen_at = ?
                    WHERE oid = ?
                    """,
                    (
                        source_url,
                        source_modified_at,
                        seen_at,
                        record.oid,
                    ),
                )
                unchanged_count += 1

            connection.execute(
                "INSERT INTO seen_oids (oid) VALUES (?)",
                (record.oid,),
            )

        deactivation_cursor = connection.execute(
            """
            UPDATE government_organizations
            SET active = 0
            WHERE active = 1
              AND oid NOT IN (SELECT oid FROM seen_oids)
            """
        )
        deactivated_count = deactivation_cursor.rowcount
        active_count = connection.execute(
            "SELECT COUNT(*) FROM government_organizations WHERE active = 1"
        ).fetchone()[0]
        database_total_count = connection.execute(
            "SELECT COUNT(*) FROM government_organizations"
        ).fetchone()[0]
        completed_at = utc_now()
        connection.execute(
            """
            UPDATE sync_runs
            SET
                completed_at = ?,
                inserted_count = ?,
                updated_count = ?,
                unchanged_count = ?,
                deactivated_count = ?,
                status = 'completed'
            WHERE run_id = ?
            """,
            (
                completed_at,
                inserted_count,
                updated_count,
                unchanged_count,
                deactivated_count,
                run_id,
            ),
        )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        try:
            connection.execute(
                """
                UPDATE sync_runs
                SET completed_at = ?, status = 'failed', error_message = ?
                WHERE run_id = ?
                """,
                (utc_now(), str(exc), run_id),
            )
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
        raise
    finally:
        connection.close()

    return ImportSummary(
        run_id=run_id,
        source_record_count=parse_result.source_record_count,
        valid_record_count=len(parse_result.records),
        invalid_count=parse_result.invalid_count,
        duplicate_count=parse_result.duplicate_count,
        inserted_count=inserted_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        deactivated_count=deactivated_count,
        active_count=active_count,
        database_total_count=database_total_count,
    )


def download_csv(
    source_url: str,
    timeout_seconds: int,
) -> tuple[bytes, str | None, str]:
    ssl_context = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        # The official OID site's certificate chain is accepted by browsers
        # but omits an extension required by OpenSSL strict verification.
        # Keep CA and hostname checks enabled while relaxing only that flag.
        ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    download_urls = [source_url]
    if source_url == DEFAULT_SOURCE_URL:
        download_urls.append(OFFICIAL_QUALITY_SNAPSHOT_URL)

    failures: list[str] = []
    for download_url in download_urls:
        request = Request(
            download_url,
            headers={
                "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
                "User-Agent": "benefits-navigation-agent/oid-importer",
            },
        )
        try:
            with urlopen(
                request,
                timeout=timeout_seconds,
                context=ssl_context,
            ) as response:
                return (
                    response.read(),
                    response.headers.get("Last-Modified"),
                    download_url,
                )
        except OSError as exc:
            failures.append(f"{download_url}: {exc}")

    raise OSError(
        "Unable to download the official OID CSV. " + " | ".join(failures)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the local SQLite government OID registry."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite output path (default: {DEFAULT_DATABASE_PATH})",
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="Canonical official CSV URL stored with imported records.",
    )
    parser.add_argument(
        "--source-file",
        type=Path,
        help="Read a previously downloaded official CSV instead of the network.",
    )
    parser.add_argument(
        "--source-modified-at",
        help="Optional official source modification timestamp.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Network timeout in seconds (default: 30).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.source_file:
            csv_bytes = args.source_file.read_bytes()
            detected_modified_at = None
            retrieval_location = str(args.source_file)
        else:
            csv_bytes, detected_modified_at, retrieval_location = download_csv(
                args.source_url,
                args.timeout,
            )
        source_modified_at = args.source_modified_at or detected_modified_at
        parse_result = parse_official_csv(csv_bytes)
        source_checksum = hashlib.sha256(csv_bytes).hexdigest()
        summary = import_into_sqlite(
            parse_result,
            args.database,
            source_url=args.source_url,
            source_checksum=source_checksum,
            source_modified_at=source_modified_at,
        )
    except (OSError, UnicodeError, ValueError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(1, f"Import failed: {exc}\n")

    print(f"Database: {args.database}")
    print(f"Retrieved from: {retrieval_location}")
    print(f"Sync run: {summary.run_id}")
    print(f"Source rows: {summary.source_record_count}")
    print(f"Valid unique OIDs: {summary.valid_record_count}")
    print(f"Invalid rows: {summary.invalid_count}")
    print(f"Duplicate rows: {summary.duplicate_count}")
    print(f"Inserted: {summary.inserted_count}")
    print(f"Updated or reactivated: {summary.updated_count}")
    print(f"Unchanged: {summary.unchanged_count}")
    print(f"Deactivated: {summary.deactivated_count}")
    print(f"Active organizations in database: {summary.active_count}")
    print(
        "Organizations retained including inactive: "
        f"{summary.database_total_count}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
