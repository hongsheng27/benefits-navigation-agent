"""一次福利導航諮詢的 workflow state 形狀定義。

這個模組**只定義資料形狀**。狀態轉換、守門條件與停止條件放在
`state_machine.py`；資格判定放在 `app.rules`。

## 隱私：這裡沒有任何可以放自由文字的欄位

[ADR-0007](../../../docs/decisions/0007-limit-data-retention-and-egress.md)
規定自由文字只在 `UNDERSTAND_EVENT` 接收，抽取出屬性後即丟棄。這個模組用結構
強制這件事：`SessionState` 沒有任何欄位可以存放使用者打的字。沒有 `text`、
`description`、`raw_input`，也沒有 `note`。後續的人如果想在這裡塞一段句子，
必須新增一個欄位，而 `tests/unit/test_workflow_state.py` 會在出現這種欄位時失敗。

依 [ADR-0005](../../../docs/decisions/0005-split-client-server-session-state.md)，
姓名、身分證字號、地址、電話與 email 留在使用者裝置上，所以這裡也沒有對應欄位。

## 為什麼用 Pydantic 而不是 dataclass
Session state 需要序列化（目前存在記憶體，未來可能存進資料庫），也需要投影成
`app.schemas` 的 API 回應。Pydantic 兩個方向都提供，包含列舉與時間的轉換，而且
專案已經依賴它。

代價是 Pydantic 的 `ValidationError` 會把不合法的值原文寫進訊息裡，如果那個值來自
request body，就可能是使用者打的字。以下三條規則讓它不會變成洩漏路徑：

1. 狀態物件永遠不由前端傳入的資料直接建立。前端資料先經過 `app.schemas` 驗證，
   只有通過的值才進到這個模組。
2. 在這裡發生驗證錯誤代表我們自己的程式寫錯了。讓它直接中斷，不要把訊息交給
   `log_event`，也不要回傳給前端。
3. 需要回報失敗的呼叫端只記錄例外的**類別名稱**，這一點 `app.observability.logging`
   已經在程式層強制。

## 為什麼模型是 frozen

`frozen=True` 讓欄位不能重新賦值，所以狀態轉換無法偷偷修改傳進來的狀態。每一步都
用 `model_copy(update=...)` 產生新的狀態，這讓 `state_machine.py` 成為唯一會改變
workflow state 的地方。

一個要誠實說明的限制：frozen 只擋住「重新綁定欄位」，不擋「修改欄位指向的那個物件」。
`SessionState.attributes` 是 `dict`，所以 `state.attributes["x"] = 1` 在執行時仍然
會成功。序列類型的欄位都用 `tuple`，因為它是不可變的替代品且用法幾乎相同；屬性
對照表保留 `dict`，因為它會被大量以欄位代號查詢。兩者都請當成唯讀，需要改就建立
新的狀態。
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.data_contracts import ProgramStatus


class WorkflowState(StrEnum):
    """專案 README 定義的八個 workflow state。

    下面的順序是正常路徑。有兩個預期的偏離：

    - `COLLECT_MISSING_FIELDS`、`RETRIEVE_RULES` 與 `EVALUATE_ELIGIBILITY`
      形成一個迴圈，因為項目是隨著必要欄位陸續到齊而逐項定案的。
    - `CONFIRM` 是條件性的。它用來複查答案與詢問轉介，沒有東西要複查也沒有需要
      轉介時會被跳過。
    """

    UNDERSTAND_EVENT = "understand_event"  # 聽懂人生事件，並等使用者確認
    RESOLVE_ENTITLEMENTS = "resolve_entitlements"  # 展開可能相關的項目
    COLLECT_MISSING_FIELDS = "collect_missing_fields"  # 按主題逐組追問缺漏欄位
    RETRIEVE_RULES = "retrieve_rules"  # 檢索官方依據
    EVALUATE_ELIGIBILITY = "evaluate_eligibility"  # 由規則引擎判定資格
    EXPLAIN_RESULT = "explain_result"  # 全部定案後補上白話說明
    CONFIRM = "confirm"  # 複查答案並詢問是否轉介（條件性）
    COMPLETE = "complete"  # 產生有順序與期限的辦理清單


class ItemKind(StrEnum):
    """區分這個項目是可以申請的福利，還是必須辦理的行政事項。

    兩種都會經過規則引擎。`BENEFIT` 判斷是否符合請領資格；`ADMINISTRATIVE`
    判斷是否適用與期限條件。兩者共用同一套判定形狀，可以省掉每個使用端的第二層分支。

    但在畫面上這個區分仍然重要：不能讓使用者把「你符合死亡登記的資格」讀成一項
    可以選擇放棄的福利。
    """

    BENEFIT = "benefit"  # 可以申請的福利，例如喪葬給付、遺屬年金
    ADMINISTRATIVE = "administrative"  # 必須辦理的行政事項，例如死亡登記、健保身分變更


class ItemStatus(StrEnum):
    """單一項目的狀態。每個項目各自帶一個。

    一次諮詢很常同時存在數個符合的項目、一個還沒定案的項目與一個不符合的項目；
    結果畫面就是把這份清單按狀態分區顯示。

    只有 `RULE_ENGINE_STATUSES` 裡的四個值可以由規則引擎產生。`PENDING` 是展開
    候選項目時給的初始值，`DECLINED_BY_USER` 記錄的是使用者的選擇。
    """

    PENDING = "pending"  # 待確認：還在等必要欄位，尚未判定
    ELIGIBLE = "eligible"  # 符合
    INELIGIBLE = "ineligible"  # 不符合，且必須指出決定性條件
    NEEDS_INFORMATION = "needs_information"  # 資訊不足，例如使用者選了「我不確定」
    NEEDS_HUMAN_REVIEW = "needs_human_review"  # 需人工協助，例如找不到官方依據
    DECLINED_BY_USER = "declined_by_user"  # 使用者選了「這一項我不想辦」


RULE_ENGINE_STATUSES: frozenset[ItemStatus] = frozenset(
    {
        ItemStatus.ELIGIBLE,
        ItemStatus.INELIGIBLE,
        ItemStatus.NEEDS_INFORMATION,
        ItemStatus.NEEDS_HUMAN_REVIEW,
    }
)
"""確定性規則引擎唯一允許回傳的狀態集合。

