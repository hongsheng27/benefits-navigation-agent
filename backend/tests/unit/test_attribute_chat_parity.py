"""對話路徑與選擇題路徑寫入相同 attributes 後，應走到相同判定結果。"""

from datetime import UTC, datetime, timedelta

from app.llm.fake import FakeLanguageModel
from app.llm.port import LlmTask
from app.orchestration.state import (
    CandidateItem,
    ItemKind,
    ItemStatus,
    SessionState,
    WorkflowState,
)
from app.orchestration.state_machine import advance
from app.schemas.session import AttributeAnswersInput, AttributeChatTurnInput

_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def _collect_state() -> SessionState:
    return SessionState(
        session_id="s_parity",
        workflow_state=WorkflowState.COLLECT_MISSING_FIELDS,
        life_event="spouse_death",
        attributes={},
        items=(
            CandidateItem(
                item_id="funeral_benefit",
                kind=ItemKind.BENEFIT,
                program_status="candidate",
            ),
        ),
        created_at=_NOW,
        updated_at=_NOW,
        expires_at=_NOW + timedelta(hours=2),
    )


def test_chat_and_mcq_paths_record_same_jurisdiction() -> None:
    """同一所在地答案：對話抽取與選擇題寫入的 attributes 一致。"""
    mcq = advance(
        _collect_state(),
        AttributeAnswersInput(answers={"applicant_jurisdiction": "TPE"}),
    )
    chat = advance(
        _collect_state(),
        AttributeChatTurnInput(text="我住臺北市"),
        language_model=FakeLanguageModel(
            responses={
                LlmTask.COLLECT_ATTRIBUTES: {
                    "field_id": "applicant_jurisdiction",
                    "value": "TPE",
                    "confident": True,
                    "next_question": None,
                }
            }
        ),
    )

    assert mcq.attributes["applicant_jurisdiction"] == "TPE"
    assert chat.attributes["applicant_jurisdiction"] == "TPE"
    assert mcq.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS
    assert chat.workflow_state is WorkflowState.COLLECT_MISSING_FIELDS
    assert {item.item_id for item in mcq.items} == {item.item_id for item in chat.items}
    assert any(item.item_id == "taipei_green_funeral_incentive" for item in chat.items)
    # 仍缺投保身分時兩路徑都必須繼續追問，不可跳結果。
    funeral_mcq = next(i for i in mcq.items if i.item_id == "funeral_benefit")
    funeral_chat = next(i for i in chat.items if i.item_id == "funeral_benefit")
    assert funeral_mcq.status is ItemStatus.PENDING
    assert funeral_chat.status is ItemStatus.PENDING
