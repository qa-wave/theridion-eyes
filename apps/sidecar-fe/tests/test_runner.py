"""Tests for the collection runner endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.api.runner import _collect_requests
from theridion_sidecar.models import CollectionItem


# ---------------------------------------------------------------------------
# _collect_requests unit tests
# ---------------------------------------------------------------------------

def test_collect_flat_list() -> None:
    items = [
        CollectionItem(id="1", name="R1", url="http://a"),
        CollectionItem(id="2", name="R2", url="http://b"),
    ]
    result = _collect_requests(items)
    assert len(result) == 2
    assert [r.id for r in result] == ["1", "2"]


def test_collect_skips_folders_but_includes_children() -> None:
    items = [
        CollectionItem(
            id="f1",
            name="Folder",
            is_folder=True,
            items=[
                CollectionItem(id="r1", name="Inner", url="http://x"),
            ],
        ),
        CollectionItem(id="r2", name="Outer", url="http://y"),
    ]
    result = _collect_requests(items)
    assert len(result) == 2
    assert [r.id for r in result] == ["r1", "r2"]


def test_collect_nested_folders() -> None:
    items = [
        CollectionItem(
            id="f1",
            name="Top",
            is_folder=True,
            items=[
                CollectionItem(
                    id="f2",
                    name="Mid",
                    is_folder=True,
                    items=[
                        CollectionItem(id="r1", name="Deep", url="http://d"),
                    ],
                ),
            ],
        ),
    ]
    result = _collect_requests(items)
    assert len(result) == 1
    assert result[0].id == "r1"


def test_collect_empty() -> None:
    assert _collect_requests([]) == []


def test_collect_empty_folder() -> None:
    items = [
        CollectionItem(id="f1", name="Empty", is_folder=True, items=[]),
    ]
    assert _collect_requests(items) == []


# ---------------------------------------------------------------------------
# Integration tests via /api/runner endpoint
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, url: str = "") -> None:
        self.status_code = 200
        self.reason_phrase = "OK"
        self.headers: dict[str, str] = {"content-type": "application/json"}
        self.text = '{"ok": true}'
        self.content = b'{"ok": true}'
        self.url = url
        self.cookies: dict[str, str] = {}


class _FakeClient:
    """Stand-in for httpx.AsyncClient that returns canned responses."""

    def __init__(self, *_a: Any, **_kw: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_a: Any) -> None:
        return None

    async def request(self, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(url=kwargs.get("url", ""))


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    from theridion_sidecar.main import create_app

    return TestClient(create_app())


def _create_collection_with_request(
    client: TestClient,
    url: str = "https://example.com/api",
    method: str = "GET",
    assertions: list[dict[str, str]] | None = None,
) -> str:
    """Helper: create a collection, add a request, return collection id."""
    coll = client.post("/api/collections", json={"name": "Test"}).json()
    coll_id = coll["id"]
    req_body: dict[str, Any] = {
        "name": "req1",
        "method": method,
        "url": url,
    }
    if assertions:
        req_body["assertions"] = assertions
    client.post(f"/api/collections/{coll_id}/requests", json=req_body)
    return coll_id


def test_run_collection_success(client: TestClient) -> None:
    coll_id = _create_collection_with_request(client)

    with patch("theridion_sidecar.api.runner.httpx.AsyncClient", _FakeClient):
        res = client.post(f"/api/runner/{coll_id}/run", json={})

    assert res.status_code == 200
    data = res.json()
    assert data["collection_id"] == coll_id
    assert data["total_requests"] == 1
    assert data["successful_requests"] == 1
    assert data["failed_requests"] == 0


def test_run_collection_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/runner/00000000-0000-0000-0000-000000000099/run",
        json={},
    )
    assert res.status_code == 404


def test_run_collection_with_assertions(client: TestClient) -> None:
    coll_id = _create_collection_with_request(
        client,
        assertions=[
            {"type": "status", "expected": "200"},
            {"type": "status", "expected": "404"},  # will fail
        ],
    )

    with patch("theridion_sidecar.api.runner.httpx.AsyncClient", _FakeClient):
        res = client.post(f"/api/runner/{coll_id}/run", json={})

    data = res.json()
    assert data["total_assertions"] == 2
    assert data["passed_assertions"] == 1
    assert data["failed_assertions"] == 1
    # Per-request breakdown
    req_result = data["results"][0]
    assert req_result["assertions_passed"] == 1
    assert req_result["assertions_failed"] == 1


def test_run_empty_collection(client: TestClient) -> None:
    coll = client.post("/api/collections", json={"name": "Empty"}).json()

    with patch("theridion_sidecar.api.runner.httpx.AsyncClient", _FakeClient):
        res = client.post(f"/api/runner/{coll['id']}/run", json={})

    data = res.json()
    assert data["total_requests"] == 0
    assert data["successful_requests"] == 0
