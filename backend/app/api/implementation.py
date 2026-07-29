"""回應裡「哪些能力還沒實作」的宣告。

每個 session 回應都帶一個 `ImplementationNotice`，讓前端可以在畫面上標示哪些內容
是佔位資料。實作完成一項就從 `PENDING_CAPABILITIES` 移除，前端不需要改程式，
畫面上的警示會自動變少。

## 這整個模組會被刪除

當 `PENDING_CAPABILITIES` 變成空的、`is_mock` 變成 False 時，這個模組與
`ImplementationNotice` 一起從契約移除。`placeholder_notice` 是唯一由後端提供中文
文案的欄位，違反本專案「後端給代號、前端給文案」的分界 —— 那是刻意的臨時例外，
它的讀者是開發者與 demo 觀眾，不是真正的使用者。
"""

from app.schemas.session import ImplementationNotice, PendingCapability

PLACEHOLDER_NOTICE = "（部分資料為後端佔位內容，尚未進行真實的事件辨識與資格判定）"

# 尚未實作、或仍是佔位版本的能力。
#
# 已經移除的：
# - STATE_MACHINE：確定性狀態機已完成（ADR-0012）
# - FIELD_REGISTRY：欄位登記表機制已完成，但內容仍是 draft 種子資料
PENDING_CAPABILITIES: tuple[PendingCapability, ...] = (
    # 事件辨識仍寫死回 spouse_death，沒有呼叫任何模型。
    PendingCapability.LIFE_EVENT_EXTRACTION,
    # 候選項目仍是寫死的四筆，不是從 entitlement graph 查的。那四筆的資料治理狀態是
    # candidate，所以離線流程一律回「需人工協助」，不會產出 eligible。
    PendingCapability.ENTITLEMENT_GRAPH,
    # 資料治理狀態的安全閘門已經實作，但還沒有任何已核准的規則可以判定，所以注入的
    # 判定服務對每一項都回「需人工協助」。
    PendingCapability.RULE_EVALUATION,
    # 檢索仍是空操作。
    PendingCapability.OFFICIAL_CITATIONS,
    # 白話說明仍是空操作。
    PendingCapability.PLAIN_LANGUAGE_EXPLANATION,
    # 辦理清單尚未組裝。
    PendingCapability.ACTION_PLAN,
    # 屬性 allowlist 驗證與原文丟棄的行為尚未實作。
    PendingCapability.PRIVACY_GATE,
)


def implementation_notice() -> ImplementationNotice:
    """描述這份回應有多少是真的。"""
    return ImplementationNotice(
        is_mock=True,
        pending=PENDING_CAPABILITIES,
        placeholder_notice=PLACEHOLDER_NOTICE,
    )
