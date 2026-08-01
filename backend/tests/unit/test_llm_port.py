"""驗證 LLM port 的邊界形狀與 schema 可攜性檢查。

可攜性檢查值得測，理由不是它複雜，是它防的錯誤**只會在切換廠商那天出現**：
寫出 Gemini 接受但 Bedrock 拒絕的 schema，現在完全沒事，換過去那天全部 400，
而且每一份 schema 都要同時重寫（ADR-0015）。
"""

import re

import pytest

from app.llm.fake import FakeLanguageModel, UnavailableLanguageModel
from app.llm.port import (
    FinishReason,
    LanguageModelUnavailableError,
    LlmRequest,
    LlmTask,
    SchemaNotPortableError,
    validate_portable_schema,
)

# 一份合規的 schema：只用允許清單上的關鍵字，物件明寫不允許多餘欄位，
# 而且用 enum 限制值 —— 那正是本專案真正需要的形狀（模型只能回代號）。
PORTABLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["event_id"],
    "properties": {
        "event_id": {
            "type": "string",
            "enum": ["spouse_death", "parent_death", "unknown"],
            "description": "辨識出來的生命事件代號",
        },
    },
}


def _request(schema: dict | None = None) -> LlmRequest:
    return LlmRequest(
        task=LlmTask.RESOLVE_LIFE_EVENT,
        instruction="把描述對應到一個事件代號",
        user_content="我先生上個月過世了",
        output_schema=schema if schema is not None else PORTABLE_SCHEMA,
        schema_name="life_event",
    )


# ---------------------------------------------------------------------------
# schema 可攜性
# ---------------------------------------------------------------------------


def test_portable_schema_passes() -> None:
    """正常路徑：只用 Bedrock 支援子集的 schema 通過檢查。"""
    validate_portable_schema(PORTABLE_SCHEMA)


def test_an_empty_object_schema_is_portable() -> None:
    """對照組：最小的合規 schema 必須通過。

    沒有這一筆，下面那個「全部拒絕」的測試就無法證明檢查不是一律拒絕。
    """
    validate_portable_schema(
        {"type": "object", "additionalProperties": False, "properties": {}}
    )


@pytest.mark.parametrize(
    ("bad_schema", "violation"),
    [
        pytest.param(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"name": {"type": "string", "maxLength": 20}},
            },
            "maxLength",
            id="string-length-constraint",
        ),
        pytest.param(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"age": {"type": "integer", "minimum": 0}},
            },
            "minimum",
            id="numeric-constraint",
        ),
        pytest.param(
            {"type": "object", "properties": {}},
            "additionalProperties",
            id="object-without-explicit-additional-properties",
        ),
        pytest.param(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"ref": {"$ref": "https://example.invalid/schema.json"}},
            },
            "$ref",
            id="external-ref",
        ),
        pytest.param(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "tags": {
                        "type": "array",
                        "minItems": 3,
                        "items": {"type": "string"},
                    }
                },
            },
            "minItems",
            id="min-items-other-than-zero-or-one",
        ),
        pytest.param(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "notes": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    }
                },
            },
            "minLength",
            id="violation-nested-in-array-items",
        ),
    ],
)
def test_non_portable_schemas_are_rejected(bad_schema: dict, violation: str) -> None:
    """邊界：每一種 Bedrock 不支援的寫法都要在送出之前被擋下。

    最後一筆刻意把違規藏在陣列元素裡 —— 只檢查最上層是不夠的，實際的 schema 幾乎都有
    嵌套，而 Bedrock 是整份一起驗。

    斷言訊息裡有違規的關鍵字，這樣錯誤訊息才幫得上寫 schema 的人。
    """
    with pytest.raises(SchemaNotPortableError, match=re.escape(violation)):
        validate_portable_schema(bad_schema)


# ---------------------------------------------------------------------------
# 離線實作
# ---------------------------------------------------------------------------


def test_fake_returns_the_registered_payload() -> None:
    """正常路徑：登記過的任務回登記的內容，並記下收到的請求。"""
    model = FakeLanguageModel(
        responses={LlmTask.RESOLVE_LIFE_EVENT: {"event_id": "spouse_death"}}
    )

    result = model.generate_structured(_request())

    assert result.task is LlmTask.RESOLVE_LIFE_EVENT
    assert result.payload == {"event_id": "spouse_death"}
    assert result.finish_reason is FinishReason.STOP
    assert len(model.calls()) == 1


def test_fake_refuses_when_the_task_is_not_registered() -> None:
    """失敗情境：沒登記就拋錯，不編造答案。

    一個會「大概猜一下」的假實作，會讓測試在真實模型接上之前就通過，
    於是缺口被藏起來。
    """
    model = FakeLanguageModel()

    with pytest.raises(LanguageModelUnavailableError):
        model.generate_structured(_request())


def test_fake_still_enforces_schema_portability() -> None:
    """失敗情境：離線實作也要擋不可攜的 schema。

    如果假實作跳過這道檢查，可攜性規則就只對有金鑰的人生效 —— 而寫 schema 的人
    大多是在離線環境下寫的。
    """
    model = FakeLanguageModel(
        responses={LlmTask.RESOLVE_LIFE_EVENT: {"event_id": "spouse_death"}}
    )
    bad = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"name": {"type": "string", "maxLength": 5}},
    }

    with pytest.raises(SchemaNotPortableError):
        model.generate_structured(_request(bad))


def test_unavailable_model_always_fails() -> None:
    """失敗情境：一律失敗的實作讓「模型壞掉」這條路測得到。"""
    with pytest.raises(LanguageModelUnavailableError):
        UnavailableLanguageModel().generate_structured(_request())
