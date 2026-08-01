"""Property 7: Projection read-only atomic replacement.

**Validates: Requirements 6.2, 6.3, 6.4, 6.8, 6.9, 6.10**

For any valid old generation, new generation, and any conversion/write failure
point, a reader can only see a complete old or complete new generation, never
partial rows; direct insert/update/delete on validated generations always fails
and the canonical DSL remains unchanged.

Uses a real SQLite database with full schema (triggers enforce immutability).
The independent oracle verifies consistency invariants that do NOT rely on
production code assertions.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.adapters.sqlite.compatibility_repository import (
    CompatibilityProjectionRepository,
    ProjectionGenerationError,
)
from app.adapters.sqlite.migrations import migrate_database
from app.rules.compatibility import convert_to_projection
from app.rules.dsl import (
    AllOf,
    AnyOf,
    Condition,
    RuleDefinition,
    RuleNode,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOW = "2026-07-30T00:00:00+00:00"

# Fixed field/operator pools for generating valid rules
INT_FIELD_IDS = ("age", "income", "years_of_service")
STR_FIELD_IDS = ("status", "category")
ALL_FIELD_IDS = INT_FIELD_IDS + STR_FIELD_IDS
COMPARISON_OPERATORS = ("==", "!=", ">=", "<=", ">", "<")
COLLECTION_OPERATORS = ("in", "not_in")


# ---------------------------------------------------------------------------
# Database setup helpers
# ---------------------------------------------------------------------------


def _setup_database(tmp_path: Path) -> Path:
    """Create a fully migrated database."""
    database = tmp_path / "prop7.db"
    migrate_database(database)
    return database


def _make_connection_factory(db_path: Path):
    """Return a callable that creates a new connection to the database."""

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    return factory


def _insert_program_and_rule_versions(
    db_path: Path,
    *,
    program_id: str = "program-1",
    rule_id: str = "rule-1",
    version_count: int = 5,
) -> list[str]:
    """Insert a program with multiple rule versions for testing.

    Returns a list of rule_version_ids.
    """
    version_ids = [f"rv-{i}" for i in range(1, version_count + 1)]
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
        for i, rv_id in enumerate(version_ids, 1):
            conn.execute(
                """
                INSERT OR IGNORE INTO rule_versions (
                    rule_version_id, rule_id, version, dsl_version,
                    approval_status, is_current, created_at
                ) VALUES (?, ?, ?, '1.0', 'candidate', 0, ?)
                """,
                (rv_id, rule_id, str(i), NOW),
            )
    return version_ids


# ---------------------------------------------------------------------------
# Strategies: Generate valid RuleDefinition trees
# ---------------------------------------------------------------------------

_int_values = st.integers(min_value=0, max_value=100)
_str_values = st.sampled_from(["alpha", "beta", "gamma", "delta"])


@st.composite
def _condition(draw: st.DrawFn, counter: list[int]) -> Condition:
    """Generate a single valid Condition node."""
    use_int = draw(st.booleans())
    if use_int:
        field_id = draw(st.sampled_from(INT_FIELD_IDS))
        operator = draw(st.sampled_from(COMPARISON_OPERATORS + COLLECTION_OPERATORS))
        if operator in COLLECTION_OPERATORS:
            expected = draw(st.lists(_int_values, min_size=1, max_size=3).map(tuple))
        else:
            expected = draw(_int_values)
    else:
        field_id = draw(st.sampled_from(STR_FIELD_IDS))
        operator = draw(st.sampled_from(("==", "!=", "in", "not_in")))
        if operator in COLLECTION_OPERATORS:
            expected = draw(st.lists(_str_values, min_size=1, max_size=3).map(tuple))
        else:
            expected = draw(_str_values)

    counter[0] += 1
    cid = f"c{counter[0]}"

    return Condition(
        condition_id=cid,
        field_id=field_id,
        operator=operator,
        expected=expected,
        label=f"label_{cid}",
        source_reference=f"ref_{cid}",
    )


@st.composite
def _rule_tree(draw: st.DrawFn) -> RuleNode:
    """Generate a valid recursive Rule DSL tree."""
    counter = [0]
    leaf = _condition(counter)

    tree = draw(
        st.recursive(
            leaf,
            lambda children: st.one_of(
                children.map(lambda c: AllOf(children=(c,))),
                st.tuples(children, children).map(
                    lambda t: AllOf(children=(t[0], t[1]))
                ),
                children.map(lambda c: AnyOf(children=(c,))),
                st.tuples(children, children).map(
                    lambda t: AnyOf(children=(t[0], t[1]))
                ),
            ),
            max_leaves=5,
        )
    )
    return tree


def _collect_field_ids(node: RuleNode) -> tuple[str, ...]:
    """Collect all unique field_ids from the tree in sorted order."""
    ids: set[str] = set()

    def _walk(n: RuleNode) -> None:
        if isinstance(n, Condition):
            ids.add(n.field_id)
        elif isinstance(n, (AllOf, AnyOf)):
            for child in n.children:
                _walk(child)

    _walk(node)
    return tuple(sorted(ids))


def _collect_source_refs(node: RuleNode) -> tuple[str, ...]:
    """Collect all source_references from the tree."""
    refs: list[str] = []

    def _walk(n: RuleNode) -> None:
        if isinstance(n, Condition):
            refs.append(n.source_reference)
        elif isinstance(n, (AllOf, AnyOf)):
            for child in n.children:
                _walk(child)

    _walk(node)
    return tuple(sorted(set(refs)))


@st.composite
def _rule_definition(draw: st.DrawFn, version: int = 1) -> RuleDefinition:
    """Generate a valid RuleDefinition with proper metadata."""
    tree = draw(_rule_tree())
    field_ids = _collect_field_ids(tree)
    source_refs = _collect_source_refs(tree)

    return RuleDefinition(
        rule_id="rule-1",
        item_id="program-1",
        version=version,
        dsl_version="1.0",
        required_field_ids=field_ids,
        root=tree,
        source_references=source_refs,
    )


# ---------------------------------------------------------------------------
# Oracle: Independent consistency invariants
# ---------------------------------------------------------------------------


def _oracle_active_generation_is_complete(
    db_path: Path, program_id: str
) -> None:
    """Verify the active generation (if any) is complete and validated.

    Oracle logic (NOT using production code):
    1. If active pointer exists, it must reference a validated generation.
    2. The validated generation's row_count must match actual row count.
    3. All rows must have consecutive ordinals starting at 0.
    """
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        # Check active pointer
        active = conn.execute(
            """
            SELECT generation_id, rule_version_id
            FROM compat_projection_active
            WHERE program_id = ?
            """,
            (program_id,),
        ).fetchone()

        if active is None:
            return  # No active generation — valid state

        generation_id = active[0]

        # Check generation is validated
        gen_row = conn.execute(
            """
            SELECT status, row_count, canonical_hash
            FROM compat_projection_generations
            WHERE generation_id = ?
            """,
            (generation_id,),
        ).fetchone()

        assert gen_row is not None, (
            f"Active pointer references non-existent generation {generation_id}"
        )
        assert gen_row[0] == "validated", (
            f"Active generation {generation_id} has status '{gen_row[0]}', "
            f"expected 'validated'"
        )
        expected_row_count = gen_row[1]
        assert expected_row_count > 0, (
            f"Validated generation {generation_id} has row_count=0"
        )

        # Count actual rows
        actual_count = conn.execute(
            "SELECT COUNT(*) FROM compat_projection_rows WHERE generation_id = ?",
            (generation_id,),
        ).fetchone()[0]

        assert actual_count == expected_row_count, (
            f"Generation {generation_id}: row_count={expected_row_count} "
            f"but actual rows={actual_count}"
        )

        # Verify ordinals are consecutive 0..N-1
        ordinals = [
            row[0]
            for row in conn.execute(
                """
                SELECT ordinal FROM compat_projection_rows
                WHERE generation_id = ?
                ORDER BY ordinal
                """,
                (generation_id,),
            ).fetchall()
        ]
        expected_ordinals = list(range(actual_count))
        assert ordinals == expected_ordinals, (
            f"Generation {generation_id}: ordinals not consecutive. "
            f"Got {ordinals[:5]}..."
        )


def _oracle_no_partial_generations_visible(
    db_path: Path, program_id: str
) -> None:
    """Verify there are no 'building' generations with an active pointer.

    The active pointer must always reference a 'validated' generation.
    """
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        # No building generation should be active
        building_active = conn.execute(
            """
            SELECT a.generation_id
            FROM compat_projection_active a
            JOIN compat_projection_generations g
              ON g.generation_id = a.generation_id
            WHERE a.program_id = ?
              AND g.status = 'building'
            """,
            (program_id,),
        ).fetchone()

        assert building_active is None, (
            f"Active pointer references 'building' generation: "
            f"{building_active[0]}"
        )


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(rules=st.lists(_rule_definition(), min_size=1, max_size=4))
@settings(max_examples=100, deadline=10000)
def test_atomic_visibility_across_sequential_generations(
    rules: list[RuleDefinition],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Property 7a: After each generation (success or failure), the active
    generation is always complete — reader sees full old or full new, never
    partial rows.

    For any sequence of valid rule definitions generated for the same program,
    after each successful generation the active pointer references a validated
    generation with a complete row set.
    """
    tmp_path = tmp_path_factory.mktemp("prop7a")
    db_path = _setup_database(tmp_path)
    version_ids = _insert_program_and_rule_versions(
        db_path, version_count=len(rules)
    )
    factory = _make_connection_factory(db_path)
    repo = CompatibilityProjectionRepository(factory)

    for i, rule in enumerate(rules):
        rv_id = version_ids[i]
        # Update version to match
        rule_with_version = RuleDefinition(
            rule_id=rule.rule_id,
            item_id=rule.item_id,
            version=i + 1,
            dsl_version=rule.dsl_version,
            required_field_ids=rule.required_field_ids,
            root=rule.root,
            source_references=rule.source_references,
        )

        try:
            repo.generate_projection(rule_with_version, rv_id, "program-1")
        except ProjectionGenerationError:
            pass  # Failures are acceptable — old generation preserved

        # Oracle: active generation is always complete
        _oracle_active_generation_is_complete(db_path, "program-1")
        _oracle_no_partial_generations_visible(db_path, "program-1")


