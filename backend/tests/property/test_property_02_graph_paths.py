"""Property 2: Graph path preservation and exclusion semantics.

**Validates: Requirements 4.1–4.7, 7.3–7.6**

Uses an independent reference model to compute BOTH reachable program IDs
AND the missing-field union for each reachable program, then compares against
the SqliteEntitlementGraphRepository output.

Reference model semantics (design section 5):
- condition field not provided: preserve path, add field_id to path's missing set (Req 4.4)
- field provided & condition passes: preserve path (Req 4.3)
- field provided & condition fails: exclude ONLY that path (Req 4.6)
- program reachable if at least one path not excluded (Req 4.3)
- all paths excluded → exclude program (Req 4.7)
- missing_field_ids = union of missing sets from all non-excluded paths, sorted ascending (Req 4.5)
- rejected/inactive programs excluded even if reachable (Req 7.6)
- candidate/under_review/verified/stale programs visible with their status (Req 7.3, 7.4)
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from backend.app.adapters.sqlite.graph_repository import (
    SqliteEntitlementGraphRepository,
)
from backend.app.adapters.sqlite.migrations import migrate_database
from hypothesis import given, settings
from hypothesis import strategies as st

NOW = "2026-07-30T00:00:00+00:00"

# Visible statuses aligned with the implementation
_VISIBLE_STATUSES = frozenset({"candidate", "under_review", "verified", "stale"})


# ---------------------------------------------------------------------------
# Reference model: pure-Python graph reachability + missing-field union
# ---------------------------------------------------------------------------


def _evaluate_condition(operator: str, threshold: int, value: int) -> bool:
    """Evaluate a condition against a value using the given operator."""
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    if operator == ">":
        return value > threshold
    if operator == "<":
        return value < threshold
    if operator == "==":
        return value == threshold
    if operator == "!=":
        return value != threshold
    return False


def _reference_expand(
    programs: list[dict],
    paths: list[dict],
    user_attributes: dict[str, int],
) -> dict[str, tuple[str, ...]]:
    """Independent reference model: reachable programs AND their missing_field_ids.

    Each "path" represents a single route from event to a program, with its
    own list of conditions. This is a simplified model that doesn't care about
    the graph topology -- it just tracks which paths lead to which programs
    and what conditions are on each path.

    Returns a dict mapping program_id -> sorted tuple of missing field_ids.
    Only includes programs that:
    - have at least one non-excluded path (Req 4.3, 4.7)
    - have a visible status (not rejected/inactive) (Req 7.6)
    """
    result: dict[str, tuple[str, ...]] = {}

    for prog in programs:
        # Req 7.6: rejected/inactive excluded from candidate results
        if prog["status"] in ("rejected", "inactive"):
            continue

        # Find all paths leading to this program
        prog_paths = [p for p in paths if p["to_program"] == prog["id"]]

        any_path_open = False
        missing_field_union: set[str] = set()

        for path in prog_paths:
            path_excluded = False
            path_missing: set[str] = set()

            for cond in path["conditions"]:
                field_id = cond["field_id"]
                if field_id not in user_attributes:
                    # Req 4.4: field not provided → preserve path, add to missing
                    path_missing.add(field_id)
                else:
                    # Req 4.6: field provided & condition fails → exclude only this path
                    if not _evaluate_condition(
                        cond["operator"], cond["threshold"], user_attributes[field_id]
                    ):
                        path_excluded = True
                        break

            if not path_excluded:
                any_path_open = True
                missing_field_union.update(path_missing)

        if any_path_open:
            # Req 4.5: missing_field_ids sorted ascending by field_id
            result[prog["id"]] = tuple(sorted(missing_field_union))

    return result


# ---------------------------------------------------------------------------
# Strategy: generate small graphs with multiple paths via intermediate nodes
# ---------------------------------------------------------------------------

_OPERATORS = [">=", "<=", ">", "<", "==", "!="]
_FIELDS = ["age", "income", "children"]


@st.composite
def _small_graphs(draw: st.DrawFn):
    """Generate a small graph with 1–3 programs, 1 event, and conditions.

    To support multiple paths to the same program (required to test missing-field
    union semantics), we route through intermediate nodes. The schema enforces
    UNIQUE(from_node_id, to_node_id, edge_type), so we use intermediate
    'insurance_system' nodes as hubs.

    Each program gets 1-2 paths:
    - Path via direct edge: event → program_node
    - Path via intermediate: event → intermediate → program_node
    """
    n_programs = draw(st.integers(min_value=1, max_value=3))
    programs = []
    for i in range(n_programs):
        status = draw(
            st.sampled_from(
                ["candidate", "under_review", "verified", "stale", "rejected", "inactive"]
            )
        )
        programs.append({"id": f"prog-{i}", "status": status})

    # Build paths: each program gets 1–2 paths from event
    # Path structure for reference model: list of {to_program, conditions: [...]}
    paths: list[dict] = []
    # Graph structure for DB insertion
    intermediates: list[str] = []  # intermediate node IDs
    edges: list[dict] = []  # {edge_id, from_node, to_node}
    conditions_db: list[dict] = []  # {edge_id, field_id, operator, threshold, order}

    edge_counter = 0

    for i in range(n_programs):
        has_second_path = draw(st.booleans())
        n_paths = 2 if has_second_path else 1

        for path_idx in range(n_paths):
            path_conditions: list[dict] = []

            # Generate 0–2 conditions for this path
            n_conds = draw(st.integers(min_value=0, max_value=2))
            for cond_idx in range(n_conds):
                field_id = draw(st.sampled_from(_FIELDS))
                operator = draw(st.sampled_from(_OPERATORS))
                threshold = draw(st.integers(min_value=0, max_value=100))
                path_conditions.append(
                    {
                        "field_id": field_id,
                        "operator": operator,
                        "threshold": threshold,
                    }
                )

            paths.append(
                {"to_program": f"prog-{i}", "conditions": path_conditions}
            )

            # Build DB structure for this path
            if path_idx == 0:
                # Direct edge: event → program_node
                edge_id = f"edge-{edge_counter}"
                edges.append(
                    {
                        "edge_id": edge_id,
                        "from_node": "event-prop",
                        "to_node": f"node-prog-{i}",
                    }
                )
                for cond_idx, cond in enumerate(path_conditions):
                    conditions_db.append(
                        {
                            "edge_id": edge_id,
                            "field_id": cond["field_id"],
                            "operator": cond["operator"],
                            "threshold": cond["threshold"],
                            "order": cond_idx,
                        }
                    )
                edge_counter += 1
            else:
                # Via intermediate: event → intermediate, intermediate → program_node
                inter_id = f"inter-{i}"
                intermediates.append(inter_id)

                # Edge 1: event → intermediate
                edge_id_1 = f"edge-{edge_counter}"
                edges.append(
                    {
                        "edge_id": edge_id_1,
                        "from_node": "event-prop",
                        "to_node": inter_id,
                    }
                )
                edge_counter += 1

                # Edge 2: intermediate → program_node
                edge_id_2 = f"edge-{edge_counter}"
                edges.append(
                    {
                        "edge_id": edge_id_2,
                        "from_node": inter_id,
                        "to_node": f"node-prog-{i}",
                    }
                )
                # Put conditions on both edges to test union semantics
                # Split conditions: first half on edge 1, rest on edge 2
                split = len(path_conditions) // 2
                for cond_idx, cond in enumerate(path_conditions[:split]):
                    conditions_db.append(
                        {
                            "edge_id": edge_id_1,
                            "field_id": cond["field_id"],
                            "operator": cond["operator"],
                            "threshold": cond["threshold"],
                            "order": cond_idx,
                        }
                    )
                for cond_idx, cond in enumerate(path_conditions[split:]):
                    conditions_db.append(
                        {
                            "edge_id": edge_id_2,
                            "field_id": cond["field_id"],
                            "operator": cond["operator"],
                            "threshold": cond["threshold"],
                            "order": cond_idx,
                        }
                    )
                edge_counter += 1

    # User may or may not provide each field
    user_attributes: dict[str, int] = {}
    for field in _FIELDS:
        if draw(st.booleans()):
            user_attributes[field] = draw(st.integers(min_value=0, max_value=100))

    return programs, paths, intermediates, edges, conditions_db, user_attributes


def _build_database(
    tmp_path: Path,
    programs: list[dict],
    intermediates: list[str],
    edges: list[dict],
    conditions_db: list[dict],
) -> Path:
    """Create a migrated DB with the generated graph."""
    database = tmp_path / "prop2.db"
    migrate_database(database)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys = ON")
        # Register all possible fields
        for field_id in _FIELDS:
            conn.execute(
                """
                INSERT OR IGNORE INTO field_registry (
                    field_id, data_type, prompt_label, why_needed,
                    pii_classification, active
                ) VALUES (?, 'integer', ?, 'Needed', 'none', 1)
                """,
                (field_id, f"{field_id}?"),
            )
        # Create the event node
        conn.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, display_name)
            VALUES ('event-prop', 'life_event', 'Property Event')
            """
        )
        # Create intermediate nodes (insurance_system type)
        for inter_id in intermediates:
            conn.execute(
                """
                INSERT INTO graph_nodes (node_id, node_type, display_name)
                VALUES (?, 'insurance_system', ?)
                """,
                (inter_id, f"System {inter_id}"),
            )
        # Create programs and their graph nodes
        for prog in programs:
            conn.execute(
                """
                INSERT INTO benefit_programs (
                    program_id, canonical_name, program_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (prog["id"], prog["id"], prog["status"], NOW, NOW),
            )
            conn.execute(
                """
                INSERT INTO graph_nodes (
                    node_id, node_type, display_name, program_id
                ) VALUES (?, 'benefit_program', ?, ?)
                """,
                (f"node-{prog['id']}", prog["id"], prog["id"]),
            )
        # Create edges
        for edge in edges:
            conn.execute(
                """
                INSERT INTO graph_edges (
                    edge_id, from_node_id, to_node_id,
                    edge_type, canonical_order
                ) VALUES (?, ?, ?, 'triggers', 0)
                """,
                (edge["edge_id"], edge["from_node"], edge["to_node"]),
            )
        # Create conditions on edges
        for cond in conditions_db:
            conn.execute(
                """
                INSERT INTO graph_edge_conditions (
                    edge_id, condition_id, field_id, operator,
                    expected_value_type, expected_value_json,
                    condition_order
                ) VALUES (?, ?, ?, ?, 'integer', ?, ?)
                """,
                (
                    cond["edge_id"],
                    f"cond-{cond['edge_id']}-{cond['order']}",
                    cond["field_id"],
                    cond["operator"],
                    str(cond["threshold"]),
                    cond["order"],
                ),
            )
    return database


@given(data=_small_graphs())
@settings(max_examples=100, deadline=5000)
def test_reachable_programs_and_missing_fields_match_reference(data: tuple) -> None:
    """Adapter output matches independent reference model for both
    reachable program IDs and missing-field union per program.

    **Validates: Requirements 4.1–4.7, 7.3–7.6**
    """
    import tempfile

    programs, paths, intermediates, edges, conditions_db, user_attributes = data
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = _build_database(
            Path(tmp_dir), programs, intermediates, edges, conditions_db
        )

        repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
        items = repo.expand_from_event("event-prop", user_attributes)

        # Build actual result: mapping of item_id -> missing_field_ids
        actual_map: dict[str, tuple[str, ...]] = {
            item.item_id: item.missing_field_ids for item in items
        }

    # Compute expected using independent reference model
    expected_map = _reference_expand(programs, paths, user_attributes)

    # Req 4.3: Each reachable program returns a CandidateItem
    # Req 4.7: All paths excluded → no CandidateItem
    # Req 7.6: rejected/inactive excluded
    assert set(actual_map.keys()) == set(expected_map.keys()), (
        f"Reachable program IDs differ.\n"
        f"  actual={sorted(actual_map.keys())}\n"
        f"  expected={sorted(expected_map.keys())}\n"
        f"  programs={programs}\n"
        f"  user_attributes={user_attributes}"
    )

    # Req 4.4: missing fields preserved for unknown fields
    # Req 4.5: missing_field_ids sorted ascending
    for prog_id in expected_map:
        assert actual_map[prog_id] == expected_map[prog_id], (
            f"Missing field IDs differ for {prog_id}.\n"
            f"  actual={actual_map[prog_id]}\n"
            f"  expected={expected_map[prog_id]}\n"
            f"  user_attributes={user_attributes}"
        )


@given(data=_small_graphs())
@settings(max_examples=100, deadline=5000)
def test_visible_status_preserved(data: tuple) -> None:
    """Req 7.3-7.4: candidate/under_review/stale programs visible with status.
    Req 7.6: rejected/inactive excluded.

    **Validates: Requirements 7.3, 7.4, 7.6**
    """
    import tempfile

    programs, paths, intermediates, edges, conditions_db, user_attributes = data
    with tempfile.TemporaryDirectory() as tmp_dir:
        database = _build_database(
            Path(tmp_dir), programs, intermediates, edges, conditions_db
        )

        repo = SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))
        items = repo.expand_from_event("event-prop", user_attributes)

    # Check that no returned item has rejected/inactive status
    for item in items:
        assert item.program_status in _VISIBLE_STATUSES, (
            f"Non-visible status returned: {item.program_status} for {item.item_id}"
        )

    # Check that visible reachable programs have their correct status preserved
    expected_statuses = {
        prog["id"]: prog["status"]
        for prog in programs
        if prog["status"] in _VISIBLE_STATUSES
    }
    for item in items:
        assert item.program_status == expected_statuses[item.item_id], (
            f"Status mismatch for {item.item_id}: "
            f"got {item.program_status}, expected {expected_statuses[item.item_id]}"
        )
