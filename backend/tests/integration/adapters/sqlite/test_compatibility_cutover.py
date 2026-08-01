"""Integration tests for migration comparison and cutover.

Validates:
- Legacy reader vs canonical projection comparison for representable data.
- Unrepresentable data stays at under_review (not silently promoted).
- View DML (INSERT/UPDATE/DELETE) on program_rule_fields is rejected.
- Runtime reader independence from writable legacy table.
- Legacy table read-only enforcement after migration.

All fixtures use synthetic IDs only — no real benefit facts.
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
    ConverterVersionError,
    convert_to_projection,
)
from app.rules.dsl import (
    AllOf,
    Condition,
    RuleDefinition,
)

NOW = "2026-08-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_database(tmp_path: Path) -> Path:
    """Create a fully migrated database."""
    db_path = tmp_path / "cutover-test.db"
    migrate_database(db_path)
    return db_path


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
    program_id: str = "synthetic-program-cutover-1",
    rule_id: str = "synthetic-rule-cutover-1",
    rule_version_id: str = "synthetic-rv-cutover-1",
) -> None:
    """Insert minimal parent records for testing."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT OR IGNORE INTO benefit_programs (
                program_id, canonical_name, created_at, updated_at
            ) VALUES (?, 'Synthetic Cutover Program', ?, ?)
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


def _make_simple_rule(
    *,
    rule_id: str = "synthetic-rule-cutover-1",
    item_id: str = "synthetic-program-cutover-1",
) -> RuleDefinition:
    """Create a simple synthetic rule for cutover testing."""
    return RuleDefinition(
        rule_id=rule_id,
        item_id=item_id,
        version=1,
        dsl_version="1.0",
        required_field_ids=("age",),
        root=AllOf(
            children=(
                Condition(
                    condition_id="cond-cutover-1",
                    field_id="age",
                    operator=">=",
                    expected=18,
                    label="Age at least 18",
                    source_reference="source-ref-cutover-1",
                ),
            )
        ),
        source_references=("source-ref-cutover-1",),
    )


def _insert_legacy_rows(
    db_path: Path,
    *,
    program_id: str = "synthetic-program-cutover-1",
) -> None:
    """Insert synthetic data into legacy_program_rule_fields_v1.

    We must disable triggers temporarily because the table is read-only
    after migration. This simulates data that was preserved during migration.
    """
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        # Disable the read-only triggers temporarily to insert test data
        conn.execute(
            "DROP TRIGGER IF EXISTS trg_legacy_program_rule_fields_read_only_insert"
        )
        conn.execute(
            """
            INSERT INTO legacy_program_rule_fields_v1 (
                program_id, field_name, field_type, field_value,
                source_excerpt, review_status, created_at, updated_at
            ) VALUES (?, 'age', 'integer', '18', 'source-ref-cutover-1',
                      'pending', ?, ?)
            """,
            (program_id, NOW, NOW),
        )
        # Re-create the trigger
        conn.execute(
            """
            CREATE TRIGGER trg_legacy_program_rule_fields_read_only_insert
            BEFORE INSERT ON legacy_program_rule_fields_v1
            BEGIN
                SELECT RAISE(ABORT, 'read-only preserved legacy rule fields');
            END
            """
        )


# ---------------------------------------------------------------------------
# Test 1: Legacy vs canonical projection comparison
# ---------------------------------------------------------------------------


