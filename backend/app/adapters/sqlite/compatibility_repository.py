"""SQLite adapter for atomic compatibility projection persistence.

Implements generation-based atomic replacement with hash and reverse-conversion
validation. The active pointer is only switched after the entire generation is
written and validated within a single transaction.

On any failure the transaction is rolled back and the old active generation
(if any) remains visible to readers.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from app.adapters.sqlite.connection import execute_read, execute_transaction
from app.orchestration.data_errors import DataLayerError
from app.rules.compatibility import (
    CONVERTER_VERSION,
    ConverterError,
    ConverterVersionError,
    ProjectionRow,
    compute_canonical_hash,
    convert_from_projection,
    convert_to_projection,
)
from app.rules.dsl import RuleDefinition

# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class ProjectionGenerationError(DataLayerError):
    """Raised when generation fails.

    The message is sanitized — it contains only a safe error code, never SQL,
    raw data, or user values.
    """


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class CompatibilityProjectionRepository:
    """Atomic compatibility projection persistence backed by SQLite."""

    def __init__(self, connection_factory: Callable[[], sqlite3.Connection]) -> None:
        self._connection_factory = connection_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_projection(
        self,
        rule: RuleDefinition,
        rule_version_id: str,
        program_id: str,
    ) -> str:
        """Generate a new projection and atomically switch the active pointer.

        Returns the generation_id on success.
        Raises ProjectionGenerationError on any failure (converter error,
        validation failure, DB error). On failure the old active generation
        is preserved.
        """
        try:
            return execute_transaction(
                self._connection_factory,
                lambda conn: self._do_generate(conn, rule, rule_version_id, program_id),
            )
        except ProjectionGenerationError:
            raise
        except (ConverterError, ConverterVersionError) as exc:
            raise ProjectionGenerationError("converter_failed") from exc
        except Exception as exc:
            raise ProjectionGenerationError("generation_failed") from exc

    def get_active_generation(self, program_id: str) -> tuple[str, str] | None:
        """Return (generation_id, rule_version_id) for the active generation.

        Returns None if no active generation exists for this program.
        """
        return execute_read(
            self._connection_factory,
            lambda conn: self._do_get_active(conn, program_id),
        )

    def read_projection_rows(self, generation_id: str) -> list[ProjectionRow]:
        """Read all rows for a generation ordered by ordinal.

        Returns an empty list if the generation doesn't exist.
        """
        return execute_read(
            self._connection_factory,
            lambda conn: self._do_read_rows(conn, generation_id),
        )

    # ------------------------------------------------------------------
    # Internal: generation within a single transaction
    # ------------------------------------------------------------------

    def _do_generate(
        self,
        conn: sqlite3.Connection,
        rule: RuleDefinition,
        rule_version_id: str,
        program_id: str,
    ) -> str:
        generation_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        # Step 1: Convert rule to projection rows
        try:
            rows = convert_to_projection(rule)
        except (ConverterError, ConverterVersionError) as exc:
            raise ProjectionGenerationError("converter_failed") from exc

        if not rows:
            raise ProjectionGenerationError("converter_empty_result")

        # Step 2: Compute canonical hash
        canonical_hash = compute_canonical_hash(rows)

        # Step 3a: INSERT generation with status='building'
        try:
            conn.execute(
                """
                INSERT INTO compat_projection_generations (
                    generation_id, rule_version_id, program_id,
                    converter_version, canonical_hash, status,
                    row_count, created_at, validated_at
                ) VALUES (?, ?, ?, ?, ?, 'building', 0, ?, NULL)
                """,
                (
                    generation_id,
                    rule_version_id,
                    program_id,
                    CONVERTER_VERSION,
                    canonical_hash,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ProjectionGenerationError("generation_insert_failed") from exc

        # Step 3b: INSERT all projection rows
        try:
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO compat_projection_rows (
                        generation_id, ordinal, program_id, field_name,
                        field_type, field_value, source_excerpt,
                        review_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        generation_id,
                        row.ordinal,
                        program_id,
                        row.field_name,
                        row.field_type,
                        row.field_value,
                        row.source_excerpt,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ProjectionGenerationError("rows_insert_failed") from exc

        # Step 3c: Validate — reverse convert rows back to RuleDefinition
        try:
            reconstructed = convert_from_projection(rows)
        except (ConverterError, ConverterVersionError) as exc:
            raise ProjectionGenerationError("reverse_conversion_failed") from exc

        # Compare semantic equivalence: re-convert the reconstructed rule and
        # verify the canonical hash matches (deterministic round-trip)
        try:
            re_rows = convert_to_projection(reconstructed)
        except (ConverterError, ConverterVersionError) as exc:
            raise ProjectionGenerationError("semantic_validation_failed") from exc

        re_hash = compute_canonical_hash(re_rows)
        if re_hash != canonical_hash:
            raise ProjectionGenerationError("hash_mismatch_after_roundtrip")

        # Step 3d: UPDATE generation status to 'validated'
        row_count = len(rows)
        validated_at = datetime.now(UTC).isoformat()
        try:
            conn.execute(
                """
                UPDATE compat_projection_generations
                SET status = 'validated',
                    row_count = ?,
                    validated_at = ?
                WHERE generation_id = ?
                """,
                (row_count, validated_at, generation_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ProjectionGenerationError("generation_validate_failed") from exc

        # Step 3e: INSERT OR REPLACE into compat_projection_active
        activated_at = datetime.now(UTC).isoformat()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO compat_projection_active (
                    program_id, rule_version_id, generation_id, activated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (program_id, rule_version_id, generation_id, activated_at),
            )
        except sqlite3.IntegrityError as exc:
            raise ProjectionGenerationError("active_pointer_switch_failed") from exc

        return generation_id

    # ------------------------------------------------------------------
    # Internal: read operations
    # ------------------------------------------------------------------

    def _do_get_active(
        self,
        conn: sqlite3.Connection,
        program_id: str,
    ) -> tuple[str, str] | None:
        row = conn.execute(
            """
            SELECT generation_id, rule_version_id
            FROM compat_projection_active
            WHERE program_id = ?
            """,
            (program_id,),
        ).fetchone()
        if row is None:
            return None
        return (str(row[0]), str(row[1]))

    def _do_read_rows(
        self,
        conn: sqlite3.Connection,
        generation_id: str,
    ) -> list[ProjectionRow]:
        rows = conn.execute(
            """
            SELECT ordinal, field_name, field_type, field_value, source_excerpt
            FROM compat_projection_rows
            WHERE generation_id = ?
            ORDER BY ordinal
            """,
            (generation_id,),
        ).fetchall()
        return [
            ProjectionRow(
                ordinal=int(row[0]),
                field_name=str(row[1]),
                field_type=str(row[2]),
                field_value=str(row[3]),
                source_excerpt=str(row[4]),
            )
            for row in rows
        ]
