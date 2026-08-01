"""Deterministic inventory for frozen legacy rule-field rows.

This module intentionally does not infer Rule DSL operators, boolean structure,
source references, or evidence. It records an under-review conversion manifest
that a human reviewer can later map to canonical Rule DSL data.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Final

CONVERTER_VERSION: Final = "legacy-rule-inventory-v1"
LEGACY_SOURCE_TABLE: Final = "program_rule_fields"
PRESERVED_LEGACY_TABLE: Final = "legacy_program_rule_fields_v1"


@dataclass(frozen=True, slots=True)
class LegacyProgramDraft:
    """One deterministic under-review draft derived without semantic guesses."""

    program_id: str
    source_row_count: int
    source_rows_sha256: str


@dataclass(frozen=True, slots=True)
class LegacyRuleInventory:
    """Pre-rename schema and row fingerprints plus per-program draft inputs."""

    inventory_id: str
    source_schema_sha256: str
    source_rows_sha256: str
    row_count: int
    drafts: tuple[LegacyProgramDraft, ...]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _object_sql(
    connection: sqlite3.Connection,
    *,
    object_type: str,
    object_name: str,
) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
        (object_type, object_name),
    ).fetchone()
    if row is None or row[0] is None:
        raise ValueError("legacy_rule_schema_unavailable")
    return str(row[0])


def prepare_legacy_rule_inventory(
    connection: sqlite3.Connection,
) -> LegacyRuleInventory | None:
    """Fingerprint the supported writable legacy table before it is renamed."""

    object_row = connection.execute(
        "SELECT type FROM sqlite_master WHERE name = ?",
        (LEGACY_SOURCE_TABLE,),
    ).fetchone()
    if object_row is None or str(object_row[0]) == "view":
        return None
    if str(object_row[0]) != "table":
        raise ValueError("legacy_rule_schema_unavailable")

    table_sql = _object_sql(
        connection,
        object_type="table",
        object_name=LEGACY_SOURCE_TABLE,
    )
    index_sql = _object_sql(
        connection,
        object_type="index",
        object_name="idx_program_rule_fields_field_name",
    )
    schema_payload = {
        "index_sql": index_sql,
        "table_sql": table_sql,
    }
    source_schema_sha256 = _sha256(_canonical_bytes(schema_payload))

    rows = tuple(
        tuple(row)
        for row in connection.execute(
            """
            SELECT
                program_id,
                field_name,
                field_type,
                field_value,
                source_excerpt,
                review_status,
                created_at,
                updated_at
            FROM program_rule_fields
            ORDER BY program_id, field_name
            """
        )
    )
    source_rows_sha256 = _sha256(_canonical_bytes(rows))
    inventory_hash = _sha256(
        _canonical_bytes((source_schema_sha256, source_rows_sha256))
    )
    inventory_id = f"legacy-rules-{inventory_hash[:24]}"

    drafts: list[LegacyProgramDraft] = []
    program_ids = sorted({str(row[0]) for row in rows})
    for program_id in program_ids:
        program_rows = tuple(row for row in rows if str(row[0]) == program_id)
        drafts.append(
            LegacyProgramDraft(
                program_id=program_id,
                source_row_count=len(program_rows),
                source_rows_sha256=_sha256(_canonical_bytes(program_rows)),
            )
        )

    return LegacyRuleInventory(
        inventory_id=inventory_id,
        source_schema_sha256=source_schema_sha256,
        source_rows_sha256=source_rows_sha256,
        row_count=len(rows),
        drafts=tuple(drafts),
    )


def _preserved_rows_sha256(connection: sqlite3.Connection) -> str:
    rows = tuple(
        tuple(row)
        for row in connection.execute(
            """
            SELECT
                program_id,
                field_name,
                field_type,
                field_value,
                source_excerpt,
                review_status,
                created_at,
                updated_at
            FROM legacy_program_rule_fields_v1
            ORDER BY program_id, field_name
            """
        )
    )
    return _sha256(_canonical_bytes(rows))


def persist_legacy_rule_conversion(
    connection: sqlite3.Connection,
    inventory: LegacyRuleInventory | None,
    *,
    captured_at: str,
) -> None:
    """Persist a rerunnable under-review manifest inside the migration transaction."""

    if inventory is None:
        return
    if _preserved_rows_sha256(connection) != inventory.source_rows_sha256:
        raise ValueError("legacy_rule_rows_changed")

    connection.execute(
        """
        INSERT INTO legacy_rule_migration_inventory (
            inventory_id,
            source_table_name,
            source_schema_sha256,
            source_rows_sha256,
            row_count,
            converter_version,
            captured_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(inventory_id) DO NOTHING
        """,
        (
            inventory.inventory_id,
            LEGACY_SOURCE_TABLE,
            inventory.source_schema_sha256,
            inventory.source_rows_sha256,
            inventory.row_count,
            CONVERTER_VERSION,
            captured_at,
        ),
    )
    stored_inventory = connection.execute(
        """
        SELECT
            source_table_name,
            source_schema_sha256,
            source_rows_sha256,
            row_count,
            converter_version
        FROM legacy_rule_migration_inventory
        WHERE inventory_id = ?
        """,
        (inventory.inventory_id,),
    ).fetchone()
    expected_inventory = (
        LEGACY_SOURCE_TABLE,
        inventory.source_schema_sha256,
        inventory.source_rows_sha256,
        inventory.row_count,
        CONVERTER_VERSION,
    )
    if stored_inventory != expected_inventory:
        raise ValueError("legacy_rule_inventory_conflict")

    for draft in inventory.drafts:
        draft_hash = _sha256(
            _canonical_bytes((inventory.inventory_id, draft.program_id))
        )
        draft_id = f"legacy-draft-{draft_hash[:24]}"
        connection.execute(
            """
            INSERT INTO legacy_rule_conversion_drafts (
                draft_id,
                inventory_id,
                program_id,
                converter_version,
                conversion_status,
                reason_code,
                source_row_count,
                source_rows_sha256,
                created_at
            ) VALUES (?, ?, ?, ?, 'under_review', ?, ?, ?, ?)
            ON CONFLICT(inventory_id, program_id) DO NOTHING
            """,
            (
                draft_id,
                inventory.inventory_id,
                draft.program_id,
                CONVERTER_VERSION,
                "manual_mapping_required",
                draft.source_row_count,
                draft.source_rows_sha256,
                captured_at,
            ),
        )
        stored_draft = connection.execute(
            """
            SELECT
                draft_id,
                converter_version,
                conversion_status,
                reason_code,
                source_row_count,
                source_rows_sha256
            FROM legacy_rule_conversion_drafts
            WHERE inventory_id = ? AND program_id = ?
            """,
            (inventory.inventory_id, draft.program_id),
        ).fetchone()
        expected_draft = (
            draft_id,
            CONVERTER_VERSION,
            "under_review",
            "manual_mapping_required",
            draft.source_row_count,
            draft.source_rows_sha256,
        )
        if stored_draft != expected_draft:
            raise ValueError("legacy_rule_draft_conflict")
