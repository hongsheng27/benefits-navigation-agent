"""Show pending benefit program candidates and their missing fields.

This script queries the local SQLite database and prints a human-readable
summary of all programs that are not yet verified, highlighting which fields
still need to be filled or confirmed.
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.import_government_oid import DEFAULT_DATABASE_PATH  # noqa: E402

# Fields that should be non-empty for a complete program record
REQUIRED_FIELDS = [
    ("canonical_name", "方案名稱"),
    ("summary", "簡介"),
    ("support_purpose", "support_purpose"),
    ("program_basis", "program_basis"),
    ("delivery_form", "delivery_form"),
    ("jurisdiction_code", "適用縣市"),
    ("claimant_rule_text", "申請人規則"),
    ("deadline_rule_text", "申請期限"),
]


def _check_missing(row: dict) -> list[str]:
    """Return list of Chinese labels for missing/empty fields."""
    missing = []
    for field, label in REQUIRED_FIELDS:
        value = row.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            missing.append(label)
    return missing


def review_status(database_path: Path) -> None:
    """Print a summary of all benefit programs and their review state."""
    with closing(sqlite3.connect(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        programs = connection.execute(
            """
            SELECT *
            FROM benefit_programs
            ORDER BY program_status, canonical_name
            """
        ).fetchall()

        if not programs:
            print("目前資料庫中沒有任何補助方案。")
            return

        # Summary counts
        total = len(programs)
        by_status: dict[str, int] = {}
        for p in programs:
            status = p["program_status"]
            by_status[status] = by_status.get(status, 0) + 1

        print("=" * 60)
        print("補助方案審查狀態總覽")
        print("=" * 60)
        print(f"  總計：{total} 筆")
        for status, count in sorted(by_status.items()):
            print(f"  {status}：{count} 筆")
        print()

        # Per-program detail
        for p in programs:
            row_dict = dict(p)
            program_id = row_dict["program_id"]
            missing = _check_missing(row_dict)

            print("-" * 60)
            print(f"【{row_dict['canonical_name']}】")
            print(f"  program_id: {program_id}")
            print(f"  狀態: {row_dict['program_status']}")
            print(f"  縣市: {row_dict['jurisdiction_code'] or '(空)'}")

            if missing:
                print(f"  ⚠ 缺少欄位: {', '.join(missing)}")
            else:
                print("  ✓ 必填欄位皆已填寫")

            if row_dict.get("status_note"):
                print(f"  備註: {row_dict['status_note'][:80]}")

            # Check evidence
            evidence_rows = connection.execute(
                """
                SELECT evidence_role, review_status,
                       LENGTH(source_excerpt) AS excerpt_len
                FROM program_sources
                WHERE program_id = ?
                """,
                (program_id,),
            ).fetchall()

            if evidence_rows:
                print("  證據:")
                for ev in evidence_rows:
                    print(
                        f"    - {ev['evidence_role']}: "
                        f"{ev['review_status']}"
                        f" (原文 {ev['excerpt_len']} 字)"
                    )
            else:
                print("  ⚠ 無關聯證據")

            # Check organization roles
            role_rows = connection.execute(
                """
                SELECT organization_role, organization_name, review_status
                FROM program_organization_roles
                WHERE program_id = ?
                """,
                (program_id,),
            ).fetchall()

            if role_rows:
                print("  機關角色:")
                for r in role_rows:
                    print(
                        f"    - {r['organization_role']}: "
                        f"{r['organization_name']} "
                        f"({r['review_status']})"
                    )

            print()

        print("=" * 60)
        print("需要人工處理的項目：")
        print("=" * 60)

        # Pending evidence
        pending_evidence = connection.execute(
            """
            SELECT p.canonical_name, ps.evidence_role
            FROM program_sources ps
            JOIN benefit_programs p ON p.program_id = ps.program_id
            WHERE ps.review_status = 'pending'
            ORDER BY p.canonical_name
            """
        ).fetchall()
        if pending_evidence:
            print(f"\n待確認證據：{len(pending_evidence)} 筆")
            for pe in pending_evidence:
                print(f"  - {pe['canonical_name']} → {pe['evidence_role']}")

        # Pending org roles
        pending_roles = connection.execute(
            """
            SELECT p.canonical_name, por.organization_name,
                   por.organization_role
            FROM program_organization_roles por
            JOIN benefit_programs p ON p.program_id = por.program_id
            WHERE por.review_status = 'pending'
            ORDER BY p.canonical_name
            """
        ).fetchall()
        if pending_roles:
            print(f"\n待確認機關角色：{len(pending_roles)} 筆")
            for pr in pending_roles:
                print(
                    f"  - {pr['canonical_name']} → "
                    f"{pr['organization_name']} ({pr['organization_role']})"
                )

        # Programs with missing fields
        programs_needing_fill: list[tuple[str, list[str]]] = []
        for p in programs:
            row_dict = dict(p)
            missing = _check_missing(row_dict)
            if missing:
                programs_needing_fill.append(
                    (row_dict["canonical_name"], missing)
                )
        if programs_needing_fill:
            print(f"\n欄位待補齊：{len(programs_needing_fill)} 筆方案")
            for name, fields in programs_needing_fill:
                print(f"  - {name}: {', '.join(fields)}")

        print()


def transition_program_status(
    database_path: Path,
    program_id: str,
    to_status: str,
    reviewer_ref: str,
    approved_version: str,
) -> None:
    """Transition a program's status (human reviewer only).

    Protected transitions (to 'verified') require complete artifacts which
    must be registered separately before calling this function.
    """
    from backend.app.curation.review_service import (
        ReviewArtifacts,
        ReviewService,
        TransitionAuditRecord,
    )

    class SqlitePersistence:
        def __init__(self, db_path: Path) -> None:
            self._db_path = db_path

        def persist_transition(self, record: TransitionAuditRecord) -> None:
            with closing(sqlite3.connect(self._db_path)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute(
                    """
                    INSERT INTO program_status_history (
                        history_id, program_id, from_status, to_status,
                        actor_type, reviewer_ref, reviewed_at, approved_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.history_id,
                        record.program_id,
                        record.from_status,
                        record.to_status,
                        record.actor_type,
                        record.reviewer_ref,
                        record.reviewed_at,
                        record.approved_version,
                    ),
                )
                conn.execute(
                    "UPDATE benefit_programs SET program_status = ?, "
                    "updated_at = ? WHERE program_id = ?",
                    (record.to_status, record.reviewed_at, record.program_id),
                )
                conn.commit()

        def get_current_status(self, program_id: str) -> str | None:
            with closing(sqlite3.connect(self._db_path)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                row = conn.execute(
                    "SELECT program_status FROM benefit_programs WHERE program_id = ?",
                    (program_id,),
                ).fetchone()
            return row[0] if row else None

    persistence = SqlitePersistence(database_path)
    service = ReviewService(persistence)

    artifacts = None
    if to_status == "verified":
        print(
            "⚠ Protected transition to 'verified' requires complete artifacts.\n"
            "  Ensure approved rule, citation, and excerpt are registered first."
        )
        artifacts = ReviewArtifacts()  # Will fail validation intentionally

    result = service.transition_status(
        program_id=program_id,
        to_status=to_status,
        actor_type="human_reviewer",
        reviewer_ref=reviewer_ref,
        approved_version=approved_version,
        artifacts=artifacts,
    )

    if result.success:
        print(f"✓ Transitioned {program_id} to '{to_status}'")
        if result.audit_record:
            print(f"  History ID: {result.audit_record.history_id}")
            print(f"  Reviewed at: {result.audit_record.reviewed_at}")
    else:
        print(f"✗ Transition failed: {result.error_code}")
        if result.error_message:
            print(f"  {result.error_message}")


def main() -> int:
    if not DEFAULT_DATABASE_PATH.exists():
        print(
            f"Database not found: {DEFAULT_DATABASE_PATH}",
            file=sys.stderr,
        )
        return 1
    review_status(DEFAULT_DATABASE_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
