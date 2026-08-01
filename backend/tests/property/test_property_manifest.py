"""PBT manifest: confirms each property test file exists and is importable.

Task 14.3 requires that Properties 1-20 each have a dedicated test file and
can be individually selected for execution.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROPERTY_DIR = Path(__file__).parent

# Expected property test files (mapping property number to filename)
EXPECTED_PROPERTIES = {
    1: "test_property_01_contracts.py",
    2: "test_property_02_graph_paths.py",
    3: "test_property_03_graph_ordering.py",
    4: "test_property_04_rule_recursion.py",
    5: "test_property_05_missing_fields.py",
    6: "test_property_06_converter_roundtrip.py",
    7: "test_property_07_projection_atomicity.py",
    8: "test_property_08_status_gates.py",
    9: "test_property_09_candidate_sorting.py",
    10: "test_property_10_citation_completeness.py",
    11: "test_property_11_response_authorization.py",
    12: "test_property_12_sanitizer.py",
    13: "test_property_13_raw_text_disposal.py",
    14: "test_property_14_refresh_dedup.py",
    15: "test_property_15_current_data_first.py",
    16: "test_property_16_coverage_invariants.py",
    17: "test_property_17_coverage_claims.py",
    18: "test_property_18_sqlite_lifecycle.py",
    19: "test_property_19_json_export.py",
    20: "test_property_20_pre_august_governance.py",
}


@pytest.mark.parametrize(
    "prop_num,filename",
    sorted(EXPECTED_PROPERTIES.items()),
    ids=[f"Property-{n}" for n in sorted(EXPECTED_PROPERTIES)],
)
def test_property_file_exists(prop_num: int, filename: str) -> None:
    """Each design property has a dedicated test file."""
    path = PROPERTY_DIR / filename
    assert path.exists(), f"Property {prop_num} test file missing: {filename}"
