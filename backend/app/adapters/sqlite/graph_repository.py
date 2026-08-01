"""SQLite adapter for the Entitlement Graph repository.

Implements EntitlementGraphRepository Protocol by reading graph_nodes,
graph_edges, graph_edge_conditions, and benefit_programs tables.

Path expansion algorithm (design section 5):
1. Verify event_id is a life_event node; invalid → InvalidEventIdError.
2. Walk edges from event node to benefit_program nodes.
3. For each edge with conditions: evaluate against user_attributes.
   - field missing → keep path, add field_id to missing set.
   - field present & condition fails → exclude that path only.
4. For each reachable program: filter rejected/inactive; union missing fields.
5. Build CandidateItem with program_id→item_id, sorted prerequisites/produces.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any

from app.adapters.sqlite.connection import execute_read
from app.adapters.sqlite.mapping import map_program_status
from app.orchestration.data_contracts import CandidateItem, GraphRelation
from app.orchestration.data_errors import InvalidEventIdError

# Visible statuses (rejected and inactive are excluded from expansion)
_VISIBLE_STATUSES = frozenset({"candidate", "under_review", "verified", "stale"})


def _evaluate_condition(
    operator: str,
    expected_json: str,
    field_value: Any,
) -> bool:
    """Evaluate a single graph edge condition against a user attribute value.

    Returns True if condition is satisfied, False otherwise.
    Uses explicit operator dispatch — no eval().
    """
    try:
        expected = json.loads(expected_json)
    except (json.JSONDecodeError, TypeError):
        return False

    if operator == "equals" or operator == "==":
        return field_value == expected
    if operator == "not_equals" or operator == "!=":
        return field_value != expected
    if operator == "greater_than" or operator == ">":
        return field_value > expected
    if operator == "greater_than_or_equal" or operator == ">=":
        return field_value >= expected
    if operator == "less_than" or operator == "<":
        return field_value < expected
    if operator == "less_than_or_equal" or operator == "<=":
        return field_value <= expected
    if operator == "in":
        if isinstance(expected, list):
            return field_value in expected
        return False
    if operator == "not_in":
        if isinstance(expected, list):
            return field_value not in expected
        return True
    # Unknown operator: treat as not satisfied (conservative)
    return False


class SqliteEntitlementGraphRepository:
    """Reads the Entitlement Graph from SQLite."""

    def __init__(self, connection_factory: Callable[[], sqlite3.Connection]) -> None:
        self._connection_factory = connection_factory

    def expand_from_event(
        self,
        event_id: str,
        user_attributes: Mapping[str, Any],
    ) -> tuple[CandidateItem, ...]:
        """Expand a life event into reachable candidate programs."""
        return execute_read(
            self._connection_factory,
            lambda conn: self._expand(conn, event_id, user_attributes),
        )

    def get_prerequisites(self, item_id: str) -> tuple[GraphRelation, ...]:
        """Get prerequisite relations for an item (program_id=item_id)."""
        return execute_read(
            self._connection_factory,
            lambda conn: self._get_relations(conn, item_id, "requires"),
        )

    def get_produces(self, item_id: str) -> tuple[GraphRelation, ...]:
        """Get produces relations for an item."""
        return execute_read(
            self._connection_factory,
            lambda conn: self._get_relations(conn, item_id, "produces"),
        )

    def get_programs_by_system(self, system_id: str) -> tuple[CandidateItem, ...]:
        """Get programs belonging to an insurance system."""
        return execute_read(
            self._connection_factory,
            lambda conn: self._programs_by_system(conn, system_id),
        )

    def _expand(
        self,
        connection: sqlite3.Connection,
        event_id: str,
        user_attributes: Mapping[str, Any],
    ) -> tuple[CandidateItem, ...]:
        # 1. Verify event_id is a life_event node
        event_node = connection.execute(
            """
            SELECT node_id, node_type
            FROM graph_nodes
            WHERE node_id = ?
            """,
            (event_id,),
        ).fetchone()
        if event_node is None or str(event_node[1]) != "life_event":
            raise InvalidEventIdError("invalid_event_id")

        # 2. Load all edges and conditions
        edges = connection.execute(
            """
            SELECT edge_id, from_node_id, to_node_id, edge_type,
                   canonical_order
            FROM graph_edges
            ORDER BY from_node_id, edge_type, canonical_order
            """
        ).fetchall()

        conditions = connection.execute(
            """
            SELECT edge_id, field_id, operator, expected_value_json
            FROM graph_edge_conditions
            ORDER BY edge_id, condition_order
            """
        ).fetchall()

        # Index conditions by edge_id
        conditions_by_edge: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for row in conditions:
            edge_id = str(row[0])
            conditions_by_edge[edge_id].append((str(row[1]), str(row[2]), str(row[3])))

        # Build adjacency: from_node → list of (to_node, edge_id, edge_type)
        adjacency: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for row in edges:
            edge_id = str(row[0])
            from_node = str(row[1])
            to_node = str(row[2])
            edge_type = str(row[3])
            adjacency[from_node].append((to_node, edge_id, edge_type))

        # 3. Load program nodes with their status
        program_nodes = connection.execute(
            """
            SELECT gn.node_id, gn.program_id, gn.display_name,
                   bp.program_status
            FROM graph_nodes gn
            JOIN benefit_programs bp ON bp.program_id = gn.program_id
            WHERE gn.node_type = 'benefit_program'
            """
        ).fetchall()
        program_info: dict[str, tuple[str, str, str]] = {}
        for row in program_nodes:
            node_id = str(row[0])
            program_id = str(row[1])
            display_name = str(row[2])
            status = str(row[3])
            program_info[node_id] = (program_id, display_name, status)

        # 4. BFS from event node, tracking per-program missing fields
        # For each program node, track: set of paths that reach it,
        # and per-path missing field sets
        program_missing_fields: dict[str, set[str]] = defaultdict(set)
        program_reachable: set[str] = set()

        # BFS with path condition evaluation
        # Each queue entry is (node_id, accumulated_missing_fields_along_path)
        visited_edges: set[str] = set()
        queue: list[tuple[str, set[str]]] = [(event_id, set())]
        visited_nodes: set[str] = set()

        while queue:
            current, inherited_missing = queue.pop(0)
            if current in visited_nodes:
                # If already visited, still propagate missing to programs
                if current in program_info:
                    program_missing_fields[current].update(inherited_missing)
                continue
            visited_nodes.add(current)

            # If this is a program node, mark it reachable
            if current in program_info:
                program_reachable.add(current)
                program_missing_fields[current].update(inherited_missing)

            for to_node, edge_id, _edge_type in adjacency.get(current, []):
                if edge_id in visited_edges:
                    continue

                # Evaluate edge conditions
                edge_conditions = conditions_by_edge.get(edge_id, [])
                path_excluded = False
                edge_missing: set[str] = set()

                for field_id, operator, expected_json in edge_conditions:
                    if field_id not in user_attributes:
                        edge_missing.add(field_id)
                    else:
                        field_value = user_attributes[field_id]
                        if not _evaluate_condition(
                            operator, expected_json, field_value
                        ):
                            path_excluded = True
                            break

                if path_excluded:
                    continue

                visited_edges.add(edge_id)

                # Accumulate missing fields along the path
                path_missing = inherited_missing | edge_missing

                # If to_node is a program, record missing fields for it
                if to_node in program_info:
                    program_missing_fields[to_node].update(path_missing)
                    program_reachable.add(to_node)
                else:
                    # Propagate missing fields through intermediate nodes
                    queue.append((to_node, path_missing))

        # 5. Build CandidateItems for visible programs
        items: list[CandidateItem] = []
        for node_id in sorted(program_reachable):
            program_id, display_name, status = program_info[node_id]
            if status not in _VISIBLE_STATUSES:
                continue

            missing = tuple(sorted(program_missing_fields.get(node_id, set())))
            prerequisites = self._compute_relations(connection, program_id, "requires")
            produces = self._compute_relations(connection, program_id, "produces")

            items.append(
                CandidateItem(
                    item_id=program_id,
                    display_name=display_name,
                    program_status=map_program_status(status),
                    relevance_score=None,
                    missing_field_ids=missing,
                    prerequisites=prerequisites,
                    produces=produces,
                )
            )

        return tuple(items)

    def _compute_relations(
        self,
        connection: sqlite3.Connection,
        program_id: str,
        edge_type: str,
    ) -> tuple[GraphRelation, ...]:
        """Get relations for a program node by edge type."""
        rows = connection.execute(
            """
            SELECT gn_target.program_id, gn_target.display_name,
                   ge.canonical_order
            FROM graph_nodes gn_source
            JOIN graph_edges ge ON ge.from_node_id = gn_source.node_id
            JOIN graph_nodes gn_target ON gn_target.node_id = ge.to_node_id
            WHERE gn_source.program_id = ?
              AND ge.edge_type = ?
            ORDER BY ge.canonical_order, gn_target.node_id
            """,
            (program_id, edge_type),
        ).fetchall()
        return tuple(
            GraphRelation(
                target_id=str(row[0]) if row[0] else str(row[1]),
                display_name=str(row[1]),
                canonical_order=int(row[2]),
            )
            for row in rows
        )

    def _get_relations(
        self,
        connection: sqlite3.Connection,
        item_id: str,
        edge_type: str,
    ) -> tuple[GraphRelation, ...]:
        """Get relations for item_id (which is program_id at boundary)."""
        return self._compute_relations(connection, item_id, edge_type)

    def _programs_by_system(
        self,
        connection: sqlite3.Connection,
        system_id: str,
    ) -> tuple[CandidateItem, ...]:
        """Get all programs belonging to a system (via belongs_to edges)."""
        rows = connection.execute(
            """
            SELECT gn_prog.program_id, gn_prog.display_name,
                   bp.program_status
            FROM graph_nodes gn_sys
            JOIN graph_edges ge
              ON ge.from_node_id = gn_sys.node_id
             AND ge.edge_type = 'belongs_to'
            JOIN graph_nodes gn_prog
              ON gn_prog.node_id = ge.to_node_id
             AND gn_prog.node_type = 'benefit_program'
            JOIN benefit_programs bp
              ON bp.program_id = gn_prog.program_id
            WHERE gn_sys.node_id = ?
              AND bp.program_status IN (
                  'candidate', 'under_review', 'verified', 'stale'
              )
            ORDER BY ge.canonical_order, gn_prog.node_id
            """,
            (system_id,),
        ).fetchall()
        return tuple(
            CandidateItem(
                item_id=str(row[0]),
                display_name=str(row[1]),
                program_status=map_program_status(str(row[2])),
                relevance_score=None,
                missing_field_ids=(),
                prerequisites=(),
                produces=(),
            )
            for row in rows
        )
