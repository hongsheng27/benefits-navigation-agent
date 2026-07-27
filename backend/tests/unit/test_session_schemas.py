"""驗證對外契約的形狀、隱私約束，以及與前端型別是否走鐘。

契約兩邊手寫（Python 與 TypeScript），所以最大的風險是改了一邊忘了另一邊。
這個檔案最後兩個測試會直接讀 `frontend/src/types/session.ts`，比對欄位名稱與列舉
值，不一致就失敗。
"""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.orchestration.state import (
    AmountPeriod,
    CandidateItem,
    Citation,
    DecisiveCondition,
    ExitReason,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)
from app.schemas.session import (
    MAX_LIFE_EVENT_TEXT_LENGTH,
    AdvanceInput,
    AdvanceRequest,
    AttributeAnswersInput,
    AttributeValueKind,
    CitationView,
    DecisiveConditionView,
    ErrorCode,
    ErrorResponse,
    ImplementationNotice,
    ItemView,
    LifeEventTextInput,
    PendingCapability,
    QuestionGroupView,
    QuestionView,
    SessionSnapshot,
)

_TYPES_FILE = (
    Path(__file__).resolve().parents[3] / "frontend" / "src" / "types" / "session.ts"
)

# 代表「可能存放使用者自由文字」的欄位名稱片段。
_FREE_TEXT_MARKERS = ("text", "raw", "input", "message", "prose", "note", "prompt")


def _state() -> SessionState:
    now = datetime(2026, 7, 26, 15, 30, tzinfo=UTC)
    return SessionState(
        session_id="s_test",
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=2),
    )


# ---------------------------------------------------------------------------
# 隱私約束
# ---------------------------------------------------------------------------


def test_only_the_life_event_input_carries_free_text() -> None:
    """自由文字在型別上只存在於第一步，不是靠檢查擋。"""
    adapter = TypeAdapter(AdvanceInput)
    members = adapter.core_schema["choices"]

    text_bearing = set()
    for kind, model in _iter_input_models():
        for field_name in model.model_fields:
            if any(marker in field_name for marker in _FREE_TEXT_MARKERS):
                text_bearing.add(kind)

    assert text_bearing == {"life_event_text"}
    assert len(members) == 7


def test_error_response_has_no_field_that_can_hold_a_value() -> None:
    """錯誤回應只帶代號。Pydantic 的原始錯誤訊息會引用原值，不得外流。"""
    assert set(ErrorResponse.model_fields) == {
        "error_code",
        "field_ids",
        "current_state",
    }

    error = ErrorResponse(error_code=ErrorCode.UNKNOWN_FIELD, field_ids=("some_field",))

    assert error.field_ids == ("some_field",)
    assert error.current_state is None


def test_life_event_text_is_length_bounded() -> None:
    with pytest.raises(ValidationError):
        LifeEventTextInput(text="")

    with pytest.raises(ValidationError):
        LifeEventTextInput(text="x" * (MAX_LIFE_EVENT_TEXT_LENGTH + 1))


# ---------------------------------------------------------------------------
# 投影：只露出前端需要的欄位
# ---------------------------------------------------------------------------


def test_snapshot_hides_internal_only_state_fields() -> None:
    hidden = {"loop_iterations", "event_retry_count", "updated_at"}

    assert hidden.isdisjoint(SessionSnapshot.model_fields)
    assert hidden <= set(SessionState.model_fields)


def test_item_view_hides_rule_traceability_fields() -> None:
    hidden = {"rule_id", "rule_version", "resolved_at"}

    assert hidden.isdisjoint(ItemView.model_fields)
    assert hidden <= set(CandidateItem.model_fields)


