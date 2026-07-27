"""Session API 的請求與回應形狀。

這是後端唯一對外承諾的形狀。`app.orchestration.state` 是內部狀態，前端看不到；
這個模組定義的是那份內部狀態的**投影**（projection）—— 只挑出前端真正需要的部分。

## 為什麼要投影，不直接照搬內部狀態

內部的 `SessionState` 有幾個欄位只有後端自己需要：`loop_iterations` 是護欄用的
計數，`updated_at` 畫面上沒有用到，項目裡的 `rule_id` 與 `rule_version` 是給我們
追查用的。照搬會把實作細節變成對外承諾，之後想改名或移除就等於改 API。

方向跟紀錄檔的欄位 allowlist 一致：明確列出要露出什麼，而不是默認全部露出。
少露出一個欄位不會有事，多露出一個可能要收回。

## 列舉刻意重用內部的定義

`WorkflowState`、`ItemStatus`、`ItemKind`、`AmountPeriod` 直接從
`app.orchestration.state` 匯入，不在這裡另寫一份。理由是這些**代號本身就是契約的
一部分** —— 前端會依 `status` 的值分區顯示。另寫一份只會製造兩邊走鐘的機會。

## 隱私：自由文字只存在一種請求裡

依 [ADR-0007](../../../docs/decisions/0007-limit-data-retention-and-egress.md)，
自由文字只在 `UNDERSTAND_EVENT` 接收。這裡用 `kind` 欄位把請求分成幾種互斥的
形狀（discriminated union，可辨識聯集），只有 `life_event_text` 那一種帶文字欄位。
其餘六種在型別上就沒有地方塞句子，不需要靠檢查擋。

回應側同樣沒有任何欄位會回傳使用者的原始文字。`DecisiveConditionView.actual`
會回傳使用者提供的**值**，因為畫面要顯示「你的情況是 X」，但那是登記表允許的
去識別化代號，不是自由文字。

## 對外欄位名是 camelCase

Python 慣例是 snake_case，TypeScript 慣例是 camelCase。這裡用 Pydantic 的
`alias_generator` 讓**線路上的 JSON 是 camelCase**，Python 程式內部仍然是
snake_case。兩種語言各自維持慣例，前端也不需要自己做一層轉換。

因此 `item_id` 在 JSON 裡是 `itemId`。列舉的**值**不受影響，例如 `needs_information`
仍然是 `needs_information` —— 那是資料內容，不是欄位名稱。

## 錯誤回應為什麼要自訂形狀

Pydantic 的 `ValidationError` 訊息會把不合法的值原文引用進去。如果直接把它回給
前端或寫進紀錄檔，使用者打的字就漏出去了。所以任何驗證錯誤都必須先轉成
`ErrorResponse` 才能離開後端。`ErrorResponse` 沒有任何欄位可以放值，所以結構上
不可能漏。轉換的實作是後續任務，這裡先把形狀定好。
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.orchestration.state import (
    AmountPeriod,
    AttributeValue,
    ExitReason,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)

# 自由文字的長度上限。目的是限制單次輸入的大小，不是內容檢查。
MAX_LIFE_EVENT_TEXT_LENGTH = 2000

# 進度顯示用的總步數。與 WorkflowState 的成員數綁在一起，改狀態就會跟著改。
WORKFLOW_STEPS: tuple[WorkflowState, ...] = tuple(WorkflowState)


class AttributeValueKind(StrEnum):
    """一個資格欄位接受哪一種值。

    這組詞彙之後會由欄位登記表宣告；契約先定義它，讓前端能在登記表完成前就開始
    做問題卡的畫面。
    """

    CODE = "code"  # 從固定選項裡選一個代號
    BOOLEAN = "boolean"  # 是或否
    BAND = "band"  # 有序級距，例如年齡或年資區間
    INTEGER = "integer"  # 精確整數，例如人數


class PendingCapability(StrEnum):
    """後端還沒實作、因此回應中相關內容為佔位資料的能力。

    每一個代號對應規劃裡的一項具體任務。實作完成就從回應的清單裡移除，前端不需要
    改程式，顯示的警示會自動變少。
    """

    LIFE_EVENT_EXTRACTION = "life_event_extraction"  # 用 LLM 聽懂人生事件
    ENTITLEMENT_GRAPH = "entitlement_graph"  # 事件對應哪些項目、順序與依賴
    STATE_MACHINE = "state_machine"  # 流程轉換與守門條件
    FIELD_REGISTRY = "field_registry"  # 有哪些資格欄位、型別與選項
    RULE_EVALUATION = "rule_evaluation"  # 確定性資格判定
    OFFICIAL_CITATIONS = "official_citations"  # 官方依據檢索
    PLAIN_LANGUAGE_EXPLANATION = "plain_language_explanation"  # 白話說明
    ACTION_PLAN = "action_plan"  # 辦理清單與順序
    PRIVACY_GATE = "privacy_gate"  # 屬性 allowlist 與原文丟棄


class ErrorCode(StrEnum):
    """錯誤代號。前端依代號決定顯示什麼文字。

    刻意只有代號，沒有訊息文字。文案屬於前端，與問題卡沿用同一條分界。
    """

    SESSION_NOT_FOUND = "session_not_found"  # 找不到這個 session
    SESSION_EXPIRED = "session_expired"  # session 已超過保存時間
    UNKNOWN_FIELD = "unknown_field"  # 送來的欄位不在登記表上
    INVALID_FIELD_VALUE = "invalid_field_value"  # 值不符合欄位宣告的型別或選項
    UNKNOWN_ITEM = "unknown_item"  # 送來的項目代號不在候選清單裡
    INVALID_TRANSITION = "invalid_transition"  # 目前狀態不允許這個動作
    INTERNAL_ERROR = "internal_error"  # 後端自身錯誤，不透露細節


# ---------------------------------------------------------------------------
# 請求：以 kind 區分的互斥形狀
# ---------------------------------------------------------------------------


class _Input(BaseModel):
    """所有請求形狀的共同設定。

    `alias_generator` 讓對外的欄位名是 camelCase，Python 內部維持 snake_case。
    `populate_by_name` 讓兩種寫法都收，測試與內部呼叫可以直接用 Python 名稱。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class LifeEventTextInput(_Input):
    """畫面 1：使用者描述發生了什麼事。

    這是整個 API 唯一帶自由文字的請求形狀。文字在抽取出屬性後即丟棄，不會存進
    session、不會寫進紀錄檔，也不會出現在任何回應裡。
    """

    kind: Literal["life_event_text"] = "life_event_text"
    text: str = Field(min_length=1, max_length=MAX_LIFE_EVENT_TEXT_LENGTH)


