"""Tests for record-and-replay mock server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    # Reset global state before each test so tests are isolated.
    import theridion_sidecar.api.mock_record as mr

    mr._record_session = None
    mr._replay_handle = None

    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Record endpoints
# ---------------------------------------------------------------------------


class TestRecordStartStop:
    def test_start_returns_session(self, client: TestClient) -> None:
        resp = client.post(
            "/api/mock/record/start",
            json={"target_url": "http://example.com", "port": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert data["target_url"] == "http://example.com"
        assert isinstance(data["port"], int)

        # Stop it
        stop = client.post("/api/mock/record/stop")
        assert stop.status_code == 200
        assert stop.json()["session_id"] == data["session_id"]

    def test_double_start_conflict(self, client: TestClient) -> None:
        client.post(
            "/api/mock/record/start",
            json={"target_url": "http://example.com", "port": 0},
        )
        resp = client.post(
            "/api/mock/record/start",
            json={"target_url": "http://other.com", "port": 0},
        )
        assert resp.status_code == 409

        # Cleanup
        client.post("/api/mock/record/stop")

    def test_stop_without_session_404(self, client: TestClient) -> None:
        resp = client.post("/api/mock/record/stop")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Interactions storage / retrieval
# ---------------------------------------------------------------------------


class TestInteractions:
    def test_interactions_empty_lists_recordings(self, client: TestClient) -> None:
        resp = client.get("/api/mock/record/interactions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["interactions"] == []
        assert isinstance(data["recordings"], list)

    def test_interactions_during_session(self, client: TestClient) -> None:
        client.post(
            "/api/mock/record/start",
            json={"target_url": "http://example.com", "port": 0},
        )
        resp = client.get("/api/mock/record/interactions")
        assert resp.status_code == 200
        assert resp.json()["session_id"] is not None
        # No interactions recorded yet (we haven't made any proxy calls)
        assert resp.json()["interactions"] == []

        client.post("/api/mock/record/stop")

    def test_saved_recording_loads(self, client: TestClient, tmp_path: Path) -> None:
        # Manually write a recording file
        rec_dir = tmp_path / "mock_recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        recording_id = "test-rec-123"
        interactions = [
            {
                "method": "GET",
                "path": "/api/users",
                "query": "",
                "request_headers": {},
                "request_body": None,
                "status": 200,
                "response_headers": {"content-type": "application/json"},
                "response_body": '{"users": []}',
                "elapsed_ms": 42.0,
                "timestamp": 1700000000.0,
            }
        ]
        (rec_dir / f"{recording_id}.json").write_text(json.dumps(interactions))

        resp = client.get(
            "/api/mock/record/interactions",
            params={"recording_id": recording_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["interactions"]) == 1
        assert data["interactions"][0]["path"] == "/api/users"

    def test_load_nonexistent_recording_404(self, client: TestClient) -> None:
        resp = client.get(
            "/api/mock/record/interactions",
            params={"recording_id": "does-not-exist"},
        )
        assert resp.status_code == 404

    def test_stop_persists_recording(self, client: TestClient, tmp_path: Path) -> None:
        start = client.post(
            "/api/mock/record/start",
            json={"target_url": "http://example.com", "port": 0},
        )
        session_id = start.json()["session_id"]
        stop = client.post("/api/mock/record/stop")
        assert stop.status_code == 200
        assert stop.json()["file"] == f"{session_id}.json"

        rec_file = tmp_path / "mock_recordings" / f"{session_id}.json"
        assert rec_file.exists()


# ---------------------------------------------------------------------------
# Replay matching logic
# ---------------------------------------------------------------------------


class TestReplayMatching:
    """Test the replay app's matching logic directly (no real server)."""

    def test_exact_match(self) -> None:
        from theridion_sidecar.api.mock_record import (
            RecordedInteraction,
            _build_replay_app,
        )

        interactions = [
            RecordedInteraction(
                method="GET",
                path="/api/items",
                query="page=1",
                status=200,
                response_body='[{"id":1}]',
                response_headers={"content-type": "application/json"},
            ),
        ]
        app = _build_replay_app(interactions, fuzzy_query=False)
        from starlette.testclient import TestClient as StarletteClient

        tc = StarletteClient(app)
        # Exact match
        resp = tc.get("/api/items?page=1")
        assert resp.status_code == 200
        assert resp.json() == [{"id": 1}]

        # Different query — no match
        resp2 = tc.get("/api/items?page=2")
        assert resp2.status_code == 404

    def test_fuzzy_match(self) -> None:
        from theridion_sidecar.api.mock_record import (
            RecordedInteraction,
            _build_replay_app,
        )

        interactions = [
            RecordedInteraction(
                method="POST",
                path="/api/create",
                query="token=abc",
                status=201,
                response_body='{"created": true}',
                response_headers={"content-type": "application/json"},
            ),
        ]
        app = _build_replay_app(interactions, fuzzy_query=True)
        from starlette.testclient import TestClient as StarletteClient

        tc = StarletteClient(app)
        # Query differs but fuzzy is on — should match by method + path
        resp = tc.post("/api/create?token=different")
        assert resp.status_code == 201

    def test_method_mismatch(self) -> None:
        from theridion_sidecar.api.mock_record import (
            RecordedInteraction,
            _build_replay_app,
        )

        interactions = [
            RecordedInteraction(
                method="GET",
                path="/api/data",
                status=200,
                response_body="ok",
            ),
        ]
        app = _build_replay_app(interactions, fuzzy_query=True)
        from starlette.testclient import TestClient as StarletteClient

        tc = StarletteClient(app)
        resp = tc.post("/api/data")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Replay server start/stop/status