規則引擎擁有資格判定權，但不擁有項目的生命週期。它回傳 `PENDING` 或
`DECLINED_BY_USER` 一定是 bug，呼叫端應該拒絕而不是存下來。
"""


class ExitReason(StrEnum):
    """整次諮詢提前停止並提供人工協助的原因。

    這些是**整次諮詢層級**的出口。已記錄的「走不下去」情況裡有兩種屬於單一項目
    層級，它們只把受影響的項目標成 `ItemStatus.NEEDS_HUMAN_REVIEW`，其餘項目
    照常進行：

    - 某個項目找不到官方依據
    - 某條規則說不出「不符合」是差在哪一個條件
    """

    EVENT_NOT_RECOGNIZED = "event_not_recognized"  # 認不出人生事件，不猜
    # 使用者說「不是這樣」超過兩次
    EVENT_RETRY_LIMIT_REACHED = "event_retry_limit_reached"
    LOOP_LIMIT_REACHED = "loop_limit_reached"  # 追問與判定的迴圈超過上限
    NO_PROGRESS = "no_progress"  # 繞了一圈但沒有任何項目狀態改變或新屬性
    USER_REQUESTED_HELP = "user_requested_help"  # 使用者主動要求人工協助


type AttributeValue = bool | int | str
"""一筆去識別化的資格答案。

`bool` 排在 `int` 前面，因為 Python 把 `bool` 當成 `int` 的子類別，順序反了會被
較寬的型別吸收。