class EventConfirmationInput(_Input):
    """畫面 2：使用者確認或否認系統理解的事件。

    `confirmed` 為 False 表示「不是這樣，我重新描述」，會累加重試計數。
    """

    kind: Literal["event_confirmation"] = "event_confirmation"
    confirmed: bool


class AttributeAnswersInput(_Input):
    """畫面 4 送出一組答案，畫面 7 修正答案也用這個形狀。

    以欄位代號為鍵。不在登記表上的代號會讓整筆請求被拒絕，回 `UNKNOWN_FIELD`，
    錯誤裡只有代號、沒有值。
    """

    kind: Literal["attribute_answers"] = "attribute_answers"
    answers: dict[str, AttributeValue] = Field(min_length=1)


class ItemDeclineInput(_Input):
    """使用者選「這一項我不想辦」。該項目退出判定，不再追問相關欄位。"""

    kind: Literal["item_decline"] = "item_decline"
    item_id: str


class ReviewConfirmationInput(_Input):
    """畫面 7：複查答案後確認，進入產生辦理清單。"""

    kind: Literal["review_confirmation"] = "review_confirmation"
    confirmed: bool


class ReferralChoiceInput(_Input):
    """畫面 7：有需人工協助的項目時，使用者決定要不要轉介。"""

    kind: Literal["referral_choice"] = "referral_choice"
    requested: bool