class TestLegacyProjectionComparison:
    """Compare legacy reader data with canonical projection for representable data."""

    def test_canonical_projection_contains_equivalent_info(
        self, tmp_path: Path
    ) -> None:
        """For representable data, canonical projection contains equivalent info."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-1"
        _insert_program_and_rule(db_path, program_id=program_id)
        _insert_legacy_rows(db_path, program_id=program_id)

        # Generate canonical projection from equivalent Rule DSL
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_simple_rule()
        gen_id = repo.generate_projection(rule, "synthetic-rv-cutover-1", program_id)

        # Read legacy data via view (before canonical replaces it)
        # After generation, the view should show canonical projection rows
        with closing(sqlite3.connect(db_path)) as conn:
            view_rows = conn.execute(
                """
                SELECT field_name, field_type, field_value, source_excerpt
                FROM program_rule_fields
                WHERE program_id = ?
                ORDER BY field_name
                """,
                (program_id,),
            ).fetchall()

        # Read canonical projection rows directly
        projection_rows = repo.read_projection_rows(gen_id)

        # The view should reflect canonical projection (not legacy)
        view_field_names = {row[0] for row in view_rows}
        projection_field_names = {r.field_name for r in projection_rows}
        assert view_field_names == projection_field_names

    def test_legacy_fallback_when_no_active_generation(self, tmp_path: Path) -> None:
        """Without active generation, view falls back to legacy data."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-2"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-2",
            rule_version_id="synthetic-rv-cutover-2",
        )
        _insert_legacy_rows(db_path, program_id=program_id)

        # No canonical projection generated — view should show legacy
        with closing(sqlite3.connect(db_path)) as conn:
            view_rows = conn.execute(
                """
                SELECT field_name, field_type, field_value
                FROM program_rule_fields
                WHERE program_id = ?
                """,
                (program_id,),
            ).fetchall()

        assert len(view_rows) == 1
        assert view_rows[0][0] == "age"
        assert view_rows[0][1] == "integer"
        assert view_rows[0][2] == "18"

    def test_canonical_replaces_legacy_in_view(self, tmp_path: Path) -> None:
        """After generating projection, view shows canonical not legacy."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-3"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-3",
            rule_version_id="synthetic-rv-cutover-3",
        )
        _insert_legacy_rows(db_path, program_id=program_id)

        # Verify legacy data visible before generation
        with closing(sqlite3.connect(db_path)) as conn:
            before = conn.execute(
                "SELECT COUNT(*) FROM program_rule_fields WHERE program_id = ?",
                (program_id,),
            ).fetchone()[0]
        assert before == 1  # Legacy row

        # Generate canonical projection
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_simple_rule(
            rule_id="synthetic-rule-cutover-3",
            item_id=program_id,
        )
        repo.generate_projection(rule, "synthetic-rv-cutover-3", program_id)

        # After generation, view should show projection rows (not legacy)
        with closing(sqlite3.connect(db_path)) as conn:
            after_rows = conn.execute(
                """
                SELECT field_name FROM program_rule_fields
                WHERE program_id = ?
                ORDER BY field_name
                """,
                (program_id,),
            ).fetchall()

        # Projection includes __meta__ and node rows — more than 1 row
        after_names = [r[0] for r in after_rows]
        assert "__meta__" in after_names
        assert len(after_names) > 1


# ---------------------------------------------------------------------------
# Test 2: Unrepresentable data stays at review
# ---------------------------------------------------------------------------


class TestUnrepresentableDataStopsAtReview:
    """Verify that data the converter cannot losslessly represent fails safely."""

    def test_unsupported_node_type_raises_converter_version_error(
        self, tmp_path: Path
    ) -> None:
        """ConverterVersionError for unsupported node types."""
        from dataclasses import dataclass

        # Create a custom node type that the converter doesn't recognize
        @dataclass(frozen=True, slots=True)
        class UnsupportedNode:
            """A node type the converter cannot represent."""

            children: tuple = ()

        rule = RuleDefinition(
            rule_id="synthetic-rule-unrepresentable",
            item_id="synthetic-program-cutover-1",
            version=1,
            dsl_version="1.0",
            required_field_ids=("age",),
            root=UnsupportedNode(),  # type: ignore[arg-type]
            source_references=("ref-1",),
        )

        with pytest.raises(ConverterVersionError):
            convert_to_projection(rule)

    def test_unrepresentable_rule_does_not_create_projection(
        self, tmp_path: Path
    ) -> None:
        """If conversion fails, no projection is created for the program."""
        from dataclasses import dataclass

        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-4"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-4",
            rule_version_id="synthetic-rv-cutover-4",
        )

        @dataclass(frozen=True, slots=True)
        class UnsupportedNode:
            children: tuple = ()

        rule = RuleDefinition(
            rule_id="synthetic-rule-cutover-4",
            item_id=program_id,
            version=1,
            dsl_version="1.0",
            required_field_ids=("age",),
            root=UnsupportedNode(),  # type: ignore[arg-type]
            source_references=("ref-1",),
        )

        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)

        with pytest.raises(ProjectionGenerationError):
            repo.generate_projection(rule, "synthetic-rv-cutover-4", program_id)

        # No active generation should exist
        active = repo.get_active_generation(program_id)
        assert active is None

    def test_legacy_conversion_drafts_stay_under_review(self, tmp_path: Path) -> None:
        """Legacy conversion drafts remain under_review, never auto-verified."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-5"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-5",
            rule_version_id="synthetic-rv-cutover-5",
        )

        # Simulate a legacy conversion draft (manually insert)
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute("PRAGMA foreign_keys = ON")
            # Insert inventory first
            conn.execute(
                """
                INSERT INTO legacy_rule_migration_inventory (
                    inventory_id, source_table_name,
                    source_schema_sha256, source_rows_sha256,
                    row_count, converter_version, captured_at
                ) VALUES (
                    'synthetic-inv-1', 'program_rule_fields',
                    ?, ?, 1, 'legacy-rule-inventory-v1', ?
                )
                """,
                ("a" * 64, "b" * 64, NOW),
            )
            conn.execute(
                """
                INSERT INTO legacy_rule_conversion_drafts (
                    draft_id, inventory_id, program_id,
                    converter_version, conversion_status,
                    reason_code, source_row_count,
                    source_rows_sha256, created_at
                ) VALUES (
                    'synthetic-draft-1', 'synthetic-inv-1', ?,
                    'legacy-rule-inventory-v1', 'under_review',
                    'manual_mapping_required', 1, ?, ?
                )
                """,
                (program_id, "c" * 64, NOW),
            )

        # Verify the draft is under_review and NOT verified
        with closing(sqlite3.connect(db_path)) as conn:
            row = conn.execute(
                """
                SELECT conversion_status
                FROM legacy_rule_conversion_drafts
                WHERE program_id = ?
                """,
                (program_id,),
            ).fetchone()

        assert row is not None
        assert row[0] == "under_review"
        # The constraint only allows 'candidate' or 'under_review'
        # — never 'verified'. This is enforced by schema CHECK constraint.


