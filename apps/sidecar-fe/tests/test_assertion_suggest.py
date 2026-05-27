"""Tests for the assertion auto-suggest endpoint."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_suggest_user_object(client: AsyncClient):
    """Typical JSON API response with a user object."""
    body = json.dumps({
        "id": 42,
        "name": "John Doe",
        "email": "john@example.com",
        "role": "admin",
    })
    resp = await client.post("/api/assertions/suggest", json={
        "status": 200,
        "headers": {"content-type": "application/json"},
        "body": body,
        "elapsed_ms": 150,
    })
    assert resp.status_code == 200
    data = resp.json()
    suggestions = data["suggestions"]
    assert len(suggestions) > 0
    assert len(suggestions) <= 15

    # Status assertion always present
    types = [s["assertion"]["type"] for s in suggestions]
    assert "status" in types

    # Should have structure suggestions
    categories = {s["category"] for s in suggestions}
    assert "status" in categories
    assert "structure" in categories

    # Important fields (name, email, id) should trigger content suggestions
    assert "content" in categories

    # Confidence ordering
    confidences = [s["confidence"] for s in suggestions]
    assert confidences == sorted(confidences, reverse=True)


@pytest.mark.anyio
async def test_suggest_list_endpoint(client: AsyncClient):
    """Array response (list of items)."""
    body = json.dumps([
        {"id": 1, "title": "Item 1", "status": "active"},
        {"id": 2, "title": "Item 2", "status": "inactive"},
    ])
    resp = await client.post("/api/assertions/suggest", json={
        "status": 200,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": body,
        "elapsed_ms": 80,
    })
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) > 0

    # Should suggest structure checks for array elements
    paths = [s["assertion"]["path"] for s in suggestions if s["assertion"]["type"] == "json_path"]
    assert any("0." in p for p in paths)


@pytest.mark.anyio
async def test_suggest_error_response(client: AsyncClient):
    """4xx error response."""
    body = json.dumps({"error": "Not Found", "message": "User 999 does not exist"})
    resp = await client.post("/api/assertions/suggest", json={
        "status": 404,
        "headers": {"content-type": "application/json"},
        "body": body,
        "elapsed_ms": 30,
    })
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]

    # Status 404 suggestion
    status_suggestions = [s for s in suggestions if s["category"] == "status"]
    assert status_suggestions[0]["assertion"]["expected"] == "404"

    # Should have content suggestion for error message
    content_suggestions = [s for s in suggestions if s["category"] == "content"]
    assert len(content_suggestions) > 0


@pytest.mark.anyio
async def test_suggest_paginated_response(client: AsyncClient):
    """Response with pagination fields."""
    body = json.dumps({
        "data": [{"id": 1}],
        "page": 1,
        "total": 100,
        "limit": 20,
        "has_next": True,
    })
    resp = await client.post("/api/assertions/suggest", json={
        "status": 200,
        "headers": {"content-type": "application/json"},
        "body": body,
        "elapsed_ms": 200,
    })
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]

    # Should suggest assertions for pagination fields
    paths = [s["assertion"]["path"] for s in suggestions]
    assert any(p in ("page", "total", "limit", "has_next") for p in paths)


@pytest.mark.anyio
async def test_suggest_auth_token_response(client: AsyncClient):
    """Response containing auth tokens."""
    body = json.dumps({
        "access_token": "eyJhbGciOiJIUzI1NiJ9...",
        "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2g...",
        "expires_in": 3600,
        "token_type": "Bearer",
    })
    resp = await client.post("/api/assertions/suggest", json={
        "status": 200,
        "headers": {"content-type": "application/json"},
        "body": body,
        "elapsed_ms": 120,
    })
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]

    # Security category present for token fields
    security = [s for s in suggestions if s["category"] == "security"]
    assert len(security) > 0

    security_paths = [s["assertion"]["path"] for s in security]
    assert "access_token" in security_paths
    assert "refresh_token" in security_paths


@pytest.mark.anyio
async def test_suggest_empty_body(client: AsyncClient):
    """Empty body handling."""
    resp = await client.post("/api/assertions/suggest", json={
        "status": 204,
        "headers": {},
        "body": "",
        "elapsed_ms": 10,
    })
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]

    # Should still have status suggestion
    assert any(s["assertion"]["type"] == "status" for s in suggestions)
    # And performance
    assert any(s["category"] == "performance" for s in suggestions)


@pytest.mark.anyio
async def test_suggest_non_json_response(client: AsyncClient):
    """Non-JSON response (HTML, plain text)."""
    resp = await client.post("/api/assertions/suggest", json={
        "status": 200,
        "headers": {"content-type": "text/html; charset=utf-8"},
        "body": "<html><body>Hello World</body></html>",
        "elapsed_ms": 50,
    })
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]

    # Status and performance still suggested
    assert any(s["assertion"]["type"] == "status" for s in suggestions)
    # Content-Type header suggestion
    assert any(
        s["assertion"]["type"] == "header_equals" and "text/html" in s["assertion"]["expected"]
        for s in suggestions
    )
    # No json_path suggestions
    assert not any(s["assertion"]["type"] == "json_path" for s in suggestions)
