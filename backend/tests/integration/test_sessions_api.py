"""驗證 session 端點：形狀、header 傳遞、錯誤碼，以及不外洩使用者輸入。

每個測試都建立一個獨立的應用程式實例，因為 session store 掛在 app 上。
"""

import pytest
from fastapi.testclient import TestClient

from app.llm.fake import FakeLanguageModel
from app.llm.port import LlmTask
from app.main import create_app
from app.orchestration.session_store import SESSION_ID_HEADER
from app.schemas.session import MAX_LIFE_EVENT_TEXT_LENGTH


@pytest.fixture
def client() -> TestClient:
    from app.application.composition import ApplicationOverrides
    from app.orchestration.protocols import (
        FixtureEligibilityService,
        FixtureEntitlementGraphRepository,
        FixtureEvidenceRepository,
        LocalSourceRefreshService,
    )

    overrides = ApplicationOverrides(
        graph_repository=FixtureEntitlementGraphRepository(),
        eligibility_service=FixtureEligibilityService(),
        evidence_repository=FixtureEvidenceRepository(),
        source_refresh_service=LocalSourceRefreshService(),
    )
    return TestClient(create_app(overrides))


def _create(client: TestClient) -> tuple[str, dict]:
    response = client.post("/sessions")
    assert response.status_code == 201
    body = response.json()
    return body["sessionId"], body


def _headers(session_id: str) -> dict[str, str]:
    return {SESSION_ID_HEADER: session_id}


def test_creating_a_session_returns_a_camel_case_snapshot(client: TestClient) -> None:
    session_id, body = _create(client)

    assert session_id
    assert body["workflowState"] == "understand_event"
    assert body["stepIndex"] == 1
    assert body["items"] == []
    assert body["questionGroups"] == []
    assert "session_id" not in body


def test_the_response_declares_which_capabilities_are_missing(
    client: TestClient,
) -> None:
    _, body = _create(client)

    notice = body["implementation"]
    assert notice["isMock"] is True
    assert "rule_evaluation" in notice["pending"]
    assert notice["placeholderNotice"]


def test_each_session_gets_its_own_identifier(client: TestClient) -> None:
    first, _ = _create(client)
    second, _ = _create(client)

    assert first != second


def test_advancing_with_text_then_confirming_reveals_items(
    client: TestClient,
) -> None:
    session_id, _ = _create(client)

    after_text = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": "我先生剛過世"}},
    )
    assert after_text.status_code == 200
    assert after_text.json()["lifeEvent"] == "spouse_death"

    confirmed = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "event_confirmation", "confirmed": True}},
    )
    assert confirmed.status_code == 200
    body = confirmed.json()
    # 確認事件後，狀態機自動推進到需要等使用者的 collect_missing_fields。
    assert body["workflowState"] == "collect_missing_fields"
    assert [item["itemId"] for item in body["items"]] == [
        "death_registration",
        "funeral_benefit",
        "survivor_pension",
        "health_insurance_change",
    ]
    assert all(item["status"] == "pending" for item in body["items"])


def test_case2_text_opens_occupational_injury_confirmation(
    client: TestClient,
) -> None:
    """案例 2：事件辨識後保存職災與長照，並停在確認狀態。"""
    client.app.state.language_model = FakeLanguageModel(
        responses={
            LlmTask.RESOLVE_LIFE_EVENT: {
                "event_ids": ["occupational_injury", "long_term_care_need"]
            }
        }
    )
    session_id, _ = _create(client)
    case_2_text = (
        "爸爸在工作中發生重大事故後失能，現在需要長期照顧。"
        "我一邊工作、一邊照顧兩歲的小孩，最近也因為照顧爸爸減少工時，"
        "不知道職災、身障和長照該先辦哪一個。"
    )

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": case_2_text}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflowState"] == "understand_event"
    assert body["lifeEvent"] == "occupational_injury"
    assert body["lifeEvents"] == ["occupational_injury", "long_term_care_need"]
    assert body["items"] == []
    assert case_2_text not in response.text


def _advance_case2_to_questions(client: TestClient) -> tuple[str, dict]:
    client.app.state.language_model = FakeLanguageModel(
        responses={
            LlmTask.RESOLVE_LIFE_EVENT: {
                "event_ids": ["occupational_injury", "long_term_care_need"]
            }
        }
    )
    session_id, _ = _create(client)
    client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": "父親工作受傷失能"}},
    )
    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "event_confirmation", "confirmed": True}},
    )
    assert response.status_code == 200
    return session_id, response.json()


