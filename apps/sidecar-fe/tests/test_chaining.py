"""Tests for request chaining — /api/requests/extract endpoint."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def test_extract_from_json_body(client: TestClient) -> None:
    body = json.dumps({"data": {"token": "abc123", "user": {"id": 42, "name": "Alice"}}})
    resp = client.post(
        "/api/requests/extract",
        json={
            "response_body": body,
            "response_headers": {},
            "response_status": 200,
            "rules": [
                {"name": "auth_token", "source": "body", "path": "data.token"},
                {"name": "user_id", "source": "body", "path": "data.user.id"},
                {"name": "user_name", "source": "body", "path": "data.user.name"},
            ],
        },
    )
    assert resp.status_code == 200
    extracted = resp.json()["extracted"]
    assert extracted["auth_token"] == "abc123"
    assert extracted["user_id"] == "42"
    assert extracted["user_name"] == "Alice"


def test_extract_from_headers(client: TestClient) -> None:
    resp = client.post(
        "/api/requests/extract",
        json={
            "response_body": "{}",
            "response_headers": {
                "X-Request-Id": "req-999",
                "Content-Type": "application/json",
            },
            "response_status": 200,
            "rules": [
                {"name": "request_id", "source": "header", "path": "X-Request-Id"},
                {"name": "ctype", "source": "header", "path": "content-type"},
            ],
        },
    )
    assert resp.status_code == 200
    extracted = resp.json()["extracted"]
    assert extracted["request_id"] == "req-999"
    # Case-insensitive lookup
    assert extracted["ctype"] == "application/json"


def test_extract_status_code(client: TestClient) -> None:
    resp = client.post(
        "/api/requests/extract",
        json={
            "response_body": "{}",
            "response_headers": {},
            "response_status": 201,
            "rules": [
                {"name": "status", "source": "status", "path": ""},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["extracted"]["status"] == "201"


def test_extract_missing_path_returns_null(client: TestClient) -> None:
    body = json.dumps({"data": {"token": "abc"}})
    resp = client.post(
        "/api/requests/extract",
        json={
            "response_body": body,
            "response_headers": {},
            "response_status": 200,
            "rules": [
                {"name": "missing", "source": "body", "path": "data.nonexistent.deep"},
                {"name": "missing_header", "source": "header", "path": "X-Not-There"},
            ],
        },
    )
    assert resp.status_code == 200
    extracted = resp.json()["extracted"]
    assert extracted["missing"] is None
    assert extracted["missing_header"] is None


def test_extract_from_array_body(client: TestClient) -> None:
    body = json.dumps({"items": [{"id": 1}, {"id": 2}, {"id": 3}]})
    resp = client.post(
        "/api/requests/extract",
        json={
            "response_body": body,
            "response_headers": {},
            "response_status": 200,
            "rules": [
                {"name": "second_id", "source": "body", "path": "items[1].id"},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["extracted"]["second_id"] == "2"


def test_extract_invalid_json_body(client: TestClient) -> None:
    resp = client.post(
        "/api/requests/extract",
        json={
            "response_body": "not json at all",
            "response_headers": {},
            "response_status": 200,
            "rules": [
                {"name": "val", "source": "body", "path": "foo"},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["extracted"]["val"] is None


def test_extract_empty_rules(client: TestClient) -> None:
    resp = client.post(
        "/api/requests/extract",
        json={
            "response_body": "{}",
            "response_headers": {},
            "response_status": 200,
            "rules": [],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["extracted"] == {}
