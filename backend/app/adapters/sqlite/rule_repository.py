"""SQLite adapter for reading canonical Rule DSL data.

This module reads rule_definitions, rule_versions, rule_nodes, rule_conditions,
rule_required_fields, approved_amounts, and rule_version_source_refs to produce
an internal RuleData structure. The full public Rule DSL API is defined in
Task 5 (app/rules/dsl.py); this reader provides the raw materialized data.

All reads use execute_read from the connection lifecycle helper.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from app.adapters.sqlite.connection import execute_read
from app.adapters.sqlite.mapping import (
    map_field_registry_entry,
)
from app.orchestration.data_contracts import FieldRegistryEntry


@dataclass(frozen=True, slots=True)
class RuleConditionData:
    """A single leaf condition from the rule tree."""

    condition_id: str
    field_id: str
    operator: str
    expected_value_type: str
    expected_value_json: str
    label: str
    source_reference: str


@dataclass(frozen=True, slots=True)
class RuleNodeData:
    """A node in the recursive rule tree (internal representation)."""

    node_id: str
    node_type: str  # 'all_of', 'any_of', 'condition'
    child_order: int
    condition: RuleConditionData | None  # Only set for node_type='condition'
    children: tuple[RuleNodeData, ...] = ()  # Only set for group nodes


@dataclass(frozen=True, slots=True)
class AmountData:
    """Approved structured amount for a rule version."""

    amount_min: int | float
    amount_max: int | float
    amount_period: str
    amount_currency: str
    source_reference: str


@dataclass(frozen=True, slots=True)
class RuleData:
    """Complete materialized rule data for one program's current approved version."""

    rule_version_id: str
    rule_id: str
    program_id: str
    version: str
    dsl_version: str
    root: RuleNodeData
    required_fields: tuple[FieldRegistryEntry, ...]
    source_references: tuple[str, ...]
    amount: AmountData | None