def test_case2_confirmation_questions_and_demo_answers_reach_results(
    client: TestClient,
) -> None:
    """案例 2 的問題與結果都來自 backend snapshot，不靠 frontend demo scene。"""
    session_id, questions = _advance_case2_to_questions(client)

    assert questions["workflowState"] == "collect_missing_fields"
    assert len(questions["questionGroups"]) == 4
    assert sum(len(group["questions"]) for group in questions["questionGroups"]) == 7
    assert len(questions["items"]) == 7

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={
            "input": {
                "kind": "attribute_answers",
                "answers": {
                    "caregiver_relationship": "relationship_child",
                    "disability_cause": "cause_occupational_injury",
                    "occupational_injury_recognition": "recognition_processing",
                    "care_recipient_insurance_type": "occupational_accident_insurance",
                    "disability_assessment_status": "disability_assessment_not_applied",
                    "current_care_arrangement": "care_mostly_solo",
                    "caregiver_employment_impact": "reduced_hours",
                },
            }
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflowState"] == "confirm"
    assert [item["itemId"] for item in body["items"]] == [
        "occupational_injury_recognition_follow_up",
        "occupational_accident_disability_benefit",
        "disability_assessment",
        "long_term_care_assessment",
        "caregiver_support_services",
        "caregiver_employment_support",
        "caregiver_support_contact",
    ]
    assert {item["status"] for item in body["items"]} == {"needs_human_review"}
    assert all(item["citations"] == [] for item in body["items"])


def test_case2_answers_filter_items_without_making_eligibility_claims(
    client: TestClient,
) -> None:
    """固定答案只做相關性篩選；保留項目仍需人工確認。"""
    session_id, _ = _advance_case2_to_questions(client)

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={
            "input": {
                "kind": "attribute_answers",
                "answers": {
                    "caregiver_relationship": "relationship_child",
                    "disability_cause": "cause_general_accident",
                    "occupational_injury_recognition": "injury_recognized",
                    "care_recipient_insurance_type": "no_insurance",
                    "disability_assessment_status": "disability_certificate_obtained",
                    "current_care_arrangement": "hired_caregiver",
                    "caregiver_employment_impact": "no_employment_change",
                },
            }
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["itemId"] for item in items] == [
        "long_term_care_assessment",
        "caregiver_support_contact",
    ]
    assert {item["status"] for item in items} == {"needs_human_review"}


def test_the_submitted_text_never_appears_in_any_response(
    client: TestClient,
) -> None:
    """自由文字抽取後即丟棄，所以不會回到前端，也不會出現在後續查詢裡。"""
    session_id, _ = _create(client)
    secret = "這段文字不應該被保存"

    advance = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": secret}},
    )
    current = client.get("/sessions/current", headers=_headers(session_id))

    assert secret not in advance.text
    assert secret not in current.text


def test_reading_the_current_session_reflects_earlier_advances(
    client: TestClient,
) -> None:
    session_id, _ = _create(client)
    client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": "我先生剛過世"}},
    )

    response = client.get("/sessions/current", headers=_headers(session_id))

    assert response.status_code == 200
    assert response.json()["lifeEvent"] == "spouse_death"


def test_a_missing_header_is_unauthorized(client: TestClient) -> None:
    response = client.get("/sessions/current")

    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_not_found"


def test_an_unknown_session_is_not_found(client: TestClient) -> None:
    response = client.get("/sessions/current", headers=_headers("nope"))

    assert response.status_code == 404
    assert response.json() == {
        "errorCode": "session_not_found",
        "fieldIds": [],
        "currentState": None,
    }


def test_text_sent_at_the_wrong_step_is_a_conflict(client: TestClient) -> None:
    session_id, _ = _create(client)
    for payload in (
        {"kind": "life_event_text", "text": "我先生剛過世"},
        {"kind": "event_confirmation", "confirmed": True},
    ):
        client.post(
            "/sessions/advance", headers=_headers(session_id), json={"input": payload}
        )

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": "我父親剛過世"}},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["errorCode"] == "invalid_transition"
    # 自動推進後停在 collect_missing_fields，不是 resolve_entitlements。
    assert body["currentState"] == "collect_missing_fields"


