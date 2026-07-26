"""Local review server for benefit program candidates.

Provides a web UI to browse, edit, and verify benefit programs stored in the
local SQLite database. This is an internal tool — not the production API.

Usage:
    python3 scripts/review_server.py

Then open http://localhost:8100 in your browser.
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.import_government_oid import DEFAULT_DATABASE_PATH  # noqa: E402

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
except ImportError:
    print(
        "FastAPI and pydantic are required. Install them or run from the "
        "backend venv:\n  pip install fastapi uvicorn pydantic",
        file=sys.stderr,
    )
    sys.exit(1)

app = FastAPI(title="Benefit Review UI", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DEFAULT_DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# --- Models ---


class ProgramUpdate(BaseModel):
    canonical_name: str | None = None
    summary: str | None = None
    support_purpose: str | None = None
    program_basis: str | None = None
    delivery_form: str | None = None
    jurisdiction_code: str | None = None
    claimant_rule_text: str | None = None
    deadline_rule_text: str | None = None
    mutual_exclusion_text: str | None = None
    status_note: str | None = None


class VerifyRequest(BaseModel):
    confirm: bool = True


# --- API Routes ---


@app.get("/api/programs")
def list_programs():
    """List all benefit programs with their evidence and org roles."""
    with closing(_get_connection()) as conn:
        programs = conn.execute(
            "SELECT * FROM benefit_programs ORDER BY canonical_name"
        ).fetchall()
        result = []
        for p in programs:
            program_id = p["program_id"]
            sources = conn.execute(
                """SELECT ps.*, sd.canonical_url, sd.title AS doc_title,
                          sd.source_updated_at
                   FROM program_sources ps
                   JOIN source_documents sd ON sd.document_id = ps.document_id
                   WHERE ps.program_id = ?""",
                (program_id,),
            ).fetchall()
            roles = conn.execute(
                "SELECT * FROM program_organization_roles WHERE program_id = ?",
                (program_id,),
            ).fetchall()
            result.append({
                "program": dict(p),
                "sources": [dict(s) for s in sources],
                "roles": [dict(r) for r in roles],
                "rule_fields": [
                    dict(rf)
                    for rf in conn.execute(
                        """SELECT field_name, field_type, field_value,
                                  source_excerpt, review_status
                           FROM program_rule_fields
                           WHERE program_id = ?
                           ORDER BY field_name""",
                        (program_id,),
                    ).fetchall()
                ],
            })
        return result


@app.get("/api/programs/{program_id}")
def get_program(program_id: str):
    """Get a single program with full detail."""
    with closing(_get_connection()) as conn:
        p = conn.execute(
            "SELECT * FROM benefit_programs WHERE program_id = ?",
            (program_id,),
        ).fetchone()
        if not p:
            raise HTTPException(404, "Program not found")
        sources = conn.execute(
            """SELECT ps.*, sd.canonical_url, sd.title AS doc_title,
                      sd.source_updated_at
               FROM program_sources ps
               JOIN source_documents sd ON sd.document_id = ps.document_id
               WHERE ps.program_id = ?""",
            (program_id,),
        ).fetchall()
        roles = conn.execute(
            "SELECT * FROM program_organization_roles WHERE program_id = ?",
            (program_id,),
        ).fetchall()
        return {
            "program": dict(p),
            "sources": [dict(s) for s in sources],
            "roles": [dict(r) for r in roles],
        }


@app.patch("/api/programs/{program_id}")
def update_program(program_id: str, body: ProgramUpdate):
    """Update editable fields of a program."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    with closing(_get_connection()) as conn:
        existing = conn.execute(
            "SELECT 1 FROM benefit_programs WHERE program_id = ?",
            (program_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Program not found")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [_utc_now(), program_id]
        conn.execute(
            f"UPDATE benefit_programs SET {set_clause}, updated_at = ? "
            f"WHERE program_id = ?",
            values,
        )
        conn.commit()
    return {"status": "updated", "program_id": program_id}


@app.post("/api/programs/{program_id}/verify")
def verify_program(program_id: str, body: VerifyRequest):
    """Mark a program as verified (requires all key fields filled)."""
    with closing(_get_connection()) as conn:
        p = conn.execute(
            "SELECT * FROM benefit_programs WHERE program_id = ?",
            (program_id,),
        ).fetchone()
        if not p:
            raise HTTPException(404, "Program not found")
        if not body.confirm:
            raise HTTPException(400, "confirm must be true")
        # Check required fields for verified status
        missing = []
        if not p["support_purpose"]:
            missing.append("support_purpose")
        if not p["program_basis"]:
            missing.append("program_basis")
        if not p["delivery_form"]:
            missing.append("delivery_form")
        if missing:
            raise HTTPException(
                400,
                f"Cannot verify: missing required fields: {', '.join(missing)}",
            )
        now = _utc_now()
        conn.execute(
            """UPDATE benefit_programs
               SET program_status = 'verified',
                   first_verified_at = COALESCE(first_verified_at, ?),
                   last_verified_at = ?,
                   updated_at = ?
               WHERE program_id = ?""",
            (now, now, now, program_id),
        )
        # Also mark sources and roles as verified
        conn.execute(
            """UPDATE program_sources
               SET review_status = 'verified', reviewed_at = ?, updated_at = ?
               WHERE program_id = ?""",
            (now, now, program_id),
        )
        conn.execute(
            """UPDATE program_organization_roles
               SET review_status = 'verified', updated_at = ?
               WHERE program_id = ?""",
            (now, program_id),
        )
        conn.commit()
    return {"status": "verified", "program_id": program_id}


@app.post("/api/programs/{program_id}/unverify")
def unverify_program(program_id: str):
    """Revert a program back to candidate status."""
    with closing(_get_connection()) as conn:
        conn.execute(
            """UPDATE benefit_programs
               SET program_status = 'candidate', updated_at = ?
               WHERE program_id = ?""",
            (_utc_now(), program_id),
        )
        conn.commit()
    return {"status": "reverted_to_candidate", "program_id": program_id}


# --- Rule Fields API ---


class RuleFieldUpdate(BaseModel):
    field_type: str = "text"
    field_value: str = ""
    source_excerpt: str = ""


@app.get("/api/programs/{program_id}/rule-fields")
def get_rule_fields(program_id: str):
    """Get all structured rule fields for a program."""
    with closing(_get_connection()) as conn:
        rows = conn.execute(
            """SELECT field_name, field_type, field_value,
                      source_excerpt, review_status
               FROM program_rule_fields
               WHERE program_id = ?
               ORDER BY field_name""",
            (program_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.put("/api/programs/{program_id}/rule-fields/{field_name}")
def upsert_rule_field(
    program_id: str, field_name: str, body: RuleFieldUpdate
):
    """Create or update a rule field for a program."""
    with closing(_get_connection()) as conn:
        existing = conn.execute(
            "SELECT 1 FROM benefit_programs WHERE program_id = ?",
            (program_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Program not found")
        now = _utc_now()
        conn.execute(
            """INSERT INTO program_rule_fields
               (program_id, field_name, field_type, field_value,
                source_excerpt, review_status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
               ON CONFLICT (program_id, field_name)
               DO UPDATE SET
                   field_type = excluded.field_type,
                   field_value = excluded.field_value,
                   source_excerpt = excluded.source_excerpt,
                   updated_at = excluded.updated_at""",
            (
                program_id,
                field_name,
                body.field_type,
                body.field_value,
                body.source_excerpt,
                now,
                now,
            ),
        )
        conn.commit()
    return {"status": "saved", "field_name": field_name}


@app.delete("/api/programs/{program_id}/rule-fields/{field_name}")
def delete_rule_field(program_id: str, field_name: str):
    """Remove a rule field from a program."""
    with closing(_get_connection()) as conn:
        conn.execute(
            """DELETE FROM program_rule_fields
               WHERE program_id = ? AND field_name = ?""",
            (program_id, field_name),
        )
        conn.commit()
    return {"status": "deleted", "field_name": field_name}


@app.get("/api/rule-field-definitions")
def list_field_definitions():
    """List all distinct field names used across programs (for reference)."""
    with closing(_get_connection()) as conn:
        rows = conn.execute(
            """SELECT field_name, field_type, COUNT(*) as usage_count
               FROM program_rule_fields
               GROUP BY field_name, field_type
               ORDER BY field_name"""
        ).fetchall()
        return [dict(r) for r in rows]


# --- HTML UI ---

REVIEW_UI_PATH = Path(__file__).parent / "review_ui.html"


@app.get("/", response_class=HTMLResponse)
def serve_ui():
    """Serve the review UI."""
    return HTMLResponse(REVIEW_UI_PATH.read_text(encoding="utf-8"))


# --- Main ---


def main() -> int:
    if not DEFAULT_DATABASE_PATH.exists():
        print(
            f"Database not found: {DEFAULT_DATABASE_PATH}\n"
            "Run the import and init scripts first.",
            file=sys.stderr,
        )
        return 1

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is required. Install it:\n  pip install uvicorn",
            file=sys.stderr,
        )
        return 1

    print("Starting review server at http://localhost:8100")
    print("Press Ctrl+C to stop.\n")
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
