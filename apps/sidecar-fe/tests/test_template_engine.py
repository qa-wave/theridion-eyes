"""Tests for the advanced template engine."""

from __future__ import annotations

import base64
import json
import os
import urllib.parse

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


# ---- Simple variable substitution ----


@pytest.mark.anyio
async def test_simple_variable(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "Hello {{name}}!",
        "variables": {"name": "World"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["rendered"] == "Hello World!"
    assert "name" in data["variables_used"]


@pytest.mark.anyio
async def test_unknown_variable_left_asis(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "Hello {{unknown}}!",
        "variables": {},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "Hello {{unknown}}!"


# ---- Conditional blocks ----


@pytest.mark.anyio
async def test_if_true(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$if show}}visible{{$endif}}",
        "variables": {"show": "yes"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "visible"


@pytest.mark.anyio
async def test_if_false(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$if show}}visible{{$endif}}",
        "variables": {"show": ""},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == ""


@pytest.mark.anyio
async def test_if_negation(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$if !debug}}production{{$endif}}",
        "variables": {"debug": ""},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "production"


@pytest.mark.anyio
async def test_if_equality(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": '{{$if env == "prod"}}PROD{{$endif}}',
        "variables": {"env": "prod"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "PROD"


@pytest.mark.anyio
async def test_nested_if(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$if a}}A{{$if b}}B{{$endif}}{{$endif}}",
        "variables": {"a": "1", "b": "1"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "AB"


@pytest.mark.anyio
async def test_nested_if_outer_false(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$if a}}A{{$if b}}B{{$endif}}{{$endif}}",
        "variables": {"a": "", "b": "1"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == ""


# ---- Loop (each/end) ----


@pytest.mark.anyio
async def test_each_loop(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$each items as item}}[{{item}}]{{$end}}",
        "variables": {"items": ["a", "b", "c"]},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "[a][b][c]"


@pytest.mark.anyio
async def test_each_not_a_list(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$each items as item}}[{{item}}]{{$end}}",
        "variables": {"items": "not-a-list"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["rendered"] == ""
    assert any("not a list" in w for w in data["warnings"])


# ---- Pipe filters ----


@pytest.mark.anyio
async def test_filter_upper(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{name | upper}}",
        "variables": {"name": "hello"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "HELLO"


@pytest.mark.anyio
async def test_filter_lower(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{name | lower}}",
        "variables": {"name": "HELLO"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "hello"


@pytest.mark.anyio
async def test_filter_base64(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{secret | base64}}",
        "variables": {"secret": "hello"},
    })
    assert resp.status_code == 200
    expected = base64.b64encode(b"hello").decode()
    assert resp.json()["rendered"] == expected


@pytest.mark.anyio
async def test_filter_json(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{val | json}}",
        "variables": {"val": "hello world"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == json.dumps("hello world")


@pytest.mark.anyio
async def test_filter_urlencode(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{q | urlencode}}",
        "variables": {"q": "hello world"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == urllib.parse.quote_plus("hello world")


@pytest.mark.anyio
async def test_filter_trim(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{val | trim}}",
        "variables": {"val": "  hello  "},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "hello"


@pytest.mark.anyio
async def test_filter_slice(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{val | slice:0:5}}",
        "variables": {"val": "hello world"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "hello"


@pytest.mark.anyio
async def test_chained_filters(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{val | trim | upper}}",
        "variables": {"val": "  hello  "},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "HELLO"


# ---- Math expressions ----


@pytest.mark.anyio
async def test_math_add(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$math 1 + 2}}",
        "variables": {},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "3"


@pytest.mark.anyio
async def test_math_with_variables(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$math x * 2}}",
        "variables": {"x": 5},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "10"


@pytest.mark.anyio
async def test_math_division(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": "{{$math 10 / 2}}",
        "variables": {},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "5"


# ---- Default values ----


@pytest.mark.anyio
async def test_default_when_missing(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": '{{$default name "stranger"}}',
        "variables": {},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "stranger"


@pytest.mark.anyio
async def test_default_when_present(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": '{{$default name "stranger"}}',
        "variables": {"name": "Alice"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "Alice"


@pytest.mark.anyio
async def test_default_when_empty(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": '{{$default name "stranger"}}',
        "variables": {"name": ""},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "stranger"


# ---- $concat ----


@pytest.mark.anyio
async def test_concat(client: AsyncClient):
    resp = await client.post("/api/template/render", json={
        "template": '{{$concat host ":" port}}',
        "variables": {"host": "localhost", "port": "8080"},
    })
    assert resp.status_code == 200
    assert resp.json()["rendered"] == "localhost:8080"


# ---- $env ----


@pytest.mark.anyio
async def test_env_denied_by_default(client: AsyncClient):
    os.environ["TEST_THERIDION_VAR"] = "secret"
    try:
        resp = await client.post("/api/template/render", json={
            "template": "{{$env TEST_THERIDION_VAR}}",
            "variables": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        # Should NOT resolve when allow_env is false
        assert "{{$env TEST_THERIDION_VAR}}" in data["rendered"]
        assert any("denied" in w for w in data["warnings"])
    finally:
        del os.environ["TEST_THERIDION_VAR"]


@pytest.mark.anyio
async def test_env_allowed(client: AsyncClient):
    os.environ["TEST_THERIDION_VAR"] = "secret_value"
    try:
        resp = await client.post("/api/template/render", json={
            "template": "{{$env TEST_THERIDION_VAR}}",
            "variables": {},
            "options": {"allow_env": True},
        })
        assert resp.status_code == 200
        assert resp.json()["rendered"] == "secret_value"
    finally:
        del os.environ["TEST_THERIDION_VAR"]


# ---- Validation ----


@pytest.mark.anyio
async def test_validate_valid(client: AsyncClient):
    resp = await client.post("/api/template/validate", json={
        "template": "{{$if x}}hello{{$endif}} {{name | upper}}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []


@pytest.mark.anyio
async def test_validate_unclosed_if(client: AsyncClient):
    resp = await client.post("/api/template/validate", json={
        "template": "{{$if x}}hello",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any("$if" in e for e in data["errors"])


@pytest.mark.anyio
async def test_validate_unclosed_each(client: AsyncClient):
    resp = await client.post("/api/template/validate", json={
        "template": "{{$each items as i}}loop body",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any("$each" in e for e in data["errors"])


@pytest.mark.anyio
async def test_validate_unknown_filter(client: AsyncClient):
    resp = await client.post("/api/template/validate", json={
        "template": "{{name | nonexistent}}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any("nonexistent" in e for e in data["errors"])


# ---- Variable extraction ----


@pytest.mark.anyio
async def test_extract_variables(client: AsyncClient):
    resp = await client.post("/api/template/variables", json={
        "template": "{{host}}:{{port}}/{{path | upper}} {{$default timeout \"30\"}}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["variables"]) == {"host", "port", "path", "timeout"}


@pytest.mark.anyio
async def test_extract_from_if(client: AsyncClient):
    resp = await client.post("/api/template/variables", json={
        "template": "{{$if auth}}Bearer {{token}}{{$endif}}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "auth" in data["variables"]
    assert "token" in data["variables"]
