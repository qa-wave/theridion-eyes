"""Tests for the multi-environment parallel runner."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    return TestClient(create_app())


@pytest.fixture()
def storage_dir(tmp_path: Path) -> Path:
    return tmp_path


def _create_env(storage_dir: Path, name: str, variables: dict[str, str]) -> str:
    env_id = str(uuid.uuid4())
    envs_dir = storage_dir / "environments"
    envs_dir.mkdir(parents=True, exist_ok=True)
    env_data = {
        "id": env_id,
        "name": name,
        "variables": [
            {"name": k, "value": v, "enabled": True}
            for k, v in variables.items()
        ],
    }
    (envs_dir / f"{env_id}.json").write_text(json.dumps(env_data))
    return env_id


def _create_collection(storage_dir: Path, items: list[dict]) -> str:
    col_id = str(uuid.uuid4())
    cols_dir = storage_dir / "collections"
    cols_dir.mkdir(parents=True, exist_ok=True)
    col_data = {
        "id": col_id,
        "name": "Test Collection",
        "items": items,
    }
    (cols_dir / f"{col_id}.json").write_text(json.dumps(col_data))
    return col_id


def _mock_response(status_code: int = 200, text: str = "ok") -> httpx.Response:
    """Create a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        text=text,
        headers={"content-type": "text/plain"},
        request=httpx.Request("GET", "http://test"),
    )


def _make_async_client_mock(url_responses: dict[str, httpx.Response | Exception]):
    """Create a mock for httpx.AsyncClient that resolves URLs to responses."""

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
            for pattern, response in url_responses.items():
                if pattern in url:
                    if isinstance(response, Exception):
                        raise response
                    return response
            return _mock_response(status_code=404, text="not found")

    return FakeClient


