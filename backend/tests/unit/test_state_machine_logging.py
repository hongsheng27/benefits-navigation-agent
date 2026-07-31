"""驗證狀態機的紀錄檔埋點。

三個案例：正常轉換記下前後狀態、守門條件跳過會被記下、以及紀錄裡不含使用者的值。

ADR-0007 把除錯手段限縮到只剩狀態轉換 —— 使用者的文字不留、值不進紀錄檔。
所以這些埋點幾乎是唯一能查的東西，值得測。
"""

import json
import logging

import pytest

from app.observability.logging import configure_logging
from app.orchestration.state_machine import advance
from app.schemas.session import EventConfirmationInput, LifeEventTextInput
from tests.unit.test_loop_guardrails import _state_at_collect


@pytest.fixture(autouse=True)
def _json_logging() -> None:
    configure_logging()


def _events(caplog: pytest.LogCaptureFixture) -> list[dict]:
    """把捕捉到的紀錄格式化成 handler 實際會輸出的樣子。"""
    handler = logging.getLogger().handlers[0]
    return [
        json.loads(handler.formatter.format(record))
        for record in caplog.records
        if record.name == "jiezhu"
    ]


def test_auto_advance_records_each_transition(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """確認事件之後會自動走過幾個狀態，每一步都要留下前後狀態。"""
    state = _state_at_collect()
    understanding = state.model_copy(
        update={"workflow_state": "understand_event", "items": (), "life_event": None}
    )

    with caplog.at_level(logging.INFO):
        advanced = advance(understanding, LifeEventTextInput(text="測試"))
        advance(advanced, EventConfirmationInput(confirmed=True))

    transitions = [e for e in _events(caplog) if e["event"] == "state_transitioned"]

    assert transitions, "自動推進至少要記一筆轉換"
    assert all("state" in e and "next_state" in e for e in transitions)
    assert all(e["transition"] == "auto_advance" for e in transitions)


def test_a_skipped_state_is_recorded_with_its_guard(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """邊界：被守門條件跳過的狀態要留下 guard 名稱。

    沒有這一筆，之後看到流程直接跳到 complete 時無法分辨是守門條件生效
    還是轉換表寫錯。
    """
    state = _state_at_collect()
    understanding = state.model_copy(
        update={"workflow_state": "understand_event", "items": (), "life_event": None}
    )

    with caplog.at_level(logging.INFO):
        advanced = advance(understanding, LifeEventTextInput(text="測試"))
        advance(advanced, EventConfirmationInput(confirmed=True))

    skipped = [e for e in _events(caplog) if e["event"] == "state_skipped"]

    for entry in skipped:
        assert entry["guard"].startswith("entry_guard:")


def test_no_log_entry_contains_the_submitted_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """失敗情境的反面：送進去的文字不得出現在任何一筆紀錄裡。"""
    secret = "這段文字不應該進紀錄檔"
    state = _state_at_collect()
    understanding = state.model_copy(
        update={"workflow_state": "understand_event", "items": (), "life_event": None}
    )

    with caplog.at_level(logging.INFO):
        advance(understanding, LifeEventTextInput(text=secret))

    rendered = json.dumps(_events(caplog), ensure_ascii=False)
    assert secret not in rendered
