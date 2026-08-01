"""Integration tests for synthetic validation data isolation.

Validates:
- Synthetic program IDs are disjoint from the 6 canonical MVP IDs
- All synthetic work happens in a temporary database, never a canonical path
- Canonical catalog artifacts keep an identical SHA-256 checksum across a full
  synthetic workload (no contamination of the real catalog)
- Synthetic rules, source content and excerpts never reach verified evidence
- Protected transitions stay gated behind a human reviewer even for synthetic
  programs, and human approvals record identity, timestamp and version

Requirements: 15.1-15.4, 15.9, 15.10, 16.6-16.13
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.migrations import (
    _MVP_CATALOG_IDS,
    migrate_database,
)
from backend.app.curation.review_service import (
    FORBIDDEN_ACTORS,
    PROTECTED_TARGET_STATUSES,
    ReviewArtifacts,
    ReviewService,
    TransitionAuditRecord,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_MANIFEST = (
    REPO_ROOT / "data" / "benefit_discovery" / "mvp_catalog_manifest.v1.json"
)
CANONICAL_DATABASE = REPO_ROOT / "data" / "local" / "government_oid.db"

SYNTHETIC_PREFIX = "synth_"
SYNTHETIC_PROGRAM_IDS = (
    "synth_test_program_001",
    "synth_test_program_002",
)
SYNTHETIC_MARKER = "SYNTHETIC-FIXTURE-DO-NOT-PUBLISH"
NOW = "2026-07-30T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _synthetic_database(tmp_path: Path) -> Path:
    """Migrate an isolated database that lives only under tmp_path."""
    database = tmp_path / "synthetic-isolation.db"
    result = migrate_database(database)
    assert result.current_version == 7
    return database


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _insert_synthetic_programs(connection: sqlite3.Connection) -> None:
    connection.executemany(
        """
        INSERT INTO benefit_programs (
            program_id, canonical_name, program_status, created_at, updated_at
        ) VALUES (?, ?, 'candidate', ?, ?)
        """,
        [
            (program_id, f"{SYNTHETIC_MARKER} {program_id}", NOW, NOW)
            for program_id in SYNTHETIC_PROGRAM_IDS
        ],
    )


def _insert_synthetic_rule(connection: sqlite3.Connection, program_id: str) -> str:
    """Insert a candidate (never approved) synthetic rule version."""
    rule_id = f"{program_id}_rule"
    rule_version_id = f"{rule_id}_v1"
    connection.execute(
        "INSERT INTO rule_definitions (rule_id, program_id) VALUES (?, ?)",
        (rule_id, program_id),
    )
    connection.execute(
        """
        INSERT INTO rule_versions (
            rule_version_id, rule_id, version, dsl_version,
            approval_status, is_current, created_at
        ) VALUES (?, ?, 'synthetic-v1', '1.0', 'candidate', 0, ?)
        """,
        (rule_version_id, rule_id, NOW),
    )
    return rule_version_id


def _insert_synthetic_evidence(connection: sqlite3.Connection) -> str:
    """Insert a candidate synthetic source document and excerpt."""
    connection.execute(
        """
        INSERT INTO source_registry (
            source_id, name, source_type, base_url, entry_url, canonical_host,
            official_status, access_method, connection_status,
            created_at, updated_at
        ) VALUES (
            'synth_source_001', ?, 'other',
            'https://synthetic.invalid', 'https://synthetic.invalid/entry',
            'synthetic.invalid', 'pending_review', 'manual_seed', 'pending',
            ?, ?
        )
        """,
        (f"{SYNTHETIC_MARKER} source", NOW, NOW),
    )
    connection.execute(
        """
        INSERT INTO source_documents (
            document_id, canonical_url, title, first_seen_at, last_seen_at,
            review_status, created_at, updated_at
        ) VALUES (
            'synth_doc_001', 'https://synthetic.invalid/doc-001', ?,
            ?, ?, 'candidate', ?, ?
        )
        """,
        (f"{SYNTHETIC_MARKER} document", NOW, NOW, NOW, NOW),
    )
    connection.execute(
        """
        INSERT INTO document_discoveries (
            document_id, source_id, discovery_method,
            first_seen_at, last_seen_at
        ) VALUES ('synth_doc_001', 'synth_source_001', 'manual_seed', ?, ?)
        """,
        (NOW, NOW),
    )
    connection.execute(
        """
        INSERT INTO evidence_excerpts (
            evidence_id, document_id, excerpt, review_status,
            created_at, updated_at
        ) VALUES ('synth_evidence_001', 'synth_doc_001', ?, 'candidate', ?, ?)
        """,
        (f"{SYNTHETIC_MARKER} excerpt text", NOW, NOW),
    )
    return "synth_evidence_001"


def _run_full_synthetic_workload(database: Path) -> None:
    """Insert synthetic programs, rules and evidence into an isolated DB."""
    with closing(_connect(database)) as connection:
        _insert_synthetic_programs(connection)
        for program_id in SYNTHETIC_PROGRAM_IDS:
            _insert_synthetic_rule(connection, program_id)
        evidence_id = _insert_synthetic_evidence(connection)
        connection.execute(
            """
            INSERT INTO program_evidence_links (
                program_id, evidence_id, evidence_role, review_status
            ) VALUES (?, ?, 'eligibility', 'candidate')
            """,
            (SYNTHETIC_PROGRAM_IDS[0], evidence_id),
        )
        connection.commit()


class _SqlitePersistence:
    """ReviewPersistence implementation bound to the temporary database."""

    def __init__(self, database: Path) -> None:
        self._database = database

    def persist_transition(self, record: TransitionAuditRecord) -> None:
        with closing(_connect(self._database)) as connection:
            connection.execute(
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
            connection.execute(
                "UPDATE benefit_programs SET program_status = ?, updated_at = ? "
                "WHERE program_id = ?",
                (record.to_status, record.reviewed_at, record.program_id),
            )
            connection.commit()

    def get_current_status(self, program_id: str) -> str | None:
        with closing(_connect(self._database)) as connection:
            row = connection.execute(
                "SELECT program_status FROM benefit_programs WHERE program_id = ?",
                (program_id,),
            ).fetchone()
        return row[0] if row else None


# ---------------------------------------------------------------------------
# Synthetic identifier isolation (Requirement 15.9)
# ---------------------------------------------------------------------------


def test_synthetic_ids_are_disjoint_from_mvp_catalog() -> None:
    """Synthetic fixture IDs must never collide with canonical MVP IDs."""
    synthetic = set(SYNTHETIC_PROGRAM_IDS)
    assert synthetic.isdisjoint(_MVP_CATALOG_IDS)
    for program_id in synthetic:
        assert program_id.startswith(SYNTHETIC_PREFIX), (
            f"synthetic id {program_id} lacks the {SYNTHETIC_PREFIX!r} prefix"
        )
    for program_id in _MVP_CATALOG_IDS:
        assert not program_id.startswith(SYNTHETIC_PREFIX)


def test_canonical_manifest_contains_only_the_six_mvp_ids() -> None:
    """The canonical manifest must list exactly the 6 MVP IDs, no synthetics."""
    manifest = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    manifest_ids = {entry["program_id"] for entry in manifest["programs"]}
    assert manifest_ids == set(_MVP_CATALOG_IDS)
    assert len(manifest["programs"]) == 6
    assert manifest_ids.isdisjoint(SYNTHETIC_PROGRAM_IDS)


def test_canonical_manifest_declares_no_real_facts() -> None:
    """Manifest constraints must forbid facts, amounts and source excerpts."""
    manifest = json.loads(CANONICAL_MANIFEST.read_text(encoding="utf-8"))
    constraints = manifest["constraints"]
    assert constraints["allowed_ids_only"] is True
    assert constraints["max_programs"] == 6
    assert constraints["no_real_facts"] is True
    assert constraints["no_thresholds"] is True
    assert constraints["no_deadlines"] is True
    assert constraints["no_amounts"] is True
    assert constraints["no_source_excerpts"] is True
    for entry in manifest["programs"]:
        assert entry["initial_status"] in ("candidate", "under_review")
        assert entry["facts_status"] == "no_human_approved_facts"


# ---------------------------------------------------------------------------
# Temporary database isolation (Requirements 15.9, 15.10)
# ---------------------------------------------------------------------------


def test_synthetic_database_lives_outside_canonical_paths(tmp_path: Path) -> None:
    """The synthetic database must not be inside any canonical data path."""
    database = _synthetic_database(tmp_path)
    resolved = database.resolve()
    assert resolved.is_relative_to(tmp_path.resolve())
    assert not resolved.is_relative_to((REPO_ROOT / "data").resolve())
    assert resolved != CANONICAL_DATABASE.resolve()


def test_canonical_manifest_checksum_unchanged_by_synthetic_workload(
    tmp_path: Path,
) -> None:
    """A full synthetic workload must not alter the canonical manifest."""
    before = _sha256(CANONICAL_MANIFEST)
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    after = _sha256(CANONICAL_MANIFEST)
    assert before == after


def test_canonical_database_checksum_unchanged_by_synthetic_workload(
    tmp_path: Path,
) -> None:
    """A full synthetic workload must not alter the canonical database."""
    if not CANONICAL_DATABASE.exists():
        pytest.skip("canonical database is not present in this environment")
    before = _sha256(CANONICAL_DATABASE)
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    after = _sha256(CANONICAL_DATABASE)
    assert before == after


def test_synthetic_workload_does_not_touch_canonical_data_directory(
    tmp_path: Path,
) -> None:
    """No canonical data file may be created, removed or renamed."""
    data_root = REPO_ROOT / "data"
    before = {path.relative_to(data_root) for path in data_root.rglob("*")}
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    after = {path.relative_to(data_root) for path in data_root.rglob("*")}
    assert before == after


# ---------------------------------------------------------------------------
# Synthetic rule / evidence containment (Requirements 15.2, 15.3, 15.9)
# ---------------------------------------------------------------------------


def test_synthetic_rules_never_attach_to_mvp_programs(tmp_path: Path) -> None:
    """Synthetic rules must not be reachable from any MVP program."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    with closing(_connect(database)) as connection:
        mvp_rules = connection.execute(
            """
            SELECT program_id FROM rule_definitions
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_CATALOG_IDS)),
        ).fetchall()
        synthetic_rules = connection.execute(
            "SELECT program_id FROM rule_definitions"
        ).fetchall()
    assert mvp_rules == []
    assert {str(row[0]) for row in synthetic_rules} == set(SYNTHETIC_PROGRAM_IDS)


def test_synthetic_rule_versions_are_never_approved(tmp_path: Path) -> None:
    """Synthetic rule versions stay candidate and never become current."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    with closing(_connect(database)) as connection:
        rows = connection.execute(
            "SELECT rule_version_id, approval_status, is_current, "
            "approved_by, approved_at FROM rule_versions"
        ).fetchall()
    assert rows, "expected synthetic rule versions to exist"
    for rule_version_id, status, is_current, approved_by, approved_at in rows:
        assert status == "candidate", f"{rule_version_id} was approved"
        assert is_current == 0
        assert approved_by is None
        assert approved_at is None


def test_synthetic_excerpts_never_become_verified_evidence(tmp_path: Path) -> None:
    """Synthetic excerpts must stay unverified and unlinked from MVP programs."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    with closing(_connect(database)) as connection:
        verified_evidence = connection.execute(
            "SELECT evidence_id FROM evidence_excerpts WHERE review_status = 'verified'"
        ).fetchall()
        verified_links = connection.execute(
            "SELECT program_id FROM program_evidence_links "
            "WHERE review_status = 'verified'"
        ).fetchall()
        mvp_links = connection.execute(
            """
            SELECT program_id FROM program_evidence_links
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_CATALOG_IDS)),
        ).fetchall()
    assert verified_evidence == []
    assert verified_links == []
    assert mvp_links == []


