"""Tests for persistent request history."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.main import create_app


@pytest.fixture(autouse=True)
def _set_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _make_entry(
    method: str = "GET",
    url: str = "http://example.com/api",
    status: int = 200,
    elapsed_ms: float = 42.0,
) -> dict:
    return {
        "method": method,
        "url": url,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "timestamp": time.time(),
        "request_body": '{"key": "value"}',
        "response_body": '{"result": "ok"}',
        "request_headers": {"Content-Type": "application/json"},
        "response_headers": {"X-Custom": "header"},
    }


# ---------------------------------------------------------------------------
# Record and retrieve
# ---------------------------------------------------------------------------

def test_record_and_list(client: TestClient) -> None:
    r = client.post("/api/history", json=_make_entry())
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["method"] == "GET"

    r2 = client.get("/api/history")
    assert r2.status_code == 200
    body = r2.json()
    assert body["total"] == 1
    assert len(body["entries"]) == 1
    # Summary should not contain bodies
    assert "request_body" not in body["entries"][0]


def test_get_full_entry(client: TestClient) -> None:
    r = client.post("/api/history", json=_make_entry())
    entry_id = r.json()["id"]

    r2 = client.get(f"/api/history/{entry_id}")
    assert r2.status_code == 200
    full = r2.json()
    assert full["request_body"] == '{"key": "value"}'
    assert full["response_body"] == '{"result": "ok"}'
    assert full["request_headers"]["Content-Type"] == "application/json"


def test_get_missing_entry(client: TestClient) -> None:
    r = client.get("/api/history/nonexistent-id")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Search and filter
# ---------------------------------------------------------------------------

def test_filter_by_method(client: TestClient) -> None:
    client.post("/api/history", json=_make_entry(method="GET"))
    client.post("/api/history", json=_make_entry(method="POST"))
    client.post("/api/history", json=_make_entry(method="GET"))

    r = client.get("/api/history?method=GET")
    assert r.json()["total"] == 2

    r2 = client.get("/api/history?method=POST")
    assert r2.json()["total"] == 1


def test_filter_by_status_class(client: TestClient) -> None:
    client.post("/api/history", json=_make_entry(status=200))
    client.post("/api/history", json=_make_entry(status=201))
    client.post("/api/history", json=_make_entry(status=404))
    client.post("/api/history", json=_make_entry(status=500))

    r = client.get("/api/history?status=2")
    assert r.json()["total"] == 2

    r2 = client.get("/api/history?status=4")
    assert r2.json()["total"] == 1

    r3 = client.get("/api/history?status=5")
    assert r3.json()["total"] == 1


def test_filter_by_exact_status(client: TestClient) -> None:
    client.post("/api/history", json=_make_entry(status=200))
    client.post("/api/history", json=_make_entry(status=201))

    r = client.get("/api/history?status=200")
    assert r.json()["total"] == 1


def test_search_by_url(client: TestClient) -> None:
    client.post("/api/history", json=_make_entry(url="http://example.com/users"))
    client.post("/api/history", json=_make_entry(url="http://example.com/posts"))
    client.post("/api/history", json=_make_entry(url="http://example.com/users/1"))

    r = client.get("/api/history?search=users")
    assert r.json()["total"] == 2

    r2 = client.get("/api/history?search=posts")
    assert r2.json()["total"] == 1


def test_pagination(client: TestClient) -> None:
    for i in range(10):
        client.post("/api/history", json=_make_entry(url=f"http://example.com/{i}"))

    r = client.get("/api/history?limit=3&offset=0")
    body = r.json()
    assert body["total"] == 10
    assert len(body["entries"]) == 3

    r2 = client.get("/api/history?limit=3&offset=8")
    assert len(r2.json()["entries"]) == 2


# ---------------------------------------------------------------------------
# FIFO trimming
# ---------------------------------------------------------------------------

def test_fifo_trimming(client: TestClient, tmp_path: Path) -> None:
    """Entries beyond MAX_ENTRIES are trimmed (oldest dropped)."""
    # Patch MAX_ENTRIES to a small number for speed
    import theridion_sidecar.api.history as hist_mod
    original = hist_mod.MAX_ENTRIES
    hist_mod.MAX_ENTRIES = 5
    try:
        for i in range(8):
            client.post("/api/history", json=_make_entry(
                url=f"http://example.com/{i}",
            ))
        r = client.get("/api/history?limit=200")
        body = r.json()
        assert body["total"] == 5
        # Most recent should be first (url ends with /7)
        assert body["entries"][0]["url"] == "http://example.com/7"
        # Oldest kept should be /3
        assert body["entries"][-1]["url"] == "http://example.com/3"
    finally:
        hist_mod.MAX_ENTRIES = original


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_stats_empty(client: TestClient) -> None:
    r = client.get("/api/history/stats")
    assert r.status_code == 200
    s = r.json()
    assert s["total"] == 0
    assert s["avg_response_time_ms"] == 0.0


def test_stats_calculation(client: TestClient) -> None:
    client.post("/api/history", json=_make_entry(
        method="GET", url="http://a.com/x", status=200, elapsed_ms=100,
    ))
    client.post("/api/history", json=_make_entry(
        method="GET", url="http://a.com/x", status=200, elapsed_ms=200,
    ))
    client.post("/api/history", json=_make_entry(
        method="POST", url="http://a.com/y", status=500, elapsed_ms=300,
    ))

    r = client.get("/api/history/stats")
    s = r.json()
    assert s["total"] == 3
    assert s["avg_response_time_ms"] == 200.0
    assert s["status_distribution"]["2xx"] == 2
    assert s["status_distribution"]["5xx"] == 1
    assert len(s["top_endpoints"]) >= 2


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_single(client: TestClient) -> None:
    r = client.post("/api/history", json=_make_entry())
    entry_id = r.json()["id"]

    r2 = client.delete(f"/api/history/{entry_id}")
    assert r2.status_code == 204

    r3 = client.get("/api/history")
    assert r3.json()["total"] == 0


def test_delete_missing_returns_404(client: TestClient) -> None:
    r = client.delete("/api/history/nonexistent")
    assert r.status_code == 404


def test_clear_all(client: TestClient) -> None:
    client.post("/api/history", json=_make_entry())
    client.post("/api/history", json=_make_entry())

    r = client.delete("/api/history")
    assert r.status_code == 204

    r2 = client.get("/api/history")
    assert r2.json()["total"] == 0


def test_body_truncation(client: TestClient) -> None:
    """Bodies exceeding 10KB are truncated."""
    big_body = "x" * 20_000
    r = client.post("/api/history", json=_make_entry() | {
        "request_body": big_body,
        "response_body": big_body,
    })
    entry = r.json()
    assert len(entry["request_body"]) == 10_000
    assert len(entry["response_body"]) == 10_000


def test_newest_first_ordering(client: TestClient) -> None:
    """Most recent entries appear first in listing."""
    for i in range(3):
        client.post("/api/history", json=_make_entry(url=f"http://e.com/{i}"))

    r = client.get("/api/history")
    urls = [e["url"] for e in r.json()["entries"]]
    assert urls == [
        "http://e.com/2",
        "http://e.com/1",
        "http://e.com/0",
    ]