def test_declining_an_unknown_item_is_reported(client: TestClient) -> None:
    session_id, _ = _create(client)
    # 先走到有 items 的狀態。
    client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": "我先生剛過世"}},
    )
    client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "event_confirmation", "confirmed": True}},
    )

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "item_decline", "itemId": "not_a_real_item"}},
    )

    assert response.status_code == 422
    assert response.json()["errorCode"] == "unknown_item"


def _advance_to_questions(client: TestClient) -> str:
    """建立 session 並走到會追問欄位的步驟，回傳 session_id。"""
    session_id, _ = _create(client)
    client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": "我先生剛過世"}},
    )
    client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "event_confirmation", "confirmed": True}},
    )
    return session_id


def test_an_unregistered_field_id_is_rejected_without_echoing_the_value(
    client: TestClient,
) -> None:
    """不在登記表上的欄位代號回 unknown_field，回應裡只有代號、沒有值。"""
    session_id = _advance_to_questions(client)
    secret = "這段文字不應該被保存"

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={
            "input": {
                "kind": "attribute_answers",
                "answers": {"totally_unknown_field": secret},
            }
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["errorCode"] == "unknown_field"
    assert body["fieldIds"] == ["totally_unknown_field"]
    assert body["currentState"] == "collect_missing_fields"
    assert secret not in response.text


def test_a_rejected_answer_set_leaves_the_session_untouched(
    client: TestClient,
) -> None:
    """一個已知 + 一個未知 → 整筆拒絕，attributes 完全沒被修改。"""
    session_id = _advance_to_questions(client)

    rejected = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={
            "input": {
                "kind": "attribute_answers",
                "answers": {
                    "deceased_insurance_type": "labor_insurance",
                    "totally_unknown_field": "編出來的代號",
                },
            }
        },
    )
    current = client.get("/sessions/current", headers=_headers(session_id))

    assert rejected.status_code == 422
    assert current.json()["attributes"] == {}
    assert current.json()["workflowState"] == "collect_missing_fields"


def test_registered_field_ids_are_recorded(client: TestClient) -> None:
    """全部都在登記表上就接受，答案回到快照裡。"""
    session_id = _advance_to_questions(client)

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={
            "input": {
                "kind": "attribute_answers",
                "answers": {"deceased_insurance_type": "labor_insurance"},
            }
        },
    )

    assert response.status_code == 200
    assert response.json()["attributes"] == {
        "deceased_insurance_type": "labor_insurance"
    }


def test_a_validation_error_reports_field_names_without_values(
    client: TestClient,
) -> None:
    """Pydantic 的錯誤訊息會引用原值，所以回應只留欄位名稱。"""
    session_id, _ = _create(client)
    overlong = "字" * (MAX_LIFE_EVENT_TEXT_LENGTH + 1)

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "life_event_text", "text": overlong}},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["errorCode"] == "invalid_field_value"
    # 路徑含判別值（`life_event_text`），因為那是輸入形狀的名稱，不是使用者的值。
    assert body["fieldIds"] == ["input.life_event_text.text"]
    assert "字" not in response.text


def test_an_unknown_input_kind_is_rejected(client: TestClient) -> None:
    session_id, _ = _create(client)

    response = client.post(
        "/sessions/advance",
        headers=_headers(session_id),
        json={"input": {"kind": "not_a_kind"}},
    )

    assert response.status_code == 422
    assert response.json()["errorCode"] == "invalid_field_value"


def test_deleting_the_session_removes_it(client: TestClient) -> None:
    session_id, _ = _create(client)

    deleted = client.delete("/sessions/current", headers=_headers(session_id))
    after = client.get("/sessions/current", headers=_headers(session_id))

    assert deleted.status_code == 204
    assert after.status_code == 404


def test_deleting_twice_still_succeeds(client: TestClient) -> None:
    """呼叫端的目的是「確保它不在了」，重複呼叫不算錯誤。"""
    session_id, _ = _create(client)

    client.delete("/sessions/current", headers=_headers(session_id))
    again = client.delete("/sessions/current", headers=_headers(session_id))

    assert again.status_code == 204
