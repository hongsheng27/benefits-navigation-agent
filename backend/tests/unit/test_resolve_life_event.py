"""驗證事件辨識：可多選、看不懂不准猜、原文不外流。"""

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
            LifeEventDefinition(event_id="job_loss", description="失業"),
            LifeEventDefinition(event_id="occupational_injury", description="職災"),
        )
    )


def _model(event_ids: str | list[str]) -> FakeLanguageModel:
    payload = (
        {"event_ids": event_ids}
        if isinstance(event_ids, list)
        else {"event_ids": [event_ids]}
    )
    return FakeLanguageModel(responses={LlmTask.RESOLVE_LIFE_EVENT: payload})


def test_schema_limits_items_to_registered_events_plus_unrecognised() -> None:
    schema = build_schema(_registry())
    assert schema["properties"]["event_ids"]["minItems"] == 1
    assert "maxItems" not in schema["properties"]["event_ids"]
    assert schema["properties"]["event_ids"]["items"]["enum"] == [
        "spouse_death",
        "parent_death",
        "job_loss",
        "occupational_injury",
        UNRECOGNISED,
    ]
    validate_portable_schema(schema)


def test_instruction_lists_the_descriptions_not_just_the_codes() -> None:
    instruction = build_instruction(_registry())
    assert "spouse_death" in instruction
    assert "配偶過世" in instruction
    assert "最多 5" in instruction


def test_a_registered_event_is_returned() -> None:
    assert resolve_life_event(
        TEXT, model=_model("spouse_death"), registry=_registry()
    ) == ("spouse_death",)


def test_multiple_registered_events_are_returned() -> None:
    assert resolve_life_event(
        "爸爸職災，我失業",
        model=_model(["occupational_injury", "job_loss"]),
        registry=_registry(),
    ) == ("occupational_injury", "job_loss")


def test_legacy_single_event_id_payload_still_works() -> None:
    model = FakeLanguageModel(
        responses={LlmTask.RESOLVE_LIFE_EVENT: {"event_id": "spouse_death"}}
    )
    assert resolve_life_event(TEXT, model=model, registry=_registry()) == (
        "spouse_death",
    )


@pytest.mark.parametrize(
    ("event_ids", "why"),
    [
        pytest.param(
            [UNRECOGNISED], "模型誠實說判斷不出來", id="model-says-unrecognised"
        ),
        pytest.param(
            ["volcano_eruption"], "代號不在登記表上", id="unregistered-code"
        ),
        pytest.param([""], "空字串不是有效代號", id="empty-string"),
    ],
)
def test_anything_but_a_registered_event_raises(
    event_ids: list[str], why: str
) -> None:
    del why
    with pytest.raises(LifeEventNotRecognisedError):
        resolve_life_event(TEXT, model=_model(event_ids), registry=_registry())


def test_an_unavailable_model_also_raises_not_recognised() -> None:
    with pytest.raises(LifeEventNotRecognisedError):
        resolve_life_event(
            TEXT, model=UnavailableLanguageModel(), registry=_registry()
        )


def test_keyword_fallback_covers_clear_short_phrases_when_model_fails() -> None:
    registry = LifeEventRegistry(
        (
            LifeEventDefinition(event_id="job_loss", description="失業"),
            LifeEventDefinition(event_id="spouse_death", description="配偶過世"),
        )
    )
    assert resolve_life_event(
        "我失業了",
        model=UnavailableLanguageModel(),
        registry=registry,
    ) == ("job_loss",)


def test_keyword_fallback_can_return_multiple_events() -> None:
    registry = _registry()
    # 備援表先掃到「失業」再掃到「職災」，順序依表而非句中出現順序。
    assert resolve_life_event(
        "爸爸職災，我失業了",
        model=UnavailableLanguageModel(),
        registry=registry,
    ) == ("job_loss", "occupational_injury")


def test_the_text_goes_to_the_model_but_not_into_the_instruction() -> None:
    model = _model("spouse_death")
    resolve_life_event(TEXT, model=model, registry=_registry())
    request = model.calls()[0]
    assert request.user_content == TEXT
    assert TEXT not in request.instruction


def test_no_log_entry_contains_the_text(caplog: pytest.LogCaptureFixture) -> None:
    configure_logging()
    secret = "這段文字不應該進紀錄檔"
    registry = _registry()

    with caplog.at_level(logging.INFO):
        resolve_life_event(secret, model=_model("spouse_death"), registry=registry)
        with pytest.raises(LifeEventNotRecognisedError):
            resolve_life_event(
                secret, model=_model([UNRECOGNISED]), registry=registry
            )
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
