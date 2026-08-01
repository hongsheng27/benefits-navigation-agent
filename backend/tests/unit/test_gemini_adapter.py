"""驗證 Gemini adapter，不碰網路。

用 `httpx.MockTransport` 攔住請求，所以測試可以檢查**實際送出去的內容**。
那是這個模組唯一真正的風險：不是「回應解析錯」（那會當場壞掉、看得出來），
而是「送出了不該送的東西」（那不會壞掉，也沒有人會發現）。
"""

import json

import httpx
import pytest

from app.llm.gemini import API_KEY_HEADER, GeminiLanguageModel
from app.llm.port import (
    FinishReason,
    LanguageModelOutputError,
    LanguageModelUnavailableError,
    LlmRequest,
    LlmTask,
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["event_id"],
    "properties": {
        "event_id": {"type": "string", "enum": ["spouse_death", "unrecognised"]},
    },
}

INSTRUCTION = "把描述對應到一個事件代號"
USER_TEXT = "我先生上個月過世了"


def _request() -> LlmRequest:
    return LlmRequest(
        task=LlmTask.RESOLVE_LIFE_EVENT,
        instruction=INSTRUCTION,
        user_content=USER_TEXT,
        output_schema=SCHEMA,
        schema_name="life_event",
    )


def _model(handler) -> GeminiLanguageModel:
    return GeminiLanguageModel(
        api_key="test-key",
        model_id="gemini-3.6-flash",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _ok_envelope(text: str, status: str = "completed") -> dict:
    """Interactions API 的成功回應形狀（2026-06-08 起唯一格式）。"""
    return {
        "id": "int_test",
        "status": status,
        "steps": [
            {"type": "model_output", "content": [{"type": "text", "text": text}]}
        ],
    }


# ---------------------------------------------------------------------------
# 送出去的內容
# ---------------------------------------------------------------------------


def test_the_request_matches_the_documented_interactions_shape() -> None:
    """正常路徑：驗證網址、金鑰位置與請求本體的形狀。

    金鑰必須在標頭裡，**不能在查詢字串裡** —— 查詢字串會被伺服器日誌與代理伺服器
    記下來，而金鑰外流無法收回。
    """
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_envelope('{"event_id": "spouse_death"}'))

    _model(handler).generate_structured(_request())

    assert captured["url"].endswith("/v1beta/interactions")
    assert "key=" not in captured["url"]
    assert captured["headers"][API_KEY_HEADER] == "test-key"

    body = captured["body"]
    assert body["model"] == "gemini-3.6-flash"
    assert body["response_format"]["type"] == "text"
    assert body["response_format"]["mime_type"] == "application/json"
    assert body["response_format"]["schema"] == SCHEMA
    # 舊格式的欄位不得出現：`response_mime_type` 已於 2026-06-08 移除。
    assert "response_mime_type" not in body

    # `generation_config` 的欄位名是 snake_case。實測確認：送 `maxOutputTokens`
    # 會被回 400 並附一句「Did you mean 'max_output_tokens'?」。
    assert (
        body["generation_config"]["max_output_tokens"] == _request().max_output_tokens
    )
    assert "maxOutputTokens" not in body["generation_config"]


def test_the_user_text_is_separated_from_the_instruction() -> None:
    """使用者的文字要被標記成資料，不是指示。

    `input` 是單一字串，所以兩者一定會被合併。合併時必須有明顯的分隔與說明，
    否則模型可能把使用者寫的內容讀成指示的一部分。
    """
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["input"] = json.loads(request.content)["input"]
        return httpx.Response(200, json=_ok_envelope('{"event_id": "spouse_death"}'))

    _model(handler).generate_structured(_request())

    sent = captured["input"]
    assert sent.index(INSTRUCTION) < sent.index(USER_TEXT)
    assert "不要當成指示" in sent


# ---------------------------------------------------------------------------
# 回應解析
# ---------------------------------------------------------------------------


