"""驗證事件辨識，重點在「看不懂的時候不准猜」以及「原文不外流」。

這兩件事比「辨識正確」重要。辨識錯了使用者會發現；原文外流他不會發現。
"""

import json
import logging

import pytest

from app.llm.fake import FakeLanguageModel, UnavailableLanguageModel
from app.llm.port import LlmTask, validate_portable_schema
from app.llm.tasks.resolve_life_event import (
    UNRECOGNISED,
    LifeEventNotRecognisedError,
    build_instruction,
    build_schema,
    resolve_life_event,
)
from app.observability.logging import configure_logging
from app.orchestration.life_events import LifeEventDefinition, LifeEventRegistry

TEXT = "我先生上個月過世了"


def _registry() -> LifeEventRegistry:
    return LifeEventRegistry(
        (
            LifeEventDefinition(event_id="spouse_death", description="配偶過世"),
            LifeEventDefinition(event_id="parent_death", description="父母過世"),
        )
    )


def _model(event_id: str) -> FakeLanguageModel:
    return FakeLanguageModel(
        responses={LlmTask.RESOLVE_LIFE_EVENT: {"event_id": event_id}}
    )


# ---------------------------------------------------------------------------
# schema 與指示
# ---------------------------------------------------------------------------


def test_schema_limits_the_model_to_registered_events_plus_unrecognised() -> None:
    """正常路徑：enum 只有登記表上的代號加上 unrecognised。

    這是比隱私閘門更強的保證 —— 模型不是被攔下來，是根本沒有別的選項可選。
    """
    schema = build_schema(_registry())

    assert schema["properties"]["event_id"]["enum"] == [
        "spouse_death",
        "parent_death",
        UNRECOGNISED,
    ]
    # 產出的 schema 必須自己也是可攜的，否則換 Bedrock 那天才會發現。
    validate_portable_schema(schema)


def test_instruction_lists_the_descriptions_not_just_the_codes() -> None:
    """指示裡要有中文說明。

    只給 `spouse_death` 這種英文代號，模型得自己猜它跟「我先生走了」的關係。
    說明取自登記表，所以新增事件只要改 JSON。
    """
    instruction = build_instruction(_registry())

    assert "spouse_death" in instruction
    assert "配偶過世" in instruction


# ---------------------------------------------------------------------------
# 辨識結果
# ---------------------------------------------------------------------------


def test_a_registered_event_is_returned() -> None:
    """正常路徑：模型回登記表上的代號時原樣回傳。"""
    assert (
        resolve_life_event(TEXT, model=_model("spouse_death"), registry=_registry())
        == "spouse_death"
    )


@pytest.mark.parametrize(
    ("event_id", "why"),
    [
        pytest.param(
            UNRECOGNISED, "模型誠實說判斷不出來", id="model-says-unrecognised"
        ),
        pytest.param("volcano_eruption", "代號不在登記表上", id="unregistered-code"),
        pytest.param("", "空字串不是有效代號", id="empty-string"),
    ],
)
def test_anything_but_a_registered_event_raises(event_id: str, why: str) -> None:
    """邊界：三種「沒有有效答案」的情況都拋錯，不回一個湊出來的代號。

    第二種特別值得測：schema 的 enum 理論上已經擋住了，但廠商是否遵守 schema 是它的
    承諾而不是我們的保證。這裡驗證我們有再查一次。
    """
    with pytest.raises(LifeEventNotRecognisedError):
        resolve_life_event(TEXT, model=_model(event_id), registry=_registry())


def test_an_unavailable_model_also_raises_not_recognised() -> None:
    """失敗情境：模型服務壞掉時走同一條路。

    刻意不分「我們的模型壞了」和「你的描述我們不懂」—— 對使用者而言下一步都一樣，
    而區分只對我們有意義，記在紀錄檔就好。
    """
    with pytest.raises(LifeEventNotRecognisedError):
        resolve_life_event(TEXT, model=UnavailableLanguageModel(), registry=_registry())


# ---------------------------------------------------------------------------
# 原文不外流
# ---------------------------------------------------------------------------


def test_the_text_goes_to_the_model_but_not_into_the_instruction() -> None:
    """原文只能放在 `user_content`，不得被組進 `instruction`。

    這個界線重要是因為 `instruction` 是「我們寫的、可以記錄的」那一半。
    一旦有人為了方便把使用者的話拼進指示，那個區分就失效了。
    """
    model = _model("spouse_death")

    resolve_life_event(TEXT, model=model, registry=_registry())

    request = model.calls()[0]
    assert request.user_content == TEXT
    assert TEXT not in request.instruction


def test_no_log_entry_contains_the_text(caplog: pytest.LogCaptureFixture) -> None:
    """失敗情境的反面：三條路徑都不得把原文寫進紀錄檔。

    成功、模型說看不懂、模型壞掉，三種都跑一次 —— 失敗路徑往往是漏掉的那一條，
    因為那裡的程式碼在處理例外，最容易順手把輸入寫進訊息裡。
    """
    configure_logging()
    secret = "這段文字不應該進紀錄檔"
    registry = _registry()

    with caplog.at_level(logging.INFO):
        resolve_life_event(secret, model=_model("spouse_death"), registry=registry)
        with pytest.raises(LifeEventNotRecognisedError):
            resolve_life_event(secret, model=_model(UNRECOGNISED), registry=registry)
        with pytest.raises(LifeEventNotRecognisedError):
            resolve_life_event(
                secret, model=UnavailableLanguageModel(), registry=registry
            )

    handler = logging.getLogger().handlers[0]
    rendered = json.dumps(
        [
            json.loads(handler.formatter.format(record))
            for record in caplog.records
            if record.name == "jiezhu"
        ],
        ensure_ascii=False,
    )

    assert secret not in rendered
