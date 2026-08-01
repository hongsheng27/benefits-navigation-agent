"""Unit tests for catalog validation (Task 14.1).

Covers:
- Valid catalog passes
- Missing required fields detected
- Invalid status detected
- Amount quartet all-or-none
- Referential integrity
- Operator allowlist
- Synthetic isolation detection
"""

from __future__ import annotations

from app.validation.catalog import validate_catalog

# ---------------------------------------------------------------------------
# Valid catalog
# ---------------------------------------------------------------------------


def test_empty_catalog_is_valid() -> None:
    """An empty catalog has no errors."""
    result = validate_catalog({})
    assert result.is_valid
    assert result.error_count == 0


def test_valid_programs_pass() -> None:
    """Programs with all required fields pass."""
    data = {
        "benefit_programs": [
            {
                "program_id": "funeral_benefit",
                "display_name": "喪葬給付",
                "program_status": "candidate",
            }
        ]
    }
    result = validate_catalog(data)
    assert result.is_valid


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


def test_missing_program_id_detected() -> None:
    """Missing program_id is an error."""
    data = {
        "benefit_programs": [{"display_name": "Test", "program_status": "candidate"}]
    }
    result = validate_catalog(data)
    assert not result.is_valid
    codes = [f.code for f in result.findings]
    assert "MISSING_REQUIRED_FIELD" in codes


def test_missing_rule_version_fields_detected() -> None:
    """Missing rule_version required fields are errors."""
    data = {"rule_versions": [{"rule_version_id": "rv-1"}]}
    result = validate_catalog(data)
    assert not result.is_valid


# ---------------------------------------------------------------------------
# Invalid status
# ---------------------------------------------------------------------------


def test_invalid_program_status_detected() -> None:
    """Unknown program_status is an error."""
    data = {
        "benefit_programs": [
            {
                "program_id": "p1",
                "display_name": "Test",
                "program_status": "unknown_status",
            }
        ]
    }
    result = validate_catalog(data)
    assert not result.is_valid
    codes = [f.code for f in result.findings]
    assert "INVALID_STATUS" in codes


# ---------------------------------------------------------------------------
# Amount quartet
# ---------------------------------------------------------------------------


def test_partial_amount_quartet_detected() -> None:
    """Partial amount fields (some present, some missing) is an error."""
    data = {
        "benefit_programs": [
            {
                "program_id": "p1",
                "display_name": "Test",
                "program_status": "candidate",
                "amount_min": 1000,
                "amount_max": None,
                "amount_period": "monthly",
                "amount_currency": "TWD",
            }
        ]
    }
    result = validate_catalog(data)
    assert not result.is_valid
    codes = [f.code for f in result.findings]
    assert "PARTIAL_AMOUNT_QUARTET" in codes


def test_complete_amount_quartet_passes() -> None:
    """All amount fields present passes."""
    data = {
        "benefit_programs": [
            {
                "program_id": "p1",
                "display_name": "Test",
                "program_status": "candidate",
                "amount_min": 1000,
                "amount_max": 5000,
                "amount_period": "monthly",
                "amount_currency": "TWD",
            }
        ]
    }
    result = validate_catalog(data)
    assert result.is_valid


def test_amount_min_gt_max_detected() -> None:
    """amount_min > amount_max is an error."""
    data = {
        "benefit_programs": [
            {
                "program_id": "p1",
                "display_name": "Test",
                "program_status": "candidate",
                "amount_min": 5000,
                "amount_max": 1000,
                "amount_period": "monthly",
                "amount_currency": "TWD",
            }
        ]
    }
    result = validate_catalog(data)
    assert not result.is_valid
    codes = [f.code for f in result.findings]
    assert "AMOUNT_MIN_GT_MAX" in codes


# ---------------------------------------------------------------------------
# Referential integrity
# ---------------------------------------------------------------------------


def test_orphan_rule_definition_detected() -> None:
    """A rule referencing a non-existent program is an error."""
    data = {
        "benefit_programs": [
            {
                "program_id": "p1",
                "display_name": "Test",
                "program_status": "candidate",
            }
        ],
        "rule_definitions": [{"rule_id": "r1", "program_id": "nonexistent_program"}],
    }
    result = validate_catalog(data)
    assert not result.is_valid
    codes = [f.code for f in result.findings]
    assert "ORPHAN_RULE_DEFINITION" in codes


def test_valid_rule_reference_passes() -> None:
    """A rule referencing an existing program passes."""
    data = {
        "benefit_programs": [
            {
                "program_id": "p1",
                "display_name": "Test",
                "program_status": "candidate",
            }
        ],
        "rule_definitions": [{"rule_id": "r1", "program_id": "p1"}],
    }
    result = validate_catalog(data)
    assert result.is_valid


# ---------------------------------------------------------------------------
# Operator allowlist
# ---------------------------------------------------------------------------


def test_invalid_operator_detected() -> None:
    """Rule conditions with unknown operators are errors."""
    data = {"rule_conditions": [{"condition_id": "c1", "operator": "INVALID_OP"}]}
    result = validate_catalog(data)
    assert not result.is_valid
    codes = [f.code for f in result.findings]
    assert "INVALID_OPERATOR" in codes


# ---------------------------------------------------------------------------
# Synthetic isolation
# ---------------------------------------------------------------------------


def test_synthetic_data_detected_as_warning() -> None:
    """Test data markers are flagged as warnings."""
    data = {
        "benefit_programs": [
            {
                "program_id": "synth-test-001",
                "display_name": "Test",
                "program_status": "candidate",
            }
        ]
    }
    result = validate_catalog(data)
    # Synthetic data is a warning, not an error
    assert result.is_valid
    assert result.warning_count > 0
    codes = [f.code for f in result.findings]
    assert "SYNTHETIC_DATA_DETECTED" in codes


# ---------------------------------------------------------------------------
# Status gates: verified requires reviewer
# ---------------------------------------------------------------------------


def test_verified_without_reviewer_detected() -> None:
    """Verified status without reviewer metadata is an error."""
    data = {
        "benefit_programs": [
            {
                "program_id": "p1",
                "display_name": "Test",
                "program_status": "verified",
                "reviewed_by": None,
            }
        ]
    }
    result = validate_catalog(data)
    assert not result.is_valid
    codes = [f.code for f in result.findings]
    assert "VERIFIED_WITHOUT_REVIEWER" in codes
