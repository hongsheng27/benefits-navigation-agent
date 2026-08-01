"""Integration test: fake startup proves zero-DB operation end-to-end.

Verifies that create_app() with all fakes:
- Opens zero sqlite3 connections during construction
- Serves the health endpoint without touching SQLite
- Creates sessions without database access
- Advances sessions without database access
- Completes a full request flow using only in-memory fakes

Requirements traced: 1.3, 2.5–2.10, 14.5, 14.6, 14.10.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import make_all_fakes_overrides


class TestFakeStartupZeroDB:
    """Prove that the application operates with zero database connections."""

    def test_app_construction_zero_db_opens(self) -> None:
        """create_app with all fakes opens zero sqlite3 connections."""
        with patch("sqlite3.connect") as mock_connect:
            _app = create_app(make_all_fakes_overrides())
            mock_connect.assert_not_called()

    def test_health_check_zero_db(self) -> None:
        """Health endpoint with fake app opens zero DB connections."""
        with patch("sqlite3.connect") as mock_connect:
            app = create_app(make_all_fakes_overrides())
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            mock_connect.assert_not_called()

    def test_session_create_zero_db(self) -> None:
        """POST /sessions with fake app opens zero DB connections."""
        with patch("sqlite3.connect") as mock_connect:
            app = create_app(make_all_fakes_overrides())
            client = TestClient(app)
            resp = client.post("/sessions")
            assert resp.status_code == 201
            mock_connect.assert_not_called()

    def test_session_advance_zero_db(self) -> None:
        """POST /sessions/advance with fake app opens zero DB connections."""
        with patch("sqlite3.connect") as mock_connect:
            app = create_app(make_all_fakes_overrides())
            client = TestClient(app)
            # Create session first
            resp = client.post("/sessions")
            assert resp.status_code == 201
            session_id = resp.json()["sessionId"]
            # Advance
            resp = client.post(
                "/sessions/advance",
                json={"input": {"kind": "life_event_text", "text": "配偶過世"}},
                headers={"X-Session-Id": session_id},
            )
            assert resp.status_code == 200
            mock_connect.assert_not_called()

    def test_full_flow_functional(self) -> None:
        """Full request flow works with only fakes — no real data needed."""
        app = create_app(make_all_fakes_overrides())
        client = TestClient(app)

        resp = client.post("/sessions")
        assert resp.status_code == 201
        data = resp.json()
        session_id = data["sessionId"]

        resp = client.post(
            "/sessions/advance",
            json={"input": {"kind": "life_event_text", "text": "配偶過世"}},
            headers={"X-Session-Id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "workflowState" in data
