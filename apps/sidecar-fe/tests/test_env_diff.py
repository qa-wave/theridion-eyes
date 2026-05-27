"""Tests for environment diff and clone endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def _create_env(client: TestClient, name: str, variables: list[dict[str, object]]) -> dict:
    env = client.post("/api/environments", json={"name": name}).json()
    if variables:
        client.put(
            f"/api/environments/{env['id']}/variables",
            json={"variables": variables},
        )
    return env


# ---- diff tests ------------------------------------------------------------


def test_diff_overlapping_and_unique_vars(client: TestClient) -> None:
    left = _create_env(client, "Left", [
        {"name": "shared", "value": "same-value"},
        {"name": "left_only", "value": "L"},
        {"name": "changed", "value": "old"},
    ])
    right = _create_env(client, "Right", [
        {"name": "shared", "value": "same-value"},
        {"name": "right_only", "value": "R"},
        {"name": "changed", "value": "new"},
    ])

    res = client.post("/api/environments/diff", json={
        "left_id": left["id"],
        "right_id": right["id"],
    })
    assert res.status_code == 200
    body = res.json()

    assert len(body["only_left"]) == 1
    assert body["only_left"][0]["name"] == "left_only"
    assert body["only_left"][0]["value"] == "L"

    assert len(body["only_right"]) == 1
    assert body["only_right"][0]["name"] == "right_only"
    assert body["only_right"][0]["value"] == "R"

    assert len(body["different"]) == 1
    assert body["different"][0]["name"] == "changed"
    assert body["different"][0]["left_value"] == "old"
    assert body["different"][0]["right_value"] == "new"

    assert len(body["same"]) == 1
    assert body["same"][0]["name"] == "shared"
    assert body["same"][0]["value"] == "same-value"


def test_diff_identical_envs(client: TestClient) -> None:
    vars_list = [
        {"name": "a", "value": "1"},
        {"name": "b", "value": "2"},
    ]
    left = _create_env(client, "E1", vars_list)
    right = _create_env(client, "E2", vars_list)

    res = client.post("/api/environments/diff", json={
        "left_id": left["id"],
        "right_id": right["id"],
    })
    assert res.status_code == 200
    body = res.json()

    assert body["only_left"] == []
    assert body["only_right"] == []
    assert body["different"] == []
    assert len(body["same"]) == 2


def test_diff_with_empty_env(client: TestClient) -> None:
    populated = _create_env(client, "Full", [
        {"name": "x", "value": "1"},
        {"name": "y", "value": "2"},
    ])
    empty = _create_env(client, "Empty", [])

    res = client.post("/api/environments/diff", json={
        "left_id": populated["id"],
        "right_id": empty["id"],
    })
    assert res.status_code == 200
    body = res.json()

    assert len(body["only_left"]) == 2
    assert body["only_right"] == []
    assert body["different"] == []
    assert body["same"] == []


def test_diff_both_empty(client: TestClient) -> None:
    e1 = _create_env(client, "A", [])
    e2 = _create_env(client, "B", [])

    res = client.post("/api/environments/diff", json={
        "left_id": e1["id"],
        "right_id": e2["id"],
    })
    assert res.status_code == 200
    body = res.json()
    assert body["only_left"] == []
    assert body["only_right"] == []
    assert body["different"] == []
    assert body["same"] == []


def test_diff_missing_env_404(client: TestClient) -> None:
    env = _create_env(client, "E", [{"name": "a", "value": "1"}])
    fake_id = "00000000-0000-0000-0000-000000000000"

    # Missing left
    res = client.post("/api/environments/diff", json={
        "left_id": fake_id,
        "right_id": env["id"],
    })
    assert res.status_code == 404

    # Missing right
    res = client.post("/api/environments/diff", json={
        "left_id": env["id"],
        "right_id": fake_id,
    })
    assert res.status_code == 404


def test_diff_ignores_disabled_vars(client: TestClient) -> None:
    left = _create_env(client, "L", [
        {"name": "active", "value": "yes"},
        {"name": "disabled_var", "value": "hidden", "enabled": False},
    ])
    right = _create_env(client, "R", [
        {"name": "active", "value": "yes"},
    ])

    res = client.post("/api/environments/diff", json={
        "left_id": left["id"],
        "right_id": right["id"],
    })
    assert res.status_code == 200
    body = res.json()

    # Disabled var should not appear in diff
    assert len(body["same"]) == 1
    assert body["only_left"] == []


# ---- clone tests -----------------------------------------------------------


def test_clone_and_verify_copy(client: TestClient) -> None:
    source = _create_env(client, "Original", [
        {"name": "host", "value": "api.example.com"},
        {"name": "token", "value": "secret123"},
    ])

    res = client.post(
        f"/api/environments/{source['id']}/clone",
        json={"new_name": "Original (Copy)"},
    )
    assert res.status_code == 201
    clone_summary = res.json()
    assert clone_summary["name"] == "Original (Copy)"
    assert clone_summary["variable_count"] == 2
    assert clone_summary["id"] != source["id"]

    # Fetch the full clone and verify variables match
    clone_full = client.get(f"/api/environments/{clone_summary['id']}").json()
    assert len(clone_full["variables"]) == 2
    assert clone_full["variables"][0]["name"] == "host"
    assert clone_full["variables"][0]["value"] == "api.example.com"
    assert clone_full["variables"][1]["name"] == "token"
    assert clone_full["variables"][1]["value"] == "secret123"


def test_clone_empty_env(client: TestClient) -> None:
    source = _create_env(client, "Bare", [])

    res = client.post(
        f"/api/environments/{source['id']}/clone",
        json={"new_name": "Bare Clone"},
    )
    assert res.status_code == 201
    assert res.json()["variable_count"] == 0


def test_clone_missing_env_404(client: TestClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    res = client.post(
        f"/api/environments/{fake_id}/clone",
        json={"new_name": "Nope"},
    )
    assert res.status_code == 404


def test_clone_preserves_enabled_state(client: TestClient) -> None:
    source = _create_env(client, "Mixed", [
        {"name": "on", "value": "1", "enabled": True},
        {"name": "off", "value": "2", "enabled": False},
    ])

    res = client.post(
        f"/api/environments/{source['id']}/clone",
        json={"new_name": "Mixed Copy"},
    )
    assert res.status_code == 201

    clone_full = client.get(f"/api/environments/{res.json()['id']}").json()
    by_name = {v["name"]: v for v in clone_full["variables"]}
    assert by_name["on"]["enabled"] is True
    assert by_name["off"]["enabled"] is False
