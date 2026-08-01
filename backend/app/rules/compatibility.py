"""Canonical projection converter and reverse converter.

Serializes a RuleDefinition into a flat list of ProjectionRow objects using
stable preorder traversal, canonical encoding, Unicode NFC normalization, and
converter versioning. The reverse converter reconstructs the full RuleDefinition
from projection rows.

This module is PURE — no side effects, no DB access, no sqlite3 imports.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass

from app.orchestration.data_contracts import FrozenValue
from app.rules.dsl import AllOf, AnyOf, Condition, RuleDefinition, RuleNode

# ---------------------------------------------------------------------------
# Converter version
# ---------------------------------------------------------------------------

CONVERTER_VERSION: str = "1.0.0"
"""Identifies the projection format. Must change when encoding changes."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ConverterError(Exception):
    """Raised when projection rows are invalid or corrupt."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ConverterVersionError(Exception):
    """Raised when the converter cannot losslessly represent the DSL."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# ProjectionRow dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProjectionRow:
    """One row of the compatibility projection."""

    ordinal: int
    field_name: str
    field_type: str
    field_value: str
    source_excerpt: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _nfc(text: str) -> str:
    """Apply Unicode NFC normalization."""
    return unicodedata.normalize("NFC", text)


def _canonical_json(value: object) -> str:
    """Produce canonical JSON: sorted keys, no trailing whitespace, compact."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _encode_frozen_value(value: FrozenValue) -> tuple[str, str]:
    """Encode a FrozenValue to (field_type, field_value) pair.

    Returns canonical type tag and serialized string representation.
    """
    if value is None:
        return ("text", "null")
    if isinstance(value, bool):
        return ("boolean", "true" if value else "false")
    if isinstance(value, int):
        return ("integer", str(value))
    if isinstance(value, float):
        return ("number", _canonical_json(value))
    if isinstance(value, str):
        return ("text", _nfc(value))
    if isinstance(value, tuple):
        # Encode tuple as JSON array with recursive handling
        serialized = _canonical_json(_frozen_to_json_serializable(value))
        return ("json", serialized)
    raise ConverterVersionError(
        f"Cannot encode FrozenValue of type {type(value).__name__}"
    )


def _frozen_to_json_serializable(value: FrozenValue) -> object:
    """Convert FrozenValue to JSON-serializable Python objects."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, tuple):
        return [_frozen_to_json_serializable(item) for item in value]
    raise ConverterVersionError(
        f"Cannot serialize FrozenValue of type {type(value).__name__}"
    )


def _decode_frozen_value(field_type: str, field_value: str) -> FrozenValue:
    """Decode a (field_type, field_value) pair back to FrozenValue."""
    if field_type == "text":
        if field_value == "null":
            return None
        return field_value
    if field_type == "boolean":
        if field_value == "true":
            return True
        if field_value == "false":
            return False
        raise ConverterError(f"Invalid boolean value: {field_value!r}")
    if field_type == "integer":
        try:
            return int(field_value)
        except ValueError as err:
            raise ConverterError(f"Invalid integer value: {field_value!r}") from err
    if field_type == "number":
        try:
            return float(json.loads(field_value))
        except (ValueError, json.JSONDecodeError) as err:
            raise ConverterError(f"Invalid number value: {field_value!r}") from err
    if field_type == "json":
        try:
            parsed = json.loads(field_value)
            return _json_to_frozen(parsed)
        except json.JSONDecodeError as err:
            raise ConverterError(f"Invalid JSON value: {field_value!r}") from err
    raise ConverterError(f"Unknown field_type: {field_type!r}")


