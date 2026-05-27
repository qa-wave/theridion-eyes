"""Tests for the request pipeline API (/api/pipeline/*)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

# Use valid UUIDs for "missing" references so storage.get doesn't choke
# on malformed path construction.
MISSING_COL = str(uuid.uuid4())
MISSING_REQ = str(uuid.uuid4())


def _seed_collection(client: TestClient, name: str = "Test") -> tuple[str, str]:
    """Create a collection with one GET request and return (collection_id, request_id)."""
    resp = client.post("/api/collections", json={"name": name})
    assert resp.status_code == 201
    col_id = resp.json()["id"]

    resp = client.post(
        f"/api/collections/{col_id}/requests",
        json={
            "name": "ping",
            "method": "GET",
            "url": "https://httpbin.org/get",
        },
    )
    assert resp.status_code == 200
    req_id = resp.json()["items"][0]["id"]
    return col_id, req_id


# ---- /api/pipeline/templates -----------------------------------------------


def test_templates_returns_list(client: TestClient) -> None:
    resp = client.get("/api/pipeline/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert isinstance(templates, list)
    assert len(templates) >= 3
    names = {t["name"] for t in templates}
    assert "Auth Flow" in names
    assert "CRUD Flow" in names
    assert "Health Check" in names


# ---- /api/pipeline/validate ------------------------------------------------


def test_validate_missing_collection(client: TestClient) -> None:
    resp = client.post(
        "/api/pipeline/validate",
        json={
            "name": "test",
            "steps": [
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert len(data["issues"]) == 1
    assert data["issues"][0]["field"] == "collection_id"


def test_validate_missing_request(client: TestClient) -> None:
    col_id, _ = _seed_collection(client)
    resp = client.post(
        "/api/pipeline/validate",
        json={
            "name": "test",
            "steps": [
                {
                    "request_id": MISSING_REQ,
                    "collection_id": col_id,
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["issues"][0]["field"] == "request_id"


def test_validate_bad_condition_syntax(client: TestClient) -> None:
    col_id, req_id = _seed_collection(client)
    resp = client.post(
        "/api/pipeline/validate",
        json={
            "name": "test",
            "steps": [
                {
                    "request_id": req_id,
                    "collection_id": col_id,
                    "condition": "this is not valid",
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["issues"][0]["field"] == "condition"


def test_validate_valid_pipeline(client: TestClient) -> None:
    col_id, req_id = _seed_collection(client)
    resp = client.post(
        "/api/pipeline/validate",
        json={
            "name": "test",
            "steps": [
                {
                    "request_id": req_id,
                    "collection_id": col_id,
                    "condition": "status == 200",
                },
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


# ---- /api/pipeline/execute -------------------------------------------------


def test_execute_nonexistent_request_stop(client: TestClient) -> None:
    """When a step references a missing request and on_fail=stop, subsequent
    steps are skipped."""
    resp = client.post(
        "/api/pipeline/execute",
        json={
            "name": "fail-fast",
            "steps": [
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                    "on_fail": "stop",
                },
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                    "on_fail": "stop",
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed"] >= 1
    # Second step should be skipped
    assert data["results"][1]["skipped"] is True


def test_execute_nonexistent_request_continue(client: TestClient) -> None:
    """When on_fail=continue, the pipeline keeps going after failure."""
    resp = client.post(
        "/api/pipeline/execute",
        json={
            "name": "keep-going",
            "steps": [
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                    "on_fail": "continue",
                },
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                    "on_fail": "continue",
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["failed"] == 2
    assert data["results"][0]["skipped"] is False
    assert data["results"][1]["skipped"] is False


def test_execute_condition_skip(client: TestClient) -> None:
    """A step with an unsatisfied condition is skipped."""
    col_id, req_id = _seed_collection(client)
    resp = client.post(
        "/api/pipeline/execute",
        json={
            "name": "conditional",
            "steps": [
                {
                    "request_id": req_id,
                    "collection_id": col_id,
                    # last_status is None at start, so 'status == 200' is False
                    "condition": "status == 200",
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["skipped"] is True


def test_execute_variables_returned(client: TestClient) -> None:
    """Pipeline variables from input are present in the result."""
    resp = client.post(
        "/api/pipeline/execute",
        json={
            "name": "with-vars",
            "variables": {"base_url": "https://example.com"},
            "steps": [
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                    "on_fail": "continue",
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["variables"]["base_url"] == "https://example.com"


def test_execute_environment_not_found(client: TestClient) -> None:
    """Referencing a non-existent environment returns 404."""
    resp = client.post(
        "/api/pipeline/execute",
        json={
            "name": "bad-env",
            "environment_id": str(uuid.uuid4()),
            "steps": [
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                },
            ],
        },
    )
    assert resp.status_code == 404


def test_condition_variable_expression(client: TestClient) -> None:
    """A variable condition that is satisfied should not skip the step."""
    resp = client.post(
        "/api/pipeline/execute",
        json={
            "name": "var-cond",
            "variables": {"token": "abc123"},
            "steps": [
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                    "condition": 'variable.token != ""',
                    "on_fail": "continue",
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Condition passes (token != ""), so step is NOT skipped
    assert data["results"][0]["skipped"] is False


def test_condition_variable_empty_skips(client: TestClient) -> None:
    """A variable condition checking non-empty but var is empty should skip."""
    resp = client.post(
        "/api/pipeline/execute",
        json={
            "name": "var-cond-skip",
            "variables": {"token": ""},
            "steps": [
                {
                    "request_id": MISSING_REQ,
                    "collection_id": MISSING_COL,
                    "condition": 'variable.token != ""',
                    "on_fail": "continue",
                },
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["skipped"] is True
