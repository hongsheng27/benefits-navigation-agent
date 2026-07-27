"""驗證 session 的建立、過期與清除。

時間由可注入的 clock 控制，所以測試不需要真的等兩小時。
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.orchestration.session_store import (
    SESSION_ID_BYTES,
    SESSION_TTL,
    InMemorySessionStore,
    SessionExpiredError,
    SessionNotFoundError,
)
from app.orchestration.state import WorkflowState

_START = datetime(2026, 7, 26, 15, 30, tzinfo=UTC)


class FakeClock:
    """可以手動往前推的時鐘。"""

    def __init__(self, now: datetime = _START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def test_a_new_session_starts_at_the_first_state() -> None:
    store = InMemorySessionStore(clock=FakeClock())

    state = store.create()

    assert state.workflow_state is WorkflowState.UNDERSTAND_EVENT
    assert state.created_at == _START
    assert state.expires_at == _START + SESSION_TTL
    assert store.count() == 1


def test_session_ids_are_unguessable_and_unique() -> None:
    store = InMemorySessionStore(clock=FakeClock())

    ids = {store.create().session_id for _ in range(50)}

    assert len(ids) == 50
    # token_urlsafe 的輸出比位元組數長，所以只檢查下界，不寫死字元數。
    assert all(len(session_id) >= SESSION_ID_BYTES for session_id in ids)


def test_an_unknown_session_is_not_found() -> None:
    store = InMemorySessionStore(clock=FakeClock())

    with pytest.raises(SessionNotFoundError):
        store.get("does-not-exist")


def test_a_session_survives_until_the_ttl() -> None:
    clock = FakeClock()
    store = InMemorySessionStore(clock=clock)
    state = store.create()

    clock.advance(SESSION_TTL - timedelta(seconds=1))

    assert store.get(state.session_id).session_id == state.session_id


def test_an_expired_session_is_reported_and_removed() -> None:
    """過期在讀取時就兌現，不等排程清理。"""
    clock = FakeClock()
    store = InMemorySessionStore(clock=clock)
    state = store.create()

    clock.advance(SESSION_TTL)

    with pytest.raises(SessionExpiredError):
        store.get(state.session_id)

    assert store.count() == 0


def test_activity_does_not_extend_the_expiry() -> None:
    """保存上限從建立時算起，不因為使用者還在操作而延長。"""
    clock = FakeClock()
    store = InMemorySessionStore(clock=clock)
    state = store.create()

    clock.advance(timedelta(hours=1))
    saved = store.save(state)

    assert saved.expires_at == _START + SESSION_TTL
    assert saved.updated_at == _START + timedelta(hours=1)


def test_saving_an_unknown_session_fails() -> None:
    clock = FakeClock()
    store = InMemorySessionStore(clock=clock)
    state = store.create()
    store.delete(state.session_id)

    with pytest.raises(SessionNotFoundError):
        store.save(state)


def test_delete_is_idempotent() -> None:
    """呼叫端的目的是「確保它不在了」，所以重複刪除不算錯誤。"""
    store = InMemorySessionStore(clock=FakeClock())
    state = store.create()

    store.delete(state.session_id)
    store.delete(state.session_id)

    assert store.count() == 0


def test_purge_removes_only_expired_sessions() -> None:
    clock = FakeClock()
    store = InMemorySessionStore(clock=clock)
    old = store.create()

    clock.advance(SESSION_TTL)
    fresh = store.create()

    removed = store.purge_expired()

    assert removed == 1
    assert store.count() == 1
    assert store.get(fresh.session_id).session_id == fresh.session_id
    with pytest.raises(SessionNotFoundError):
        store.get(old.session_id)
