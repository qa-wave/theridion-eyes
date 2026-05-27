"""Tests for the safe mini-interpreter in /api/scripts/execute-safe,
and the 410 Gone response for the removed Node.js subprocess endpoint.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

# Re-use the shared token constant from conftest so tests work when
# THERIDION_TOKEN is set (the token middleware is active in all test apps).
_TEST_TOKEN = "test-token-fixture"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    monkeypatch.setenv("THERIDION_TOKEN", _TEST_TOKEN)
    import theridion_sidecar.main as _main
    monkeypatch.setattr(_main, "_SIDECAR_TOKEN", _TEST_TOKEN)
    app = _main.create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Theridion-Token": _TEST_TOKEN},
    )


@pytest.mark.anyio
async def test_pre_request_set_header(client: AsyncClient) -> None:
    """Pre-request script that sets a header."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": 'setHeader("Authorization", "Bearer abc123")',
        "phase": "pre",
        "context": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["headers"]["Authorization"] == "Bearer abc123"


@pytest.mark.anyio
async def test_post_response_extract_variable(client: AsyncClient) -> None:
    """Post-response script that extracts a variable from response context."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": 'set("userId", response.json.data.id)',
        "phase": "post",
        "context": {
            "response": {
                "status": 200,
                "json": {"data": {"id": "usr_42"}},
            },
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["variables"]["userId"] == "usr_42"


@pytest.mark.anyio
async def test_assertion_pass(client: AsyncClient) -> None:
    """Script with a passing assertion."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": 'assert(response.status, "Expected non-zero status")',
        "phase": "post",
        "context": {"response": {"status": 200}},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert len(data["assertions"]) == 1
    assert data["assertions"][0]["passed"] is True
    assert data["assertions"][0]["message"] == "Expected non-zero status"


@pytest.mark.anyio
async def test_assertion_fail(client: AsyncClient) -> None:
    """Script with a failing assertion (value is falsy)."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": 'assert(response.error, "Expected no error")',
        "phase": "post",
        "context": {"response": {"error": None}},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert len(data["assertions"]) == 1
    assert data["assertions"][0]["passed"] is False


@pytest.mark.anyio
async def test_log_output(client: AsyncClient) -> None:
    """Script with log() calls should capture output."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": 'log("Hello", "World")\nlog("Token is", response.token)',
        "phase": "post",
        "context": {"response": {"token": "xyz"}},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["logs"] == ["Hello World", "Token is xyz"]


@pytest.mark.anyio
async def test_invalid_script_returns_error(client: AsyncClient) -> None:
    """Invalid syntax should return an error, not crash."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": "this is not valid syntax at all",
        "phase": "pre",
        "context": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is not None
    assert "syntax error" in data["error"].lower() or "unknown function" in data["error"].lower()


@pytest.mark.anyio
async def test_unknown_function_returns_error(client: AsyncClient) -> None:
    """Calling an undefined function should return an error."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": 'deleteDatabase("production")',
        "phase": "pre",
        "context": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is not None
    assert "unknown function" in data["error"].lower()


@pytest.mark.anyio
async def test_set_and_get_roundtrip(client: AsyncClient) -> None:
    """set() followed by get() inside another set()."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": (
            'set("token", "abc")\n'
            'setHeader("Authorization", "Bearer " + get("token"))'
        ),
        "phase": "pre",
        "context": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["variables"]["token"] == "abc"
    assert data["headers"]["Authorization"] == "Bearer abc"


@pytest.mark.anyio
async def test_comments_and_blank_lines(client: AsyncClient) -> None:
    """Comments and blank lines should be ignored."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": (
            "// This is a comment\n"
            "# Also a comment\n"
            "\n"
            'log("works")\n'
        ),
        "phase": "pre",
        "context": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["logs"] == ["works"]


@pytest.mark.anyio
async def test_env_seeded_from_context(client: AsyncClient) -> None:
    """Variables should be seeded from context.env."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": 'setHeader("X-Api-Key", get("api_key"))',
        "phase": "pre",
        "context": {"env": {"api_key": "secret123"}},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["headers"]["X-Api-Key"] == "secret123"


@pytest.mark.anyio
async def test_semicolons_tolerated(client: AsyncClient) -> None:
    """Trailing semicolons should be stripped without error."""
    resp = await client.post("/api/scripts/execute-safe", json={
        "script": 'set("a", "1");\nlog("ok");',
        "phase": "pre",
        "context": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] is None
    assert data["variables"]["a"] == "1"
    assert data["logs"] == ["ok"]


@pytest.mark.anyio
async def test_nodejs_execute_returns_410(client: AsyncClient) -> None:
    """POST /execute (Node.js subprocess) must return 410 Gone — P0 security."""
    resp = await client.post("/api/scripts/execute", json={
        "script": "require('fs').readFileSync('/etc/passwd', 'utf8')",
        "variables": {},
        "request": {},
    })
    assert resp.status_code == 410
    body = resp.json()
    assert "detail" in body
    assert "removed" in body["detail"].lower() or "hardening" in body["detail"].lower()