class SqliteRuleRepository:
    """Reads canonical Rule DSL data from SQLite."""

    def __init__(self, connection_factory: Callable[[], sqlite3.Connection]) -> None:
        self._connection_factory = connection_factory

    def load_current_approved_rule(self, program_id: str) -> RuleData | None:
        """Load the single current approved rule for a program.

        Returns None if the program has no rule, or no current approved version,
        or multiple current approved versions (caller interprets as needs_human_review).
        """
        return execute_read(
            self._connection_factory,
            lambda conn: self._load_rule(conn, program_id),
        )

    def load_required_fields(self, program_id: str) -> tuple[FieldRegistryEntry, ...]:
        """Load required fields for the program's current approved rule version."""
        return execute_read(
            self._connection_factory,
            lambda conn: self._load_fields(conn, program_id),
        )

    def _load_rule(
        self, connection: sqlite3.Connection, program_id: str
    ) -> RuleData | None:
        # Find rule_definition for this program
        rule_row = connection.execute(
            "SELECT rule_id FROM rule_definitions WHERE program_id = ?",
            (program_id,),
        ).fetchone()
        if rule_row is None:
            return None
        rule_id = str(rule_row[0])

        # Find exactly one current approved version
        version_rows = connection.execute(
            """
            SELECT rule_version_id, version, dsl_version, root_node_id
            FROM rule_versions
            WHERE rule_id = ?
              AND is_current = 1
              AND approval_status = 'approved'
            """,
            (rule_id,),
        ).fetchall()
        if len(version_rows) != 1:
            return None
        rule_version_id, version, dsl_version, root_node_id = version_rows[0]
        rule_version_id = str(rule_version_id)

        # Build recursive tree
        root = self._build_tree(connection, rule_version_id, root_node_id)
        if root is None:
            return None

        # Load required fields
        required_fields = self._query_required_fields(connection, rule_version_id)

        # Load source references
        ref_rows = connection.execute(
            """
            SELECT source_reference
            FROM rule_version_source_refs
            WHERE rule_version_id = ?
            ORDER BY source_reference
            """,
            (rule_version_id,),
        ).fetchall()
        source_references = tuple(str(row[0]) for row in ref_rows)

        # Load approved amounts
        amount = self._query_amount(connection, rule_version_id)

        return RuleData(
            rule_version_id=rule_version_id,
            rule_id=rule_id,
            program_id=program_id,
            version=str(version),
            dsl_version=str(dsl_version),
            root=root,
            required_fields=required_fields,
            source_references=source_references,
            amount=amount,
        )

    def _build_tree(
        self,
        connection: sqlite3.Connection,
        rule_version_id: str,
        node_id: str | None,
    ) -> RuleNodeData | None:
        if node_id is None:
            return None

        # Load all nodes for this version
        node_rows = connection.execute(
            """
            SELECT node_id, parent_node_id, node_type, child_order
            FROM rule_nodes
            WHERE rule_version_id = ?
            ORDER BY parent_node_id, child_order
            """,
            (rule_version_id,),
        ).fetchall()

        # Load all conditions for this version
        condition_rows = connection.execute(
            """
            SELECT
                rc.node_id, rc.condition_id, rc.field_id, rc.operator,
                rc.expected_value_type, rc.expected_value_json,
                rc.label, rc.source_reference
            FROM rule_conditions rc
            JOIN rule_nodes rn ON rn.node_id = rc.node_id
            WHERE rn.rule_version_id = ?
            """,
            (rule_version_id,),
        ).fetchall()

        # Index conditions by node_id
        conditions_by_node: dict[str, RuleConditionData] = {}
        for row in condition_rows:
            n_id = str(row[0])
            conditions_by_node[n_id] = RuleConditionData(
                condition_id=str(row[1]),
                field_id=str(row[2]),
                operator=str(row[3]),
                expected_value_type=str(row[4]),
                expected_value_json=str(row[5]),
                label=str(row[6]),
                source_reference=str(row[7]),
            )

        # Index children by parent_node_id
        children_by_parent: dict[str | None, list[tuple[str, str, int]]] = {}
        for row in node_rows:
            n_id, parent_id, node_type, child_order = (
                str(row[0]),
                row[1],
                str(row[2]),
                int(row[3]),
            )
            parent_key = str(parent_id) if parent_id is not None else None
            children_by_parent.setdefault(parent_key, []).append(
                (n_id, node_type, child_order)
            )

        def build(current_id: str) -> RuleNodeData | None:
            # Find this node's type
            node_info = None
            for row in node_rows:
                if str(row[0]) == current_id:
                    node_info = (str(row[2]), int(row[3]))
                    break
            if node_info is None:
                return None
            node_type, child_order = node_info

            if node_type == "condition":
                condition = conditions_by_node.get(current_id)
                return RuleNodeData(
                    node_id=current_id,
                    node_type=node_type,
                    child_order=child_order,
                    condition=condition,
                    children=(),
                )

            # Group node: build children recursively
            child_entries = children_by_parent.get(current_id, [])
            child_nodes = []
            for child_id, _child_type, _child_order in sorted(
                child_entries, key=lambda x: x[2]
            ):
                child_node = build(child_id)
                if child_node is not None:
                    child_nodes.append(child_node)

            return RuleNodeData(
                node_id=current_id,
                node_type=node_type,
                child_order=child_order,
                condition=None,
                children=tuple(child_nodes),
            )

        return build(str(node_id))

    def _query_required_fields(
        self, connection: sqlite3.Connection, rule_version_id: str
    ) -> tuple[FieldRegistryEntry, ...]:
        rows = connection.execute(
            """
            SELECT
                fr.field_id, fr.data_type, fr.prompt_label,
                fr.why_needed, fr.pii_classification, fr.active
            FROM rule_required_fields rrf
            JOIN field_registry fr ON fr.field_id = rrf.field_id
            WHERE rrf.rule_version_id = ?
            ORDER BY rrf.canonical_order
            """,
            (rule_version_id,),
        ).fetchall()

        entries: list[FieldRegistryEntry] = []
        for row in rows:
            field_id = str(row[0])
            # Load allowed values for this field
            av_rows = connection.execute(
                """
                SELECT value FROM field_allowed_values
                WHERE field_id = ? ORDER BY canonical_order
                """,
                (field_id,),
            ).fetchall()
            allowed_values = tuple(str(r[0]) for r in av_rows)
            entries.append(
                map_field_registry_entry(
                    (
                        str(row[0]),
                        str(row[1]),
                        str(row[2]),
                        str(row[3]),
                        str(row[4]),
                        str(row[5]),
                    ),
                    allowed_values=allowed_values,
                )
            )
        return tuple(entries)

    def _query_amount(
        self, connection: sqlite3.Connection, rule_version_id: str
    ) -> AmountData | None:
        row = connection.execute(
            """
            SELECT amount_min, amount_max, amount_period,
                   amount_currency, source_reference
            FROM approved_amounts
            WHERE rule_version_id = ?
            """,
            (rule_version_id,),
        ).fetchone()
        if row is None:
            return None
        return AmountData(
            amount_min=row[0],
            amount_max=row[1],
            amount_period=str(row[2]),
            amount_currency=str(row[3]),
            source_reference=str(row[4]),
        )

    def _load_fields(
        self, connection: sqlite3.Connection, program_id: str
    ) -> tuple[FieldRegistryEntry, ...]:
        rule_row = connection.execute(
            "SELECT rule_id FROM rule_definitions WHERE program_id = ?",
            (program_id,),
        ).fetchone()
        if rule_row is None:
            return ()
        rule_id = str(rule_row[0])

        version_rows = connection.execute(
            """
            SELECT rule_version_id
            FROM rule_versions
            WHERE rule_id = ?
              AND is_current = 1
              AND approval_status = 'approved'
            """,
            (rule_id,),
        ).fetchall()
        if len(version_rows) != 1:
            return ()
        rule_version_id = str(version_rows[0][0])
        return self._query_required_fields(connection, rule_version_id)
