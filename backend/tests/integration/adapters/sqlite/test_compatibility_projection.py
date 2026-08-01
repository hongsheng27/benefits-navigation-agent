"""Integration tests for CompatibilityProjectionRepository.

Tests atomic generation persistence, active pointer switching, read-only
enforcement, and failure rollback using a temporary SQLite database with
all migrations applied.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.adapters.sqlite.compatibility_repository import (
    CompatibilityProjectionRepository,
    ProjectionGenerationError,
)
from app.adapters.sqlite.migrations import migrate_database
from app.rules.compatibility import (
    compute_canonical_hash,
    convert_to_projection,
)
from app.rules.dsl import (
    AllOf,
    AnyOf,
    Condition,
    RuleDefinition,
)

NOW = "2026-07-30T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_database(tmp_path: Path) -> Path:
    """Create a fully migrated database."""
    database = tmp_path / "compat-projection.db"
    migrate_database(database)
    return database


def _make_connection_factory(db_path: Path):
    """Return a callable that creates a new connection to the database."""

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    return factory


def _insert_program_and_rule(
    db_path: Path,
    *,
    program_id: str = "program-1",
    rule_id: str = "rule-1",
    rule_version_id: str = "rv-1",
) -> None:
    """Insert minimal program, rule_definition, and rule_version for testing."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT OR IGNORE INTO benefit_programs (
                program_id, canonical_name, created_at, updated_at
            ) VALUES (?, 'Synthetic Program', ?, ?)
            """,
            (program_id, NOW, NOW),
        )
        conn.execute(
            "INSERT OR IGNORE INTO rule_definitions VALUES (?, ?)",
            (rule_id, program_id),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO rule_versions (
                rule_version_id, rule_id, version, dsl_version,
                approval_status, is_current, created_at
            ) VALUES (?, ?, '1', '1.0', 'candidate', 0, ?)
            """,
            (rule_version_id, rule_id, NOW),
        )


def _make_rule(
    *,
    rule_id: str = "rule-1",
    item_id: str = "program-1",
) -> RuleDefinition:
    """Create a simple synthetic rule for testing."""
    return RuleDefinition(
        rule_id=rule_id,
        item_id=item_id,
        version=1,
        dsl_version="1.0",
        required_field_ids=("age",),
        root=AllOf(
            children=(
                Condition(
                    condition_id="cond-1",
                    field_id="age",
                    operator=">=",
                    expected=18,
                    label="Age at least 18",
                    source_reference="source-ref-1",
                ),
            )
        ),
        source_references=("source-ref-1",),
    )


def _make_rule_v2(
    *,
    rule_id: str = "rule-1",
    item_id: str = "program-1",
) -> RuleDefinition:
    """Create a different rule for testing replacement."""
    return RuleDefinition(
        rule_id=rule_id,
        item_id=item_id,
        version=2,
        dsl_version="1.0",
        required_field_ids=("age", "income"),
        root=AllOf(
            children=(
                Condition(
                    condition_id="cond-1",
                    field_id="age",
                    operator=">=",
                    expected=65,
                    label="Age at least 65",
                    source_reference="source-ref-2",
                ),
                Condition(
                    condition_id="cond-2",
                    field_id="income",
                    operator="<=",
                    expected=30000,
                    label="Income at most 30000",
                    source_reference="source-ref-3",
                ),
            )
        ),
        source_references=("source-ref-2", "source-ref-3"),
    )


# ---------------------------------------------------------------------------
# Tests: Successful generation and active pointer switch
# ---------------------------------------------------------------------------