有哪些欄位代號存在、每個欄位接受上述哪一種型別，由欄位登記表宣告，不寫在這裡。
這樣情境相關的政策就留在可審查的資料裡，而不是散進程式碼。
"""


class DecisiveCondition(BaseModel):
    """決定這個項目結果的那個條件。

    這是讓產品能說「你只差這一個條件」而不是「不符合」的關鍵，也是整個專案建立
    起來的差異點。規則如果無法為「不符合」指出決定性條件，就必須把該項目降級為
    `NEEDS_HUMAN_REVIEW`。

    `actual` 存的是使用者提供的值。它會回傳給前端，因為使用者需要看到它。但它
    絕對不能寫進紀錄檔。`app.observability.logging` 的允許欄位清單裡沒有任何欄位
    能接受這種值，所以照規定使用 `log_event` 就足夠了。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    field_id: str  # 是哪一個資格欄位造成這個結果
    expected: AttributeValue  # 規則要求的值
    actual: AttributeValue  # 使用者實際的情況（可回前端顯示，但不得寫入紀錄檔）


class Citation(BaseModel):
    """支撐一項判定的官方依據。

    欄位名稱對齊本機 benefit catalog，讓紀錄可以在兩邊搬動而不需要轉換層：
    `title`、`publisher_name` 與 `published_at` 來自 `source_documents`，
    `excerpt` 對應 `program_sources.source_excerpt`。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str  # 文件代號，對應 catalog 的 source_documents.document_id
    title: str  # 官方文件標題
    publisher_name: str  # 發布機關名稱
    published_at: str | None = None  # 發布日期，官方頁面沒有標示時為 None
    url: str  # 官方連結，供使用者自行查證
    excerpt: str = ""  # 引用的段落，讓使用者拿著它去問承辦人


class AmountPeriod(StrEnum):
    """金額的發放性質。

    「5,000 元」與「每月 5,000 元」對使用者的意義差很多，不能讓前端從數字猜。
    行政事項通常沒有金額，此時整組金額欄位都留空。
    """

    ONE_TIME = "one_time"  # 一次性發放
    MONTHLY = "monthly"  # 按月發放
    ANNUAL = "annual"  # 按年發放


class CandidateItem(BaseModel):
    """一個正在評估的福利或行政事項。

    尚未建模：互斥關係。有些給付不能同時請領，所以兩個項目可能都是 `ELIGIBLE`
    但使用者只能選一個。Catalog 已經用
    `benefit_programs.mutual_exclusion_text` 預留了這件事，但互斥的組合本身取決於
    還沒審核完的官方文件。互斥應該當成規則的一部分，跟著規則引擎一起加，而不是
    現在猜一個形狀。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str  # 項目代號，例如 funeral_benefit
    kind: ItemKind  # 福利或行政事項
    status: ItemStatus = ItemStatus.PENDING  # 這個項目自己的狀態，與其他項目無關

    # 複合情境展開時，此項目來自哪些 life_event（用於結果分區）。
    source_life_events: tuple[str, ...] = ()

    # 資料層對這筆方案資料的治理狀態，決定 runtime 敢對它做到什麼程度
    # （閘門實作見 `determination.py`）。這不是使用者的判定結果 —— `status` 才是。
    #
    # 預設 `"candidate"` 是刻意選擇：依提案第 14 節，crawler 與 LLM 只能建立候選資料，
    # 所以「沒有人明確說這筆已經審過」時就必須當成候選。預設 `"verified"` 會讓任何
    # 忘記帶狀態的資料自動取得完整判定資格，那是最危險的預設值。
    program_status: ProgramStatus = "candidate"

    missing_field_ids: tuple[str, ...] = ()  # 還缺哪些欄位才能判定這一項
    decisive_conditions: tuple[DecisiveCondition, ...] = ()  # 造成這個結果的條件
    citations: tuple[Citation, ...] = ()  # 支撐這個結果的官方依據

    rule_id: str | None = None  # 用哪一條規則判的，供追查與修正
    rule_version: str | None = None  # 規則版本，規則調整後舊結果仍可追溯

    # 金額只放結構，不放給人看的文字。前端負責組出「骨灰 10,000 元」這種句子，
    # 因為千分位、幣別寫法與語氣都屬於呈現層的決定。
    # 對齊資料層的 `min_amount` 與 `max_amount`：金額本來就可能是一個範圍，
    # 壓成單一數字會在轉接時遺失資訊。單一固定金額時兩者填相同的值。
    amount_min: int | None = None  # 最低金額，無金額或未知時為 None
    amount_max: int | None = None  # 最高金額，無金額或未知時為 None
    amount_period: AmountPeriod | None = None  # 一次性、按月或按年
    amount_currency: str | None = None  # 幣別代號，例如 TWD

    # 在 EXPLAIN_RESULT、所有項目都定案之後才填入。模型可以改寫已定案結果的說法，
    # 但不能改變結論、不能新增項目，也不能引用沒有交給它的文件。
    explanation: str | None = None

    resolved_at: datetime | None = None  # 定案時間，尚未定案時為 None


