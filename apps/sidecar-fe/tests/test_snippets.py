"""Tests for the snippets API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app
    app = create_app()
    return TestClient(app)


def test_list_includes_builtins(client):
    r = client.get("/api/snippets")
    assert r.status_code == 200
    items = r.json()["items"]
    builtin_ids = [s["id"] for s in items if s["builtin"]]
    assert "builtin-health-check" in builtin_ids
    assert "builtin-graphql-introspection" in builtin_ids
    assert "builtin-oauth2-token" in builtin_ids


def test_create_snippet(client):
    payload = {
        "name": "My Test Snippet",
        "category": "Testing",
        "description": "A test snippet",
        "method": "POST",
        "url": "https://example.com/api",
        "headers": {"X-Custom": "value"},
        "body": '{"key": "value"}',
        "tags": ["test", "example"],
    }
    r = client.post("/api/snippets", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "My Test Snippet"
    assert data["category"] == "Testing"
    assert data["method"] == "POST"
    assert data["builtin"] is False
    assert "id" in data


def test_get_snippet_by_id(client):
    # Create one
    r = client.post("/api/snippets", json={"name": "Fetch Me", "url": "/fetch"})
    assert r.status_code == 201
    sid = r.json()["id"]
    # Get it
    r2 = client.get(f"/api/snippets/{sid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Fetch Me"


def test_get_builtin_snippet(client):
    r = client.get("/api/snippets/builtin-health-check")
    assert r.status_code == 200
    assert r.json()["name"] == "Health Check"


def test_update_snippet(client):
    r = client.post("/api/snippets", json={"name": "Original", "url": "/orig"})
    sid = r.json()["id"]
    r2 = client.put(f"/api/snippets/{sid}", json={"name": "Updated", "category": "New"})
    assert r2.status_code == 200
    assert r2.json()["name"] == "Updated"
    assert r2.json()["category"] == "New"


def test_cannot_update_builtin(client):
    r = client.put("/api/snippets/builtin-health-check", json={"name": "Hacked"})
    assert r.status_code == 403


def test_delete_snippet(client):
    r = client.post("/api/snippets", json={"name": "Delete Me", "url": "/del"})
    sid = r.json()["id"]
    r2 = client.delete(f"/api/snippets/{sid}")
    assert r2.status_code == 204
    r3 = client.get(f"/api/snippets/{sid}")
    assert r3.status_code == 404


def test_cannot_delete_builtin(client):
    r = client.delete("/api/snippets/builtin-health-check")
    assert r.status_code == 403


def test_filter_by_category(client):
    client.post("/api/snippets", json={"name": "A", "category": "Alpha", "url": "/a"})
    client.post("/api/snippets", json={"name": "B", "category": "Beta", "url": "/b"})
    r = client.get("/api/snippets", params={"category": "Alpha"})
    items = r.json()["items"]
    assert all(s["category"] == "Alpha" for s in items)


def test_filter_by_tag(client):
    client.post("/api/snippets", json={"name": "Tagged", "url": "/t", "tags": ["special"]})
    client.post("/api/snippets", json={"name": "Untagged", "url": "/u", "tags": []})
    r = client.get("/api/snippets", params={"tag": "special"})
    items = r.json()["items"]
    assert any(s["name"] == "Tagged" for s in items)
    assert not any(s["name"] == "Untagged" for s in items)


def test_search(client):
    client.post("/api/snippets", json={"name": "Searchable API", "url": "/s"})
    client.post("/api/snippets", json={"name": "Hidden", "url": "/h"})
    r = client.get("/api/snippets", params={"search": "searchable"})
    items = r.json()["items"]
    assert any(s["name"] == "Searchable API" for s in items)
    assert not any(s["name"] == "Hidden" for s in items)


def test_categories(client):
    client.post("/api/snippets", json={"name": "X", "category": "Unique", "url": "/x"})
    r = client.get("/api/snippets/categories")
    assert r.status_code == 200
    cats = r.json()
    assert "Unique" in cats
    # Builtins also present
    assert "Common" in cats


def test_export_import_roundtrip(client):
    client.post("/api/snippets", json={"name": "Export Me", "category": "RT", "url": "/e", "tags": ["round"]})
    # Export
    r = client.get("/api/snippets/export")
    assert r.status_code == 200
    exported = r.json()["snippets"]
    assert len(exported) >= 1
    # Clear (delete all user snippets)
    for s in exported:
        client.delete(f"/api/snippets/{s['id']}")
    # Import
    import_payload = {"snippets": [{"name": s["name"], "category": s["category"], "url": s["url"], "tags": s["tags"]} for s in exported]}
    r2 = client.post("/api/snippets/import", json=import_payload)
    assert r2.status_code == 200
    imported = r2.json()["items"]
    assert len(imported) == len(exported)
    assert imported[0]["name"] == "Export Me"


def test_not_found(client):
    r = client.get("/api/snippets/nonexistent-id")
    assert r.status_code == 404
