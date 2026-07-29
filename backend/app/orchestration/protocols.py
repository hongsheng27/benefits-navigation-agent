"""狀態機與外部世界之間的接縫（seams）。

這個模組只定義**形狀**：狀態機需要從外面拿到什麼、用什麼方法拿。真正去讀
entitlement graph、SQLite 規則表或官方文件的程式碼不在這裡。

## 為什麼要先定形狀

Phase 2 的資料來源全部是寫死的 fixture，Phase 4/5 才會換成真的。如果狀態機直接
讀模組層常數或自己開 SQLite 連線，替換的時候就得改狀態機本身 —— 而狀態機是整條
流程的權威，每次改動都要重新驗證所有轉換。

把依賴倒過來（狀態機宣告它要什麼，呼叫端決定給什麼）之後，Phase 4 只要傳入另一個
實作，狀態機一行都不用改（Req 19.3）。

## 為什麼用 Protocol 而不是抽象基底類別

`Protocol` 是結構型別：只要方法簽章對得上就算實作，不需要繼承。這讓測試可以直接
用幾行的假物件，也讓未來的實作不必為了滿足型別而 import 這個模組。

## 目前有哪些實作

| 接縫 | Phase 2 實作 | 之後 |
| --- | --- | --- |
| `EntitlementSource` | `FixtureEntitlementSource` | entitlement graph（T15） |
| `RuleSource` | 無，還沒接規則資料 | SQLite 規則表（T18） |
| `EvidenceRetriever` | 無，檢索目前是空操作 | 官方依據檢索（T15+） |
| `PrivacyGate` | `PassThroughPrivacyGate` | 值的型別與選項驗證（T11） |
"""

from typing import Any, Protocol

from app.orchestration.state import (
    AttributeValue,
    CandidateItem,
    Citation,
    ItemKind,
)


class EntitlementSource(Protocol):
    """人生事件 → 可能相關的候選項目。"""

    def resolve(self, life_event: str) -> tuple[CandidateItem, ...]:
        """展開某個事件對應的候選項目。

        認不出事件時回空 tuple，而不是猜一組項目 —— 猜錯會讓使用者白跑一趟。
        """
        ...


class RuleSource(Protocol):
    """項目代號 → 該項目的規則欄位。"""

    def load_rules(self, program_id: str) -> dict[str, Any]:
        """取出一個項目的規則欄位。找不到時回空 dict。

        回傳形狀刻意與 `app.rules.engine.load_program_rules` 一致，這樣接上真正的
        資料來源時不需要再多一層轉換。
        """
        ...


class EvidenceRetriever(Protocol):
    """項目代號 → 支撐判定的官方依據。"""

    def retrieve(self, item_id: str) -> tuple[Citation, ...]:
        """取出一個項目的官方依據。找不到時回空 tuple。

        找不到依據不是「沒有限制」，呼叫端應該把該項目降級為需人工協助。
        """
        ...


class PrivacyGate(Protocol):
    """屬性值進入 state 之前的最後一道檢查。"""

    def validate_attributes(
        self,
        answers: dict[str, AttributeValue],
        registry: Any,
    ) -> dict[str, AttributeValue]:
        """回傳可以寫進 state 的答案，或在不合法時拋出例外。

        `registry` 的型別是 `app.orchestration.field_registry.FieldRegistry`，但這裡
        標成 `Any`：`field_registry` 會 import `app.schemas.session`，而
        `app.schemas.session` 又 import `app.orchestration.state`。在接縫定義裡加上
        這條 import 只是為了型別註記，卻會讓模組相依圖更難拆（Req 20.2 另案處理）。
        """
        ...


class PassThroughPrivacyGate:
    """Phase 2 的隱私閘門：原樣回傳。

    值本身的型別與選項驗證屬於 Req 16.3（T11），還沒實作。**欄位代號的 allowlist
    不靠這個閘門**，它由狀態機在 `_record_answers` 裡強制執行，所以即使有人注入一個
    什麼都不做的閘門，未登記的欄位仍然會被拒絕。
    """

    def validate_attributes(
        self,
        answers: dict[str, AttributeValue],
        registry: Any,
    ) -> dict[str, AttributeValue]:
        """原樣回傳。刻意複製一份，避免呼叫端之後改動同一個 dict。"""
        del registry  # 這個實作不查登記表，簽章為了符合 PrivacyGate 才保留它。
        return dict(answers)


# 寫死的候選項目，取自 README 的 MVP 情境（配偶過世）。
# TODO(T15): 改成從 entitlement graph 依事件代號查。
_FIXTURE_ITEMS_BY_EVENT: dict[str, tuple[CandidateItem, ...]] = {
    "spouse_death": (
        CandidateItem(item_id="death_registration", kind=ItemKind.ADMINISTRATIVE),
        CandidateItem(item_id="funeral_benefit", kind=ItemKind.BENEFIT),
        CandidateItem(item_id="survivor_pension", kind=ItemKind.BENEFIT),
        CandidateItem(item_id="health_insurance_change", kind=ItemKind.ADMINISTRATIVE),
    ),
}


class FixtureEntitlementSource:
    """離線用的 `EntitlementSource`：一份寫死的對照表。

    只有 MVP 情境（配偶過世）有資料。其他事件回空 tuple，因為這個實作**沒有**那些
    事件的資料 —— 回一組猜的項目會讓下游誤以為展開成功。

    TODO(T15): 換成讀 entitlement graph 的實作。
    """

    def resolve(self, life_event: str) -> tuple[CandidateItem, ...]:
        """查對照表。事件不在表上時回空 tuple。"""
        return _FIXTURE_ITEMS_BY_EVENT.get(life_event, ())