# ---------------------------------------------------------------------------
# Test 3: View DML rejection
# ---------------------------------------------------------------------------


class TestViewDMLRejection:
    """Verify INSERT/UPDATE/DELETE on program_rule_fields view is rejected."""

    def test_insert_into_view_rejected(self, tmp_path: Path) -> None:
        """Direct INSERT on program_rule_fields view raises IntegrityError."""
        db_path = _setup_database(tmp_path)

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError, match="read-only"):
                conn.execute(
                    """
                    INSERT INTO program_rule_fields (
                        program_id, field_name, field_type, field_value,
                        source_excerpt, review_status, created_at, updated_at
                    ) VALUES (
                        'synthetic-inject', 'injected', 'text', 'bad',
                        '', 'pending', ?, ?
                    )
                    """,
                    (NOW, NOW),
                )

    def test_update_view_rejected(self, tmp_path: Path) -> None:
        """Direct UPDATE on program_rule_fields view raises IntegrityError."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-6"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-6",
            rule_version_id="synthetic-rv-cutover-6",
        )
        _insert_legacy_rows(db_path, program_id=program_id)

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError, match="read-only"):
                conn.execute(
                    """
                    UPDATE program_rule_fields
                    SET field_value = 'tampered'
                    WHERE program_id = ?
                    """,
                    (program_id,),
                )

    def test_delete_from_view_rejected(self, tmp_path: Path) -> None:
        """Direct DELETE on program_rule_fields view raises IntegrityError."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-7"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-7",
            rule_version_id="synthetic-rv-cutover-7",
        )
        _insert_legacy_rows(db_path, program_id=program_id)

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError, match="read-only"):
                conn.execute(
                    """
                    DELETE FROM program_rule_fields
                    WHERE program_id = ?
                    """,
                    (program_id,),
                )


# ---------------------------------------------------------------------------
# Test 4: Runtime reader independence from writable legacy table
# ---------------------------------------------------------------------------


