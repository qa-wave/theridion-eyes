"""Tests for API Documentation Generator endpoint."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.main import app
from theridion_sidecar import storage
from theridion_sidecar.models import Collection, CollectionItem

BASE = "http://test"


@pytest.fixture(autouse=True)
def _tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))


def _create_collection(name: str = "Test API", items: list | None = None) -> Collection:
    """Create a collection with some requests for testing."""
    if items is None:
        items = [
            CollectionItem(
                id=str(uuid.uuid4()),
                name="Get Users",
                method="GET",
                url="https://api.example.com/users",
                headers={"Authorization": "Bearer {{token}}", "Accept": "application/json"},
                notes="Retrieves all users",
            ),
            CollectionItem(
                id=str(uuid.uuid4()),
                name="Create User",
                method="POST",
                url="https://api.example.com/users",
                headers={"Content-Type": "application/json"},
                body='{"name": "John", "email": "john@example.com"}',
                notes="Creates a new user",
            ),
            CollectionItem(
                id=str(uuid.uuid4()),
                name="Auth Folder",
                is_folder=True,
                items=[
                    CollectionItem(
                        id=str(uuid.uuid4()),
                        name="Login",
                        method="POST",
                        url="https://api.example.com/auth/login",
                        headers={"Content-Type": "application/json"},
                        body='{"username": "admin", "password": "secret"}',
                    ),
                ],
            ),
        ]
    coll = Collection(
        id=str(uuid.uuid4()),
        name=name,
        version=1,
        items=items,
    )
    storage._atomic_write(coll)
    return coll


@pytest.mark.anyio
async def test_generate_html():
    coll = _create_collection()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post("/api/docs/generate", json={
            "collection_id": coll.id,
            "format": "html",
            "options": {},
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "html"
    assert data["endpoint_count"] == 3
    assert "<!DOCTYPE html>" in data["content"]
    assert "Get Users" in data["content"]
    assert "Create User" in data["content"]
    assert "Login" in data["content"]
    # Check search functionality present
    assert "filterEndpoints" in data["content"]
    # Check copy-to-clipboard present
    assert "copyCode" in data["content"]


@pytest.mark.anyio
async def test_generate_markdown():
    coll = _create_collection()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post("/api/docs/generate", json={
            "collection_id": coll.id,
            "format": "markdown",
            "options": {"title": "My API Docs"},
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "markdown"
    assert data["endpoint_count"] == 3
    content = data["content"]
    assert "# My API Docs" in content
    assert "**`GET`**" in content
    assert "**`POST`**" in content
    assert "| `Authorization`" in content
    assert "```json" in content


@pytest.mark.anyio
async def test_generate_openapi():
    coll = _create_collection()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post("/api/docs/generate", json={
            "collection_id": coll.id,
            "format": "openapi",
            "options": {"base_url": "https://api.example.com"},
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["format"] == "openapi"
    assert data["endpoint_count"] == 3
    spec = json.loads(data["content"])
    assert spec["openapi"] == "3.0.3"
    assert spec["info"]["title"] == "Test API"
    assert "/users" in spec["paths"]
    assert "get" in spec["paths"]["/users"]
    assert "post" in spec["paths"]["/users"]
    assert spec["servers"][0]["url"] == "https://api.example.com"


@pytest.mark.anyio
async def test_empty_collection():
    coll = _create_collection(name="Empty", items=[])
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post("/api/docs/generate", json={
            "collection_id": coll.id,
            "format": "html",
            "options": {},
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["endpoint_count"] == 0
    assert data["format"] == "html"


@pytest.mark.anyio
async def test_not_found_collection():
    fake_id = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post("/api/docs/generate", json={
            "collection_id": fake_id,
            "format": "html",
            "options": {},
        })
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_options_group_by_method():
    coll = _create_collection()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post("/api/docs/generate", json={
            "collection_id": coll.id,
            "format": "markdown",
            "options": {"group_by": "method"},
        })
    assert resp.status_code == 200
    content = resp.json()["content"]
    # Should have GET and POST as section headers
    assert "## GET" in content
    assert "## POST" in content


@pytest.mark.anyio
async def test_options_exclude_examples():
    coll = _create_collection()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post("/api/docs/generate", json={
            "collection_id": coll.id,
            "format": "markdown",
            "options": {"include_examples": False},
        })
    assert resp.status_code == 200
    content = resp.json()["content"]
    # Body should not be included
    assert "```json" not in content


@pytest.mark.anyio
async def test_options_exclude_headers():
    coll = _create_collection()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post("/api/docs/generate", json={
            "collection_id": coll.id,
            "format": "markdown",
            "options": {"include_headers": False},
        })
    assert resp.status_code == 200
    content = resp.json()["content"]
    assert "| `Authorization`" not in content
