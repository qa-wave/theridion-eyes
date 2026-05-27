"""Tests for the request diff API endpoint."""

from __future__ import annotations

import json
import os
import tempfile
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.main import create_app


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_collection(client: AsyncClient, name: str = "Test") -> dict:
    resp = await client.post("/api/collections", json={"name": name})
    assert resp.status_code in (200, 201)
    return resp.json()


async def _save_request(client: AsyncClient, collection_id: str, **kwargs) -> dict:
    payload = {
        "name": kwargs.get("name", "req"),
        "method": kwargs.get("method", "GET"),
        "url": kwargs.get("url", "http://example.com"),
        "headers": kwargs.get("headers", {}),
        "body": kwargs.get("body", None),
        "auth": kwargs.get("auth", None),
    }
    resp = await client.post(f"/api/collections/{collection_id}/requests", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # Return the last item added
    items = data["items"]
    return items[-1]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_diff_identical_requests(client: AsyncClient):
    """Two identical requests should produce no changes."""
    col = await _create_collection(client)
    req1 = await _save_request(client, col["id"], name="r1", url="http://a.com", method="POST",
                               headers={"X-Foo": "bar"}, body='{"key": "val"}')
    req2 = await _save_request(client, col["id"], name="r2", url="http://a.com", method="POST",
                               headers={"X-Foo": "bar"}, body='{"key": "val"}')

    resp = await client.post("/api/requests/diff", json={
        "left": {"collection_id": col["id"], "request_id": req1["id"]},
        "right": {"collection_id": col["id"], "request_id": req2["id"]},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["method_changed"] is False
    assert data["url_diff"] is None
    assert data["header_changes"] == []
    assert data["body_diff"] is None
    assert data["auth_diff"] is None
    assert data["summary"] == "No changes"


@pytest.mark.anyio
async def test_diff_url_change(client: AsyncClient):
    """URL difference should be reported."""
    col = await _create_collection(client)
    req1 = await _save_request(client, col["id"], name="r1", url="http://old.com/api")
    req2 = await _save_request(client, col["id"], name="r2", url="http://new.com/api")

    resp = await client.post("/api/requests/diff", json={
        "left": {"collection_id": col["id"], "request_id": req1["id"]},
        "right": {"collection_id": col["id"], "request_id": req2["id"]},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["url_diff"] is not None
    assert data["url_diff"]["left"] == "http://old.com/api"
    assert data["url_diff"]["right"] == "http://new.com/api"


@pytest.mark.anyio
async def test_diff_header_additions_removals(client: AsyncClient):
    """Added and removed headers should be detected."""
    col = await _create_collection(client)
    req1 = await _save_request(client, col["id"], name="r1",
                               headers={"Authorization": "Bearer x", "X-Old": "val"})
    req2 = await _save_request(client, col["id"], name="r2",
                               headers={"Authorization": "Bearer y", "X-New": "val2"})

    resp = await client.post("/api/requests/diff", json={
        "left": {"collection_id": col["id"], "request_id": req1["id"]},
        "right": {"collection_id": col["id"], "request_id": req2["id"]},
    })
    assert resp.status_code == 200
    data = resp.json()
    changes = data["header_changes"]
    names = {c["name"]: c for c in changes}
    assert "Authorization" in names
    assert names["Authorization"]["type"] == "changed"
    assert "X-Old" in names
    assert names["X-Old"]["type"] == "removed"
    assert "X-New" in names
    assert names["X-New"]["type"] == "added"


@pytest.mark.anyio
async def test_diff_body_json(client: AsyncClient):
    """JSON body structural diff should report changes."""
    col = await _create_collection(client)
    req1 = await _save_request(client, col["id"], name="r1",
                               body=json.dumps({"name": "Alice", "age": 30}))
    req2 = await _save_request(client, col["id"], name="r2",
                               body=json.dumps({"name": "Bob", "age": 30, "email": "b@x.com"}))

    resp = await client.post("/api/requests/diff", json={
        "left": {"collection_id": col["id"], "request_id": req1["id"]},
        "right": {"collection_id": col["id"], "request_id": req2["id"]},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["body_diff"] is not None
    assert data["body_diff"]["format"] == "json"
    paths = [c["path"] for c in data["body_diff"]["changes"]]
    assert "$.name" in paths
    assert "$.email" in paths
    # age unchanged
    assert "$.age" not in paths
    assert len(data["body_diff"]["unified"]) > 0


@pytest.mark.anyio
async def test_diff_auth_change(client: AsyncClient):
    """Auth type change should be detected."""
    col = await _create_collection(client)
    req1 = await _save_request(client, col["id"], name="r1",
                               auth={"type": "bearer", "token": "abc123"})
    req2 = await _save_request(client, col["id"], name="r2",
                               auth={"type": "basic", "username": "user", "password": "pass"})

    resp = await client.post("/api/requests/diff", json={
        "left": {"collection_id": col["id"], "request_id": req1["id"]},
        "right": {"collection_id": col["id"], "request_id": req2["id"]},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["auth_diff"] is not None
    assert data["auth_diff"]["left_type"] == "bearer"
    assert data["auth_diff"]["right_type"] == "basic"
    assert "Type changed" in data["auth_diff"]["details"]


@pytest.mark.anyio
async def test_diff_nonexistent_request_404(client: AsyncClient):
    """Referencing a non-existent request should return 404."""
    col = await _create_collection(client)
    req1 = await _save_request(client, col["id"], name="r1")
    fake_id = str(uuid.uuid4())

    resp = await client.post("/api/requests/diff", json={
        "left": {"collection_id": col["id"], "request_id": req1["id"]},
        "right": {"collection_id": col["id"], "request_id": fake_id},
    })
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_diff_nonexistent_collection_404(client: AsyncClient):
    """Referencing a non-existent collection should return 404."""
    fake_col = str(uuid.uuid4())
    fake_req = str(uuid.uuid4())

    resp = await client.post("/api/requests/diff", json={
        "left": {"collection_id": fake_col, "request_id": fake_req},
        "right": {"collection_id": fake_col, "request_id": fake_req},
    })
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_diff_method_change(client: AsyncClient):
    """Method change should be flagged."""
    col = await _create_collection(client)
    req1 = await _save_request(client, col["id"], name="r1", method="GET")
    req2 = await _save_request(client, col["id"], name="r2", method="POST")

    resp = await client.post("/api/requests/diff", json={
        "left": {"collection_id": col["id"], "request_id": req1["id"]},
        "right": {"collection_id": col["id"], "request_id": req2["id"]},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["method_changed"] is True
