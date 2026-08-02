"""Database-backed integration coverage for Case 2.

The seed remains candidate-only: these tests verify retrieval and relevance
filtering, never an eligibility approval.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app.llm.fake import FakeLanguageModel
from app.llm.port import LlmTask
from app.main import create_app
from app.orchestration.session_store import SESSION_ID_HEADER


def _client(tmp_path: Path) -> TestClient:
    client = TestClient(create_app(db_path=tmp_path / "case2.db"))
    client.app.state.language_model = FakeLanguageModel(
        responses={
            LlmTask.RESOLVE_LIFE_EVENT: {
                "event_ids": ["occupational_injury", "long_term_care_need"]
            }
        }
    )
    return client


def _advance_to_questions(client: TestClient) -> tuple[str, dict]:
    created = client.post("/sessions").json()
    session_id = created["sessionId"]
    headers = {SESSION_ID_HEADER: session_id}
    described = client.post(
        "/sessions/advance",
        headers=headers,
        json={"input": {"kind": "life_event_text", "text": "父親職災後需要長照"}},
    )
    assert described.status_code == 200
    confirmed = client.post(
        "/sessions/advance",
        headers=headers,
        json={
            "input": {
                "kind": "event_confirmation",
                "confirmed": True,
                "event_ids": ["occupational_injury", "long_term_care_need"],
            }
        },
    )
    assert confirmed.status_code == 200
    return session_id, confirmed.json()


def test_migration_seeds_candidate_programs_graph_and_evidence(tmp_path: Path) -> None:
    database = tmp_path / "case2.db"
    with _client(tmp_path):
        pass

    with closing(sqlite3.connect(database)) as connection:
        program_count = connection.execute(
            """
            SELECT COUNT(*) FROM benefit_programs
            WHERE program_id IN (
                'occupational_injury_recognition_follow_up',
                'occupational_accident_disability_benefit',
                'disability_assessment',
                'long_term_care_assessment',
                'caregiver_support_services',
                'caregiver_employment_support',
                'caregiver_support_contact'
            ) AND program_status = 'candidate'
            """
        ).fetchone()[0]
        evidence_statuses = connection.execute(
            "SELECT DISTINCT review_status FROM evidence_excerpts"
        ).fetchall()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert program_count == 7
    assert evidence_statuses == [("candidate",)]
    assert foreign_key_errors == []


def test_case2_questions_and_results_come_from_database(tmp_path: Path) -> None:
    client = _client(tmp_path)
    session_id, questions = _advance_to_questions(client)
    headers = {SESSION_ID_HEADER: session_id}

    assert [item["itemId"] for item in questions["items"]] == [
        "occupational_injury_recognition_follow_up",
        "occupational_accident_disability_benefit",
        "disability_assessment",
        "long_term_care_assessment",
        "caregiver_support_services",
        "caregiver_employment_support",
        "caregiver_support_contact",
    ]
    assert sum(len(group["questions"]) for group in questions["questionGroups"]) == 7

    response = client.post(
        "/sessions/advance",
        headers=headers,
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
    assert {item["status"] for item in body["items"]} == {"needs_human_review"}
    assert all(item["displayName"] and item["summary"] for item in body["items"])
    assert all(item["citations"] for item in body["items"])


def test_case2_answers_filter_database_candidates_conservatively(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    session_id, _ = _advance_to_questions(client)
    response = client.post(
        "/sessions/advance",
        headers={SESSION_ID_HEADER: session_id},
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
    assert all(item["status"] == "needs_human_review" for item in items)
