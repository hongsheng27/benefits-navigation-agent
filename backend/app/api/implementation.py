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
    # 設定 Bedrock 時會呼叫模型；未設定時仍使用可重現的離線示範。
    PendingCapability.LIFE_EVENT_EXTRACTION,
    # Entitlement graph 已接上 database repository，但目前只有配偶過世與 Case 2 有完整
    # seed／流程覆蓋，其餘事件仍沒有足夠的 curated programs。
    PendingCapability.ENTITLEMENT_GRAPH,
    # 資料治理狀態的安全閘門已經實作，但還沒有任何已核准的規則可以判定，所以注入的
    # 判定服務對每一項都回「需人工協助」。
    PendingCapability.RULE_EVALUATION,
    # 候選官方摘錄已可顯示，但尚無足以支撐 eligibility 的人工核對 citations。
    PendingCapability.OFFICIAL_CITATIONS,
    # 白話說明仍是空操作。
    PendingCapability.PLAIN_LANGUAGE_EXPLANATION,
    # 辦理清單尚未組裝。
    PendingCapability.ACTION_PLAN,
)

# 已經移除的（續）：
# - PRIVACY_GATE：三個部分都完成了。未登記的欄位代號會讓整筆請求被拒
#   （`unknown_field`）、值本身依登記表的型別與選項驗證（`invalid_field_value`）、
#   而自由文字現在真的被丟棄 —— `resolve_life_event` 只回事件代號清單，原文沒有任何
#   路徑進到 state、紀錄檔或回應裡。


def implementation_notice() -> ImplementationNotice:
    """描述這份回應有多少是真的。"""
    return ImplementationNotice(
        is_mock=True,
        pending=PENDING_CAPABILITIES,
        placeholder_notice=PLACEHOLDER_NOTICE,
    )
