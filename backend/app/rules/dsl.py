"""Canonical immutable Rule DSL tree and validator.

Defines the three node types (AllOf, AnyOf, Condition), a versioned operator
allowlist, the RuleDefinition container, and a validate_rule function that
checks all structural invariants.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.orchestration.data_contracts import FrozenValue

# ---------------------------------------------------------------------------
# Versioned operator allowlist
# ---------------------------------------------------------------------------

DSL_VERSION = "1.0"
"""Current canonical DSL version identifier."""

OPERATOR_ALLOWLIST_V1: frozenset[str] = frozenset(
    {"==", "!=", ">=", "<=", ">", "<", "in", "not_in"}
)
"""MVP operator allowlist for DSL version 1.0."""

# Map DSL version to its operator allowlist. New versions may expand the set
# but must never change existing operator semantics.
OPERATOR_ALLOWLISTS: dict[str, frozenset[str]] = {
    DSL_VERSION: OPERATOR_ALLOWLIST_V1,
}

# ---------------------------------------------------------------------------
# DSL node types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AllOf:
    """All children must evaluate to true for this node to be true."""

    children: tuple[RuleNode, ...]


@dataclass(frozen=True, slots=True)
class AnyOf:
    """At least one child must evaluate to true for this node to be true."""

    children: tuple[RuleNode, ...]


@dataclass(frozen=True, slots=True)
class Condition:
    """A leaf condition comparing a field value against an expected value."""

    condition_id: str
    field_id: str
    operator: str
    expected: FrozenValue
    label: str
    source_reference: str


RuleNode = AllOf | AnyOf | Condition

# ---------------------------------------------------------------------------
# Rule definition container
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    """Container for a versioned rule definition.

    Holds rule metadata and the root of the immutable DSL tree.
    """

    rule_id: str
    item_id: str
    version: int
    dsl_version: str
    required_field_ids: tuple[str, ...]
    root: RuleNode
    source_references: tuple[str, ...]


# Keep backward-compatible alias
RuleVersion = RuleDefinition


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class RuleValidationError(ValueError):
    """Raised when a rule fails structural validation.

    Subclass of ValueError for easy catching alongside other value errors.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_rule(rule: RuleDefinition) -> None:
    """Validate all structural invariants of a RuleDefinition.

    Checks:
    - dsl_version is recognized
    - Group non-empty (AllOf/AnyOf must have at least one child)
    - Condition IDs unique within a rule version
    - Operators in the version's allowlist
    - Condition field_id in required_field_ids
    - Source references present on each condition
    - required_field_ids must not contain IDs unused by leaf conditions

    Raises RuleValidationError with a clear message on any invariant violation.
    """
    # Resolve allowlist for this DSL version
    allowlist = OPERATOR_ALLOWLISTS.get(rule.dsl_version)
    if allowlist is None:
        raise RuleValidationError(
            "unsupported_dsl_version",
            f"DSL version '{rule.dsl_version}' is not supported; "
            f"recognized versions: {sorted(OPERATOR_ALLOWLISTS.keys())}",
        )

    required_set = set(rule.required_field_ids)

    # Collect all condition IDs and field IDs from leaves
    condition_ids: list[str] = []
    leaf_field_ids: set[str] = set()

    def _validate_node(node: RuleNode) -> None:
        if isinstance(node, (AllOf, AnyOf)):
            if len(node.children) == 0:
                node_type = "AllOf" if isinstance(node, AllOf) else "AnyOf"
                raise RuleValidationError(
                    "group_empty",
                    f"{node_type} node must have at least one child",
                )
            for child in node.children:
                _validate_node(child)
        elif isinstance(node, Condition):
            # Condition ID must be non-empty
            if not node.condition_id:
                raise RuleValidationError(
                    "condition_id_empty",
                    "Condition must have a non-empty condition_id",
                )
            condition_ids.append(node.condition_id)
            leaf_field_ids.add(node.field_id)

            # Operator must be in allowlist
            if node.operator not in allowlist:
                raise RuleValidationError(
                    "invalid_operator",
                    f"Operator '{node.operator}' is not in the allowlist "
                    f"for DSL version '{rule.dsl_version}'",
                )

            # Field_id must be in required_field_ids
            if node.field_id not in required_set:
                raise RuleValidationError(
                    "field_not_in_required",
                    f"Condition '{node.condition_id}' references field "
                    f"'{node.field_id}' which is not in required_field_ids",
                )

            # Source reference must be present
            if not node.source_reference:
                raise RuleValidationError(
                    "missing_source_reference",
                    f"Condition '{node.condition_id}' must have a "
                    f"non-empty source_reference",
                )
        else:
            raise RuleValidationError(
                "invalid_node_type",
                f"Unknown node type: {type(node).__name__}",
            )

    # Walk the tree from root
    _validate_node(rule.root)

    # Condition IDs must be unique
    seen_ids: set[str] = set()
    for cid in condition_ids:
        if cid in seen_ids:
            raise RuleValidationError(
                "duplicate_condition_id",
                f"Duplicate condition_id '{cid}' within rule",
            )
        seen_ids.add(cid)

    # required_field_ids must not contain IDs unused by any leaf condition
    extra_in_required = required_set - leaf_field_ids
    if extra_in_required:
        raise RuleValidationError(
            "extra_required_field_ids",
            f"required_field_ids contains IDs not used by any condition: "
            f"{sorted(extra_in_required)}",
        )
