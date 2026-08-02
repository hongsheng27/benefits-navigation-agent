"""POST /sessions/current/explain 端點。"""

from fastapi.testclient import TestClient

from app.main import create_app
from app.llm.fake import FakeLanguageModel, UnavailableLanguageModel
from app.llm.port import LlmTask


def _client_with_model(model) -> TestClient:
    app = create_app()
    app.state.language_model = model
    return TestClient(app)


def _open_session(client: TestClient) -> str:
    created = client.post("/sessions")
    assert created.status_code == 201
    return created.json()["sessionId"]


def test_explain_returns_grounded_answer() -> None:
    client = _client_with_model(
        FakeLanguageModel(
            responses={
                LlmTask.ANSWER_WITH_REFERENCES: {
                    "answer": "依參考資料，完成後一個月內申請。"
                }
            }
        )
    )
    session_id = _open_session(client)
    response = client.post(
        "/sessions/current/explain",
        headers={"X-Session-Id": session_id},
        json={
            "question": "期限多久？",
            "panelKind": "related_provisions",
            "references": [
                {
                    "title": "新北市環保葬鼓勵金",
                    "body": "完成環保葬次日起1個月內臨櫃申辦",
                    "sourceUrl": "https://example.test/nwt",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json() == {"answer": "依參考資料，完成後一個月內申請。"}


def test_explain_unavailable_when_model_fails() -> None:
    client = _client_with_model(UnavailableLanguageModel())
    session_id = _open_session(client)
    response = client.post(
        "/sessions/current/explain",
        headers={"X-Session-Id": session_id},
        json={
            "question": "要帶什麼？",
            "panelKind": "application_guide",
            "references": [{"title": "步驟一", "body": "帶死亡證明"}],
        },
    )
    assert response.status_code == 503
    assert response.json()["errorCode"] == "explanation_unavailable"


def test_explain_requires_session_header() -> None:
    client = _client_with_model(
        FakeLanguageModel(
            responses={LlmTask.ANSWER_WITH_REFERENCES: {"answer": "ok"}}
        )
    )
    response = client.post(
        "/sessions/current/explain",
        json={
            "question": "期限多久？",
            "panelKind": "related_provisions",
            "references": [{"title": "a", "body": "b"}],
        },
    )
    assert response.status_code == 401
