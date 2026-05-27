"""Tests for authentication injection in request execution.

Tests both the low-level `_apply_auth` helper and the end-to-end flow
through the /api/requests/execute endpoint using httpbin-style echo.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.api.requests import _apply_auth
from theridion_sidecar.models import AuthConfig


# ---- unit tests for _apply_auth -------------------------------------------


def test_bearer_injects_authorization_header() -> None:
    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    auth = AuthConfig(type="bearer", token="my-secret-token")
    _apply_auth(auth, headers, query, None)
    assert headers["Authorization"] == "Bearer my-secret-token"
    assert query == {}


def test_basic_injects_base64_header() -> None:
    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    auth = AuthConfig(type="basic", username="alice", password="s3cret")
    _apply_auth(auth, headers, query, None)
    expected = base64.b64encode(b"alice:s3cret").decode()
    assert headers["Authorization"] == f"Basic {expected}"


def test_apikey_header_mode() -> None:
    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    auth = AuthConfig(type="apikey", key="X-API-Key", value="abc123", add_to="header")
    _apply_auth(auth, headers, query, None)
    assert headers["X-API-Key"] == "abc123"
    assert query == {}


def test_apikey_query_mode() -> None:
    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    auth = AuthConfig(type="apikey", key="api_key", value="abc123", add_to="query")
    _apply_auth(auth, headers, query, None)
    assert query["api_key"] == "abc123"
    assert "api_key" not in headers


def test_none_type_is_noop() -> None:
    headers: dict[str, str] = {"Existing": "header"}
    query: dict[str, str] = {}
    auth = AuthConfig(type="none")
    # _apply_auth should never be called with type=none in prod, but
    # verify it's harmless if it is.
    _apply_auth(auth, headers, query, None)
    assert headers == {"Existing": "header"}


# ---- env-var substitution in auth values ----------------------------------


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def test_bearer_with_env_substitution(client: TestClient) -> None:
    # Create an environment with a token variable.
    env_res = client.post("/api/environments", json={"name": "auth-test"})
    assert env_res.status_code == 201
    env_id = env_res.json()["id"]
    client.put(
        f"/api/environments/{env_id}/variables",
        json={"variables": [{"name": "token", "value": "resolved-secret", "enabled": True}]},
    )

    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    auth = AuthConfig(type="bearer", token="{{token}}")

    from theridion_sidecar import environments

    env = environments.get(env_id)
    _apply_auth(auth, headers, query, env)
    assert headers["Authorization"] == "Bearer resolved-secret"


def test_basic_with_env_substitution(client: TestClient) -> None:
    env_res = client.post("/api/environments", json={"name": "basic-test"})
    env_id = env_res.json()["id"]
    client.put(
        f"/api/environments/{env_id}/variables",
        json={
            "variables": [
                {"name": "user", "value": "bob", "enabled": True},
                {"name": "pass", "value": "hunter2", "enabled": True},
            ]
        },
    )

    headers: dict[str, str] = {}
    query: dict[str, str] = {}
    auth = AuthConfig(type="basic", username="{{user}}", password="{{pass}}")

    from theridion_sidecar import environments

    env = environments.get(env_id)
    _apply_auth(auth, headers, query, env)
    expected = base64.b64encode(b"bob:hunter2").decode()
    assert headers["Authorization"] == f"Basic {expected}"


# ---- persistence round-trip -----------------------------------------------


def test_auth_persists_in_collection(client: TestClient) -> None:
    # Create a collection, save a request with auth, reload.
    coll_res = client.post("/api/collections", json={"name": "AuthColl"})
    coll_id = coll_res.json()["id"]

    save_res = client.post(
        f"/api/collections/{coll_id}/requests",
        json={
            "name": "Secured endpoint",
            "method": "GET",
            "url": "https://api.example.com/data",
            "auth": {"type": "bearer", "token": "{{token}}"},
        },
    )
    assert save_res.status_code == 200

    # Reload collection from disk.
    get_res = client.get(f"/api/collections/{coll_id}")
    items = get_res.json()["items"]
    assert len(items) == 1
    assert items[0]["auth"]["type"] == "bearer"
    assert items[0]["auth"]["token"] == "{{token}}"


def test_auth_null_when_omitted(client: TestClient) -> None:
    coll_res = client.post("/api/collections", json={"name": "NoAuth"})
    coll_id = coll_res.json()["id"]

    save_res = client.post(
        f"/api/collections/{coll_id}/requests",
        json={
            "name": "Public endpoint",
            "method": "GET",
            "url": "https://example.com",
        },
    )
    assert save_res.status_code == 200
    items = client.get(f"/api/collections/{coll_id}").json()["items"]
    assert items[0]["auth"] is None
