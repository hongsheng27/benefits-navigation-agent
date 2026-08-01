"""Property 3: Graph deterministic ordering.

**Validates: Requirements 4.5, 4.8, 4.9, 8.11**

Shuffling insertion order must produce identical candidates,
missing IDs, prerequisites, and produces — with stable sorting.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from random import Random

from backend.app.adapters.sqlite.graph_repository import (
    SqliteEntitlementGraphRepository,
)
from backend.app.adapters.sqlite.migrations import migrate_database
from hypothesis import given, settings
from hypothesis import strategies as st

NOW = "2026-07-30T00:00:00+00:00"


def _build_database_with_insertion_order(
    tmp_path: Path,
    program_ids: list[str],
    field_ids: list[str],
    condition_assignments: list[tuple[str, str, str, int]],
    relation_edges: list[tuple[str, str, str, str, int]],
    insertion_seed: int,
    suffix: str,
) -> Path:
    """Create a migrated DB with predetermined logical data but shuffled insertion.

    Args:
        program_ids: canonical list of program IDs
        field_ids: canonical list of field IDs
        condition_assignments: (edge_id, condition_id, field_id, condition_order)
        relation_edges: (edge_id, from_node_id, to_node_id, edge_type, canonical_order)
        insertion_seed: seed controlling insertion order only
        suffix: filename suffix
    """
    database = tmp_path / f"order-{suffix}.db"
    migrate_database(database)

    rng = Random(insertion_seed)

    # Shuffle all insertion sequences
    shuffled_programs = list(program_ids)
    rng.shuffle(shuffled_programs)

    shuffled_fields = list(field_ids)
    rng.shuffle(shuffled_fields)

    shuffled_conditions = list(condition_assignments)
    rng.shuffle(shuffled_conditions)

    shuffled_relations = list(relation_edges)
    rng.shuffle(shuffled_relations)

    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, display_name)
            VALUES ('event-order', 'life_event', 'Order Event')
            """
        )

        # Register fields in shuffled order
        for fid in shuffled_fields:
            conn.execute(
                """
                INSERT INTO field_registry (
                    field_id, data_type, prompt_label,
                    why_needed, pii_classification
                ) VALUES (?, 'integer', ?, 'testing', 'none')
                """,
                (fid, f"Prompt for {fid}"),
            )

        # Insert programs and trigger edges in shuffled order
        for prog_id in shuffled_programs:
            # canonical_order is deterministic per program (based on its index)
            canon_idx = program_ids.index(prog_id)
            conn.execute(
                """
                INSERT INTO benefit_programs (
                    program_id, canonical_name, program_status,
                    created_at, updated_at
                ) VALUES (?, ?, 'candidate', ?, ?)
                """,
                (prog_id, f"Program {prog_id}", NOW, NOW),
            )
            conn.execute(
                """
                INSERT INTO graph_nodes (
                    node_id, node_type, display_name, program_id
                ) VALUES (?, 'benefit_program', ?, ?)
                """,
                (f"node-{prog_id}", f"Program {prog_id}", prog_id),
            )
            conn.execute(
                """
                INSERT INTO graph_edges (
                    edge_id, from_node_id, to_node_id,
                    edge_type, canonical_order
                ) VALUES (?, 'event-order', ?, 'triggers', ?)
                """,
                (f"edge-{prog_id}", f"node-{prog_id}", canon_idx),
            )

        # Insert relation edges in shuffled order
        for edge_id, from_node, to_node, edge_type, canon_order in shuffled_relations:
            conn.execute(
                """
                INSERT INTO graph_edges (
                    edge_id, from_node_id, to_node_id,
                    edge_type, canonical_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (edge_id, from_node, to_node, edge_type, canon_order),
            )

        # Insert conditions in shuffled order
        for edge_id, cond_id, fid, cond_order in shuffled_conditions:
            conn.execute(
                """
                INSERT INTO graph_edge_conditions (
                    edge_id, condition_id, field_id,
                    operator, expected_value_type,
                    expected_value_json, condition_order
                ) VALUES (?, ?, ?, 'equals', 'integer', '1', ?)
                """,
                (edge_id, cond_id, fid, cond_order),
            )

    return database


def _prepare_test_data(
    n_programs: int,
    n_fields: int,
    n_relations: int,
) -> tuple[
    list[str],
    list[str],
    list[tuple[str, str, str, int]],
    list[tuple[str, str, str, str, int]],
]:
    """Prepare deterministic logical data for the database.

    Returns (program_ids, field_ids, condition_assignments, relation_edges).
    """
    program_ids = [f"prog-{i}" for i in range(n_programs)]
    field_ids = [f"field-{i}" for i in range(n_fields)]

    # Create edge conditions: assign fields to programs deterministically
    condition_assignments: list[tuple[str, str, str, int]] = []
    for prog_idx, prog_id in enumerate(program_ids):
        cond_order = 0
        for field_idx, fid in enumerate(field_ids):
            # Deterministic assignment: interleave fields across programs
            if (prog_idx + field_idx) % 3 == 0:
                condition_assignments.append((
                    f"edge-{prog_id}",
                    f"cond-{prog_id}-{fid}",
                    fid,
                    cond_order,
                ))
                cond_order += 1

    # Create relation edges with varying canonical_orders (including ties)
    relation_edges: list[tuple[str, str, str, str, int]] = []
    for src_idx in range(min(n_relations, n_programs - 1)):
        src = program_ids[src_idx]
        for tgt_idx in range(src_idx + 1, min(src_idx + 3, n_programs)):
            tgt = program_ids[tgt_idx]
            # Use canonical_order that causes ties to test secondary sort
            canon_order = tgt_idx % 3
            relation_edges.append((
                f"rel-requires-{src}-{tgt}",
                f"node-{src}",
                f"node-{tgt}",
                "requires",
                canon_order,
            ))
            relation_edges.append((
                f"rel-produces-{src}-{tgt}",
                f"node-{src}",
                f"node-{tgt}",
                "produces",
                canon_order,
            ))

    return program_ids, field_ids, condition_assignments, relation_edges


@given(
    n_programs=st.integers(min_value=2, max_value=6),
    seed_a=st.integers(min_value=0, max_value=10000),
    seed_b=st.integers(min_value=0, max_value=10000),
    n_fields=st.integers(min_value=2, max_value=4),
)
@settings(max_examples=50, deadline=5000)
def test_different_insertion_orders_produce_same_candidates(
    n_programs: int,
    seed_a: int,
    seed_b: int,
    n_fields: int,
) -> None:
    """Same logical data inserted in different orders → same candidate tuples.

    Verifies full tuple equality (content + ordering), not just item_id set.
    Covers Req 4.9 and 8.11.
    """
    import tempfile

    program_ids, field_ids, conditions, relations = _prepare_test_data(
        n_programs, n_fields, n_relations=n_programs - 1,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_a = _build_database_with_insertion_order(
            tmp_path, program_ids, field_ids, conditions, relations,
            insertion_seed=seed_a, suffix=f"a-{seed_a}",
        )
        db_b = _build_database_with_insertion_order(
            tmp_path, program_ids, field_ids, conditions, relations,
            insertion_seed=seed_b, suffix=f"b-{seed_b}",
        )

        repo_a = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(db_a))
        repo_b = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(db_b))

        items_a = repo_a.expand_from_event("event-order", {})
        items_b = repo_b.expand_from_event("event-order", {})

    # Full tuple equality: same content AND same order
    assert items_a == items_b
    assert len(items_a) == n_programs


@given(
    n_programs=st.integers(min_value=2, max_value=5),
    seed=st.integers(min_value=0, max_value=10000),
    n_fields=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=50, deadline=5000)
def test_repeated_queries_same_order(
    n_programs: int,
    seed: int,
    n_fields: int,
) -> None:
    """Same database queried twice → identical content and order.

    **Validates: Requirement 4.9** — same data version, event ID, and
    attributes → same content and order on repeated queries.
    """
    import tempfile

    program_ids, field_ids, conditions, relations = _prepare_test_data(
        n_programs, n_fields, n_relations=n_programs - 1,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        database = _build_database_with_insertion_order(
            tmp_path, program_ids, field_ids, conditions, relations,
            insertion_seed=seed, suffix=f"rep-{seed}",
        )

        repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))

        result1 = repo.expand_from_event("event-order", {})
        result2 = repo.expand_from_event("event-order", {})

    assert result1 == result2


@given(
    n_programs=st.integers(min_value=2, max_value=5),
    n_fields=st.integers(min_value=2, max_value=5),
    seed=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=50, deadline=5000)
def test_missing_field_ids_sorted_ascending(
    n_programs: int,
    n_fields: int,
    seed: int,
) -> None:
    """missing_field_ids are always sorted ascending by field_id.

    **Validates: Requirement 4.5** — WHEN Entitlement_Graph_Repository builds
    missing_field_ids, it SHALL return stable ascending order by field_id.
    """
    import tempfile

    program_ids, field_ids, conditions, relations = _prepare_test_data(
        n_programs, n_fields, n_relations=0,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        database = _build_database_with_insertion_order(
            tmp_path, program_ids, field_ids, conditions, relations,
            insertion_seed=seed, suffix=f"miss-{seed}",
        )

        repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))

        # Query with no user_attributes → all condition fields are "missing"
        items = repo.expand_from_event("event-order", {})

    for item in items:
        if item.missing_field_ids:
            # Verify ascending sort
            assert item.missing_field_ids == tuple(sorted(item.missing_field_ids)), (
                f"missing_field_ids not sorted for {item.item_id}: "
                f"{item.missing_field_ids}"
            )
            # Verify uniqueness (de-duplicated)
            assert len(item.missing_field_ids) == len(set(item.missing_field_ids)), (
                f"missing_field_ids has duplicates for {item.item_id}: "
                f"{item.missing_field_ids}"
            )


@given(
    n_programs=st.integers(min_value=3, max_value=6),
    seed=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=50, deadline=5000)
def test_prerequisites_produces_ordered_by_canonical_then_target(
    n_programs: int,
    seed: int,
) -> None:
    """prerequisites and produces are ordered by (canonical_order, target_id).

    **Validates: Requirement 4.8** — prerequisites/produces sorted by
    canonical_order first, then target_id ascending as stable secondary.
    """
    import tempfile

    program_ids, field_ids, conditions, relations = _prepare_test_data(
        n_programs, n_fields=0, n_relations=n_programs - 1,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        database = _build_database_with_insertion_order(
            tmp_path, program_ids, field_ids, conditions, relations,
            insertion_seed=seed, suffix=f"rel-{seed}",
        )

        repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
        items = repo.expand_from_event("event-order", {})

    for item in items:
        # Check prerequisites ordering
        if len(item.prerequisites) > 1:
            for i in range(len(item.prerequisites) - 1):
                curr = item.prerequisites[i]
                nxt = item.prerequisites[i + 1]
                assert (curr.canonical_order, curr.target_id) <= (
                    nxt.canonical_order,
                    nxt.target_id,
                ), (
                    f"prerequisites not sorted for {item.item_id}: "
                    f"({curr.canonical_order}, {curr.target_id}) > "
                    f"({nxt.canonical_order}, {nxt.target_id})"
                )

        # Check produces ordering
        if len(item.produces) > 1:
            for i in range(len(item.produces) - 1):
                curr = item.produces[i]
                nxt = item.produces[i + 1]
                assert (curr.canonical_order, curr.target_id) <= (
                    nxt.canonical_order,
                    nxt.target_id,
                ), (
                    f"produces not sorted for {item.item_id}: "
                    f"({curr.canonical_order}, {curr.target_id}) > "
                    f"({nxt.canonical_order}, {nxt.target_id})"
                )


@given(
    n_programs=st.integers(min_value=2, max_value=5),
    seed_a=st.integers(min_value=0, max_value=10000),
    seed_b=st.integers(min_value=0, max_value=10000),
)
@settings(max_examples=50, deadline=5000)
def test_shuffled_insertion_same_candidate_order(
    n_programs: int,
    seed_a: int,
    seed_b: int,
) -> None:
    """Shuffled insertion order → same candidate order (not just same set).

    **Validates: Requirement 8.11** — same data and user attributes repeated
    sorting → same candidate order regardless of DB insertion sequence.
    """
    import tempfile

    program_ids, field_ids, conditions, relations = _prepare_test_data(
        n_programs, n_fields=2, n_relations=n_programs - 1,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_a = _build_database_with_insertion_order(
            tmp_path, program_ids, field_ids, conditions, relations,
            insertion_seed=seed_a, suffix=f"ord-a-{seed_a}",
        )
        db_b = _build_database_with_insertion_order(
            tmp_path, program_ids, field_ids, conditions, relations,
            insertion_seed=seed_b, suffix=f"ord-b-{seed_b}",
        )

        repo_a = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(db_a))
        repo_b = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(db_b))

        # Query with same (empty) user attributes
        items_a = repo_a.expand_from_event("event-order", {})
        items_b = repo_b.expand_from_event("event-order", {})

    # Verify identical ordering of item_ids
    order_a = [item.item_id for item in items_a]
    order_b = [item.item_id for item in items_b]
    assert order_a == order_b, (
        f"Candidate order differs:\n  A: {order_a}\n  B: {order_b}"
    )

    # Also verify missing_field_ids and relations match
    for a, b in zip(items_a, items_b):
        assert a.missing_field_ids == b.missing_field_ids
        assert a.prerequisites == b.prerequisites
        assert a.produces == b.produces