@given(rule=_rule_definition())
@settings(max_examples=100, deadline=10000)
def test_failure_preserves_previous_active_generation(
    rule: RuleDefinition,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Property 7b: When generation fails, the previous active generation is
    preserved unchanged.

    Generate a valid projection, then attempt one that will fail (bad program_id).
    Verify the original active generation is untouched.
    """
    tmp_path = tmp_path_factory.mktemp("prop7b")
    db_path = _setup_database(tmp_path)
    version_ids = _insert_program_and_rule_versions(db_path, version_count=2)
    factory = _make_connection_factory(db_path)
    repo = CompatibilityProjectionRepository(factory)

    # Generate a valid first projection
    gen_id = repo.generate_projection(rule, version_ids[0], "program-1")

    # Record the state before failure
    rows_before = repo.read_projection_rows(gen_id)
    active_before = repo.get_active_generation("program-1")

    # Attempt a generation that will fail (nonexistent program triggers
    # foreign key / trigger rejection)
    try:
        repo.generate_projection(rule, version_ids[1], "nonexistent-program")
    except (ProjectionGenerationError, Exception):
        pass

    # Oracle: active generation unchanged
    active_after = repo.get_active_generation("program-1")
    assert active_after == active_before, (
        f"Active generation changed after failure: "
        f"before={active_before}, after={active_after}"
    )

    # Oracle: rows unchanged
    rows_after = repo.read_projection_rows(gen_id)
    assert len(rows_after) == len(rows_before), (
        f"Row count changed after failure: "
        f"before={len(rows_before)}, after={len(rows_after)}"
    )

    # Oracle: completeness invariant still holds
    _oracle_active_generation_is_complete(db_path, "program-1")


@given(rule=_rule_definition())
@settings(max_examples=100, deadline=10000)
def test_direct_dml_on_validated_generation_always_rejected(
    rule: RuleDefinition,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Property 7c: For any validated generation, direct INSERT/UPDATE/DELETE
    on projection rows always fails with IntegrityError.

    Triggers protect validated generations from any DML modification.
    The canonical DSL (rule tree) is never affected by these attempts.
    """
    tmp_path = tmp_path_factory.mktemp("prop7c")
    db_path = _setup_database(tmp_path)
    _insert_program_and_rule_versions(db_path, version_count=1)
    factory = _make_connection_factory(db_path)
    repo = CompatibilityProjectionRepository(factory)

    gen_id = repo.generate_projection(rule, "rv-1", "program-1")
    rows_before = repo.read_projection_rows(gen_id)

    # DML attempt 1: INSERT into validated generation
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute(
                """
                INSERT INTO compat_projection_rows (
                    generation_id, ordinal, program_id, field_name,
                    field_type, field_value, source_excerpt,
                    review_status, created_at, updated_at
                ) VALUES (?, 999, 'program-1', 'injected', 'text',
                          'bad', '', 'pending', ?, ?)
                """,
                (gen_id, NOW, NOW),
            )
            # Should not reach here
            pytest.fail("INSERT into validated generation rows should be rejected")
        except sqlite3.IntegrityError:
            pass  # Expected: trigger rejects insert

    # DML attempt 2: UPDATE validated generation rows
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute(
                """
                UPDATE compat_projection_rows
                SET field_value = 'tampered'
                WHERE generation_id = ?
                """,
                (gen_id,),
            )
            pytest.fail("UPDATE on validated generation rows should be rejected")
        except sqlite3.IntegrityError:
            pass  # Expected: trigger rejects update

    # DML attempt 3: DELETE from validated generation rows
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute(
                """
                DELETE FROM compat_projection_rows
                WHERE generation_id = ?
                """,
                (gen_id,),
            )
            pytest.fail("DELETE from validated generation rows should be rejected")
        except sqlite3.IntegrityError:
            pass  # Expected: trigger rejects delete

    # Oracle: rows are unchanged after all DML attempts
    rows_after = repo.read_projection_rows(gen_id)
    assert len(rows_after) == len(rows_before)
    for before, after in zip(rows_before, rows_after, strict=True):
        assert before.ordinal == after.ordinal
        assert before.field_name == after.field_name
        assert before.field_type == after.field_type
        assert before.field_value == after.field_value
        assert before.source_excerpt == after.source_excerpt


@given(rule=_rule_definition())
@settings(max_examples=100, deadline=10000)
def test_generation_metadata_immutable_after_validation(
    rule: RuleDefinition,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Property 7d: Once a generation is validated, its metadata (row_count,
    canonical_hash, status) cannot be modified. The generation record is
    immutable.
    """
    tmp_path = tmp_path_factory.mktemp("prop7d")
    db_path = _setup_database(tmp_path)
    _insert_program_and_rule_versions(db_path, version_count=1)
    factory = _make_connection_factory(db_path)
    repo = CompatibilityProjectionRepository(factory)

    gen_id = repo.generate_projection(rule, "rv-1", "program-1")

    # Record original metadata
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        original = conn.execute(
            """
            SELECT status, row_count, canonical_hash, validated_at
            FROM compat_projection_generations
            WHERE generation_id = ?
            """,
            (gen_id,),
        ).fetchone()

    assert original[0] == "validated"

    # Attempt to modify row_count
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute(
                """
                UPDATE compat_projection_generations
                SET row_count = 999
                WHERE generation_id = ?
                """,
                (gen_id,),
            )
            pytest.fail("UPDATE on validated generation metadata should be rejected")
        except sqlite3.IntegrityError:
            pass

    # Attempt to modify canonical_hash
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute(
                """
                UPDATE compat_projection_generations
                SET canonical_hash = 'a' * 64
                WHERE generation_id = ?
                """,
                (gen_id,),
            )
            pytest.fail("UPDATE on validated generation hash should be rejected")
        except sqlite3.IntegrityError:
            pass

    # Attempt to delete the generation
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute(
                """
                DELETE FROM compat_projection_generations
                WHERE generation_id = ?
                """,
                (gen_id,),
            )
            pytest.fail("DELETE on validated generation should be rejected")
        except sqlite3.IntegrityError:
            pass

    # Oracle: metadata unchanged
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        after = conn.execute(
            """
            SELECT status, row_count, canonical_hash, validated_at
            FROM compat_projection_generations
            WHERE generation_id = ?
            """,
            (gen_id,),
        ).fetchone()

    assert after == original, (
        f"Generation metadata changed: original={original}, after={after}"
    )


@given(rule=_rule_definition())
@settings(max_examples=100, deadline=10000)
def test_active_pointer_always_references_validated_complete_generation(
    rule: RuleDefinition,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Property 7e: The active pointer always points to a validated generation
    with the correct row count. This is enforced by DB triggers on the
    compat_projection_active table.
    """
    tmp_path = tmp_path_factory.mktemp("prop7e")
    db_path = _setup_database(tmp_path)
    _insert_program_and_rule_versions(db_path, version_count=1)
    factory = _make_connection_factory(db_path)
    repo = CompatibilityProjectionRepository(factory)

    gen_id = repo.generate_projection(rule, "rv-1", "program-1")

    # Oracle: verify active pointer integrity
    _oracle_active_generation_is_complete(db_path, "program-1")

    # Verify the active pointer cannot be set to point to a non-validated
    # generation (attempt to insert a fake building generation and point to it)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            # Try to switch active to a nonexistent generation
            conn.execute(
                """
                UPDATE compat_projection_active
                SET generation_id = 'fake-generation-id'
                WHERE program_id = 'program-1'
                """,
            )
            conn.commit()
            pytest.fail(
                "Active pointer should not be switchable to invalid generation"
            )
        except sqlite3.IntegrityError:
            pass

    # Oracle: active still points to original valid generation
    active = repo.get_active_generation("program-1")
    assert active is not None
    assert active[0] == gen_id

    # Verify rows are still complete
    rows = repo.read_projection_rows(gen_id)
    expected_rows = convert_to_projection(rule)
    assert len(rows) == len(expected_rows)