def _json_to_frozen(value: object) -> FrozenValue:
    """Convert JSON-parsed object back to FrozenValue."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return tuple(_json_to_frozen(item) for item in value)
    raise ConverterError(
        f"Cannot decode JSON type {type(value).__name__} to FrozenValue"
    )


# ---------------------------------------------------------------------------
# Forward converter: RuleDefinition -> list[ProjectionRow]
# ---------------------------------------------------------------------------


def convert_to_projection(rule: RuleDefinition) -> list[ProjectionRow]:
    """Serialize a RuleDefinition into a flat list of ProjectionRows.

    Uses stable preorder traversal. Deterministic: same input always produces
    byte-equivalent output.

    Raises ConverterVersionError if the DSL contains features that cannot be
    losslessly represented.
    """
    rows: list[ProjectionRow] = []

    # --- Metadata rows ---
    # Row 0: rule metadata
    metadata = _canonical_json(
        {
            "converter_version": CONVERTER_VERSION,
            "dsl_version": rule.dsl_version,
            "item_id": rule.item_id,
            "required_field_ids": list(rule.required_field_ids),
            "rule_id": rule.rule_id,
            "source_references": list(rule.source_references),
            "version": rule.version,
        }
    )
    rows.append(
        ProjectionRow(
            ordinal=0,
            field_name="__meta__",
            field_type="json",
            field_value=_nfc(metadata),
            source_excerpt="",
        )
    )

    # --- Tree nodes in preorder ---
    _convert_node(rule.root, rows, parent_ordinal=-1, child_order=0)

    return rows


def _convert_node(
    node: RuleNode,
    rows: list[ProjectionRow],
    parent_ordinal: int,
    child_order: int,
) -> None:
    """Recursively convert a node in preorder traversal."""
    ordinal = len(rows)

    if isinstance(node, AllOf):
        node_info = _canonical_json(
            {
                "child_order": child_order,
                "node_type": "all_of",
                "parent_ordinal": parent_ordinal,
            }
        )
        rows.append(
            ProjectionRow(
                ordinal=ordinal,
                field_name=f"__node_{ordinal}__",
                field_type="json",
                field_value=_nfc(node_info),
                source_excerpt="",
            )
        )
        for i, child in enumerate(node.children):
            _convert_node(child, rows, parent_ordinal=ordinal, child_order=i)

    elif isinstance(node, AnyOf):
        node_info = _canonical_json(
            {
                "child_order": child_order,
                "node_type": "any_of",
                "parent_ordinal": parent_ordinal,
            }
        )
        rows.append(
            ProjectionRow(
                ordinal=ordinal,
                field_name=f"__node_{ordinal}__",
                field_type="json",
                field_value=_nfc(node_info),
                source_excerpt="",
            )
        )
        for i, child in enumerate(node.children):
            _convert_node(child, rows, parent_ordinal=ordinal, child_order=i)

    elif isinstance(node, Condition):
        expected_type, expected_value = _encode_frozen_value(node.expected)
        condition_info = _canonical_json(
            {
                "child_order": child_order,
                "condition_id": node.condition_id,
                "expected_type": expected_type,
                "expected_value": expected_value,
                "field_id": node.field_id,
                "label": node.label,
                "node_type": "condition",
                "operator": node.operator,
                "parent_ordinal": parent_ordinal,
                "source_reference": node.source_reference,
            }
        )
        rows.append(
            ProjectionRow(
                ordinal=ordinal,
                field_name=f"__node_{ordinal}__",
                field_type="json",
                field_value=_nfc(condition_info),
                source_excerpt=_nfc(node.source_reference),
            )
        )

    else:
        raise ConverterVersionError(
            f"Cannot represent node type {type(node).__name__} "
            f"in converter version {CONVERTER_VERSION}"
        )


# ---------------------------------------------------------------------------
# Reverse converter: list[ProjectionRow] -> RuleDefinition
# ---------------------------------------------------------------------------


def convert_from_projection(rows: list[ProjectionRow]) -> RuleDefinition:
    """Reconstruct a full RuleDefinition from projection rows.

    Validates structural integrity. Raises ConverterError if rows are
    invalid or corrupt.
    """
    if not rows:
        raise ConverterError("Empty projection rows")

    # Validate ordinals are consecutive starting at 0
    for i, row in enumerate(rows):
        if row.ordinal != i:
            raise ConverterError(f"Expected ordinal {i}, got {row.ordinal}")

    # Parse metadata from row 0
    meta_row = rows[0]
    if meta_row.field_name != "__meta__":
        raise ConverterError(f"First row must be __meta__, got {meta_row.field_name!r}")
    if meta_row.field_type != "json":
        raise ConverterError(
            f"Meta row must have field_type 'json', got {meta_row.field_type!r}"
        )

    try:
        meta = json.loads(meta_row.field_value)
    except json.JSONDecodeError as e:
        raise ConverterError(f"Invalid metadata JSON: {e}") from e

    # Extract metadata fields
    rule_id = meta.get("rule_id")
    item_id = meta.get("item_id")
    version = meta.get("version")
    dsl_version = meta.get("dsl_version")
    required_field_ids = meta.get("required_field_ids")
    source_references = meta.get("source_references")
    converter_version = meta.get("converter_version")

    if rule_id is None or item_id is None or version is None:
        raise ConverterError("Metadata missing required fields")
    if dsl_version is None:
        raise ConverterError("Metadata missing dsl_version")
    if required_field_ids is None or not isinstance(required_field_ids, list):
        raise ConverterError("Metadata missing or invalid required_field_ids")
    if source_references is None or not isinstance(source_references, list):
        raise ConverterError("Metadata missing or invalid source_references")
    if converter_version is None:
        raise ConverterError("Metadata missing converter_version")

    # Parse tree nodes
    if len(rows) < 2:
        raise ConverterError("Projection must have at least one tree node")

    # Build node info list (index by ordinal, skip metadata at 0)
    node_infos: list[dict] = []
    for row in rows[1:]:
        if row.field_type != "json":
            raise ConverterError(
                f"Node row at ordinal {row.ordinal} has unexpected "
                f"field_type {row.field_type!r}"
            )
        try:
            info = json.loads(row.field_value)
        except json.JSONDecodeError as e:
            raise ConverterError(
                f"Invalid node JSON at ordinal {row.ordinal}: {e}"
            ) from e
        node_infos.append(info)

    # Build children map: parent_ordinal -> list of (child_order, node_index)
    # node_index is 0-based index into node_infos (actual ordinal - 1)
    children_map: dict[int, list[tuple[int, int]]] = {}
    root_indices: list[int] = []

    for idx, info in enumerate(node_infos):
        parent_ordinal = info.get("parent_ordinal")
        child_order = info.get("child_order", 0)

        if parent_ordinal == -1:
            # Root node
            root_indices.append(idx)
        else:
            # Convert parent_ordinal to node_infos index
            parent_idx = parent_ordinal - 1  # offset for metadata row
            if parent_idx < 0 or parent_idx >= len(node_infos):
                raise ConverterError(
                    f"Node at ordinal {idx + 1} references invalid "
                    f"parent_ordinal {parent_ordinal}"
                )
            if parent_idx not in children_map:
                children_map[parent_idx] = []
            children_map[parent_idx].append((child_order, idx))

    if len(root_indices) != 1:
        raise ConverterError(f"Expected exactly 1 root node, found {len(root_indices)}")

    # Recursively reconstruct the tree
    def _build_node(idx: int) -> RuleNode:
        info = node_infos[idx]
        node_type = info.get("node_type")

        if node_type == "all_of":
            child_entries = children_map.get(idx, [])
            # Sort by child_order to restore original order
            child_entries.sort(key=lambda x: x[0])
            children = tuple(_build_node(child_idx) for _, child_idx in child_entries)
            if not children:
                raise ConverterError(f"AllOf node at ordinal {idx + 1} has no children")
            return AllOf(children=children)

        elif node_type == "any_of":
            child_entries = children_map.get(idx, [])
            child_entries.sort(key=lambda x: x[0])
            children = tuple(_build_node(child_idx) for _, child_idx in child_entries)
            if not children:
                raise ConverterError(f"AnyOf node at ordinal {idx + 1} has no children")
            return AnyOf(children=children)

        elif node_type == "condition":
            condition_id = info.get("condition_id", "")
            field_id = info.get("field_id", "")
            operator = info.get("operator", "")
            label = info.get("label", "")
            source_reference = info.get("source_reference", "")
            expected_type = info.get("expected_type", "text")
            expected_value = info.get("expected_value", "")

            expected = _decode_frozen_value(expected_type, expected_value)

            return Condition(
                condition_id=condition_id,
                field_id=field_id,
                operator=operator,
                expected=expected,
                label=label,
                source_reference=source_reference,
            )

        else:
            raise ConverterError(
                f"Unknown node_type {node_type!r} at ordinal {idx + 1}"
            )

    root = _build_node(root_indices[0])

    return RuleDefinition(
        rule_id=rule_id,
        item_id=item_id,
        version=version,
        dsl_version=dsl_version,
        required_field_ids=tuple(required_field_ids),
        root=root,
        source_references=tuple(source_references),
    )


# ---------------------------------------------------------------------------
# Canonical hash
# ---------------------------------------------------------------------------


def compute_canonical_hash(rows: list[ProjectionRow]) -> str:
    """Compute SHA-256 of the canonical byte serialization of projection rows.

    Used for integrity verification. Deterministic: same rows always produce
    the same hash.
    """
    # Build canonical byte representation
    parts: list[str] = []
    for row in rows:
        # Use a stable format: ordinal|field_name|field_type|field_value|source_excerpt
        parts.append(
            f"{row.ordinal}|{row.field_name}|{row.field_type}|{row.field_value}|{row.source_excerpt}"
        )
    canonical = "\n".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
