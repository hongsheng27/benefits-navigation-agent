"""Load extracted benefit candidates into the local SQLite database.

Reads the structured JSON produced by extract_benefit_candidates.py and
inserts records into benefit_programs, program_sources, and
program_organization_roles. All records are created with candidate/pending
status. Running this script multiple times is safe — existing program_id
rows are skipped (not overwritten).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.benefit_catalog import utc_now  # noqa: E402
from scripts.import_government_oid import DEFAULT_DATABASE_PATH  # noqa: E402
from scripts.init_benefit_catalog import initialize_database  # noqa: E402

DEFAULT_CANDIDATES_PATH = (
    REPO_ROOT
    / "data"
    / "benefit_discovery"
    / "extracted_candidates.v0.1.json"
)


def _to_null(value: str) -> str | None:
    """Convert 'unknown' or empty string to None for nullable DB fields."""
    if not value or value.strip().lower() == "unknown":
        return None
    return value.strip()


def _make_program_id(candidate_id: str) -> str:
    """Deterministic program_id from candidate_id for idempotent inserts."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"benefit:{candidate_id}"))


def _lookup_document_id(
    connection: sqlite3.Connection, source_url: str
) -> str | None:
    """Find document_id by canonical_url."""
    row = connection.execute(
        "SELECT document_id FROM source_documents WHERE canonical_url = ?",
        (source_url,),
    ).fetchone()
    return str(row[0]) if row else None


def _insert_program(
    connection: sqlite3.Connection,
    candidate: dict,
    now: str,
) -> tuple[str, bool]:
    """Insert one benefit_programs row. Returns (program_id, inserted)."""
    program_id = _make_program_id(candidate["candidate_id"])

    existing = connection.execute(
        "SELECT 1 FROM benefit_programs WHERE program_id = ?",
        (program_id,),
    ).fetchone()
    if existing is not None:
        return program_id, False

    # Map delivery_form: 'unknown' -> None (nullable in schema)
    delivery_form = _to_null(candidate.get("delivery_form", ""))
    support_purpose = _to_null(candidate.get("support_purpose", ""))
    program_basis = _to_null(candidate.get("program_basis", ""))

    connection.execute(
        """
        INSERT INTO benefit_programs (
            program_id,
            canonical_name,
            summary,
            support_purpose,
            program_basis,
            delivery_form,
            jurisdiction_code,
            program_status,
            status_note,
            claimant_rule_text,
            deadline_rule_text,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?, ?, ?, ?)
        """,
        (
            program_id,
            candidate["canonical_name"],
            candidate.get("summary", ""),
            support_purpose,
            program_basis,
            delivery_form,
            candidate.get("jurisdiction_code", ""),
            candidate.get("extraction_notes", ""),
            candidate.get("claimant_rule_text", "") or "",
            candidate.get("deadline_rule_text", "") or "",
            now,
            now,
        ),
    )
    return program_id, True


def _insert_program_source(
    connection: sqlite3.Connection,
    program_id: str,
    document_id: str,
    candidate: dict,
    now: str,
) -> None:
    """Insert program_sources evidence rows for the candidate."""
    # We insert one 'overview' evidence linking the source excerpt
    source_excerpt = candidate.get("source_excerpt", "")
    existing = connection.execute(
        """
        SELECT 1 FROM program_sources
        WHERE program_id = ? AND document_id = ? AND evidence_role = 'overview'
        """,
        (program_id, document_id),
    ).fetchone()
    if existing is not None:
        return

    connection.execute(
        """
        INSERT INTO program_sources (
            program_id,
            document_id,
            evidence_role,
            source_excerpt,
            review_status,
            created_at,
            updated_at
        ) VALUES (?, ?, 'overview', ?, 'pending', ?, ?)
        """,
        (program_id, document_id, source_excerpt, now, now),
    )


def _insert_organization_role(
    connection: sqlite3.Connection,
    program_id: str,
    document_id: str | None,
    candidate: dict,
    now: str,
) -> None:
    """Insert program_organization_roles for the accepting agency."""
    agency_name = candidate.get("accepting_agency_name", "")
    if not agency_name or agency_name.lower() == "unknown":
        return

    role = candidate.get("accepting_agency_role", "application_contact")
    role_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"role:{candidate['candidate_id']}:{role}",
        )
    )

    existing = connection.execute(
        "SELECT 1 FROM program_organization_roles WHERE role_id = ?",
        (role_id,),
    ).fetchone()
    if existing is not None:
        return

    connection.execute(
        """
        INSERT INTO program_organization_roles (
            role_id,
            program_id,
            organization_role,
            oid,
            organization_name,
            evidence_document_id,
            review_status,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, NULL, ?, ?, 'pending', ?, ?)
        """,
        (
            role_id,
            program_id,
            role,
            agency_name,
            document_id,
            now,
            now,
        ),
    )


def load_candidates(
    database_path: Path,
    candidates_path: Path,
) -> tuple[int, int]:
    """Load candidates into DB. Returns (inserted_count, skipped_count)."""
    initialize_database(database_path)

    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates", [])
    if not candidates:
        raise ValueError(f"No candidates found in {candidates_path}")

    inserted = 0
    skipped = 0

    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        now = utc_now()

        for candidate in candidates:
            program_id, was_inserted = _insert_program(
                connection, candidate, now
            )
            if not was_inserted:
                skipped += 1
                continue

            inserted += 1
            source_url = candidate.get("source_url", "")
            document_id = _lookup_document_id(connection, source_url)

            if document_id:
                _insert_program_source(
                    connection, program_id, document_id, candidate, now
                )
                _insert_organization_role(
                    connection, program_id, document_id, candidate, now
                )
            else:
                _insert_organization_role(
                    connection, program_id, None, candidate, now
                )

        connection.commit()

    return inserted, skipped


def main() -> int:
    if not DEFAULT_DATABASE_PATH.exists():
        print(
            f"Database not found: {DEFAULT_DATABASE_PATH}\n"
            "Run the import and init scripts first.",
            file=sys.stderr,
        )
        return 1
    if not DEFAULT_CANDIDATES_PATH.exists():
        print(
            f"Candidates file not found: {DEFAULT_CANDIDATES_PATH}\n"
            "Run scripts/extract_benefit_candidates.py first.",
            file=sys.stderr,
        )
        return 1

    inserted, skipped = load_candidates(
        DEFAULT_DATABASE_PATH, DEFAULT_CANDIDATES_PATH
    )
    print(f"Done. Inserted: {inserted}, Skipped (already exist): {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