class TestSuccessfulGeneration:
    """Tests for successful projection generation."""

    def test_generate_creates_active_generation(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        assert generation_id is not None
        assert len(generation_id) == 36  # UUID format

        # Active pointer should be set
        active = repo.get_active_generation("program-1")
        assert active is not None
        assert active == (generation_id, "rv-1")

    def test_generate_stores_validated_generation(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        # Verify the generation is marked validated in DB
        with closing(sqlite3.connect(db_path)) as conn:
            row = conn.execute(
                """
                SELECT status, row_count, validated_at
                FROM compat_projection_generations
                WHERE generation_id = ?
                """,
                (generation_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == "validated"
        assert row[1] > 0
        assert row[2] is not None

    def test_read_projection_rows_returns_correct_data(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")
        rows = repo.read_projection_rows(generation_id)

        assert len(rows) > 0
        # Rows should be ordered by ordinal
        ordinals = [r.ordinal for r in rows]
        assert ordinals == sorted(ordinals)
        # First row should be the metadata row
        assert rows[0].field_name == "__meta__"
        assert rows[0].field_type == "json"

    def test_read_projection_rows_matches_converter_output(
        self, tmp_path: Path
    ) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")
        stored_rows = repo.read_projection_rows(generation_id)
        expected_rows = convert_to_projection(rule)

        assert len(stored_rows) == len(expected_rows)
        for stored, expected in zip(stored_rows, expected_rows, strict=True):
            assert stored.ordinal == expected.ordinal
            assert stored.field_name == expected.field_name
            assert stored.field_type == expected.field_type
            assert stored.field_value == expected.field_value
            assert stored.source_excerpt == expected.source_excerpt

    def test_hash_matches_canonical_computation(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            row = conn.execute(
                "SELECT canonical_hash"
                " FROM compat_projection_generations"
                " WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
        stored_hash = row[0]

        expected_rows = convert_to_projection(rule)
        expected_hash = compute_canonical_hash(expected_rows)
        assert stored_hash == expected_hash


# ---------------------------------------------------------------------------
# Tests: Atomic replacement — new generation replaces old
# ---------------------------------------------------------------------------


class TestAtomicReplacement:
    """Tests for atomic replacement of generations."""

    def test_new_generation_replaces_old_active(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        # Add a second rule version for the replacement
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO rule_versions (
                    rule_version_id, rule_id, version, dsl_version,
                    approval_status, is_current, created_at
                ) VALUES ('rv-2', 'rule-1', '2', '1.0', 'candidate', 0, ?)
                """,
                (NOW,),
            )

        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)

        # Generate first projection
        rule_v1 = _make_rule()
        gen_id_1 = repo.generate_projection(rule_v1, "rv-1", "program-1")

        # Generate second projection (replacement)
        rule_v2 = _make_rule_v2()
        gen_id_2 = repo.generate_projection(rule_v2, "rv-2", "program-1")

        # Active pointer should now point to the new generation
        active = repo.get_active_generation("program-1")
        assert active is not None
        assert active == (gen_id_2, "rv-2")
        assert gen_id_1 != gen_id_2

    def test_old_generation_rows_still_readable(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute(
                """
                INSERT INTO rule_versions (
                    rule_version_id, rule_id, version, dsl_version,
                    approval_status, is_current, created_at
                ) VALUES ('rv-2', 'rule-1', '2', '1.0', 'candidate', 0, ?)
                """,
                (NOW,),
            )

        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)

        rule_v1 = _make_rule()
        gen_id_1 = repo.generate_projection(rule_v1, "rv-1", "program-1")
        rows_v1 = repo.read_projection_rows(gen_id_1)

        rule_v2 = _make_rule_v2()
        repo.generate_projection(rule_v2, "rv-2", "program-1")

        # Old generation rows should still be readable
        rows_after = repo.read_projection_rows(gen_id_1)
        assert len(rows_after) == len(rows_v1)


# ---------------------------------------------------------------------------
# Tests: Failure preserves old generation
# ---------------------------------------------------------------------------


class TestFailurePreservesOldGeneration:
    """Tests that failures during generation preserve the old active pointer."""

    def test_invalid_program_id_preserves_old(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)

        # Generate a valid first projection
        rule = _make_rule()
        gen_id_1 = repo.generate_projection(rule, "rv-1", "program-1")

        # Try to generate with a non-existent program — should fail
        with pytest.raises(ProjectionGenerationError):
            repo.generate_projection(rule, "rv-1", "nonexistent-program")

        # Old active should be preserved
        active = repo.get_active_generation("program-1")
        assert active is not None
        assert active[0] == gen_id_1

    def test_no_active_generation_for_nonexistent_program(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)

        active = repo.get_active_generation("nonexistent-program")
        assert active is None

    def test_read_projection_rows_empty_for_nonexistent_generation(
        self, tmp_path: Path
    ) -> None:
        db_path = _setup_database(tmp_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)

        rows = repo.read_projection_rows("nonexistent-generation-id")
        assert rows == []


# ---------------------------------------------------------------------------
# Tests: Direct DML on projection rows/generations is rejected by triggers
# ---------------------------------------------------------------------------


class TestTriggerProtection:
    """Tests that DB triggers protect validated projections."""

    def test_insert_into_validated_generation_rows_rejected(
        self, tmp_path: Path
    ) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO compat_projection_rows (
                        generation_id, ordinal, program_id, field_name,
                        field_type, field_value, source_excerpt,
                        review_status, created_at, updated_at
                    ) VALUES (?, 999, 'program-1', 'injected', 'text',
                              'bad', '', 'pending', ?, ?)
                    """,
                    (generation_id, NOW, NOW),
                )

    def test_update_validated_generation_rows_rejected(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    UPDATE compat_projection_rows
                    SET field_value = 'tampered'
                    WHERE generation_id = ?
                    """,
                    (generation_id,),
                )

    def test_delete_validated_generation_rows_rejected(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    DELETE FROM compat_projection_rows
                    WHERE generation_id = ?
                    """,
                    (generation_id,),
                )

    def test_update_validated_generation_metadata_rejected(
        self, tmp_path: Path
    ) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    UPDATE compat_projection_generations
                    SET row_count = 999
                    WHERE generation_id = ?
                    """,
                    (generation_id,),
                )

    def test_delete_validated_generation_rejected(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    DELETE FROM compat_projection_generations
                    WHERE generation_id = ?
                    """,
                    (generation_id,),
                )


# ---------------------------------------------------------------------------
# Tests: Read-only view enforcement
# ---------------------------------------------------------------------------


class TestReadOnlyView:
    """Tests that the program_rule_fields view rejects DML."""

    def test_insert_into_view_rejected(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()
        repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    INSERT INTO program_rule_fields
                    VALUES ('p', 'f', 'text', 'v', '', 'pending', ?, ?)
                    """,
                    (NOW, NOW),
                )

    def test_update_view_rejected(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()
        repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("UPDATE program_rule_fields SET field_value = 'changed'")

    def test_delete_from_view_rejected(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()
        repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM program_rule_fields")


# ---------------------------------------------------------------------------
# Tests: View shows active generation data
# ---------------------------------------------------------------------------


class TestViewReflectsActive:
    """Tests that the program_rule_fields view reflects active generation."""

    def test_view_returns_active_generation_rows(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_rule()
        generation_id = repo.generate_projection(rule, "rv-1", "program-1")

        with closing(sqlite3.connect(db_path)) as conn:
            view_rows = conn.execute(
                """
                SELECT field_name, field_type
                FROM program_rule_fields
                WHERE program_id = 'program-1'
                ORDER BY field_name
                """
            ).fetchall()

        # The view should show the same rows stored in the generation
        stored_rows = repo.read_projection_rows(generation_id)
        view_field_names = {row[0] for row in view_rows}
        stored_field_names = {r.field_name for r in stored_rows}
        assert view_field_names == stored_field_names


# ---------------------------------------------------------------------------
# Tests: Complex rule with nested nodes
# ---------------------------------------------------------------------------


class TestComplexRule:
    """Tests with more complex rule structures."""

    def test_anyof_nested_rule_roundtrips(self, tmp_path: Path) -> None:
        db_path = _setup_database(tmp_path)
        _insert_program_and_rule(db_path)
        # Need field registry entries for the fields used
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executemany(
                """
                INSERT OR IGNORE INTO field_registry (
                    field_id, data_type, prompt_label, why_needed,
                    pii_classification, active
                ) VALUES (?, 'text', 'Label', 'Needed', 'none', 1)
                """,
                [("age",), ("income",), ("status",)],
            )

        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)

        rule = RuleDefinition(
            rule_id="rule-1",
            item_id="program-1",
            version=1,
            dsl_version="1.0",
            required_field_ids=("age", "income", "status"),
            root=AnyOf(
                children=(
                    AllOf(
                        children=(
                            Condition(
                                condition_id="c1",
                                field_id="age",
                                operator=">=",
                                expected=65,
                                label="Senior",
                                source_reference="ref-1",
                            ),
                            Condition(
                                condition_id="c2",
                                field_id="income",
                                operator="<=",
                                expected=20000,
                                label="Low income",
                                source_reference="ref-2",
                            ),
                        )
                    ),
                    Condition(
                        condition_id="c3",
                        field_id="status",
                        operator="==",
                        expected="disabled",
                        label="Disabled",
                        source_reference="ref-3",
                    ),
                )
            ),
            source_references=("ref-1", "ref-2", "ref-3"),
        )

        generation_id = repo.generate_projection(rule, "rv-1", "program-1")
        rows = repo.read_projection_rows(generation_id)

        # Should have metadata + nodes for AnyOf, AllOf, and 3 conditions
        assert len(rows) >= 4  # At minimum: meta + 3 nodes
        assert rows[0].field_name == "__meta__"

        # Verify hash integrity
        expected_hash = compute_canonical_hash(convert_to_projection(rule))
        with closing(sqlite3.connect(db_path)) as conn:
            stored_hash = conn.execute(
                "SELECT canonical_hash"
                " FROM compat_projection_generations"
                " WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()[0]
        assert stored_hash == expected_hash
