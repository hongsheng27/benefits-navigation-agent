"""PostgreSQL adapter for the Entitlement Graph repository.

Same semantics as SqliteEntitlementGraphRepository — implements the
EntitlementGraphRepository Protocol via PostgreSQL queries.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.adapters.event_ids import event_id_candidates
from app.adapters.postgresql.connection import execute_read
from app.orchestration.data_contracts import CandidateItem, GraphRelation
from app.orchestration.data_errors import InvalidEventIdError

_VISIBLE_STATUSES = frozenset({"candidate", "under_review", "verified", "stale"})


def _evaluate_condition(
    operator: str,
    expected_json: str,
    field_value: Any,
) -> bool:
    """Evaluate a single graph edge condition against a user attribute value."""
    try:
        expected = (
            json.loads(expected_json)
            if isinstance(expected_json, str)
            else expected_json
        )
    except (json.JSONDecodeError, TypeError):
        return False

    if operator in ("equals", "=="):
        return field_value == expected
    if operator in ("not_equals", "!="):
        return field_value != expected
    if operator in ("greater_than", ">"):
        return field_value > expected
    if operator in ("greater_than_or_equal", ">="):
        return field_value >= expected
    if operator in ("less_than", "<"):
        return field_value < expected
    if operator in ("less_than_or_equal", "<="):
        return field_value <= expected
    if operator == "in":
        return isinstance(expected, list) and field_value in expected
    if operator == "not_in":
        return not isinstance(expected, list) or field_value not in expected
    return False


class PgEntitlementGraphRepository:
    """Reads the Entitlement Graph from PostgreSQL."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def expand_from_event(
        self,
        event_id: str,
        user_attributes: Mapping[str, Any],
    ) -> tuple[CandidateItem, ...]:
        """Expand a life event into reachable candidate programs."""
        return execute_read(
            self._pool,
            lambda conn: self._expand(conn, event_id, user_attributes),
        )

    def get_prerequisites(self, item_id: str) -> tuple[GraphRelation, ...]:
        return execute_read(
            self._pool,
            lambda conn: self._get_relations(conn, item_id, "requires"),
        )

    def get_produces(self, item_id: str) -> tuple[GraphRelation, ...]:
        return execute_read(
            self._pool,
            lambda conn: self._get_relations(conn, item_id, "produces"),
        )

    def get_programs_by_system(self, system_id: str) -> tuple[CandidateItem, ...]:
        return execute_read(
            self._pool,
            lambda conn: self._programs_by_system(conn, system_id),
        )

    def _expand(
        self,
        conn: psycopg.Connection,
        event_id: str,
        user_attributes: Mapping[str, Any],
    ) -> tuple[CandidateItem, ...]:
        with conn.cursor(row_factory=dict_row) as cur:
            # Verify event node exists and is a life_event
            node_row = None
            for candidate_id in event_id_candidates(event_id):
                cur.execute(
                    "SELECT node_id, node_type FROM graph_nodes WHERE node_id = %s",
                    (candidate_id,),
                )
                node_row = cur.fetchone()
                if node_row is not None and node_row["node_type"] == "life_event":
                    break
            if node_row is None or node_row["node_type"] != "life_event":
                raise InvalidEventIdError("invalid_event_id")
            resolved_event_id = node_row["node_id"]

            # Get all edges from this event
            cur.execute(
                """
                SELECT e.edge_id, e.to_node_id, e.canonical_order
                FROM graph_edges e
                WHERE e.from_node_id = %s AND e.edge_type = 'triggers'
                ORDER BY e.canonical_order, e.to_node_id
                """,
                (resolved_event_id,),
            )
            trigger_edges = cur.fetchall()

            if not trigger_edges:
                return ()

            # Get conditions for all edges
            edge_ids = [e["edge_id"] for e in trigger_edges]
            cur.execute(
                """
                SELECT edge_id, condition_id, field_id, operator,
                       expected_value_json::TEXT as expected_value_json,
                       condition_order
                FROM graph_edge_conditions
                WHERE edge_id = ANY(%s)
                ORDER BY edge_id, condition_order
                """,
                (edge_ids,),
            )
            conditions_by_edge: dict[str, list[dict]] = defaultdict(list)
            for cond in cur.fetchall():
                conditions_by_edge[cond["edge_id"]].append(cond)

            # Evaluate which programs are reachable
            # program_node_id -> set of missing field ids
            reachable: dict[str, set[str]] = {}

            for edge in trigger_edges:
                edge_id = edge["edge_id"]
                to_node_id = edge["to_node_id"]
                conditions = conditions_by_edge.get(edge_id, [])

                path_excluded = False
                path_missing: set[str] = set()

                for cond in conditions:
                    field_id = cond["field_id"]
                    if field_id not in user_attributes:
                        path_missing.add(field_id)
                    else:
                        if not _evaluate_condition(
                            cond["operator"],
                            cond["expected_value_json"],
                            user_attributes[field_id],
                        ):
                            path_excluded = True
                            break

                if not path_excluded:
                    if to_node_id in reachable:
                        reachable[to_node_id].update(path_missing)
                    else:
                        reachable[to_node_id] = path_missing

            if not reachable:
                return ()

            # Get program details for reachable nodes
            cur.execute(
                """
                SELECT n.node_id, n.display_name, n.program_id,
                       p.program_status, p.summary
                FROM graph_nodes n
                JOIN benefit_programs p ON p.program_id = n.program_id
                WHERE n.node_id = ANY(%s)
                  AND n.node_type = 'benefit_program'
                """,
                (list(reachable.keys()),),
            )
            program_nodes = cur.fetchall()
            order_by_node = {
                node_id: index for index, node_id in enumerate(reachable.keys())
            }
            program_nodes.sort(key=lambda row: order_by_node[row["node_id"]])

            # Build CandidateItems
            items: list[CandidateItem] = []
            for pn in program_nodes:
                status = pn["program_status"]
                if status not in _VISIBLE_STATUSES:
                    continue

                node_id = pn["node_id"]
                missing = sorted(reachable.get(node_id, set()))

                # Get relevance_score from program (default 0.0)
                items.append(
                    CandidateItem(
                        item_id=pn["program_id"],
                        display_name=pn["display_name"],
                        program_status=status,
                        relevance_score=0.0,
                        missing_field_ids=tuple(missing),
                        prerequisites=self._get_relations(
                            conn, pn["program_id"], "requires"
                        ),
                        produces=self._get_relations(
                            conn, pn["program_id"], "produces"
                        ),
                        summary=pn["summary"] or None,
                    )
                )

            return tuple(items)

    def _get_relations(
        self,
        conn: psycopg.Connection,
        item_id: str,
        edge_type: str,
    ) -> tuple[GraphRelation, ...]:
        with conn.cursor(row_factory=dict_row) as cur:
            # Find the graph node for this program
            cur.execute(
                "SELECT node_id FROM graph_nodes WHERE program_id = %s",
                (item_id,),
            )
            node_row = cur.fetchone()
            if node_row is None:
                return ()

            cur.execute(
                """
                SELECT e.to_node_id, n.display_name, e.canonical_order
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.to_node_id
                WHERE e.from_node_id = %s AND e.edge_type = %s
                ORDER BY e.canonical_order, e.to_node_id
                """,
                (node_row["node_id"], edge_type),
            )
            return tuple(
                GraphRelation(
                    target_id=r["to_node_id"],
                    display_name=r["display_name"],
                )
                for r in cur.fetchall()
            )

    def _programs_by_system(
        self,
        conn: psycopg.Connection,
        system_id: str,
    ) -> tuple[CandidateItem, ...]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT n.program_id, n.display_name, p.program_status
                FROM graph_edges e
                JOIN graph_nodes n ON n.node_id = e.from_node_id
                JOIN benefit_programs p ON p.program_id = n.program_id
                WHERE e.to_node_id = %s
                  AND e.edge_type = 'belongs_to'
                  AND n.node_type = 'benefit_program'
                ORDER BY e.canonical_order, n.node_id
                """,
                (system_id,),
            )
            rows = cur.fetchall()

            return tuple(
                CandidateItem(
                    item_id=r["program_id"],
                    display_name=r["display_name"],
                    program_status=r["program_status"],
                    relevance_score=0.0,
                    missing_field_ids=(),
                    prerequisites=(),
                    produces=(),
                )
                for r in rows
                if r["program_status"] in _VISIBLE_STATUSES
            )
