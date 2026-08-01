"""驗證欄位登記表的讀取、驗證與查詢。"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.orchestration.field_registry import FieldRegistry
from app.schemas.session import AttributeValueKind


def _write_registry(fields: list[dict], tmp_path: Path) -> Path:
    path = tmp_path / "test_fields.json"
    path.write_text(
        json.dumps({"fields": fields}, ensure_ascii=False), encoding="utf-8"
    )
    return path


def _minimal_field(**overrides) -> dict:
    base = {
        "field_id": "test_field",
        "value_kind": "code",
        "option_ids": ["a", "b"],
        "required": True,
        "purpose": "測試用途",
        "used_by": ["some_item"],
        "topic_id": "test_topic",
        "status": "draft",
    }
    base.update(overrides)
    return base


def test_loads_the_seed_data_without_error() -> None:
    """種子資料 v0.1.json 能成功讀取。"""
    registry = FieldRegistry.from_json()

    assert registry.count() == 4
    assert registry.has("applicant_jurisdiction")
    assert registry.has("deceased_insurance_type")
    assert registry.has("has_dependent_children")
    assert registry.has("applicant_age_band")


def test_field_definition_values(tmp_path: Path) -> None:
    path = _write_registry([_minimal_field()], tmp_path)
    registry = FieldRegistry.from_json(path)

    field = registry.get("test_field")
    assert field is not None
    assert field.value_kind is AttributeValueKind.CODE
    assert field.option_ids == ("a", "b")
    assert field.required is True
    assert field.purpose == "測試用途"
    assert field.used_by == ("some_item",)
    assert field.topic_id == "test_topic"


def test_purpose_cannot_be_empty(tmp_path: Path) -> None:
    """purpose 是強制填寫的，空字串不行。"""
    path = _write_registry([_minimal_field(purpose="")], tmp_path)

    with pytest.raises(ValidationError):
        FieldRegistry.from_json(path)


def test_purpose_cannot_be_whitespace_only(tmp_path: Path) -> None:
    path = _write_registry([_minimal_field(purpose="   ")], tmp_path)

    with pytest.raises(ValidationError):
        FieldRegistry.from_json(path)


def test_unknown_value_kind_is_rejected(tmp_path: Path) -> None:
    path = _write_registry([_minimal_field(value_kind="unknown")], tmp_path)

    with pytest.raises(ValidationError):
        FieldRegistry.from_json(path)


def test_extra_fields_are_rejected(tmp_path: Path) -> None:
    path = _write_registry([_minimal_field(surprise="bad")], tmp_path)

    with pytest.raises(ValidationError):
        FieldRegistry.from_json(path)


def test_has_returns_false_for_unregistered_fields(tmp_path: Path) -> None:
    path = _write_registry([_minimal_field()], tmp_path)
    registry = FieldRegistry.from_json(path)

    assert not registry.has("not_registered")
    assert registry.get("not_registered") is None


def test_fields_for_items_filters_by_used_by(tmp_path: Path) -> None:
    fields = [
        _minimal_field(field_id="f1", used_by=["item_a", "item_b"], topic_id="t1"),
        _minimal_field(field_id="f2", used_by=["item_b"], topic_id="t1"),
        _minimal_field(field_id="f3", used_by=["item_c"], topic_id="t2"),
    ]
    path = _write_registry(fields, tmp_path)
    registry = FieldRegistry.from_json(path)

    result = registry.fields_for_items(frozenset({"item_b"}))

    assert {d.field_id for d in result} == {"f1", "f2"}


def test_topics_preserves_registration_order(tmp_path: Path) -> None:
    fields = [
        _minimal_field(field_id="f1", topic_id="topic_b"),
        _minimal_field(field_id="f2", topic_id="topic_a"),
        _minimal_field(field_id="f3", topic_id="topic_b"),
    ]
    path = _write_registry(fields, tmp_path)
    registry = FieldRegistry.from_json(path)

    assert registry.topics() == ("topic_b", "topic_a")


def test_fields_in_topic_returns_only_that_topic(tmp_path: Path) -> None:
    fields = [
        _minimal_field(field_id="f1", topic_id="topic_x"),
        _minimal_field(field_id="f2", topic_id="topic_y"),
        _minimal_field(field_id="f3", topic_id="topic_x"),
    ]
    path = _write_registry(fields, tmp_path)
    registry = FieldRegistry.from_json(path)

    result = registry.fields_in_topic("topic_x")
    assert [d.field_id for d in result] == ["f1", "f3"]


def test_all_field_ids_is_a_frozenset(tmp_path: Path) -> None:
    fields = [
        _minimal_field(field_id="a", topic_id="t"),
        _minimal_field(field_id="b", topic_id="t"),
    ]
    path = _write_registry(fields, tmp_path)
    registry = FieldRegistry.from_json(path)

    ids = registry.all_field_ids()
    assert isinstance(ids, frozenset)
    assert ids == {"a", "b"}


def test_seed_data_fields_have_valid_purposes() -> None:
    """種子資料裡每一筆的 purpose 都不是空的。"""
    registry = FieldRegistry.from_json()

    for field_id in registry.all_field_ids():
        field = registry.get(field_id)
        assert field is not None
        assert field.purpose.strip(), f"{field_id} 的 purpose 不能是空白"
