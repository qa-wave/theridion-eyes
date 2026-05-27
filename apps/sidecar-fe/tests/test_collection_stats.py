"""Tests for the collection statistics endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def _create_collection(client: TestClient, name: str = "Test") -> str:
    res = client.post("/api/collections", json={"name": name})
    assert res.status_code == 201
    return res.json()["id"]


def _add_request(
    client: TestClient,
    coll_id: str,
    *,
    name: str = "req",
    method: str = "GET",
    url: str = "http://example.com/api",
    headers: dict | None = None,
    body: str | None = None,
    auth: dict | None = None,
    assertions: list | None = None,
    parent_folder_id: str | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "method": method,
        "url": url,
    }
    if headers:
        payload["headers"] = headers
    if body is not None:
        payload["body"] = body
    if auth is not None:
        payload["auth"] = auth
    if assertions is not None:
        payload["assertions"] = assertions
    if parent_folder_id is not None:
        payload["parent_folder_id"] = parent_folder_id
    res = client.post(f"/api/collections/{coll_id}/requests", json=payload)
    assert res.status_code == 200
    return res.json()


def test_stats_mixed_methods(client: TestClient) -> None:
    coll_id = _create_collection(client)
    _add_request(client, coll_id, name="Get Users", method="GET", url="http://api.test/users")
    _add_request(client, coll_id, name="Create User", method="POST", url="http://api.test/users", body='{"name":"x"}')
    _add_request(client, coll_id, name="Delete User", method="DELETE", url="http://api.test/users/1")
    _add_request(client, coll_id, name="Update User", method="PUT", url="http://api.test/users/1", body='{"name":"y"}')

    res = client.get(f"/api/collections/{coll_id}/stats")
    assert res.status_code == 200
    data = res.json()

    breakdown = data["request_breakdown"]
    assert breakdown["total"] == 4
    assert breakdown["by_method"]["GET"] == 1
    assert breakdown["by_method"]["POST"] == 1
    assert breakdown["by_method"]["DELETE"] == 1
    assert breakdown["by_method"]["PUT"] == 1

    # Body analysis
    body = data["body_analysis"]
    assert body["with_body"] == 2
    assert body["without_body"] == 2

    # URL analysis
    url_analysis = data["url_analysis"]
    assert "http://api.test" in url_analysis["unique_base_urls"]


def test_stats_empty_collection(client: TestClient) -> None:
    coll_id = _create_collection(client)

    res = client.get(f"/api/collections/{coll_id}/stats")
    assert res.status_code == 200
    data = res.json()

    assert data["request_breakdown"]["total"] == 0
    assert data["coverage"]["with_assertions"] == 0
    assert data["coverage"]["assertion_coverage_pct"] == 0
    assert data["auth_usage"]["with_auth"] == 0
    assert data["complexity"]["total_headers"] == 0


def test_stats_with_assertions_and_auth(client: TestClient) -> None:
    coll_id = _create_collection(client)
    _add_request(
        client, coll_id,
        name="Authed",
        method="GET",
        url="http://api.test/me",
        auth={"type": "bearer", "token": "abc123"},
        assertions=[
            {"type": "status", "expected": "200"},
            {"type": "body_contains", "expected": "user"},
        ],
    )
    _add_request(
        client, coll_id,
        name="No Auth",
        method="GET",
        url="http://api.test/public",
    )

    res = client.get(f"/api/collections/{coll_id}/stats")
    assert res.status_code == 200
    data = res.json()

    # Coverage
    cov = data["coverage"]
    assert cov["with_assertions"] == 1
    assert cov["without_assertions"] == 1
    assert cov["assertion_coverage_pct"] == 50.0
    assert cov["assertion_type_distribution"]["status"] == 1
    assert cov["assertion_type_distribution"]["body_contains"] == 1

    # Auth
    auth = data["auth_usage"]
    assert auth["with_auth"] == 1
    assert auth["without_auth"] == 1
    assert auth["auth_coverage_pct"] == 50.0
    assert auth["auth_type_distribution"]["bearer"] == 1


def test_stats_nonexistent_collection(client: TestClient) -> None:
    res = client.get("/api/collections/00000000-0000-0000-0000-000000000000/stats")
    assert res.status_code == 404
