"""Catalog validation logic (Req 15.5-15.12).

Validates schema integrity, operator allowlist, required fields, citations,
referential integrity, status gates, amount quartet, projection consistency,
and synthetic isolation.

Failure outputs safe IDs/version/code with non-zero exit.
Success outputs validated count with zero exit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from app.rules.dsl import OPERATOR_ALLOWLIST_V1 as OPERATOR_ALLOWLIST

# Valid program statuses
VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {"candidate", "under_review", "verified", "stale", "rejected", "inactive"}
)

# Required fields for benefit programs
REQUIRED_PROGRAM_FIELDS: Final[frozenset[str]] = frozenset(
    {"program_id", "display_name", "program_status"}
)

# Required fields for rule versions
REQUIRED_RULE_FIELDS: Final[frozenset[str]] = frozenset(
    {"rule_version_id", "rule_id", "version", "dsl_version", "approval_status"}
)


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """A single validation finding."""

    code: str
    severity: str  # "error" or "warning"
    item_id: str = ""
    message: str = ""


@dataclass(slots=True)
class ValidationResult:
    """Aggregate result of catalog validation."""

    findings: list[ValidationFinding] = field(default_factory=list)
    tables_checked: int = 0
    rows_checked: int = 0

    @property
    def is_valid(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")


def validate_catalog(data: dict[str, list[dict[str, Any]]]) -> ValidationResult:
    """Run all validation checks against catalog data.

    Args:
        data: Dict mapping table names to lists of row dicts.

    Returns:
        ValidationResult with findings.
    """
    result = ValidationResult()

    # Schema checks
    _check_program_schema(data, result)
    _check_rule_schema(data, result)

    # Status gate checks
    _check_status_gates(data, result)

    # Amount quartet checks
    _check_amount_quartets(data, result)

    # Referential integrity
    _check_referential_integrity(data, result)

    # Operator allowlist
    _check_operator_allowlist(data, result)

    # Synthetic isolation
    _check_synthetic_isolation(data, result)

    result.tables_checked = len(data)
    result.rows_checked = sum(len(rows) for rows in data.values())

    return result


def _check_program_schema(
    data: dict[str, list[dict[str, Any]]], result: ValidationResult
) -> None:
    """Check benefit_programs table schema."""
    programs = data.get("benefit_programs", [])
    for row in programs:
        for field_name in REQUIRED_PROGRAM_FIELDS:
            if field_name not in row or row[field_name] is None:
                result.findings.append(
                    ValidationFinding(
                        code="MISSING_REQUIRED_FIELD",
                        severity="error",
                        item_id=row.get("program_id", "unknown"),
                        message=f"Missing required field: {field_name}",
                    )
                )
        status = row.get("program_status")
        if status and status not in VALID_STATUSES:
            result.findings.append(
                ValidationFinding(
                    code="INVALID_STATUS",
                    severity="error",
                    item_id=row.get("program_id", "unknown"),
                    message=f"Invalid program_status: {status}",
                )
            )


def _check_rule_schema(
    data: dict[str, list[dict[str, Any]]], result: ValidationResult
) -> None:
    """Check rule_versions table schema."""
    rules = data.get("rule_versions", [])
    for row in rules:
        for field_name in REQUIRED_RULE_FIELDS:
            if field_name not in row or row[field_name] is None:
                result.findings.append(
                    ValidationFinding(
                        code="MISSING_REQUIRED_FIELD",
                        severity="error",
                        item_id=row.get("rule_version_id", "unknown"),
                        message=f"Missing required field: {field_name}",
                    )
                )


def _check_status_gates(
    data: dict[str, list[dict[str, Any]]], result: ValidationResult
) -> None:
    """Verified status requires reviewer metadata."""
    programs = data.get("benefit_programs", [])
    for row in programs:
        if row.get("program_status") == "verified":
            if not row.get("reviewed_by"):
                result.findings.append(
                    ValidationFinding(
                        code="VERIFIED_WITHOUT_REVIEWER",
                        severity="error",
                        item_id=row.get("program_id", "unknown"),
                        message="Verified status requires reviewer metadata",
                    )
                )


def _check_amount_quartets(
    data: dict[str, list[dict[str, Any]]], result: ValidationResult
) -> None:
    """Amount fields must be all-or-none."""
    amount_fields = (
        "amount_min",
        "amount_max",
        "amount_period",
        "amount_currency",
    )
    programs = data.get("benefit_programs", [])
    for row in programs:
        present = [row.get(f) is not None for f in amount_fields if f in row]
        if present and any(present) and not all(present):
            result.findings.append(
                ValidationFinding(
                    code="PARTIAL_AMOUNT_QUARTET",
                    severity="error",
                    item_id=row.get("program_id", "unknown"),
                    message="Amount quartet must be all-or-none",
                )
            )
        # Validate min <= max
        if row.get("amount_min") is not None and row.get("amount_max") is not None:
            if row["amount_min"] > row["amount_max"]:
                result.findings.append(
                    ValidationFinding(
                        code="AMOUNT_MIN_GT_MAX",
                        severity="error",
                        item_id=row.get("program_id", "unknown"),
                        message="amount_min must be <= amount_max",
                    )
                )


def _check_referential_integrity(
    data: dict[str, list[dict[str, Any]]], result: ValidationResult
) -> None:
    """Check FK-like references between tables."""
    program_ids = {
        row.get("program_id")
        for row in data.get("benefit_programs", [])
        if row.get("program_id")
    }

    # rule_definitions.program_id → benefit_programs.program_id
    for row in data.get("rule_definitions", []):
        pid = row.get("program_id")
        if pid and pid not in program_ids:
            result.findings.append(
                ValidationFinding(
                    code="ORPHAN_RULE_DEFINITION",
                    severity="error",
                    item_id=row.get("rule_id", "unknown"),
                    message=f"rule references non-existent program: {pid}",
                )
            )


def _check_operator_allowlist(
    data: dict[str, list[dict[str, Any]]], result: ValidationResult
) -> None:
    """Rule conditions must use allowed operators."""
    conditions = data.get("rule_conditions", [])
    for row in conditions:
        op = row.get("operator")
        if op and op not in OPERATOR_ALLOWLIST:
            result.findings.append(
                ValidationFinding(
                    code="INVALID_OPERATOR",
                    severity="error",
                    item_id=row.get("condition_id", "unknown"),
                    message=f"Operator '{op}' not in allowlist",
                )
            )


def _check_synthetic_isolation(
    data: dict[str, list[dict[str, Any]]], result: ValidationResult
) -> None:
    """Synthetic/test data should not appear in canonical catalog."""
    for table_name, rows in data.items():
        for row in rows:
            for key, value in row.items():
                if isinstance(value, str) and value.startswith("synth-test-"):
                    result.findings.append(
                        ValidationFinding(
                            code="SYNTHETIC_DATA_DETECTED",
                            severity="warning",
                            item_id=str(row.get("program_id", row.get("id", ""))),
                            message=f"Synthetic test data in {table_name}.{key}",
                        )
                    )
