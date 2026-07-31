"""示範用的資料層實作。**這裡的資料不是真的，不得作為任何預設值。**

依 ADR-0014：預設路徑永遠不會產生 `verified`（已核對）狀態，因為那個狀態的意思是
「有人真的讀過法規、確認過條件與依據、而且那次審查被記錄下來」。
`protocols.py` 的離線實作因此全部維持 `candidate`（候選），結果是整條離線流程
四個項目全部停在需人工協助，走不到「符合資格」。

這個模組補的是**示範與測試需要的深度**。它可以設 `verified`，因為那個狀態本身就是
它要示範的東西之一 —— 沒有它，`determination.gated_status` 會擋掉完整判定，連
「不符合」都到不了。約束改成「看得見」：模組名稱有 `demo`、類別名稱有 `Demo`、
而且**任何地方都不得把它設成預設值**，只能透過 `state_machine.advance()` 的具名參數
主動傳進去。

分界是「說謊」與「演示」的差別。在真實的 catalog 資料上標 `verified` 而沒有人審查過，
是對那筆資料做了不實的宣稱；一個叫 `demo_fixtures` 而且自己在開頭寫明的模組，
沒有宣稱任何事。

## 為什麼只做一項

T17 的要求是「窄而深」，不是「寬而淺」。現在四個項目都有一點資料但每一項都沒有判斷
條件，所以整條路走不到結局。只把一項填到底才驗證得出管路通不通；四項各填一半，
等於四條路都不通。

挑喪葬給付（`funeral_benefit`）的理由是它只需要一個資格欄位
（`deceased_insurance_type`），是最短的完整路徑。

## 這裡還沒有的東西

**官方依據（citations）不在這個模組裡。** `EligibilityDecision` 沒有依據欄位，
`rule_adapter.apply_decision` 也不搬依據 —— 依據要走 `EvidenceRepository`，而
`state_machine._do_retrieve_rules` 目前是空操作。接上檢索是另一個獨立的小任務，
跟這裡分開才各自驗證得出來。

所以示範跑出來的項目會有狀態、決定性條件與金額，但 `citations` 是空的。
"""

from dataclasses import replace

from app.orchestration.data_contracts import (
    CandidateItem,
    EligibilityDecision,
    GraphRelation,
    StructuredReason,
)
from app.orchestration.protocols import (
    FixtureEligibilityService,
    FixtureEntitlementGraphRepository,
    UserAttributes,
)

DEMO_ITEM_ID = "funeral_benefit"
"""唯一被填到底的項目代號。"""

DEMO_FIELD_ID = "deceased_insurance_type"
"""這一項唯一需要的資格欄位。必須是欄位登記表上真的有的代號。

不能隨便編一個：欄位登記表現在是屬性的唯一入口，登記表上沒有的代號問不出來也收不進來
（見 `docs/back_database_doc/README.md` 的落差九）。用登記表上沒有的代號當示範條件，
示範就會卡在「永遠缺這個欄位」。
"""

DEMO_EXPECTED_VALUE = "labor_insurance"
"""示範條件要求的值。必須是登記表裡 `deceased_insurance_type` 的合法選項之一。"""

# 示範金額。**這不是真實的給付金額**，是一個明顯整數，用來證明金額欄位會被搬到畫面上。
#
# 真實的喪葬給付是「平均月投保薪資的若干個月」，要看投保紀錄才算得出來，而且必須有人
# 核對過法規才能寫進來。這裡不假裝知道那個數字。
_DEMO_AMOUNT_TWD = 100_000