class HelpRequestInput(_Input):
    """使用者在任何時候主動要求人工協助。

    這是流程的出口之一，對應 `ExitReason.USER_REQUESTED_HELP`。
    """

    kind: Literal["help_request"] = "help_request"


AdvanceInput = Annotated[
    LifeEventTextInput
    | EventConfirmationInput
    | AttributeAnswersInput
    | ItemDeclineInput
    | ReviewConfirmationInput
    | ReferralChoiceInput
    | HelpRequestInput,
    Field(discriminator="kind"),
]
"""推進一步時可以送的七種輸入。

用 `kind` 當判別欄位，所以 Pydantic 看到 kind 的值就知道其餘欄位該長什麼樣。
這也是「自由文字只存在第一步」的結構保證：其他六種形狀沒有文字欄位。
"""


class AdvanceRequest(_Input):
    """`POST /sessions/{session_id}/advance` 的請求本體。"""

    input: AdvanceInput


# ---------------------------------------------------------------------------
# 回應：內部狀態的投影
# ---------------------------------------------------------------------------


class _View(BaseModel):
    """所有回應形狀的共同設定。

    回應要用 `model_dump(by_alias=True)` 或在 FastAPI 設定 `response_model_by_alias`
    才會輸出 camelCase。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class DecisiveConditionView(_View):
    """畫面 5 顯示「差在這個條件：你的情況 X ／ 需要 Y」所需的三段。

    `actual` 是使用者提供的值。它會回傳給前端，因為使用者需要看到自己的情況；
    但它不得寫進紀錄檔。
    """

    field_id: str
    expected: AttributeValue
    actual: AttributeValue


class CitationView(_View):
    """官方依據。六個欄位都是文件本身的資訊，與使用者無關。"""

    document_id: str
    title: str
    publisher_name: str
    published_at: str | None = None
    url: str
    excerpt: str = ""


class ItemView(_View):
    """一個候選項目對前端露出的部分。

    刻意不露出的內部欄位：`rule_id`、`rule_version`、`resolved_at`。前三者是給我們
    追查用的，露出去會讓規則的內部編號變成對外承諾。
    """

    item_id: str
    kind: ItemKind
    status: ItemStatus

    missing_field_ids: tuple[str, ...] = ()
    decisive_conditions: tuple[DecisiveConditionView, ...] = ()
    citations: tuple[CitationView, ...] = ()

    amount_min: int | None = None
    amount_max: int | None = None
    amount_period: AmountPeriod | None = None
    amount_currency: str | None = None

    explanation: str | None = None


class QuestionView(_View):
    """一個問題的結構。文案全部由前端提供。

    後端只給代號與型別；`purpose_id` 對應「為什麼問這個？」那段說明的代號，實際
    文字由前端負責。`option_ids` 只在型別為 `CODE` 或 `BAND` 時有值。
    """

    field_id: str
    value_kind: AttributeValueKind
    option_ids: tuple[str, ...] = ()
    required: bool = True
    purpose_id: str

    # 回答這一題會讓哪些項目可以被判定。前端用它顯示「再答 2 題可確認遺屬年金」。
    unlocks_item_ids: tuple[str, ...] = ()


class QuestionGroupView(_View):
    """一組同主題的問題。

    分組按**主題**而非按項目，因為同一個欄位常同時被多個項目需要，按項目分組會讓
    使用者被問兩次同樣的問題。
    """

    topic_id: str
    questions: tuple[QuestionView, ...]
    group_index: int  # 目前是第幾組，從 1 開始
    group_total: int  # 目前已知共幾組


class ImplementationNotice(_View):
    """這份回應有多少是真的。

    存在的理由是誠實：目前多數能力還沒實作，回應裡的事件代號與項目清單是寫死的
    佔位資料。前端據此在畫面上標示，demo 現場被問到「這個判定是真的嗎」時答得出來。

    `placeholder_notice` 是唯一一個由後端提供**給人看的中文文字**的欄位，違反本專案
    「後端給代號、前端給文案」的分界。這是刻意的臨時例外：它的讀者是開發者與 demo
    觀眾，不是真正的使用者，而且它會在佔位資料移除時**連同這整個類別一起刪除**。
    只有 `is_mock` 為 True 時才有值。
    """

    is_mock: bool = False
    pending: tuple[PendingCapability, ...] = ()
    placeholder_notice: str = ""


class SessionSnapshot(_View):
    """一次諮詢在某個時間點的完整對外狀態。

    三個端點都回這個形狀。回完整快照而不是只回變動，是因為後端擁有權威狀態；
    只回變動會讓前端必須自己拼湊完整狀態，等於出現第二份真相。
    """

    session_id: str
    workflow_state: WorkflowState

    # 進度顯示用。因為中間有迴圈，這個數字可能往回走。
    step_index: int
    step_total: int

    life_event: str | None = None

    # 使用者答過的答案，畫面 7 複查時要顯示。
    attributes: dict[str, AttributeValue] = Field(default_factory=dict)

    items: tuple[ItemView, ...] = ()

    # 登記表完成前，後端會回空清單。形狀先定，讓前端能開始做問題卡的畫面。
    question_groups: tuple[QuestionGroupView, ...] = ()

    exit_reason: ExitReason | None = None
    referral_requested: bool = False

    # 還有工作沒完成時為 True，輪詢的前端依此決定要不要再問一次。
    is_processing: bool = False

    created_at: datetime
    expires_at: datetime

    # 這份回應有多少是真的。實作完成後清單會逐項變短。
    implementation: ImplementationNotice = Field(default_factory=ImplementationNotice)

    @classmethod
    def from_state(
        cls,
        state: SessionState,
        question_groups: tuple[QuestionGroupView, ...] = (),
        implementation: ImplementationNotice | None = None,
    ) -> "SessionSnapshot":
        """從內部狀態組出對外快照。

        `question_groups` 由外部傳入而不是從 state 讀，因為缺漏欄位要變成可顯示的
        問題卡，需要欄位登記表，那不屬於 workflow state。

        `implementation` 同樣由外部傳入，因為「哪些能力已經實作」是應用程式層的
        事實，不屬於某一次諮詢的狀態。
        """
        return cls(
            implementation=implementation or ImplementationNotice(),
            session_id=state.session_id,
            workflow_state=state.workflow_state,
            step_index=WORKFLOW_STEPS.index(state.workflow_state) + 1,
            step_total=len(WORKFLOW_STEPS),
            life_event=state.life_event,
            attributes=dict(state.attributes),
            items=tuple(
                ItemView(
                    item_id=item.item_id,
                    kind=item.kind,
                    status=item.status,
                    missing_field_ids=item.missing_field_ids,
                    decisive_conditions=tuple(
                        DecisiveConditionView(
                            field_id=condition.field_id,
                            expected=condition.expected,
                            actual=condition.actual,
                        )
                        for condition in item.decisive_conditions
                    ),
                    citations=tuple(
                        CitationView(
                            document_id=citation.document_id,
                            title=citation.title,
                            publisher_name=citation.publisher_name,
                            published_at=citation.published_at,
                            url=citation.url,
                            excerpt=citation.excerpt,
                        )
                        for citation in item.citations
                    ),
                    amount_min=item.amount_min,
                    amount_max=item.amount_max,
                    amount_period=item.amount_period,
                    amount_currency=item.amount_currency,
                    explanation=item.explanation,
                )
                for item in state.items
            ),
            question_groups=question_groups,
            exit_reason=state.exit_reason,
            referral_requested=state.referral_requested,
            is_processing=state.is_processing,
            created_at=state.created_at,
            expires_at=state.expires_at,
        )


class ErrorResponse(_View):
    """所有錯誤共用的形狀。

    三個欄位都不能放值：`error_code` 是代號，`field_ids` 是欄位代號，
    `current_state` 是狀態名稱。因此這個形狀在結構上不可能洩漏使用者輸入。
    """

    error_code: ErrorCode
    field_ids: tuple[str, ...] = ()
    current_state: WorkflowState | None = None
