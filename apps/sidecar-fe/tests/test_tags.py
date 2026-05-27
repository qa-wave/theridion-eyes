"""Tests for the /api/tags endpoints."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from theridion_sidecar.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app, tmp_path, monkeypatch):
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from httpx import ASGITransport

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def _create_collection_with_requests(client: AsyncClient) -> tuple[str, str, str]:
    """Helper: create a collection with two requests, return (coll_id, req1_id, req2_id)."""
    resp = await client.post("/api/collections", json={"name": "Tag Test"})
    assert resp.status_code in (200, 201)
    coll_id = resp.json()["id"]

    req1_id = str(uuid.uuid4())
    await client.post(
        f"/api/collections/{coll_id}/requests",
        json={"id": req1_id, "name": "Get Users", "method": "GET", "url": "http://example.com/users"},
    )

    req2_id = str(uuid.uuid4())
    await client.post(
        f"/api/collections/{coll_id}/requests",
        json={"id": req2_id, "name": "Create User", "method": "POST", "url": "http://example.com/users"},
    )

    return coll_id, req1_id, req2_id


@pytest.mark.anyio
async def test_assign_and_retrieve_tags(client: AsyncClient):
    coll_id, req1_id, _ = await _create_collection_with_requests(client)

    # Assign tags
    resp = await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req1_id, "tags": ["auth", "smoke"]},
    )
    assert resp.status_code == 200
    assert resp.json() == ["auth", "smoke"]

    # Verify in collection
    resp = await client.get(f"/api/collections/{coll_id}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    req = next(it for it in items if it["id"] == req1_id)
    assert req["tags"] == ["auth", "smoke"]


@pytest.mark.anyio
async def test_list_tags_with_counts(client: AsyncClient):
    coll_id, req1_id, req2_id = await _create_collection_with_requests(client)

    # Assign same tag to both requests
    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req1_id, "tags": ["smoke", "critical"]},
    )
    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req2_id, "tags": ["smoke"]},
    )

    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    tags_map = {t["tag"]: t["count"] for t in data["tags"]}
    assert tags_map["smoke"] == 2
    assert tags_map["critical"] == 1
    assert "suggestions" in data


@pytest.mark.anyio
async def test_search_by_single_tag(client: AsyncClient):
    coll_id, req1_id, req2_id = await _create_collection_with_requests(client)

    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req1_id, "tags": ["auth"]},
    )
    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req2_id, "tags": ["smoke"]},
    )

    resp = await client.get("/api/tags/search", params={"tags": "auth"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["request_id"] == req1_id


@pytest.mark.anyio
async def test_search_by_multiple_tags_any_mode(client: AsyncClient):
    coll_id, req1_id, req2_id = await _create_collection_with_requests(client)

    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req1_id, "tags": ["auth", "critical"]},
    )
    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req2_id, "tags": ["smoke"]},
    )

    # mode=any: either auth or smoke
    resp = await client.get("/api/tags/search", params={"tags": "auth,smoke", "mode": "any"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2


@pytest.mark.anyio
async def test_search_by_multiple_tags_all_mode(client: AsyncClient):
    coll_id, req1_id, req2_id = await _create_collection_with_requests(client)

    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req1_id, "tags": ["auth", "critical"]},
    )
    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req2_id, "tags": ["auth"]},
    )

    # mode=all: must have both auth AND critical
    resp = await client.get("/api/tags/search", params={"tags": "auth,critical", "mode": "all"})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["request_id"] == req1_id


@pytest.mark.anyio
async def test_bulk_assign(client: AsyncClient):
    coll_id, req1_id, req2_id = await _create_collection_with_requests(client)

    resp = await client.post(
        "/api/tags/bulk",
        json={"collection_id": coll_id, "request_ids": [req1_id, req2_id], "tags": ["regression"]},
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2

    # Verify both have the tag
    resp = await client.get("/api/tags/search", params={"tags": "regression"})
    assert len(resp.json()["results"]) == 2


@pytest.mark.anyio
async def test_remove_tag(client: AsyncClient):
    coll_id, req1_id, _ = await _create_collection_with_requests(client)

    await client.post(
        "/api/tags/assign",
        json={"collection_id": coll_id, "request_id": req1_id, "tags": ["auth", "smoke"]},
    )

    resp = await client.post(
        "/api/tags/remove",
        json={"collection_id": coll_id, "request_id": req1_id, "tag": "auth"},
    )
    assert resp.status_code == 200
    assert resp.json() == ["smoke"]