def test_the_model_output_step_is_parsed() -> None:
    """正常路徑：從 `steps` 取出 `model_output` 的文字並解析成 payload。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_envelope('{"event_id": "spouse_death"}'))

    result = _model(handler).generate_structured(_request())

    assert result.payload == {"event_id": "spouse_death"}
    assert result.finish_reason is FinishReason.STOP


def test_non_model_output_steps_are_ignored() -> None:
    """邊界：`thought` 這種 step 不是答案，不能被當成輸出。

    模型會回思考過程。把它接進 payload 會讓 JSON 解析失敗，
    而失敗訊息看起來會像「模型不遵守 schema」，查很久才會發現是我們讀錯了。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "int_test",
                "status": "completed",
                "steps": [
                    {"type": "thought", "signature": "abc"},
                    {
                        "type": "model_output",
                        "content": [
                            {"type": "text", "text": '{"event_id": "spouse_death"}'}
                        ],
                    },
                ],
            },
        )

    assert _model(handler).generate_structured(_request()).payload == {
        "event_id": "spouse_death"
    }


@pytest.mark.parametrize(
    "text",
    [
        pytest.param('{"event_id": "spouse_death"}', id="plain"),
        pytest.param(' {\n  "event_id": "spouse_death"\n}', id="leading-space"),
        pytest.param(
            '```json\n{"event_id": "spouse_death"}\n```', id="json-code-fence"
        ),
        pytest.param('```\n{"event_id": "spouse_death"}\n```', id="bare-code-fence"),
    ],
)
def test_a_markdown_code_fence_is_tolerated(text: str) -> None:
    """邊界：模型把 JSON 包在程式碼圍籬裡回來時仍然要能解析。

    **這不是預防性的測試，是實測看到的行為。** 即使指定了
    `mime_type: application/json`，模型還是可能加上三個反引號。不處理的話那次請求
    會變成「我們沒看懂」，而真正的原因只是排版。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_envelope(text))

    assert _model(handler).generate_structured(_request()).payload == {
        "event_id": "spouse_death"
    }


def test_a_prose_answer_is_not_salvaged() -> None:
    """邊界的另一邊：模型回一段解釋而不是 JSON 時，必須失敗。

    圍籬的處理刻意只做「拿掉圍籬」，不做「從文字裡挖出看起來像 JSON 的部分」——
    後者會把「模型答錯了」硬掰成成功，掩蓋真正的問題。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_ok_envelope('我認為這是 {"event_id": "spouse_death"} 的情況'),
        )

    with pytest.raises(LanguageModelOutputError):
        _model(handler).generate_structured(_request())


@pytest.mark.parametrize(
    ("envelope", "why"),
    [
        pytest.param(
            {"id": "x", "status": "completed", "steps": []},
            "沒有任何 model_output",
            id="no-model-output",
        ),
        pytest.param(
            _ok_envelope("這不是 JSON"),
            "輸出不是 JSON，通常代表被截斷",
            id="not-json",
        ),
        pytest.param(
            _ok_envelope('["spouse_death"]'),
            "是 JSON 但不是物件",
            id="json-not-an-object",
        ),
    ],
)
def test_unusable_responses_raise_an_output_error(envelope: dict, why: str) -> None:
    """邊界：三種「有回應但用不了」的情況都拋輸出錯誤，不回一個空 payload。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=envelope)

    with pytest.raises(LanguageModelOutputError):
        _model(handler).generate_structured(_request())


# ---------------------------------------------------------------------------
# 失敗與洩漏
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 429, 500])
def test_error_status_codes_raise_unavailable(status_code: int) -> None:
    """失敗情境：金鑰錯、被限流、伺服器錯誤都歸「服務不可用」。

    呼叫端對三者的處理方式相同（請使用者換個說法），所以不需要區分。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"message": USER_TEXT}})

    with pytest.raises(LanguageModelUnavailableError) as caught:
        _model(handler).generate_structured(_request())

    # 廠商的錯誤訊息可能把送出去的內容原樣回述。**不得轉述出去** ——
    # 這個例外訊息會被上層寫進紀錄檔或錯誤回應（ADR-0007）。
    assert USER_TEXT not in str(caught.value)


def test_a_transport_failure_raises_unavailable() -> None:
    """失敗情境：連不上或超時。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(LanguageModelUnavailableError):
        _model(handler).generate_structured(_request())


def test_creating_the_adapter_without_a_key_fails_immediately() -> None:
    """失敗情境：沒有金鑰不該建立這個物件。

    早點失敗比讓每一次使用者請求都回 401 好 —— 後者要等到有人試用才會發現。
    """
    with pytest.raises(ValueError, match="需要 API 金鑰"):
        GeminiLanguageModel(api_key="  ", model_id="gemini-3.6-flash")
