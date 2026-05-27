"""Tests for the /api/environments CRUD + {{var}} substitution in execute."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def test_list_is_empty(client: TestClient) -> None:
    res = client.get("/api/environments")
    assert res.status_code == 200
    assert res.json() == []


def test_create_then_list(client: TestClient) -> None:
    res = client.post("/api/environments", json={"name": "Production"})
    assert res.status_code == 201
    env = res.json()
    assert env["name"] == "Production"
    assert env["variables"] == []

    listed = client.get("/api/environments").json()
    assert len(listed) == 1
    assert listed[0]["id"] == env["id"]
    assert listed[0]["variable_count"] == 0


def test_replace_variables(client: TestClient) -> None:
    env = client.post("/api/environments", json={"name": "E"}).json()
    res = client.put(
        f"/api/environments/{env['id']}/variables",
        json={
            "variables": [
                {"name": "baseUrl", "value": "https://api.example.com"},
                {"name": "token", "value": "secret123", "enabled": False},
            ]
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["variables"]) == 2
    assert body["variables"][0]["name"] == "baseUrl"
    assert body["variables"][1]["enabled"] is False


def test_rename(client: TestClient) -> None:
    env = client.post("/api/environments", json={"name": "Old"}).json()
    res = client.patch(
        f"/api/environments/{env['id']}", json={"name": "New"}
    )
    assert res.status_code == 200
    assert res.json()["name"] == "New"


def test_delete(client: TestClient) -> None:
    env = client.post("/api/environments", json={"name": "Doomed"}).json()
    res = client.delete(f"/api/environments/{env['id']}")
    assert res.status_code == 204
    assert client.get("/api/environments").json() == []


def test_get_unknown_404(client: TestClient) -> None:
    res = client.get("/api/environments/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404


# ---- substitution -------------------------------------------------------

def test_substitution_replaces_known_vars() -> None:
    from theridion_sidecar.environments import Environment, EnvVariable, substitute

    env = Environment(
        id="x",
        name="E",
        variables=[
            EnvVariable(name="host", value="api.example.com"),
            EnvVariable(name="ver", value="v2"),
        ],
    )
    assert (
        substitute("https://{{host}}/{{ver}}/things", env)
        == "https://api.example.com/v2/things"
    )


def test_substitution_leaves_unknown_vars_in_place() -> None:
    from theridion_sidecar.environments import Environment, EnvVariable, substitute

    env = Environment(
        id="x", name="E", variables=[EnvVariable(name="known", value="K")]
    )
    assert substitute("x={{unknown}} y={{known}}", env) == "x={{unknown}} y=K"


def test_substitution_skips_disabled() -> None:
    from theridion_sidecar.environments import Environment, EnvVariable, substitute

    env = Environment(
        id="x",
        name="E",
        variables=[EnvVariable(name="t", value="ON", enabled=False)],
    )
    assert substitute("{{t}}", env) == "{{t}}"


def test_substitution_handles_whitespace_inside_braces() -> None:
    from theridion_sidecar.environments import Environment, EnvVariable, substitute

    env = Environment(
        id="x", name="E", variables=[EnvVariable(name="a", value="b")]
    )
    assert substitute("{{ a }}", env) == "b"


def test_substitution_passthrough_when_env_is_none() -> None:
    from theridion_sidecar.environments import substitute

    assert substitute("{{x}}", None) == "{{x}}"


# ---- substitution in /execute ------------------------------------------

class _FakeResponse:
    def __init__(self, url: str) -> None:
        self.status_code = 200
        self.reason_phrase = "OK"
        self.headers: dict[str, str] = {"content-type": "text/plain"}
        self.text = ""
        self.content = b""
        self.url = url
        self.cookies: dict[str, str] = {}


class _FakeRequest:
    """Minimal stand-in for httpx.Request."""

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self.extensions: dict[str, Any] = {}


class _FakeClient:
    """Stand-in for httpx.AsyncClient that records what it got."""

    last_kwargs: dict[str, Any] = {}

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None

    def build_request(self, **kwargs: Any) -> _FakeRequest:
        return _FakeRequest(**kwargs)

    async def send(self, request: _FakeRequest, **_kw: Any) -> _FakeResponse:
        _FakeClient.last_kwargs = request._kwargs
        return _FakeResponse(url=request._kwargs.get("url", ""))

    async def request(self, **kwargs: Any) -> _FakeResponse:
        _FakeClient.last_kwargs = kwargs
        return _FakeResponse(url=kwargs.get("url", ""))


def test_execute_substitutes_url_headers_body(client: TestClient) -> None:
    env = client.post("/api/environments", json={"name": "E"}).json()
    client.put(
        f"/api/environments/{env['id']}/variables",
        json={
            "variables": [
                {"name": "host", "value": "api.example.com"},
                {"name": "tok", "value": "ABC123"},
            ]
        },
    )
    with patch("theridion_sidecar.api.requests.httpx.AsyncClient", _FakeClient):
        res = client.post(
            "/api/requests/execute",
            json={
                "method": "POST",
                "url": "https://{{host}}/v1/things",
                "headers": {"Authorization": "Bearer {{tok}}"},
                "body": '{"to":"{{host}}"}',
                "environment_id": env["id"],
            },
        )
    assert res.status_code == 200
    sent = _FakeClient.last_kwargs
    assert sent["url"] == "https://api.example.com/v1/things"
    assert sent["headers"]["Authorization"] == "Bearer ABC123"
    assert sent["content"] == b'{"to":"api.example.com"}'
    assert res.json()["resolved_url"] == "https://api.example.com/v1/things"


def test_execute_with_unknown_environment_404s(client: TestClient) -> None:
    res = client.post(
        "/api/requests/execute",
        json={
            "url": "https://example.com",
            "environment_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert res.status_code == 404


def test_execute_without_env_does_not_substitute(client: TestClient) -> None:
    with patch("theridion_sidecar.api.requests.httpx.AsyncClient", _FakeClient):
        client.post(
            "/api/requests/execute",
            json={"url": "https://example.com/{{leave-me}}"},
        )
    # No env → placeholder stays.
    assert "{{leave-me}}" in _FakeClient.last_kwargs["url"]
