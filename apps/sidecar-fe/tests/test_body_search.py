"""Tests for /api/search/* endpoints (body text, JSONPath, XPath)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Text / Regex body search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_text_search_case_insensitive(client: AsyncClient):
    async with client:
        r = await client.post("/api/search/body", json={
            "body": "Hello World hello world HELLO",
            "query": "hello",
            "regex": False,
            "case_sensitive": False,
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert data["query_valid"] is True
    assert data["matches"][0]["line"] == 1
    assert data["matches"][0]["start"] == 0
    assert data["matches"][0]["end"] == 5


@pytest.mark.asyncio
async def test_text_search_case_sensitive(client: AsyncClient):
    async with client:
        r = await client.post("/api/search/body", json={
            "body": "Hello World hello world HELLO",
            "query": "hello",
            "regex": False,
            "case_sensitive": True,
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["matches"][0]["start"] == 12


@pytest.mark.asyncio
async def test_regex_search(client: AsyncClient):
    async with client:
        r = await client.post("/api/search/body", json={
            "body": '{"id": 123, "name": "test", "id": 456}',
            "query": r'"id":\s*\d+',
            "regex": True,
            "case_sensitive": True,
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert data["query_valid"] is True


@pytest.mark.asyncio
async def test_regex_invalid_pattern(client: AsyncClient):
    async with client:
        r = await client.post("/api/search/body", json={
            "body": "some text",
            "query": "[invalid",
            "regex": True,
        })
    assert r.status_code == 200
    data = r.json()
    assert data["query_valid"] is False
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_no_matches(client: AsyncClient):
    async with client:
        r = await client.post("/api/search/body", json={
            "body": "Hello World",
            "query": "xyz",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["matches"] == []


@pytest.mark.asyncio
async def test_empty_query(client: AsyncClient):
    async with client:
        r = await client.post("/api/search/body", json={
            "body": "Hello World",
            "query": "",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["query_valid"] is True


@pytest.mark.asyncio
async def test_multiline_line_column(client: AsyncClient):
    body = "line1\nline2 match\nline3"
    async with client:
        r = await client.post("/api/search/body", json={
            "body": body,
            "query": "match",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["matches"][0]["line"] == 2
    assert data["matches"][0]["column"] == 7


@pytest.mark.asyncio
async def test_context_extraction(client: AsyncClient):
    body = "A" * 50 + "FIND" + "B" * 50
    async with client:
        r = await client.post("/api/search/body", json={
            "body": body,
            "query": "FIND",
            "case_sensitive": True,
        })
    data = r.json()
    ctx = data["matches"][0]["context"]
    assert "FIND" in ctx
    # Context should be ~40+4+40 = 84 chars
    assert len(ctx) == 84


# ---------------------------------------------------------------------------
# JSONPath search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jsonpath_simple(client: AsyncClient):
    import json
    body = json.dumps({"name": "Alice", "age": 30, "items": [1, 2, 3]})
    async with client:
        r = await client.post("/api/search/json-path", json={
            "body": body,
            "path": "$.name",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["matches"][0]["value"] == "Alice"
    assert data["matches"][0]["type"] == "str"


@pytest.mark.asyncio
async def test_jsonpath_array(client: AsyncClient):
    import json
    body = json.dumps({"users": [{"name": "A"}, {"name": "B"}, {"name": "C"}]})
    async with client:
        r = await client.post("/api/search/json-path", json={
            "body": body,
            "path": "$.users[*].name",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    assert [m["value"] for m in data["matches"]] == ["A", "B", "C"]


@pytest.mark.asyncio
async def test_jsonpath_nested(client: AsyncClient):
    import json
    body = json.dumps({"a": {"b": {"c": 42}}})
    async with client:
        r = await client.post("/api/search/json-path", json={
            "body": body,
            "path": "$.a.b.c",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["matches"][0]["value"] == 42
    assert data["matches"][0]["type"] == "int"


@pytest.mark.asyncio
async def test_jsonpath_invalid_body(client: AsyncClient):
    async with client:
        r = await client.post("/api/search/json-path", json={
            "body": "not json at all",
            "path": "$.foo",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_jsonpath_no_match(client: AsyncClient):
    import json
    body = json.dumps({"name": "Alice"})
    async with client:
        r = await client.post("/api/search/json-path", json={
            "body": body,
            "path": "$.nonexistent",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# XPath search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_xpath_simple(client: AsyncClient):
    body = "<root><item>hello</item><item>world</item></root>"
    async with client:
        r = await client.post("/api/search/xpath", json={
            "body": body,
            "xpath": ".//item",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert data["matches"][0]["value"] == "hello"
    assert data["matches"][1]["value"] == "world"


@pytest.mark.asyncio
async def test_xpath_nested(client: AsyncClient):
    body = "<root><a><b>deep</b></a></root>"
    async with client:
        r = await client.post("/api/search/xpath", json={
            "body": body,
            "xpath": ".//b",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["matches"][0]["value"] == "deep"


@pytest.mark.asyncio
async def test_xpath_no_match(client: AsyncClient):
    body = "<root><item>hello</item></root>"
    async with client:
        r = await client.post("/api/search/xpath", json={
            "body": body,
            "xpath": ".//nonexistent",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_xpath_invalid_xml(client: AsyncClient):
    async with client:
        r = await client.post("/api/search/xpath", json={
            "body": "not xml at all",
            "xpath": ".//item",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_xpath_invalid_expression(client: AsyncClient):
    body = "<root><item>hello</item></root>"
    async with client:
        r = await client.post("/api/search/xpath", json={
            "body": body,
            "xpath": "///[[[invalid",
        })
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
