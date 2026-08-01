"""PostgreSQL adapter for reading canonical Rule DSL data.

Same semantics as SqliteRuleRepository — reads rule_definitions, rule_versions,
rule_nodes, rule_conditions, rule_required_fields, approved_amounts.
"""

from __future__ import annotations

import json

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.adapters.postgresql.connection import execute_read
from app.adapters.sqlite.rule_repository import (
    AmountData,
    RuleConditionData,
    RuleData,
    RuleNodeData,
)
from app.orchestration.data_contracts import FieldRegistryEntry


class PgRuleRepository:
    """Reads canonical Rule DSL data from PostgreSQL."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def load_current_approved_rule(self, program_id: str) -> RuleData | None:
        """Load the single current approved rule for a program."""
        return execute_read(
            self._pool,
            lambda conn: self._load_rule(conn, program_id),
        )

    def load_required_fields(self, program_id: str) -> tuple[FieldRegistryEntry, ...]:
        """Load required fields for the program's current approved rule version."""
        return execute_read(
            self._pool,
            lambda conn: self._load_fields(conn, program_id),
        )

    def _load_rule(
        self, conn: psycopg.Connection, program_id: str
    ) -> RuleData | None:
        with conn.cursor(row_factory=dict_row) as cur:
            # Find the current approved rule version
            cur.execute(
                """
                SELECT rv.rule_version_id, rv.rule_id, rv.version,
                       rv.dsl_version, rv.root_node_id
                FROM rule_versions rv
                JOIN rule_definitions rd ON rd.rule_id = rv.rule_id
                WHERE rd.program_id = %s
                  AND rv.is_current = TRUE
                  AND rv.approval_status = 'approved'
                """,
                (program_id,),
            )
            version_row = cur.fetchone()
            if version_row is None:
                return None

            rule_version_id = version_row["rule_version_id"]
            root_node_id = version_row["root_node_id"]

            # Load all nodes for this version
            cur.execute(
                """
                SELECT node_id, parent_node_id, node_type, child_order
                FROM rule_nodes
                WHERE rule_version_id = %s
                ORDER BY parent_node_id NULLS FIRST, child_order
                """,
                (rule_version_id,),
            )
            node_rows = cur.fetchall()

            # Load all conditions
            cur.execute(
                """
                SELECT rc.condition_id, rc.node_id, rc.field_id,
                       rc.operator, rc.expected_value_type,
                       rc.expected_value_json::TEXT as expected_value_json,
                       rc.label, rc.source_reference
                FROM rule_conditions rc
                JOIN rule_nodes rn ON rn.node_id = rc.node_id
                WHERE rn.rule_version_id = %s
                """,
                (rule_version_id,),
            )
            conditions_by_node: dict[str, dict] = {}
            for cond_row in cur.fetchall():
                conditions_by_node[cond_row["node_id"]] = cond_row

            # Build tree recursively
            children_by_parent: dict[str | None, list[dict]] = {}
            for nr in node_rows:
                parent = nr["parent_node_id"]
                children_by_parent.setdefault(parent, []).append(nr)

            def build_node(node_id: str, node_type: str, child_order: int) -> RuleNodeData:
                condition: RuleConditionData | None = None
                children: tuple[RuleNodeData, ...] = ()

                if node_type == "condition":
                    cond = conditions_by_node.get(node_id)
                    if cond:
                        condition = RuleConditionData(
                            condition_id=cond["condition_id"],
                            field_id=cond["field_id"],
                            operator=cond["operator"],
                            expected_value_type=cond["expected_value_type"],
                            expected_value_json=cond["expected_value_json"],
                            label=cond["label"],
                            source_reference=cond["source_reference"],
                        )
                else:
                    child_rows = children_by_parent.get(node_id, [])
                    children = tuple(
                        build_node(cr["node_id"], cr["node_type"], cr["child_order"])
                        for cr in sorted(child_rows, key=lambda x: x["child_order"])
                    )

                return RuleNodeData(
                    node_id=node_id,
                    node_type=node_type,
                    child_order=child_order,
                    condition=condition,
                    children=children,
                )

            # Find root node
            root_row = next(
                (nr for nr in node_rows if nr["node_id"] == root_node_id), None
            )
            if root_row is None:
                return None

            root = build_node(root_row["node_id"], root_row["node_type"], 0)

            # Load required fields
            required_fields = self._load_fields(conn, program_id)

            # Load source references
            cur.execute(
                """
                SELECT source_reference FROM rule_version_source_refs
                WHERE rule_version_id = %s
                ORDER BY source_reference
                """,
                (rule_version_id,),
            )
            source_refs = tuple(r["source_reference"] for r in cur.fetchall())

            # Load amount
            cur.execute(
                """
                SELECT amount_min, amount_max, amount_period,
                       amount_currency, source_reference
                FROM approved_amounts
                WHERE rule_version_id = %s
                """,
                (rule_version_id,),
            )
            amount_row = cur.fetchone()
            amount: AmountData | None = None
            if amount_row:
                amount = AmountData(
                    amount_min=amount_row["amount_min"],
                    amount_max=amount_row["amount_max"],
                    amount_period=amount_row["amount_period"],
                    amount_currency=amount_row["amount_currency"],
                    source_reference=amount_row["source_reference"],
                )

            return RuleData(
                rule_version_id=rule_version_id,
                rule_id=version_row["rule_id"],
                program_id=program_id,
                version=version_row["version"],
                dsl_version=version_row["dsl_version"],
                root=root,
                required_fields=required_fields,
                source_references=source_refs,
                amount=amount,
            )

    def _load_fields(
        self, conn: psycopg.Connection, program_id: str
    ) -> tuple[FieldRegistryEntry, ...]:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT fr.field_id, fr.data_type, fr.prompt_label,
                       fr.why_needed, fr.pii_classification
                FROM rule_required_fields rrf
                JOIN rule_versions rv ON rv.rule_version_id = rrf.rule_version_id
                JOIN rule_definitions rd ON rd.rule_id = rv.rule_id
                JOIN field_registry fr ON fr.field_id = rrf.field_id
                WHERE rd.program_id = %s
                  AND rv.is_current = TRUE
                  AND rv.approval_status = 'approved'
                  AND fr.active = TRUE
                ORDER BY rrf.canonical_order
                """,
                (program_id,),
            )
            rows = cur.fetchall()

            # Load allowed values for enum fields
            result: list[FieldRegistryEntry] = []
            for r in rows:
                allowed_values: tuple[str, ...] = ()
                if r["data_type"] == "enum":
                    cur.execute(
                        """
                        SELECT value FROM field_allowed_values
                        WHERE field_id = %s
                        ORDER BY canonical_order
                        """,
                        (r["field_id"],),
                    )
                    allowed_values = tuple(av["value"] for av in cur.fetchall())

                result.append(
                    FieldRegistryEntry(
                        field_id=r["field_id"],
                        data_type=r["data_type"],
                        prompt_label=r["prompt_label"],
                        why_needed=r["why_needed"],
                        pii_classification=r["pii_classification"],
                        allowed_values=allowed_values,
                    )
                )

            return tuple(result)