def test_snapshot_projects_items_amounts_and_citations() -> None:
    state = _state().model_copy(
        update={
            "life_event": "spouse_death",
            "attributes": {"deceased_insurance_type": "labor_insurance"},
            "items": (
                CandidateItem(
                    item_id="funeral_benefit",
                    kind=ItemKind.BENEFIT,
                    status=ItemStatus.ELIGIBLE,
                    amount_min=10000,
                    amount_max=10000,
                    amount_period=AmountPeriod.ONE_TIME,
                    amount_currency="TWD",
                    citations=(
                        Citation(
                            document_id="doc_1",
                            title="〈條例名稱〉",
                            publisher_name="〈機關〉",
                            url="https://example.gov.tw/rule",
                        ),
                    ),
                    rule_id="funeral_benefit_relationship",
                    rule_version="v0.1",
                ),
                CandidateItem(
                    item_id="survivor_pension",
                    kind=ItemKind.BENEFIT,
                    status=ItemStatus.INELIGIBLE,
                    decisive_conditions=(
                        DecisiveCondition(
                            field_id="deceased_insured_years_band",
                            expected="fifteen_years_or_more",
                            actual="five_to_fifteen_years",
                        ),
                    ),
                ),
            ),
        }
    )

    snapshot = SessionSnapshot.from_state(state)

    assert snapshot.session_id == "s_test"
    assert snapshot.life_event == "spouse_death"
    assert snapshot.attributes == {"deceased_insurance_type": "labor_insurance"}

    funeral, pension = snapshot.items
    assert funeral.amount_min == funeral.amount_max == 10000
    assert funeral.amount_period is AmountPeriod.ONE_TIME
    assert funeral.citations[0].url == "https://example.gov.tw/rule"
    assert pension.decisive_conditions[0].actual == "five_to_fifteen_years"


def test_snapshot_reports_progress_and_defaults_to_no_questions() -> None:
    snapshot = SessionSnapshot.from_state(_state())

    assert snapshot.step_index == 1
    assert snapshot.step_total == len(WorkflowState)
    assert snapshot.question_groups == ()
    assert snapshot.is_processing is False


def test_snapshot_accepts_question_groups_supplied_from_outside() -> None:
    """問題卡需要欄位登記表，不屬於 workflow state，所以由外部傳入。"""
    group = QuestionGroupView(
        topic_id="deceased_insurance",
        group_index=1,
        group_total=3,
        questions=(
            QuestionView(
                field_id="deceased_insurance_type",
                value_kind=AttributeValueKind.CODE,
                option_ids=("labor_insurance", "national_pension", "none_or_unsure"),
                purpose_id="deceased_insurance_type.purpose",
                unlocks_item_ids=("funeral_benefit", "survivor_pension"),
            ),
        ),
    )

    snapshot = SessionSnapshot.from_state(_state(), question_groups=(group,))

    assert snapshot.question_groups[0].topic_id == "deceased_insurance"
    assert snapshot.question_groups[0].questions[0].required is True


# ---------------------------------------------------------------------------
# 請求：以 kind 區分
# ---------------------------------------------------------------------------


def test_input_is_selected_by_its_kind() -> None:
    adapter = TypeAdapter(AdvanceInput)

    parsed = adapter.validate_python(
        {"kind": "attribute_answers", "answers": {"has_dependent_children": True}}
    )

    assert isinstance(parsed, AttributeAnswersInput)
    assert parsed.answers["has_dependent_children"] is True


def test_text_cannot_be_smuggled_into_a_later_step() -> None:
    adapter = TypeAdapter(AdvanceInput)

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "review_confirmation", "confirmed": True, "text": "我先生過世了"}
        )


def test_answers_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        AttributeAnswersInput(answers={})


# ---------------------------------------------------------------------------
# 線路格式：對外是 camelCase
# ---------------------------------------------------------------------------


def test_wire_format_uses_camel_case_field_names() -> None:
    snapshot = SessionSnapshot.from_state(_state())
    payload = snapshot.model_dump(by_alias=True)

    assert "sessionId" in payload
    assert "workflowState" in payload
    assert "questionGroups" in payload
    assert "session_id" not in payload


def test_enum_values_stay_snake_case_because_they_are_data() -> None:
    payload = ErrorResponse(
        error_code=ErrorCode.SESSION_EXPIRED,
        current_state=WorkflowState.COLLECT_MISSING_FIELDS,
    ).model_dump(by_alias=True, mode="json")

    assert payload["errorCode"] == "session_expired"
    assert payload["currentState"] == "collect_missing_fields"


