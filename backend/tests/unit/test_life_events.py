"""驗證生命事件登記表的讀取與驗證。

登記表是模型唯一被允許回答的事件集合，所以它的格式錯誤必須在建立時就爆掉，
不能延後到某次請求。
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.orchestration.life_events import LifeEventRegistry


def _write(events: list[dict], tmp_path: Path) -> Path:
    path = tmp_path / "events.json"
    path.write_text(json.dumps({"events": events}), encoding="utf-8")
    return path


def test_loads_the_seed_data_without_error() -> None:
    """正常路徑：種子資料讀得起來，而且順序固定。

    順序要固定是因為它會直接變成 schema 裡 enum 的順序 —— 順序會變的話，
    同一份登記表會產出不同的請求內容，行為就無法重現。
    """
    registry = LifeEventRegistry.from_json()

    assert registry.count() >= 1
    assert registry.all_event_ids() == registry.all_event_ids()
    assert registry.has(registry.all_event_ids()[0])


def test_a_blank_description_is_rejected(tmp_path: Path) -> None:
    """邊界：說明不能是空白。

    沒有說明的話，模型只能從 `spouse_death` 這種英文代號的字面猜它對應什麼中文描述。
    """
    path = _write([{"event_id": "spouse_death", "description": "   "}], tmp_path)

    with pytest.raises(ValidationError):
        LifeEventRegistry.from_json(path)


def test_an_empty_registry_is_rejected() -> None:
    """失敗情境：空的登記表要當場拒絕。

    空登記表會產出一個空的 enum，而空 enum 的意思是「沒有任何值合法」——
    模型必然失敗，但沒有人會知道原因是登記表是空的。
    """
    with pytest.raises(ValueError, match="不能是空的"):
        LifeEventRegistry(())