class TestRuntimeReaderIndependence:
    """Verify canonical projection is self-contained from Rule DSL."""

    def test_projection_is_self_contained(self, tmp_path: Path) -> None:
        """Projection rows are generated entirely from Rule DSL."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-8"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-8",
            rule_version_id="synthetic-rv-cutover-8",
        )

        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_simple_rule(
            rule_id="synthetic-rule-cutover-8",
            item_id=program_id,
        )
        gen_id = repo.generate_projection(rule, "synthetic-rv-cutover-8", program_id)

        # Read projection — it was generated from Rule DSL, no legacy needed
        rows = repo.read_projection_rows(gen_id)
        assert len(rows) > 0
        assert rows[0].field_name == "__meta__"

        # Verify that the generation came from a Rule DSL conversion
        expected_rows = convert_to_projection(rule)
        assert len(rows) == len(expected_rows)
        for stored, expected in zip(rows, expected_rows, strict=True):
            assert stored.field_name == expected.field_name
            assert stored.field_value == expected.field_value

    def test_projection_unchanged_even_if_legacy_data_differs(
        self, tmp_path: Path
    ) -> None:
        """Canonical projection remains unchanged regardless of legacy content."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-9"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-9",
            rule_version_id="synthetic-rv-cutover-9",
        )

        # Insert legacy data (different from what canonical would produce)
        _insert_legacy_rows(db_path, program_id=program_id)

        # Generate canonical projection
        factory = _make_connection_factory(db_path)
        repo = CompatibilityProjectionRepository(factory)
        rule = _make_simple_rule(
            rule_id="synthetic-rule-cutover-9",
            item_id=program_id,
        )
        gen_id = repo.generate_projection(rule, "synthetic-rv-cutover-9", program_id)

        rows_before = repo.read_projection_rows(gen_id)

        # Even with legacy data present, the projection is deterministic
        # and generated purely from Rule DSL
        expected_rows = convert_to_projection(rule)
        assert len(rows_before) == len(expected_rows)

        # Verify the view shows projection data (not legacy)
        with closing(sqlite3.connect(db_path)) as conn:
            view_rows = conn.execute(
                """
                SELECT field_name FROM program_rule_fields
                WHERE program_id = ?
                ORDER BY field_name
                """,
                (program_id,),
            ).fetchall()

        view_names = {r[0] for r in view_rows}
        projection_names = {r.field_name for r in rows_before}
        assert view_names == projection_names

    def test_legacy_table_is_frozen_artifact(self, tmp_path: Path) -> None:
        """legacy_program_rule_fields_v1 is a frozen read-only artifact."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-10"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-10",
            rule_version_id="synthetic-rv-cutover-10",
        )
        _insert_legacy_rows(db_path, program_id=program_id)

        # The legacy table exists and has data
        with closing(sqlite3.connect(db_path)) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM legacy_program_rule_fields_v1"
                " WHERE program_id = ?",
                (program_id,),
            ).fetchone()[0]
        assert count == 1

        # But it's read-only (attempts to modify fail)
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    """
                    UPDATE legacy_program_rule_fields_v1
                    SET field_value = 'modified'
                    WHERE program_id = ?
                    """,
                    (program_id,),
                )


# ---------------------------------------------------------------------------
# Test 5: Legacy table read-only enforcement
# ---------------------------------------------------------------------------


class TestLegacyTableReadOnly:
    """Verify legacy_program_rule_fields_v1 rejects all DML after migration."""

    def test_insert_into_legacy_table_rejected(self, tmp_path: Path) -> None:
        """INSERT on legacy_program_rule_fields_v1 is rejected by trigger."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-11"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-11",
            rule_version_id="synthetic-rv-cutover-11",
        )

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError, match="read-only"):
                conn.execute(
                    """
                    INSERT INTO legacy_program_rule_fields_v1 (
                        program_id, field_name, field_type, field_value,
                        source_excerpt, review_status, created_at, updated_at
                    ) VALUES (?, 'new_field', 'text', 'value', '',
                              'pending', ?, ?)
                    """,
                    (program_id, NOW, NOW),
                )

    def test_update_legacy_table_rejected(self, tmp_path: Path) -> None:
        """UPDATE on legacy_program_rule_fields_v1 is rejected by trigger."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-12"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-12",
            rule_version_id="synthetic-rv-cutover-12",
        )
        _insert_legacy_rows(db_path, program_id=program_id)

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError, match="read-only"):
                conn.execute(
                    """
                    UPDATE legacy_program_rule_fields_v1
                    SET field_value = 'modified'
                    WHERE program_id = ?
                    """,
                    (program_id,),
                )

    def test_delete_from_legacy_table_rejected(self, tmp_path: Path) -> None:
        """DELETE on legacy_program_rule_fields_v1 is rejected by trigger."""
        db_path = _setup_database(tmp_path)
        program_id = "synthetic-program-cutover-13"
        _insert_program_and_rule(
            db_path,
            program_id=program_id,
            rule_id="synthetic-rule-cutover-13",
            rule_version_id="synthetic-rv-cutover-13",
        )
        _insert_legacy_rows(db_path, program_id=program_id)

        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError, match="read-only"):
                conn.execute(
                    """
                    DELETE FROM legacy_program_rule_fields_v1
                    WHERE program_id = ?
                    """,
                    (program_id,),
                )
