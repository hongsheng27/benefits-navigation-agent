"""驗證屬性值的型別與選項檢查。

三個案例：正常放行、邊界（`True` 不算整數）、失敗（不合法值只回代號不回值）。
"""

import pytest

from app.orchestration.field_registry import FieldRegistry
from app.privacy.attribute_gate import (
    InvalidAttributeValueError,
    RegistryBackedPrivacyGate,
)


def test_valid_values_pass_through() -> None:
    """三種型別各給一個合法值，全部放行。"""
    gate = RegistryBackedPrivacyGate()
    answers = {
        "deceased_insurance_type": "labor_insurance",  # code
        "has_dependent_children": True,  # boolean
        "applicant_age_band": "25_to_55",  # band
    }

    accepted = gate.validate_attributes(dict(answers), FieldRegistry.from_json())

    assert accepted == answers


def test_boolean_does_not_satisfy_an_integer_field() -> None:
    """邊界：Python 的 True 是 int 的子類別，不特別擋會被當成合法整數。

    種子登記表沒有 integer 欄位，所以用一個臨時的 registry 來測這條邊界。
    """
    gate = RegistryBackedPrivacyGate()

    class _IntegerOnlyRegistry:
        def get(self, field_id: str):
            from app.orchestration.field_registry import FieldDefinition
            from app.schemas.session import AttributeValueKind

            return FieldDefinition(
                field_id=field_id,
                value_kind=AttributeValueKind.INTEGER,
                purpose="測試 integer 邊界",
                topic_id="test",
            )

    registry = _IntegerOnlyRegistry()

    assert gate.validate_attributes({"child_count": 2}, registry) == {"child_count": 2}

    with pytest.raises(InvalidAttributeValueError):
        gate.validate_attributes({"child_count": True}, registry)


def test_free_text_in_a_code_field_is_rejected_without_echoing_the_value() -> None:
    """失敗：代號合法但值是自由文字。錯誤只帶欄位代號，不帶那段文字。

    沒有這道檢查，任何文字都能藉合法代號存進 state 再原值回到前端（ADR-0007）。
    """
    gate = RegistryBackedPrivacyGate()
    secret = "這段文字不應該出現在錯誤裡"

    with pytest.raises(InvalidAttributeValueError) as caught:
        gate.validate_attributes(
            {"deceased_insurance_type": secret}, FieldRegistry.from_json()
        )

    assert caught.value.field_ids == ("deceased_insurance_type",)
    assert secret not in str(caught.value)
