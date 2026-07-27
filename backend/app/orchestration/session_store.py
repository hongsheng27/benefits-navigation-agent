"""Session 的建立、讀取與過期。

這個模組只負責「一份 workflow state 存在哪裡、活多久」。狀態怎麼變是
`state_machine.py` 的事，這裡不做任何流程判斷。

## 為什麼存在記憶體

MVP 只需要撐過現場操作。行程重啟就全部消失，這在隱私上是優點而不是缺點 ——
沒有留下來的東西不需要刪除政策。正式的持久化方案（DynamoDB、AgentCore Memory
或其他）仍是未決事項，見 ADR-0005。

因為存在記憶體，這個 store **不適用於多個行程**。若之後部署成多個實例，同一個
`session_id` 可能落到沒有它的行程上。換掉時只要維持這個類別的方法簽名即可。

遷移步驟、必須保留的行為與需要填入的環境變數，一律記在
[`docs/aws_migration_guide.md`](../../../docs/aws_migration_guide.md) 的
Session Persistence 一節。那份指南是遷移說明的唯一來源，這裡不重複。

## session_id 是憑證，不只是識別碼

`session_id` 同時扮演「是誰」與「證明是本人」兩個角色 —— 誰拿到就能讀到那份
state。這在安全上稱為 bearer token（持有即通行）。因此：

- 用 `secrets.token_urlsafe` 產生，不用流水號、不用時間戳、不用 `uuid1`。
  那些可以被推測。
- 走 HTTP header，不走網址路徑。放在網址會被瀏覽記錄、referrer 與伺服器日誌
  帶走。
- 搭配短保存期限，降低外洩後的可用時間。

即使後端存的是去識別化資料，「配偶過世 + 有未成年子女」這種組合本身仍然敏感。
"""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.orchestration.state import SessionState

# 保存時間。畫面上會告知使用者「進度保留 2 小時」，兩邊必須一致。
SESSION_TTL = timedelta(hours=2)

# 產生 session_id 的隨機位元組數。32 位元組約等於 43 個字元，遠超過可暴力猜測的
# 範圍。
SESSION_ID_BYTES = 32

# 傳遞 session_id 的 header 名稱。
SESSION_ID_HEADER = "X-Session-Id"

type Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SessionNotFoundError(LookupError):
    """沒有這個 session_id。

    與過期分開，因為前端的處置不同：找不到通常代表本機存的 id 已經無效，
    應該清掉重新開始。
    """


class SessionExpiredError(LookupError):
    """session 存在過，但已超過保存時間。

    與找不到分開，因為這個情況可以明確告知使用者「進度已過期」，而不是含糊的
    錯誤訊息。
    """


class InMemorySessionStore:
    """把 workflow state 存在行程記憶體裡。

    `clock` 可注入，讓測試不需要真的等兩小時就能驗證過期行為。
    """

    def __init__(self, clock: Clock = _utc_now) -> None:
        self._clock = clock
        self._states: dict[str, SessionState] = {}

    def create(self) -> SessionState:
        """建立一份新的 session state。

        `session_id` 與身分無關，只是隨機值。
        """
        now = self._clock()
        state = SessionState(
            session_id=secrets.token_urlsafe(SESSION_ID_BYTES),
            created_at=now,
            updated_at=now,
            expires_at=now + SESSION_TTL,
        )
        self._states[state.session_id] = state
        return state

    def get(self, session_id: str) -> SessionState:
        """取出一份 state。

        過期的 state 會在這裡直接刪除，而不是留著等排程清理。理由是保存期限是對
        使用者的承諾，讀取時就應該兌現。
        """
        state = self._states.get(session_id)
        if state is None:
            raise SessionNotFoundError

        if self._clock() >= state.expires_at:
            del self._states[session_id]
            raise SessionExpiredError

        return state

    def save(self, state: SessionState) -> SessionState:
        """寫回一份更新後的 state，並更新 `updated_at`。

        `SessionState` 是 frozen，所以呼叫端傳進來的一定是新物件；這裡只負責替換
        以及蓋上時間。過期時間不因為活動而延長 —— 保存上限是從建立時算起。
        """
        if state.session_id not in self._states:
            raise SessionNotFoundError

        stamped = state.model_copy(update={"updated_at": self._clock()})
        self._states[state.session_id] = stamped
        return stamped

    def delete(self, session_id: str) -> None:
        """立刻刪除。

        對應使用者選「現在就清除」。已經不存在時不視為錯誤，因為呼叫端的目的是
        「確保它不在了」。
        """
        self._states.pop(session_id, None)

    def purge_expired(self) -> int:
        """刪除所有已過期的 state，回傳刪掉幾筆。

        `get` 已經會處理過期，這個方法是為了讓沒有人再來讀的 session 也不會一直
        佔著記憶體。
        """
        now = self._clock()
        expired = [
            session_id
            for session_id, state in self._states.items()
            if now >= state.expires_at
        ]
        for session_id in expired:
            del self._states[session_id]
        return len(expired)

    def count(self) -> int:
        """目前保存的 session 數量。僅供測試與健康檢查使用。"""
        return len(self._states)
