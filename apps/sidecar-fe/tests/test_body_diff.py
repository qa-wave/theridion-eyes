"""Tests for the body diff API endpoints."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# JSON structural diff
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_json_diff_nested(client: AsyncClient):
    left = json.dumps({"name": "Alice", "age": 30, "address": {"city": "Prague"}})
    right = json.dumps({"name": "Bob", "age": 30, "address": {"city": "Brno", "zip": "60200"}})

    resp = await client.post("/api/diff/bodies", json={"left": left, "right": right})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_detected"] == "json"
    changes = data["structural_changes"]
    paths = [c["path"] for c in changes]
    assert "$.name" in paths
    assert "$.address.city" in paths
    assert "$.address.zip" in paths
    # age unchanged
    assert "$.age" not in paths
    assert data["stats"]["additions"] >= 1
    assert data["stats"]["modifications"] >= 1


@pytest.mark.anyio
async def test_json_diff_arrays(client: AsyncClient):
    left = json.dumps([1, 2, 3])
    right = json.dumps([1, 2, 3, 4])

    resp = await client.post("/api/diff/bodies", json={"left": left, "right": right})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_detected"] == "json"
    changes = data["structural_changes"]
    assert any(c["path"] == "$[3]" and c["type"] == "added" for c in changes)


# ---------------------------------------------------------------------------
# XML element diff
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_xml_diff(client: AsyncClient):
    left = '<root><name>Alice</name><age>30</age></root>'
    right = '<root><name>Bob</name><age>30</age><city>Brno</city></root>'

    resp = await client.post("/api/diff/bodies", json={"left": left, "right": right})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_detected"] == "xml"
    changes = data["structural_changes"]
    assert len(changes) > 0
    # Name text changed
    assert any("name/text()" in c["path"] for c in changes)
    # city added
    assert any(c["type"] == "added" for c in changes)


# ---------------------------------------------------------------------------
# Text line diff
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_text_diff(client: AsyncClient):
    left = "line1\nline2\nline3\n"
    right = "line1\nmodified\nline3\nline4\n"

    resp = await client.post("/api/diff/bodies", json={"left": left, "right": right, "format": "text"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_detected"] == "text"
    assert data["unified_diff"] != ""
    assert data["stats"]["additions"] >= 1
    assert data["stats"]["deletions"] >= 1


# ---------------------------------------------------------------------------
# Auto-format detection
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_auto_detect_json(client: AsyncClient):
    left = '{"key": "value"}'
    right = '{"key": "other"}'
    resp = await client.post("/api/diff/bodies", json={"left": left, "right": right})
    assert resp.status_code == 200
    assert resp.json()["format_detected"] == "json"


@pytest.mark.anyio
async def test_auto_detect_xml(client: AsyncClient):
    left = '<root><a>1</a></root>'
    right = '<root><a>2</a></root>'
    resp = await client.post("/api/diff/bodies", json={"left": left, "right": right})
    assert resp.status_code == 200
    assert resp.json()["format_detected"] == "xml"


@pytest.mark.anyio
async def test_auto_detect_text(client: AsyncClient):
    left = "just some plain text"
    right = "just some other text"
    resp = await client.post("/api/diff/bodies", json={"left": left, "right": right})
    assert resp.status_code == 200
    assert resp.json()["format_detected"] == "text"


# ---------------------------------------------------------------------------
# Identical bodies
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_identical_json(client: AsyncClient):
    body = json.dumps({"a": 1, "b": [2, 3]})
    resp = await client.post("/api/diff/bodies", json={"left": body, "right": body})
    assert resp.status_code == 200
    data = resp.json()
    assert data["structural_changes"] == []
    assert data["stats"]["additions"] == 0
    assert data["stats"]["deletions"] == 0
    assert data["stats"]["modifications"] == 0


# ---------------------------------------------------------------------------
# Three-way merge
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_merge_no_conflict(client: AsyncClient):
    base = json.dumps({"a": 1, "b": 2, "c": 3})
    left = json.dumps({"a": 10, "b": 2, "c": 3})  # changed a
    right = json.dumps({"a": 1, "b": 2, "c": 30})  # changed c

    resp = await client.post("/api/diff/merge", json={"base": base, "left": left, "right": right})
    assert resp.status_code == 200
    data = resp.json()
    merged = json.loads(data["merged"])
    assert merged["a"] == 10
    assert merged["c"] == 30
    assert data["conflicts"] == []


@pytest.mark.anyio
async def test_merge_with_conflict(client: AsyncClient):
    base = json.dumps({"x": "original"})
    left = json.dumps({"x": "left-change"})
    right = json.dumps({"x": "right-change"})

    resp = await client.post("/api/diff/merge", json={"base": base, "left": left, "right": right})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["conflicts"]) >= 1
    assert data["conflicts"][0]["path"] == "$.x"


# ---------------------------------------------------------------------------
# Format endpoint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_format_json(client: AsyncClient):
    compact = '{"a":1,"b":[2,3]}'
    resp = await client.post("/api/diff/format", json={"body": compact})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_detected"] == "json"
    assert "\n" in data["formatted"]


@pytest.mark.anyio
async def test_format_xml(client: AsyncClient):
    raw = '<root><child>text</child></root>'
    resp = await client.post("/api/diff/format", json={"body": raw, "format": "xml"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_detected"] == "xml"