def test_synthetic_evidence_cannot_be_verified_without_official_source(
    tmp_path: Path,
) -> None:
    """Only human-approved official sources can back verified evidence."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    with closing(_connect(database)) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="verified official source"):
            connection.execute(
                "UPDATE evidence_excerpts SET review_status = 'verified', "
                "reviewer_ref = 'reviewer-001', reviewed_at = ? "
                "WHERE evidence_id = 'synth_evidence_001'",
                (NOW,),
            )


def test_mvp_programs_keep_unknown_facts_after_synthetic_workload(
    tmp_path: Path,
) -> None:
    """MVP programs keep null amounts and non-verified status (no presumption)."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    with closing(_connect(database)) as connection:
        rows = connection.execute(
            """
            SELECT program_id, program_status, amount_min, amount_max,
                   amount_period, amount_currency
            FROM benefit_programs
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_CATALOG_IDS)),
        ).fetchall()
    assert {str(row[0]) for row in rows} == set(_MVP_CATALOG_IDS)
    for row in rows:
        assert row[1] in ("candidate", "under_review"), f"{row[0]}: {row[1]}"
        assert all(value is None for value in row[2:6]), f"{row[0]} has amounts"


def test_canonical_names_carry_no_synthetic_marker(tmp_path: Path) -> None:
    """Synthetic marker text must never appear on an MVP program row."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    with closing(_connect(database)) as connection:
        rows = connection.execute(
            """
            SELECT program_id, canonical_name, summary, claimant_rule_text,
                   deadline_rule_text
            FROM benefit_programs
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_CATALOG_IDS)),
        ).fetchall()
    for row in rows:
        for value in row[1:]:
            assert SYNTHETIC_MARKER not in str(value), f"{row[0]} leaked synthetic text"


# ---------------------------------------------------------------------------
# Protected transition gates (Requirements 15.4, 16.6-16.13)
# ---------------------------------------------------------------------------


def test_schema_rejects_non_human_actor_types(tmp_path: Path) -> None:
    """crawler / llm / importer are not even representable as actor types."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    program_id = SYNTHETIC_PROGRAM_IDS[0]
    with closing(_connect(database)) as connection:
        for index, actor in enumerate(sorted(FORBIDDEN_ACTORS - {"migration"})):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO program_status_history (
                        history_id, program_id, from_status, to_status,
                        actor_type, reviewer_ref, reviewed_at, approved_version
                    ) VALUES (?, ?, 'candidate', 'verified', ?, ?, ?, 'v1')
                    """,
                    (f"synth-history-{index}", program_id, actor, actor, NOW),
                )


def test_migration_actor_cannot_verify_synthetic_program(tmp_path: Path) -> None:
    """The migration actor is blocked from protected transitions by trigger."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    with closing(_connect(database)) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="human reviewer"):
            connection.execute(
                """
                INSERT INTO program_status_history (
                    history_id, program_id, from_status, to_status,
                    actor_type, reviewer_ref, reviewed_at, approved_version
                ) VALUES (
                    'synth-history-migration', ?, 'candidate', 'verified',
                    'migration', 'test-migration', ?, 'v1'
                )
                """,
                (SYNTHETIC_PROGRAM_IDS[0], NOW),
            )


@pytest.mark.parametrize("actor", sorted(FORBIDDEN_ACTORS))
def test_review_service_blocks_forbidden_actors(tmp_path: Path, actor: str) -> None:
    """ReviewService rejects every non-human actor before touching storage."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    service = ReviewService(_SqlitePersistence(database))

    result = service.transition_status(
        program_id=SYNTHETIC_PROGRAM_IDS[0],
        to_status="verified",
        actor_type=actor,
        reviewer_ref=f"{actor}-bot",
        approved_version="v1.0",
        artifacts=ReviewArtifacts(
            approved_rule_version="v1.0",
            citation_ids=("synth-cite-001",),
            approved_excerpt=f"{SYNTHETIC_MARKER} excerpt",
        ),
    )

    assert result.success is False
    assert result.error_code == "forbidden_actor"
    with closing(_connect(database)) as connection:
        rows = connection.execute("SELECT * FROM program_status_history").fetchall()
        status = connection.execute(
            "SELECT program_status FROM benefit_programs WHERE program_id = ?",
            (SYNTHETIC_PROGRAM_IDS[0],),
        ).fetchone()
    assert rows == []
    assert status == ("candidate",)


def test_review_service_blocks_incomplete_artifacts(tmp_path: Path) -> None:
    """A human reviewer without complete artifacts cannot verify."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    service = ReviewService(_SqlitePersistence(database))

    result = service.transition_status(
        program_id=SYNTHETIC_PROGRAM_IDS[0],
        to_status="verified",
        actor_type="human_reviewer",
        reviewer_ref="reviewer-001",
        approved_version="v1.0",
        artifacts=ReviewArtifacts(approved_rule_version="v1.0"),
    )

    assert result.success is False
    assert result.error_code == "incomplete_artifacts"
    with closing(_connect(database)) as connection:
        rows = connection.execute("SELECT * FROM program_status_history").fetchall()
    assert rows == []


def test_human_approval_records_identity_timestamp_and_version(
    tmp_path: Path,
) -> None:
    """A complete human approval persists reviewer ref, timestamp and version."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    service = ReviewService(_SqlitePersistence(database))

    result = service.transition_status(
        program_id=SYNTHETIC_PROGRAM_IDS[0],
        to_status="verified",
        actor_type="human_reviewer",
        reviewer_ref="reviewer-001",
        approved_version="v1.0",
        artifacts=ReviewArtifacts(
            approved_rule_version="v1.0",
            citation_ids=("synth-cite-001",),
            approved_excerpt=f"{SYNTHETIC_MARKER} excerpt",
        ),
    )

    assert result.success is True
    assert result.audit_record is not None
    with closing(_connect(database)) as connection:
        row = connection.execute(
            """
            SELECT program_id, from_status, to_status, actor_type,
                   reviewer_ref, reviewed_at, approved_version
            FROM program_status_history
            """
        ).fetchone()
    assert row[0] == SYNTHETIC_PROGRAM_IDS[0]
    assert row[1] == "candidate"
    assert row[2] == "verified"
    assert row[3] == "human_reviewer"
    assert row[4] == "reviewer-001"
    assert row[5] != ""
    assert row[6] == "v1.0"


def test_verified_synthetic_program_does_not_reach_mvp_catalog(
    tmp_path: Path,
) -> None:
    """Even an approved synthetic program leaves the MVP catalog untouched."""
    manifest_before = _sha256(CANONICAL_MANIFEST)
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    service = ReviewService(_SqlitePersistence(database))

    result = service.transition_status(
        program_id=SYNTHETIC_PROGRAM_IDS[0],
        to_status="verified",
        actor_type="human_reviewer",
        reviewer_ref="reviewer-001",
        approved_version="v1.0",
        artifacts=ReviewArtifacts(
            approved_rule_version="v1.0",
            citation_ids=("synth-cite-001",),
            approved_excerpt=f"{SYNTHETIC_MARKER} excerpt",
        ),
    )
    assert result.success is True

    with closing(_connect(database)) as connection:
        mvp_statuses = connection.execute(
            """
            SELECT program_status FROM benefit_programs
            WHERE program_id IN (?, ?, ?, ?, ?, ?)
            """,
            tuple(sorted(_MVP_CATALOG_IDS)),
        ).fetchall()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert all(status == ("candidate",) for status in mvp_statuses)
    assert violations == []
    assert _sha256(CANONICAL_MANIFEST) == manifest_before


def test_protected_target_statuses_are_gated(tmp_path: Path) -> None:
    """Every protected target status is unreachable without a human reviewer."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    service = ReviewService(_SqlitePersistence(database))

    assert PROTECTED_TARGET_STATUSES == frozenset({"verified"})
    for to_status in sorted(PROTECTED_TARGET_STATUSES):
        result = service.transition_status(
            program_id=SYNTHETIC_PROGRAM_IDS[1],
            to_status=to_status,
            actor_type="llm",
            reviewer_ref="llm-agent",
            approved_version="v1.0",
            artifacts=None,
        )
        assert result.success is False
        assert result.error_code == "forbidden_actor"


def test_llm_and_crawler_results_stay_candidate_or_under_review(
    tmp_path: Path,
) -> None:
    """Non-human pipelines can only leave rows at candidate / under_review."""
    database = _synthetic_database(tmp_path)
    _run_full_synthetic_workload(database)
    with closing(_connect(database)) as connection:
        statuses = connection.execute(
            "SELECT program_id, program_status FROM benefit_programs"
        ).fetchall()
        document_statuses = connection.execute(
            "SELECT document_id, review_status FROM source_documents"
        ).fetchall()
    for program_id, status in statuses:
        assert status in ("candidate", "under_review"), f"{program_id}: {status}"
    for document_id, status in document_statuses:
        assert status in ("candidate", "under_review"), f"{document_id}: {status}"