def test_single_request_two_envs(client: TestClient, storage_dir: Path) -> None:
    """Run a single request against 2 environments with different base URLs."""
    env1_id = _create_env(storage_dir, "Staging", {"base_url": "http://staging.local"})
    env2_id = _create_env(storage_dir, "Production", {"base_url": "http://prod.local"})

    mock_client = _make_async_client_mock({
        "staging.local/health": _mock_response(200, '{"ok":true}'),
        "prod.local/health": _mock_response(200, '{"ok":true}'),
    })

    with patch("theridion_sidecar.api.multi_env_runner.httpx.AsyncClient", mock_client):
        resp = client.post("/api/runner/multi-env", json={
            "request": {
                "method": "GET",
                "url": "{{base_url}}/health",
                "headers": {},
            },
            "environment_ids": [env1_id, env2_id],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 2
    assert data["comparison"]["all_same_status"] is True
    assert data["comparison"]["fastest_env"] in ("Staging", "Production")
    assert data["comparison"]["slowest_env"] in ("Staging", "Production")


def test_comparison_different_statuses(client: TestClient, storage_dir: Path) -> None:
    """Comparison detects different status codes across envs."""
    env1_id = _create_env(storage_dir, "Staging", {"base_url": "http://staging.local"})
    env2_id = _create_env(storage_dir, "Production", {"base_url": "http://prod.local"})

    mock_client = _make_async_client_mock({
        "staging.local/api": _mock_response(200, "ok"),
        "prod.local/api": _mock_response(500, "error"),
    })

    with patch("theridion_sidecar.api.multi_env_runner.httpx.AsyncClient", mock_client):
        resp = client.post("/api/runner/multi-env", json={
            "request": {"method": "GET", "url": "{{base_url}}/api"},
            "environment_ids": [env1_id, env2_id],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["comparison"]["all_same_status"] is False


def test_error_handling_one_env_fails(client: TestClient, storage_dir: Path) -> None:
    """When one environment fails, the other still returns results."""
    env1_id = _create_env(storage_dir, "Working", {"base_url": "http://working.local"})
    env2_id = _create_env(storage_dir, "Broken", {"base_url": "http://broken.local"})

    mock_client = _make_async_client_mock({
        "working.local/test": _mock_response(200, "fine"),
        "broken.local/test": httpx.ConnectError("Connection refused"),
    })

    with patch("theridion_sidecar.api.multi_env_runner.httpx.AsyncClient", mock_client):
        resp = client.post("/api/runner/multi-env", json={
            "request": {"method": "GET", "url": "{{base_url}}/test"},
            "environment_ids": [env1_id, env2_id],
        })

    assert resp.status_code == 200
    data = resp.json()
    results = data["results"]
    working = next(r for r in results if r["env_name"] == "Working")
    broken = next(r for r in results if r["env_name"] == "Broken")
    assert working["status"] == 200
    assert working["error"] is None
    assert broken["error"] is not None
    assert broken["status"] is None


def test_empty_environment_list_validation(client: TestClient, storage_dir: Path) -> None:
    """Fewer than 2 environments should return 422."""
    env1_id = _create_env(storage_dir, "Only", {"base_url": "http://only.local"})

    resp = client.post("/api/runner/multi-env", json={
        "request": {"method": "GET", "url": "http://example.com"},
        "environment_ids": [env1_id],
    })

    assert resp.status_code == 422


def test_collection_run_multiple_envs(client: TestClient, storage_dir: Path) -> None:
    """Run entire collection against multiple environments."""
    env1_id = _create_env(storage_dir, "Dev", {"base_url": "http://dev.local"})
    env2_id = _create_env(storage_dir, "Prod", {"base_url": "http://prod.local"})

    col_id = _create_collection(storage_dir, [
        {"name": "Health", "method": "GET", "url": "{{base_url}}/health"},
        {"name": "Users", "method": "GET", "url": "{{base_url}}/users"},
    ])

    mock_client = _make_async_client_mock({
        "dev.local/health": _mock_response(200, "ok"),
        "prod.local/health": _mock_response(200, "ok"),
        "dev.local/users": _mock_response(200, '[{"id":1}]'),
        "prod.local/users": _mock_response(200, '[{"id":1},{"id":2}]'),
    })

    with patch("theridion_sidecar.api.multi_env_runner.httpx.AsyncClient", mock_client):
        resp = client.post("/api/runner/multi-env/collection", json={
            "collection_id": col_id,
            "environment_ids": [env1_id, env2_id],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 2
    assert data["rows"][0]["request_name"] == "Health"
    assert data["rows"][1]["request_name"] == "Users"
    # Users endpoint returns different body sizes
    assert data["rows"][1]["comparison"]["response_size_diff"] is True
    assert data["summary"]["fastest_env"] in ("Dev", "Prod")


def test_nonexistent_environment_returns_404(client: TestClient, storage_dir: Path) -> None:
    """Unknown environment ID should return 404."""
    env1_id = _create_env(storage_dir, "Real", {"base_url": "http://real.local"})
    fake_id = str(uuid.uuid4())

    resp = client.post("/api/runner/multi-env", json={
        "request": {"method": "GET", "url": "{{base_url}}/x"},
        "environment_ids": [env1_id, fake_id],
    })

    assert resp.status_code == 404


def test_nonexistent_collection_returns_404(client: TestClient, storage_dir: Path) -> None:
    """Unknown collection ID should return 404."""
    env1_id = _create_env(storage_dir, "A", {"base_url": "http://a.local"})
    env2_id = _create_env(storage_dir, "B", {"base_url": "http://b.local"})

    resp = client.post("/api/runner/multi-env/collection", json={
        "collection_id": str(uuid.uuid4()),
        "environment_ids": [env1_id, env2_id],
    })

    assert resp.status_code == 404


def test_legacy_endpoint_still_works(client: TestClient, storage_dir: Path) -> None:
    """Legacy /api/test/multi-env still returns the old format."""
    env1_id = _create_env(storage_dir, "A", {"base_url": "http://a.local"})
    env2_id = _create_env(storage_dir, "B", {"base_url": "http://b.local"})
    col_id = _create_collection(storage_dir, [
        {"name": "Ping", "method": "GET", "url": "{{base_url}}/ping"},
    ])

    mock_client = _make_async_client_mock({
        "a.local/ping": _mock_response(200, "pong"),
        "b.local/ping": _mock_response(200, "pong"),
    })

    with patch("theridion_sidecar.api.multi_env_runner.httpx.AsyncClient", mock_client):
        resp = client.post("/api/test/multi-env", json={
            "collection_id": col_id,
            "environment_ids": [env1_id, env2_id],
        })

    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "comparison" in data
    assert data["results"][0]["passed"] == 1
