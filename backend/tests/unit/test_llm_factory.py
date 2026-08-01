"""驗證「有金鑰用真模型、沒金鑰用示範實作」的選擇。

這一組只有三個測試，但它守的是一個很容易壞的性質：**沒有金鑰不能是錯誤**。
一旦缺金鑰會讓後端啟動失敗，任何想看前端畫面的人都得先去申請一把金鑰。
"""

from app.config import Settings, get_settings
from app.llm.factory import build_language_model
from app.llm.gemini import GeminiLanguageModel
from app.llm.port import LlmTask


def test_a_missing_key_falls_back_instead_of_failing() -> None:
    """正常路徑（對隊友而言）：沒有金鑰就用示範實作，而且它真的會回答。"""
    model = build_language_model(Settings(gemini_api_key=""))

    assert not isinstance(model, GeminiLanguageModel)
    # 示範實作必須有登記事件辨識的答案，否則流程在第一步就停住。
    assert LlmTask.RESOLVE_LIFE_EVENT in {
        task for task in LlmTask if _answers(model, task)
    }


def test_a_whitespace_only_key_counts_as_missing() -> None:
    """邊界：`.env` 裡不小心留一個空白，不該變成每個請求都 401。"""
    model = build_language_model(Settings(gemini_api_key="   "))

    assert not isinstance(model, GeminiLanguageModel)


def test_a_present_key_selects_gemini() -> None:
    """正常路徑（對有金鑰的人而言）：有金鑰就用真的 adapter。"""
    model = build_language_model(
        Settings(gemini_api_key="test-key", gemini_model_id="gemini-3.6-flash")
    )

    assert isinstance(model, GeminiLanguageModel)


def test_the_test_suite_never_gets_a_live_model() -> None:
    """守住 `tests/conftest.py` 的那道保護。

    `get_settings()` 會讀本機 `.env`。在有金鑰的人的機器上，如果沒有那個 autouse
    fixture，整合測試會真的打網路 —— 我們實際撞到過：測試從 3 秒變成 46 秒且七個失敗。

    這個測試會在有人拿掉那道保護時失敗，**而且只會在有金鑰的機器上失敗**，
    所以它抓不到所有情況。但它是唯一能從測試裡表達這個約束的方式。
    """
    assert not get_settings().has_live_language_model()


def _answers(model: object, task: LlmTask) -> bool:
    """這個實作有沒有登記某個任務的答案。

    只用在上面那個斷言裡。直接讀 `calls()` 之類的內部狀態會讓測試綁死實作，
    所以用「呼叫它會不會成功」來判斷。
    """
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
