"""Tests for the traffic replay endpoint and diff engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


# ---------------------------------------------------------------------------
# HAR fixtures
# ---------------------------------------------------------------------------

def _make_har(entries: list[dict]) -> str:
    return json.dumps({
        "log": {
            "version": "1.2",
            "entries": entries,
        }
    })


def _har_entry(
    method: str = "GET",
    url: str = "https://example.com/api",
    status: int = 200,
    response_body: str = '{"ok": true}',
    elapsed: float = 42.0,
) -> dict:
    return {
        "request": {
            "method": method,
            "url": url,
            "headers": [{"name": "Accept", "value": "application/json"}],
        },
        "response": {
            "status": status,
            "headers": [{"name": "Content-Type", "value": "application/json"}],
            "content": {"text": response_body},
        },
        "time": elapsed,
    }


# ---------------------------------------------------------------------------
# Unit tests for the diff engine
# ---------------------------------------------------------------------------

def test_deep_diff_identical() -> None:
    from theridion_sidecar.api.replay import _deep_diff

    a = {"name": "Alice", "age": 30, "tags": ["a", "b"]}
    diffs = _deep_diff(a, a)
    assert diffs == []


def test_deep_diff_detects_changes() -> None:
    from theridion_sidecar.api.replay import _deep_diff

    a = {"name": "Alice", "age": 30}
    b = {"name": "Alice", "age": 31}
    diffs = _deep_diff(a, b)
    assert len(diffs) == 1
    assert diffs[0]["path"] == "age"
    assert diffs[0]["original"] == 30
    assert diffs[0]["replayed"] == 31


def test_deep_diff_added_removed_keys() -> None:
    from theridion_sidecar.api.replay import _deep_diff

    a = {"x": 1}
    b = {"y": 2}
    diffs = _deep_diff(a, b)
    paths = {d["path"] for d in diffs}
    assert "x" in paths
    assert "y" in paths


def test_deep_diff_respects_ignore() -> None:
    from theridion_sidecar.api.replay import _deep_diff

    a = {"name": "Alice", "timestamp": "old"}
    b = {"name": "Alice", "timestamp": "new"}
    diffs = _deep_diff(a, b, ignore={"timestamp"})
    assert diffs == []


def test_deep_diff_nested_objects() -> None:
    from theridion_sidecar.api.replay import _deep_diff

    a = {"data": {"id": 1, "status": "active"}}
    b = {"data": {"id": 1, "status": "inactive"}}
    diffs = _deep_diff(a, b)
    assert len(diffs) == 1
    assert diffs[0]["path"] == "data.status"


def test_deep_diff_arrays() -> None:
    from theridion_sidecar.api.replay import _deep_diff

    a = [1, 2, 3]
    b = [1, 2, 4]
    diffs = _deep_diff(a, b)
    assert len(diffs) == 1
    assert diffs[0]["path"] == "[2]"


# ---------------------------------------------------------------------------
# HAR parsing
# ---------------------------------------------------------------------------

def test_parse_har_entries() -> None:
    from theridion_sidecar.api.replay import _parse_har_entries

    har = _make_har([
        _har_entry(method="GET", url="https://example.com/users", status=200),
        _har_entry(method="POST", url="https://example.com/users", status=201),
    ])
    entries = _parse_har_entries(har)
    assert len(entries) == 2
    assert entries[0]["method"] == "GET"
    assert entries[1]["method"] == "POST"
    assert entries[0]["original_status"] == 200
    assert entries[1]["original_status"] == 201


def test_parse_har_invalid_json() -> None:
    from theridion_sidecar.api.replay import _parse_har_entries
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _parse_har_entries("not json")
    assert exc_info.value.status_code == 400


def test_parse_har_no_entries() -> None:
    from theridion_sidecar.api.replay import _parse_har_entries
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _parse_har_entries(json.dumps({"log": {"entries": []}}))
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Integration: from-har endpoint (mocked httpx)
# ---------------------------------------------------------------------------

def test_replay_from_har_endpoint(client: TestClient) -> None:
    """POST /api/replay/from-har should parse HAR and return diff results."""
    har = _make_har([_har_entry()])

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = '{"ok": true}'
    mock_response.headers = {"Content-Type": "application/json"}

    with patch("theridion_sidecar.api.replay.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.request = AsyncMock(return_value=mock_response)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        res = client.post("/api/replay/from-har", json={
            "har_content": har,
        })

    assert res.status_code == 200
    data = res.json()
    assert data["total_requests"] == 1
    assert data["replayed"] == 1
    assert data["matches"] == 1
    assert data["diffs"] == 0
    assert data["errors"] == 0


def test_replay_from_har_detects_status_diff(client: TestClient) -> None:
    """Should detect when replay status differs from original."""
    har = _make_har([_har_entry(status=200)])

    mock_response = AsyncMock()
    mock_response.status_code = 404
    mock_response.text = '{"error": "not found"}'
    mock_response.headers = {"Content-Type": "application/json"}

    with patch("theridion_sidecar.api.replay.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.request = AsyncMock(return_value=mock_response)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        res = client.post("/api/replay/from-har", json={
            "har_content": har,
        })

    assert res.status_code == 200
    data = res.json()
    assert data["diffs"] == 1
    result = data["results"][0]
    assert result["status_match"] is False
    assert result["original_status"] == 200
    assert result["replay_status"] == 404


# ---------------------------------------------------------------------------
# Collection replay
# ---------------------------------------------------------------------------

def test_replay_collection_not_found(client: TestClient) -> None:
    res = client.post("/api/replay/run-collection", json={
        "collection_id": "00000000-0000-0000-0000-000000000000",
    })
    assert res.status_code == 404


def test_replay_collection(client: TestClient) -> None:
    """Create a collection with a request and replay it."""
    # Create collection with a request.
    coll_res = client.post("/api/collections", json={"name": "Replay Test"})
    coll_id = coll_res.json()["id"]
    client.post(f"/api/collections/{coll_id}/requests", json={
        "name": "Get Users",
        "method": "GET",
        "url": "https://httpbin.org/get",
    })

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = '{"ok": true}'
    mock_response.headers = {"Content-Type": "application/json"}

    with patch("theridion_sidecar.api.replay.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.request = AsyncMock(return_value=mock_response)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        res = client.post("/api/replay/run-collection", json={
            "collection_id": coll_id,
        })

    assert res.status_code == 200
    data = res.json()
    assert data["total_requests"] == 1
    assert data["replayed"] == 1
    assert data["collection_id"] == coll_id


def test_ignore_paths_filter() -> None:
    """Verify that ignore_paths actually suppresses diffs on those paths."""
    from theridion_sidecar.api.replay import _deep_diff, _normalize_ignore

    a = {"timestamp": "2024-01-01", "data": {"id": 1}}
    b = {"timestamp": "2025-01-01", "data": {"id": 1}}

    ignore = _normalize_ignore(["$.timestamp"])
    diffs = _deep_diff(a, b, ignore=ignore)
    assert diffs == []
