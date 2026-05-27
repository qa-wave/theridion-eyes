"""Tests for performance budget monitoring API."""

from __future__ import annotations

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


def test_list_budgets_empty(client: TestClient):
    resp = client.get("/api/perf/budgets")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_budget(client: TestClient):
    payload = {
        "url_pattern": "https://api.example.com/*",
        "method": "GET",
        "max_time_ms": 500,
        "max_size_bytes": 10240,
        "name": "Example API",
    }
    resp = client.post("/api/perf/budgets", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["url_pattern"] == "https://api.example.com/*"
    assert data["max_time_ms"] == 500
    assert data["name"] == "Example API"
    assert "id" in data


def test_update_budget(client: TestClient):
    resp = client.post("/api/perf/budgets", json={
        "url_pattern": "https://api.example.com/*",
        "max_time_ms": 500,
    })
    budget_id = resp.json()["id"]

    resp = client.put(f"/api/perf/budgets/{budget_id}", json={
        "max_time_ms": 1000,
        "name": "Updated",
    })
    assert resp.status_code == 200
    assert resp.json()["max_time_ms"] == 1000
    assert resp.json()["name"] == "Updated"


def test_update_budget_not_found(client: TestClient):
    resp = client.put("/api/perf/budgets/nonexistent", json={
        "max_time_ms": 1000,
    })
    assert resp.status_code == 404


def test_delete_budget(client: TestClient):
    resp = client.post("/api/perf/budgets", json={
        "url_pattern": "*",
        "max_time_ms": 500,
    })
    budget_id = resp.json()["id"]

    resp = client.delete(f"/api/perf/budgets/{budget_id}")
    assert resp.status_code == 204

    resp = client.get("/api/perf/budgets")
    assert resp.json() == []


def test_delete_budget_not_found(client: TestClient):
    resp = client.delete("/api/perf/budgets/nonexistent")
    assert resp.status_code == 404


def test_check_passes_under_budget(client: TestClient):
    client.post("/api/perf/budgets", json={
        "url_pattern": "https://api.example.com/*",
        "max_time_ms": 500,
        "max_size_bytes": 10240,
    })

    resp = client.post("/api/perf/check", json={
        "url": "https://api.example.com/users",
        "method": "GET",
        "elapsed_ms": 200,
        "body_size": 5000,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["violations"] == []
    assert len(data["passed"]) == 1


def test_check_fails_over_time_budget(client: TestClient):
    client.post("/api/perf/budgets", json={
        "url_pattern": "https://api.example.com/*",
        "max_time_ms": 500,
        "name": "Time Budget",
    })

    resp = client.post("/api/perf/check", json={
        "url": "https://api.example.com/users",
        "method": "GET",
        "elapsed_ms": 800,
    })
    data = resp.json()
    assert len(data["violations"]) == 1
    v = data["violations"][0]
    assert v["metric"] == "max_time_ms"
    assert v["actual"] == 800
    assert v["threshold"] == 500
    assert v["exceeded_by_percent"] == 60.0


def test_check_fails_over_size_budget(client: TestClient):
    client.post("/api/perf/budgets", json={
        "url_pattern": "*",
        "max_time_ms": 10000,
        "max_size_bytes": 1000,
        "name": "Size Budget",
    })

    resp = client.post("/api/perf/check", json={
        "url": "https://example.com/data",
        "elapsed_ms": 100,
        "body_size": 2000,
    })
    data = resp.json()
    assert len(data["violations"]) == 1
    assert data["violations"][0]["metric"] == "max_size_bytes"
    assert data["violations"][0]["exceeded_by_percent"] == 100.0


def test_url_pattern_glob_matching(client: TestClient):
    client.post("/api/perf/budgets", json={
        "url_pattern": "https://api.example.com/v2/*",
        "max_time_ms": 200,
    })

    # Should NOT match v1
    resp = client.post("/api/perf/check", json={
        "url": "https://api.example.com/v1/users",
        "elapsed_ms": 500,
    })
    assert resp.json()["violations"] == []

    # Should match v2
    resp = client.post("/api/perf/check", json={
        "url": "https://api.example.com/v2/users",
        "elapsed_ms": 500,
    })
    assert len(resp.json()["violations"]) == 1


def test_url_pattern_regex_matching(client: TestClient):
    client.post("/api/perf/budgets", json={
        "url_pattern": "^https://api\\.example\\.com/v\\d+/users",
        "max_time_ms": 200,
    })

    # Match
    resp = client.post("/api/perf/check", json={
        "url": "https://api.example.com/v3/users",
        "elapsed_ms": 500,
    })
    assert len(resp.json()["violations"]) == 1

    # No match
    resp = client.post("/api/perf/check", json={
        "url": "https://other.com/v3/users",
        "elapsed_ms": 500,
    })
    assert resp.json()["violations"] == []


def test_method_filter(client: TestClient):
    client.post("/api/perf/budgets", json={
        "url_pattern": "*",
        "method": "POST",
        "max_time_ms": 200,
    })

    # GET should not be checked against POST budget
    resp = client.post("/api/perf/check", json={
        "url": "https://example.com/data",
        "method": "GET",
        "elapsed_ms": 500,
    })
    assert resp.json()["violations"] == []

    # POST should match
    resp = client.post("/api/perf/check", json={
        "url": "https://example.com/data",
        "method": "POST",
        "elapsed_ms": 500,
    })
    assert len(resp.json()["violations"]) == 1


def test_violations_tracking(client: TestClient):
    client.post("/api/perf/budgets", json={
        "url_pattern": "*",
        "max_time_ms": 100,
        "name": "Global",
    })

    # Trigger violation
    client.post("/api/perf/check", json={
        "url": "https://example.com",
        "elapsed_ms": 500,
    })

    resp = client.get("/api/perf/violations")
    assert resp.status_code == 200
    violations = resp.json()
    assert len(violations) == 1
    assert violations[0]["budget_name"] == "Global"


def test_auto_budget_generation(client: TestClient):
    history = [
        {"url": "https://api.example.com/users", "method": "GET", "elapsed_ms": 100, "body_size": 500},
        {"url": "https://api.example.com/users", "method": "GET", "elapsed_ms": 120, "body_size": 600},
        {"url": "https://api.example.com/users", "method": "GET", "elapsed_ms": 150, "body_size": 700},
        {"url": "https://api.example.com/users", "method": "GET", "elapsed_ms": 200, "body_size": 800},
        {"url": "https://api.example.com/users", "method": "GET", "elapsed_ms": 250, "body_size": 900},
        {"url": "https://api.example.com/posts", "method": "POST", "elapsed_ms": 300, "body_size": 1000},
        {"url": "https://api.example.com/posts", "method": "POST", "elapsed_ms": 350, "body_size": 1200},
    ]

    resp = client.post("/api/perf/auto-budget", json={
        "history": history,
        "multiplier": 1.5,
    })
    assert resp.status_code == 200
    data = resp.json()
    suggested = data["suggested"]
    assert len(suggested) == 2

    for budget in suggested:
        assert budget["max_time_ms"] > 0
        assert budget["p95_time_ms"] is not None
        assert budget["url_pattern"] in [
            "https://api.example.com/users",
            "https://api.example.com/posts",
        ]


def test_auto_budget_empty_history(client: TestClient):
    resp = client.post("/api/perf/auto-budget", json={"history": []})
    assert resp.status_code == 200
    assert resp.json()["suggested"] == []
