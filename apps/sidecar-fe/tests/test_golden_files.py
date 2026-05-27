"""Tests for golden file storage and comparison."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    # Force re-import to pick up env
    from theridion_sidecar.main import create_app

    app = create_app()
    return TestClient(app)


def test_save_and_retrieve(client: TestClient):
    """Save a golden file and retrieve it."""
    resp = client.post("/api/golden/save", json={
        "name": "GET users",
        "url": "https://api.example.com/users",
        "method": "GET",
        "status": 200,
        "headers": {"content-type": "application/json"},
        "body": '{"users": []}',
        "description": "Empty user list baseline",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "GET users"
    assert data["url"] == "https://api.example.com/users"
    assert data["status"] == 200
    assert data["body_size"] == len('{"users": []}'.encode())
    golden_id = data["id"]

    # Retrieve
    resp2 = client.get(f"/api/golden/{golden_id}")
    assert resp2.status_code == 200
    assert resp2.json()["id"] == golden_id
    assert resp2.json()["body"] == '{"users": []}'


def test_list_golden(client: TestClient):
    """List returns saved golden files."""
    client.post("/api/golden/save", json={
        "url": "https://api.example.com/a",
        "method": "GET",
        "status": 200,
        "body": "a",
    })
    client.post("/api/golden/save", json={
        "url": "https://api.example.com/b",
        "method": "POST",
        "status": 201,
        "body": "b",
    })
    resp = client.get("/api/golden")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2


def test_compare_matching(client: TestClient):
    """Compare with identical response gives 100% match."""
    resp = client.post("/api/golden/save", json={
        "url": "https://api.example.com/users",
        "method": "GET",
        "status": 200,
        "headers": {"content-type": "application/json"},
        "body": '{"users": ["alice"]}',
    })
    golden_id = resp.json()["id"]

    compare_resp = client.post("/api/golden/compare", json={
        "golden_id": golden_id,
        "current": {
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": '{"users": ["alice"]}',
        },
    })
    assert compare_resp.status_code == 200
    result = compare_resp.json()
    assert result["match"] is True
    assert result["status_match"] is True
    assert result["body_match"] is True
    assert result["score"] == 1.0
    assert result["header_changes"] == []


def test_compare_with_differences(client: TestClient):
    """Compare with changed body and status."""
    resp = client.post("/api/golden/save", json={
        "url": "https://api.example.com/users",
        "method": "GET",
        "status": 200,
        "headers": {"content-type": "application/json", "x-request-id": "abc"},
        "body": '{"users": ["alice"]}',
    })
    golden_id = resp.json()["id"]

    # Different status, body, and headers
    compare_resp = client.post("/api/golden/compare", json={
        "golden_id": golden_id,
        "current": {
            "status": 201,
            "headers": {"content-type": "text/plain", "x-new": "yes"},
            "body": '{"users": ["alice", "bob"]}',
        },
    })
    assert compare_resp.status_code == 200
    result = compare_resp.json()
    assert result["match"] is False
    assert result["status_match"] is False
    assert result["body_match"] is False
    assert result["score"] < 1.0
    # Header changes
    changes = result["header_changes"]
    types = {c["type"] for c in changes}
    assert "removed" in types or "changed" in types or "added" in types
    # Body diff has additions/deletions
    assert result["body_diff"]["additions"] > 0 or result["body_diff"]["deletions"] > 0


def test_auto_compare_finds_by_url(client: TestClient):
    """Auto-compare finds matching golden file by URL and method."""
    client.post("/api/golden/save", json={
        "url": "https://api.example.com/health",
        "method": "GET",
        "status": 200,
        "body": '{"status": "ok"}',
    })

    resp = client.post("/api/golden/auto-compare", json={
        "url": "https://api.example.com/health",
        "method": "GET",
        "status": 200,
        "headers": {},
        "body": '{"status": "ok"}',
    })
    assert resp.status_code == 200
    result = resp.json()
    assert result["found"] is True
    assert result["golden_id"] is not None
    assert result["comparison"]["match"] is True


def test_auto_compare_no_match(client: TestClient):
    """Auto-compare returns found=false when no golden exists."""
    resp = client.post("/api/golden/auto-compare", json={
        "url": "https://api.example.com/nonexistent",
        "method": "GET",
        "status": 200,
        "headers": {},
        "body": "",
    })
    assert resp.status_code == 200
    result = resp.json()
    assert result["found"] is False
    assert result["comparison"] is None


def test_delete_golden(client: TestClient):
    """Delete removes the golden file."""
    resp = client.post("/api/golden/save", json={
        "url": "https://api.example.com/del",
        "method": "DELETE",
        "status": 204,
        "body": "",
    })
    golden_id = resp.json()["id"]

    del_resp = client.delete(f"/api/golden/{golden_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Should be 404 now
    get_resp = client.get(f"/api/golden/{golden_id}")
    assert get_resp.status_code == 404


def test_delete_nonexistent(client: TestClient):
    """Delete of nonexistent ID returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = client.delete(f"/api/golden/{fake_id}")
    assert resp.status_code == 404
