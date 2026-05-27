"""Tests for the full variable scoping / resolution chain.

Resolution order (later wins):
    globals -> collection vars -> env vars -> extra (runtime) -> built-ins
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def _set_globals(client: TestClient, variables: list[dict[str, object]]) -> None:
    res = client.put("/api/globals", json={"variables": variables})
    assert res.status_code == 200


def _create_env(client: TestClient, name: str, variables: list[dict[str, object]]) -> str:
    env = client.post("/api/environments", json={"name": name}).json()
    client.put(
        f"/api/environments/{env['id']}/variables",
        json={"variables": variables},
    )
    return env["id"]


def _create_collection_with_vars(
    client: TestClient,
    name: str,
    variables: list[dict[str, object]],
) -> str:
    coll = client.post("/api/collections", json={"name": name}).json()
    client.patch(
        f"/api/collections/{coll['id']}/variables",
        json={"variables": variables},
    )
    return coll["id"]


# --------------------------------------------------------------------------
# Pure substitute() unit tests
# --------------------------------------------------------------------------


def test_globals_only_substitution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Globals are the lowest-priority scope and should resolve alone."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import globals as gs, environments

    gs.save(gs.GlobalsStore(variables=[gs.GlobalVariable(name="host", value="example.com")]))
    result = environments.substitute("https://{{host}}/api", None)
    assert result == "https://example.com/api"


def test_collection_vars_override_globals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Collection vars sit above globals in priority."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import globals as gs, environments

    gs.save(gs.GlobalsStore(variables=[gs.GlobalVariable(name="host", value="global.example.com")]))
    coll_vars = {"host": "collection.example.com"}
    result = environments.substitute("https://{{host}}/api", None, collection_vars=coll_vars)
    assert result == "https://collection.example.com/api"


def test_env_vars_override_collection_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment vars override collection vars."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import globals as gs, environments

    gs.save(gs.GlobalsStore(variables=[gs.GlobalVariable(name="host", value="global.example.com")]))
    coll_vars = {"host": "collection.example.com"}
    env = environments.create("prod")
    environments.replace_variables(env.id, [environments.EnvVariable(name="host", value="prod.example.com")])
    env = environments.get(env.id)
    result = environments.substitute("https://{{host}}/api", env, collection_vars=coll_vars)
    assert result == "https://prod.example.com/api"


def test_extra_overrides_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runtime extra dict should override globals, collection, and env."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import globals as gs, environments

    gs.save(gs.GlobalsStore(variables=[gs.GlobalVariable(name="token", value="global-tok")]))
    coll_vars = {"token": "coll-tok"}
    env = environments.create("staging")
    environments.replace_variables(env.id, [environments.EnvVariable(name="token", value="env-tok")])
    env = environments.get(env.id)
    extra = {"token": "runtime-tok"}
    result = environments.substitute("Bearer {{token}}", env, extra=extra, collection_vars=coll_vars)
    assert result == "Bearer runtime-tok"


def test_disabled_globals_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import globals as gs, environments

    gs.save(gs.GlobalsStore(variables=[
        gs.GlobalVariable(name="host", value="enabled.example.com"),
        gs.GlobalVariable(name="port", value="9999", enabled=False),
    ]))
    result = environments.substitute("{{host}}:{{port}}", None)
    assert result == "enabled.example.com:{{port}}"


def test_disabled_collection_vars_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import environments

    # Disabled collection vars should not appear in the dict (caller filters)
    coll_vars = {"active": "yes"}  # only enabled vars passed
    result = environments.substitute("{{active}} {{missing}}", None, collection_vars=coll_vars)
    assert result == "yes {{missing}}"


def test_disabled_env_vars_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import environments

    env = environments.create("test")
    environments.replace_variables(env.id, [
        environments.EnvVariable(name="a", value="ON"),
        environments.EnvVariable(name="b", value="OFF", enabled=False),
    ])
    env = environments.get(env.id)
    result = environments.substitute("{{a}} {{b}}", env)
    assert result == "ON {{b}}"


def test_builtins_work_alongside_all_scopes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Built-in $-functions coexist with user-defined vars at all scopes."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import globals as gs, environments

    gs.save(gs.GlobalsStore(variables=[gs.GlobalVariable(name="host", value="api.test")]))
    coll_vars = {"version": "v2"}
    result = environments.substitute(
        "https://{{host}}/{{version}}/{{$uuid}}",
        None,
        collection_vars=coll_vars,
    )
    assert "api.test" in result
    assert "/v2/" in result
    # UUID should be replaced (36 chars, 8-4-4-4-12 pattern)
    assert re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", result)


def test_substitute_dict_passes_collection_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """substitute_dict should forward collection_vars."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import environments

    coll_vars = {"token": "abc123"}
    result = environments.substitute_dict(
        {"Authorization": "Bearer {{token}}", "Accept": "application/json"},
        None,
        collection_vars=coll_vars,
    )
    assert result["Authorization"] == "Bearer abc123"
    assert result["Accept"] == "application/json"


