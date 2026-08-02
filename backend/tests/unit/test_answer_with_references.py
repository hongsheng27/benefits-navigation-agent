"""諮詢後 grounded 說明任務。"""

import pytest

from app.llm.fake import FakeLanguageModel, UnavailableLanguageModel
from app.llm.port import LlmTask
from app.llm.tasks.answer_with_references import (
    ExplanationUnavailableError,
    ReferenceExcerpt,
    answer_with_references,
    build_schema,
    build_user_content,
)


def test_schema_is_portable() -> None:
    build_schema()  # validate_portable_schema 會在內部執行


def test_user_content_includes_question_and_reference_bodies() -> None:
    content = build_user_content(
        "期限多久？",
        (
            ReferenceExcerpt(
                title="新北市環保葬鼓勵金",
                body="完成環保葬次日起1個月內臨櫃申辦",
                source_url="https://example.test/nwt",
            ),
        ),
        panel_kind="related_provisions",
    )
    assert "期限多久？" in content
    assert "新北市環保葬鼓勵金" in content
    assert "1個月內臨櫃申辦" in content
    assert "https://example.test/nwt" in content


def test_answer_returns_model_payload() -> None:
    model = FakeLanguageModel(
        responses={
            LlmTask.ANSWER_WITH_REFERENCES: {"answer": "請在一個月內臨櫃申請。"}
        }
    )
    answer = answer_with_references(
        "期限多久？",
        (ReferenceExcerpt(title="示範", body="一個月內申請"),),
        model=model,
        panel_kind="related_provisions",
    )
    assert answer == "請在一個月內臨櫃申請。"
    assert model.calls()[0].task is LlmTask.ANSWER_WITH_REFERENCES
    assert "一個月內申請" in model.calls()[0].user_content


def test_unavailable_model_raises_explanation_error() -> None:
    with pytest.raises(ExplanationUnavailableError):
        answer_with_references(
            "可不可以領？",
            (ReferenceExcerpt(title="示範", body="條件說明"),),
            model=UnavailableLanguageModel(),
            panel_kind="application_guide",
        )
