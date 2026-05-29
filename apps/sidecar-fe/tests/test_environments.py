"""Tests for the /api/environments CRUD + {{var}} substitution helper.

Request execution (/api/requests/execute) lives in the BE sidecar — the slim
FE sidecar deliberately omits that router (see main.create_app), so those
integration tests belong to theridion-be, not here.
"""

from __future__ import annotations

from pathlib import Path

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