def test_camel_case_input_is_accepted_from_the_client() -> None:
    request = AdvanceRequest.model_validate(
        {"input": {"kind": "item_decline", "itemId": "survivor_pension"}}
    )

    assert request.input.item_id == "survivor_pension"


# ---------------------------------------------------------------------------
# 走鐘檢查：與前端型別比對
# ---------------------------------------------------------------------------


def _iter_input_models() -> list[tuple[str, type[BaseModel]]]:
    """列出七種輸入形狀及其 kind 值。"""
    adapter = TypeAdapter(AdvanceInput)
    mapping = adapter.core_schema["choices"]
    return [(kind, schema["cls"]) for kind, schema in mapping.items()]


def _read_types_source() -> str:
    assert _TYPES_FILE.exists(), f"找不到前端型別檔案：{_TYPES_FILE}"
    return _TYPES_FILE.read_text(encoding="utf-8")


def _typescript_object_fields(source: str, type_name: str) -> set[str]:
    """取出一個 TypeScript 物件型別宣告裡的屬性名稱。"""
    match = re.search(
        rf"export type {type_name} = \{{(.*?)\n\}};",
        source,
        re.DOTALL,
    )
    assert match, f"前端型別檔案裡找不到 {type_name}"

    body = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.DOTALL)
    body = re.sub(r"//.*", "", body)

    return set(re.findall(r"^\s{2}(\w+)\??:", body, re.MULTILINE))


def _typescript_union_values(source: str, type_name: str) -> set[str]:
    """取出一個 TypeScript 字串聯集型別的所有值。"""
    match = re.search(rf"export type {type_name} =(.*?);", source, re.DOTALL)
    assert match, f"前端型別檔案裡找不到 {type_name}"

    return set(re.findall(r'"([^"]+)"', match.group(1)))


@pytest.mark.parametrize(
    ("model", "type_name"),
    [
        (SessionSnapshot, "SessionSnapshot"),
        (ItemView, "ItemView"),
        (DecisiveConditionView, "DecisiveConditionView"),
        (CitationView, "CitationView"),
        (QuestionView, "QuestionView"),
        (QuestionGroupView, "QuestionGroupView"),
        (ImplementationNotice, "ImplementationNotice"),
        (ErrorResponse, "ErrorResponse"),
        (LifeEventTextInput, "LifeEventTextInput"),
        (AttributeAnswersInput, "AttributeAnswersInput"),
    ],
)
def test_frontend_types_match_the_backend_field_names(
    model: type[BaseModel], type_name: str
) -> None:
    """欄位名稱兩邊必須一致，比對的是對外的 camelCase 名稱。"""
    source = _read_types_source()

    backend_fields = {field.alias or name for name, field in model.model_fields.items()}

    assert _typescript_object_fields(source, type_name) == backend_fields


@pytest.mark.parametrize(
    ("enum_type", "type_name"),
    [
        (WorkflowState, "WorkflowState"),
        (ItemKind, "ItemKind"),
        (ItemStatus, "ItemStatus"),
        (AmountPeriod, "AmountPeriod"),
        (ExitReason, "ExitReason"),
        (AttributeValueKind, "AttributeValueKind"),
        (PendingCapability, "PendingCapability"),
        (ErrorCode, "ErrorCode"),
    ],
)
def test_frontend_unions_match_the_backend_enum_values(
    enum_type: type, type_name: str
) -> None:
    source = _read_types_source()

    assert _typescript_union_values(source, type_name) == {
        member.value for member in enum_type
    }


def test_the_text_length_limit_is_stated_on_both_sides() -> None:
    source = _read_types_source()

    match = re.search(r"MAX_LIFE_EVENT_TEXT_LENGTH = (\d+)", source)
    assert match, "前端型別檔案裡找不到 MAX_LIFE_EVENT_TEXT_LENGTH"
    assert int(match.group(1)) == MAX_LIFE_EVENT_TEXT_LENGTH