DEMO_DECISION = EligibilityDecision(
    item_id=DEMO_ITEM_ID,
    status="eligible",
    amount_min=_DEMO_AMOUNT_TWD,
    amount_max=_DEMO_AMOUNT_TWD,
    # 一次性。這個欄位存在的理由是「5,000 元」與「每月 5,000 元」對使用者的意義
    # 完全不同，不能讓前端從數字猜。
    amount_period="one_time",
    amount_currency="TWD",
    reasons=(
        StructuredReason(
            condition_id="demo_insurance_type_matches",
            field_id=DEMO_FIELD_ID,
            operator="equals",
            expected=DEMO_EXPECTED_VALUE,
            actual=DEMO_EXPECTED_VALUE,
            # `label` 與 `source_reference` 不會流到前端：
            # `rule_adapter._decisive_conditions` 只搬 field_id、expected、actual。
            # 這裡填的字串只有讀程式的人看得到。
            label="示範用條件，非真實法規要求",
            source_reference="demo_fixture",
        ),
    ),
)
"""喪葬給付的示範判定。

`expected` 與 `actual` 刻意填同一個值，所以這是一個**說得出理由的「符合」** ——
決定性條件會被搬進 workflow 形狀，畫面上可以顯示「因為這個條件成立」。

`status` 是 `eligible` 而不是 `ineligible`，因為 `ineligible` 沒辦法單純用示範資料
驗證：`rule_adapter.downgrade_unexplained_ineligible` 會把說不出決定性條件的「不符合」
降級，那條路徑已經有自己的測試，不需要在這裡再走一次。
"""


class DemoEntitlementGraphRepository:
    """把**一個**項目的資料治理狀態提升為 `verified` 的示範用 graph repository。

    包在 `FixtureEntitlementGraphRepository` 外面，而不是自己複製一份候選清單。
    複製的話,那四筆項目就會有兩份定義，其中一份遲早過期。

    只有 `expand_from_event` 與 `get_programs_by_system` 需要提升狀態，因為
    `get_prerequisites` 與 `get_produces` 回的是 `GraphRelation`（圖上的關係），
    那個型別沒有資料治理狀態 —— 關係本身不需要被核對，被核對的是方案。
    """

    def __init__(
        self,
        inner: FixtureEntitlementGraphRepository | None = None,
        demo_item_id: str = DEMO_ITEM_ID,
    ) -> None:
        self._inner = (
            inner if inner is not None else FixtureEntitlementGraphRepository()
        )
        self._demo_item_id = demo_item_id

    def _promote(self, item: CandidateItem) -> CandidateItem:
        """只有示範項目被提升，其餘原樣回傳。

        用 `dataclasses.replace` 而不是改欄位，因為 `CandidateItem` 是 frozen ——
        改不動，也不該改：其他呼叫端可能正拿著同一個物件。
        """
        if item.item_id != self._demo_item_id:
            return item
        return replace(item, program_status="verified")

    def expand_from_event(
        self,
        event_id: str,
        user_attributes: UserAttributes,
    ) -> tuple[CandidateItem, ...]:
        """展開事件，並把示範項目標成已核對。"""
        return tuple(
            self._promote(item)
            for item in self._inner.expand_from_event(event_id, user_attributes)
        )

    def get_prerequisites(self, item_id: str) -> tuple[GraphRelation, ...]:
        """原樣轉給離線實作。關係沒有資料治理狀態。"""
        return self._inner.get_prerequisites(item_id)

    def get_produces(self, item_id: str) -> tuple[GraphRelation, ...]:
        """原樣轉給離線實作。關係沒有資料治理狀態。"""
        return self._inner.get_produces(item_id)

    def get_programs_by_system(self, system_id: str) -> tuple[CandidateItem, ...]:
        """查某個制度底下的方案，並把示範項目標成已核對。"""
        return tuple(
            self._promote(item)
            for item in self._inner.get_programs_by_system(system_id)
        )


def demo_eligibility_service() -> FixtureEligibilityService:
    """帶著喪葬給付示範判定的判定服務。

    直接重用 `FixtureEligibilityService`，因為它對查不到的項目已經回
    `needs_human_review` —— 那正是其餘三項應該得到的結果。不需要另寫一個類別。
    """
    return FixtureEligibilityService(decisions={DEMO_ITEM_ID: DEMO_DECISION})