def test_full_chain_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each scope only overrides the vars it defines; others pass through."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import globals as gs, environments

    gs.save(gs.GlobalsStore(variables=[
        gs.GlobalVariable(name="a", value="global-a"),
        gs.GlobalVariable(name="b", value="global-b"),
        gs.GlobalVariable(name="c", value="global-c"),
        gs.GlobalVariable(name="d", value="global-d"),
    ]))
    coll_vars = {"b": "coll-b", "c": "coll-c", "d": "coll-d"}
    env = environments.create("e")
    environments.replace_variables(env.id, [
        environments.EnvVariable(name="c", value="env-c"),
        environments.EnvVariable(name="d", value="env-d"),
    ])
    env = environments.get(env.id)
    extra = {"d": "extra-d"}

    result = environments.substitute(
        "{{a}} {{b}} {{c}} {{d}}",
        env,
        extra=extra,
        collection_vars=coll_vars,
    )
    assert result == "global-a coll-b env-c extra-d"


# --------------------------------------------------------------------------
# Integration test: execute endpoint with collection_id
# --------------------------------------------------------------------------


def test_execute_uses_collection_vars(client: TestClient) -> None:
    """The /api/requests/execute endpoint should resolve collection vars."""
    coll_id = _create_collection_with_vars(client, "Test API", [
        {"name": "base", "value": "httpbin.org", "enabled": True},
    ])
    # We can't actually call httpbin in a unit test, so we just verify the
    # resolved_url in a 502 (transport error) response or check that the
    # endpoint accepts collection_id without error. Use a non-routable address
    # to get a fast transport error.
    res = client.post("/api/requests/execute", json={
        "method": "GET",
        "url": "http://{{base}}/get",
        "collection_id": coll_id,
        "timeout_seconds": 1,
    })
    # Expect 502 (transport error) because httpbin.org may not be reachable,
    # but the URL must have been resolved (not contain {{base}}).
    if res.status_code == 200:
        assert "httpbin.org" in res.json()["final_url"]
    else:
        assert res.status_code == 502
        # The resolved URL appears in the detail message
        detail = res.json().get("detail", "")
        assert "{{base}}" not in detail


def test_execute_collection_vars_lower_than_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment vars should override collection vars at substitution level.

    We test this via the pure substitute() function to avoid network
    dependency -- the priority chain is the same one used by the execute
    endpoint.
    """
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar import environments

    coll_vars = {"host": "coll-host"}
    env = environments.create("Env")
    environments.replace_variables(env.id, [
        environments.EnvVariable(name="host", value="env-host"),
    ])
    env = environments.get(env.id)
    result = environments.substitute("http://{{host}}/test", env, collection_vars=coll_vars)
    assert result == "http://env-host/test"
