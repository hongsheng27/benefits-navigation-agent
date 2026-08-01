"""對話式屬性抽取。"""

from app.llm.fake import FakeLanguageModel
from app.llm.port import LlmTask
from app.llm.tasks.collect_attributes import (
    collect_attributes_from_reply,
    heuristic_extract,
)
from app.orchestration.field_registry import FieldRegistry


def test_heuristic_extracts_jurisdiction() -> None:
    registry = FieldRegistry.from_json()
    field = registry.get("applicant_jurisdiction")
    assert field is not None
    found = heuristic_extract("我住台北", (field,))
    assert found == {"applicant_jurisdiction": "TPE"}


def test_model_extracts_one_field() -> None:
    registry = FieldRegistry.from_json()
    field = registry.get("applicant_jurisdiction")
    assert field is not None
    model = FakeLanguageModel(
        responses={
            LlmTask.COLLECT_ATTRIBUTES: {
                "field_id": "applicant_jurisdiction",
                "value": "NWT",
                "confident": True,
                "next_question": "過世者有勞保嗎？",
            }
        }
    )
    result = collect_attributes_from_reply(
        "新北",
        fields=(field,),
        model=model,
        registry=registry,
    )
    assert result.attributes["applicant_jurisdiction"] == "NWT"