# ---------------------------------------------------------------------------


class TestReplayServer:
    def test_status_idle(self, client: TestClient) -> None:
        resp = client.get("/api/mock/replay/status")
        assert resp.status_code == 200
        assert resp.json()["running"] is False

    def test_start_with_inline_interactions(self, client: TestClient) -> None:
        resp = client.post(
            "/api/mock/replay/start",
            json={
                "interactions": [
                    {
                        "method": "GET",
                        "path": "/hello",
                        "query": "",
                        "request_headers": {},
                        "request_body": None,
                        "status": 200,
                        "response_headers": {},
                        "response_body": '{"msg":"hi"}',
                        "elapsed_ms": 10,
                        "timestamp": 0,
                    }
                ],
                "port": 0,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["route_count"] == 1

        # Status should show running
        status = client.get("/api/mock/replay/status")
        assert status.json()["running"] is True

        # Stop
        stop = client.post("/api/mock/replay/stop")
        assert stop.status_code == 200
        assert stop.json()["status"] == "stopped"

        # Status should show idle again
        status2 = client.get("/api/mock/replay/status")
        assert status2.json()["running"] is False

    def test_start_from_recording(self, client: TestClient, tmp_path: Path) -> None:
        rec_dir = tmp_path / "mock_recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        (rec_dir / "my-rec.json").write_text(
            json.dumps(
                [
                    {
                        "method": "GET",
                        "path": "/test",
                        "query": "",
                        "request_headers": {},
                        "request_body": None,
                        "status": 200,
                        "response_headers": {},
                        "response_body": "ok",
                        "elapsed_ms": 5,
                        "timestamp": 0,
                    }
                ]
            )
        )
        resp = client.post(
            "/api/mock/replay/start",
            json={"recording_id": "my-rec", "port": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["route_count"] == 1

        # Cleanup
        client.post("/api/mock/replay/stop")

    def test_double_start_conflict(self, client: TestClient) -> None:
        client.post(
            "/api/mock/replay/start",
            json={
                "interactions": [
                    {
                        "method": "GET",
                        "path": "/a",
                        "status": 200,
                        "response_body": "x",
                    }
                ],
                "port": 0,
            },
        )
        resp = client.post(
            "/api/mock/replay/start",
            json={
                "interactions": [
                    {
                        "method": "GET",
                        "path": "/b",
                        "status": 200,
                        "response_body": "y",
                    }
                ],
                "port": 0,
            },
        )
        assert resp.status_code == 409

        # Cleanup
        client.post("/api/mock/replay/stop")

    def test_stop_without_server_404(self, client: TestClient) -> None:
        resp = client.post("/api/mock/replay/stop")
        assert resp.status_code == 404

    def test_start_without_data_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/mock/replay/start",
            json={"port": 0},
        )
        assert resp.status_code == 400
