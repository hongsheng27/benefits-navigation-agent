"""驗證「Bedrock → Gemini → 示範」的選擇順序。

這一組測試守的是：沒有憑證不能是錯誤，而且 Bedrock 設定時優先於 Gemini。
"""

from app.config import Settings, get_settings
from app.llm.bedrock import BedrockLanguageModel
from app.llm.factory import build_language_model
from app.llm.gemini import GeminiLanguageModel
from app.llm.port import LlmTask


def test_a_missing_provider_falls_back_instead_of_failing() -> None:
    """正常路徑（對隊友而言）：沒有模型設定就用示範實作。"""
    model = build_language_model(Settings(bedrock_model_id="", gemini_api_key=""))

    assert not isinstance(model, BedrockLanguageModel)
    assert not isinstance(model, GeminiLanguageModel)
    assert LlmTask.RESOLVE_LIFE_EVENT in {
        task for task in LlmTask if _answers(model, task)
    }


def test_a_whitespace_only_bedrock_id_counts_as_missing() -> None:
    model = build_language_model(Settings(bedrock_model_id="   ", gemini_api_key=""))

    assert not isinstance(model, BedrockLanguageModel)


def test_bedrock_is_preferred_over_gemini() -> None:
    model = build_language_model(
        Settings(
            bedrock_model_id="anthropic.claude-3-haiku-20240307-v1:0",
            gemini_api_key="test-key",
            gemini_model_id="gemini-3.6-flash",
        )
    )

    assert isinstance(model, BedrockLanguageModel)


def test_a_present_gemini_key_selects_gemini_when_bedrock_is_absent() -> None:
    model = build_language_model(
        Settings(
            bedrock_model_id="",
            gemini_api_key="test-key",
            gemini_model_id="gemini-3.6-flash",
        )
    )

    assert isinstance(model, GeminiLanguageModel)


def test_the_test_suite_never_gets_a_live_model() -> None:
    """守住 `tests/conftest.py` 的那道保護。"""
    assert not get_settings().has_live_language_model()


def _answers(model: object, task: LlmTask) -> bool:
    from app.llm.port import LanguageModelError, LlmRequest

    request = LlmRequest(
        task=task,
        instruction="測試",
        user_content="測試",
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
        schema_name="probe",
    )
    try:
        model.generate_structured(request)  # type: ignore[attr-defined]
    except LanguageModelError:
        return False
    return True
