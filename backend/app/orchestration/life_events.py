"""生命事件登記表的讀取與驗證。

跟 `field_registry.py` 是同一個模式：這個模組只負責「讀一份 JSON、驗證格式、提供查詢」。
**有哪些事件不是這裡決定的** —— 那是政策資料，放在 `data/life_events/` 底下。

## 為什麼需要這份登記表

模型辨識事件時必須被限制在一個**封閉清單**內：ADR-0015 規定 schema 只能用 Bedrock
支援的 JSON Schema 子集，而那個子集裡表達「值只能是這幾個之一」的方式是 `enum`。
`enum` 需要一份明確的清單。

這帶來一個比隱私閘門更強的保證：**模型在結構上就無法回一個我們不認得的事件代號**，
因為它根本沒有那個選項。不是攔下來，是不存在。

## 為什麼不寫在程式裡

`orchestration/state.py` 對 `life_event` 有一條明確的原則：

> 刻意不用列舉：事件的集合是由 entitlement graph 擁有的 curated 資料，
> 寫死在這裡會把政策放進應用程式碼。

那條原則仍然成立。這份 JSON 是**資料**，由政策資料負責人維護，不是程式碼裡的列舉。

## 為什麼不放在 `EntitlementGraphRepository` 上

嚴格來說「有哪些事件」確實屬於 entitlement graph，加一個 `list_events()` 方法會更正確。
沒有那樣做的原因是時機：`orchestration/protocols.py` 正在被 `feat/databaseV3` 這個尚未
合併的分支大幅修改（約 +242 行），現在動同一個檔案會製造合併衝突。

**這是暫行安排。** 資料層之後若在 graph 契約上提供事件清單，這份 JSON 應該退場，
改由 repository 供應。屆時只有 `default_life_events()` 的呼叫端需要改。
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_EVENTS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "life_events" / "events.v0.1.json"
)


class LifeEventDefinition(BaseModel):
    """登記表裡一個生命事件的定義。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    description: str = Field(min_length=1)
    """給模型看的說明，用來判斷一段描述屬於哪個事件。

    **不是給使用者看的文案。** 畫面上的事件名稱由前端提供（後端給代號、前端給文字）。
    強制不能空白的理由是：沒有說明的話，模型只能從代號的英文字面猜，
    而 `spouse_death` 這種代號對「我先生上個月走了」的對應關係並不明顯。
    """

    status: str = "draft"  # draft 或 active

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, v: str) -> str:
        if not v.strip():
            msg = "description 不能是空白字串，否則模型只能從代號的字面猜。"
            raise ValueError(msg)
        return v


class LifeEventRegistry:
    """生命事件登記表的查詢介面。

    建立時讀取並驗證整份 JSON，格式錯誤在建立時就拋出。
    """

    def __init__(self, definitions: tuple[LifeEventDefinition, ...]) -> None:
        if not definitions:
            # 空的登記表會讓 schema 產出一個空的 enum，而空 enum 的意思是「沒有任何值
            # 合法」—— 模型必然失敗，卻不會有人知道原因是登記表是空的。
            msg = "生命事件登記表不能是空的，否則模型沒有任何合法選項可回。"
            raise ValueError(msg)
        self._by_id: dict[str, LifeEventDefinition] = {
            d.event_id: d for d in definitions
        }

    @classmethod
    def from_json(cls, path: Path = DEFAULT_EVENTS_PATH) -> "LifeEventRegistry":
        """從 JSON 檔案建立。格式錯誤會在這裡拋出。"""
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        definitions = tuple(
            LifeEventDefinition.model_validate(entry) for entry in raw["events"]
        )
        return cls(definitions)

    def has(self, event_id: str) -> bool:
        """這個代號在不在登記表上。"""
        return event_id in self._by_id

    def all_event_ids(self) -> tuple[str, ...]:
        """所有事件代號，依登記順序。

        回 tuple 而不是 set：這個順序會直接變成 schema 裡 `enum` 的順序，
        而 set 的順序不保證固定 —— 那會讓同一份登記表產出不同的 schema，
        使得請求內容無法重現，也讓測試變得脆弱。
        """
        return tuple(self._by_id.keys())

    def definitions(self) -> tuple[LifeEventDefinition, ...]:
        """所有定義，依登記順序。"""
        return tuple(self._by_id.values())

    def count(self) -> int:
        """登記的事件總數。"""
        return len(self._by_id)


_REGISTRY_CACHE: LifeEventRegistry | None = None
_REGISTRY_CACHE_MTIME_NS: int | None = None


def default_life_events() -> LifeEventRegistry:
    """取得共用的事件登記表實例。

    lazy 初始化並快取，與 `state_machine.default_registry()` 同一個作法：
    `from_json` 會讀磁碟，放在 import 時執行會讓「匯入這個模組」變成一件可能失敗的事。

    JSON 在 `backend/` 目錄外，uvicorn --reload 不一定會重載此模組；因此比對檔案
    mtime，變更後下次請求會重新讀取，避免改了 description 卻一直用舊快取。
    """
    global _REGISTRY_CACHE, _REGISTRY_CACHE_MTIME_NS
    path = DEFAULT_EVENTS_PATH
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        mtime_ns = None

    if (
        _REGISTRY_CACHE is None
        or mtime_ns is None
        or mtime_ns != _REGISTRY_CACHE_MTIME_NS
    ):
        _REGISTRY_CACHE = LifeEventRegistry.from_json(path)
        _REGISTRY_CACHE_MTIME_NS = mtime_ns
    return _REGISTRY_CACHE