class SessionState(BaseModel):
    """一次諮詢在伺服器端的權威狀態。

    前端可以持有呈現用的狀態，但不擁有這一份。依 ADR-0005，傳入的 workflow state
    不予信任，後端會重新計算每一次轉換。

    刻意先不放的欄位，以及各自會由哪個任務引入：

    - 產生出來的辦理清單，可能改成需要時即時推導（T5）
    - 問題分組的總數，需要先定出分組規則（T8）
    - 檢索或模型暫時性失敗的可重試標記（T19）
    - 狀態的 schema 版本，只有在 state 真的持久化之後才需要
    - 轉換歷程，`log_event` 已經用 `state`、`next_state`、`transition` 與 `guard`
      這幾個欄位記錄了。要注意 ADR-0005 把轉換歷程列為後端擁有；它確實由後端
      擁有，只是放在紀錄檔而不是狀態裡。紀錄檔是給人看的，程式邏輯不會去讀它，
      而目前沒有任何轉換需要依賴歷程。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # 隨機產生，與身分無關。它同時扮演「持有即通行」的憑證，所以走 HTTP header
    # 而不是網址路徑。
    session_id: str

    workflow_state: WorkflowState = WorkflowState.UNDERSTAND_EVENT  # 目前走到哪一步

    # 正規化後的事件代號，例如 `spouse_death`。刻意不用列舉：事件的集合是由
    # entitlement graph 擁有的 curated 資料，寫死在這裡會把政策放進應用程式碼。
    #
    # `life_event` 保留給舊客戶端：永遠等於 `life_events` 的第一筆（或 None）。
    # `life_events` 是確認後（或辨識後待確認）的複合情境，最多 5 個。
    # `extra_candidate_life_events` 是確認頁「另外可能相關」的未預選選項（最多 3）。
    life_event: str | None = None
    life_events: tuple[str, ...] = ()
    extra_candidate_life_events: tuple[str, ...] = ()

    # 去識別化的答案，以欄位代號為鍵。用對照表而不是清單，因為一個欄位只能有一個
    # 值，而使用者在 CONFIRM 修正答案時是直接覆蓋。
    attributes: dict[str, AttributeValue] = Field(default_factory=dict)

    items: tuple[CandidateItem, ...] = ()  # 候選項目與各自的判定結果

    # 迴圈與重試的計數。上限屬於政策而非形狀，所以跟轉換規則一起放在
    # `state_machine.py`，不放這裡。
    loop_iterations: int = 0  # 追問與判定的迴圈已經繞了幾圈
    event_retry_count: int = 0  # 使用者說「不是這樣」的次數

    exit_reason: ExitReason | None = None  # 提前結束的原因，正常進行時為 None
    referral_requested: bool = False  # 使用者是否要求轉介人工協助

    # 還有工作沒完成時為 True，讓輪詢的前端知道要不要再問一次。目前永遠是 False，
    # 因為一次請求是同步處理完的；把它保留在形狀裡，是為了將來改成非同步時前端
    # 不需要跟著改。
    is_processing: bool = False

    # 對話式補欄位時，下一句要問使用者的話（系統／模型產生，不是使用者原文）。
    collector_question: str | None = None

    created_at: datetime  # 建立時間，回訪畫面用它顯示「幾點開始的諮詢」
    updated_at: datetime  # 最後更新時間
    expires_at: datetime  # 自動失效時間，過期後 session 不再存在
