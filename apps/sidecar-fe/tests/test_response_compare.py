"""Tests for the response comparison endpoint."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from theridion_sidecar.main import create_app

client = TestClient(create_app())


def test_json_diff_added_removed_changed() -> None:
    left = json.dumps({"a": 1, "b": 2, "c": 3})
    right = json.dumps({"a": 1, "b": 99, "d": 4})
    resp = client.post("/api/compare/responses", json={
        "left": left, "right": right, "format": "json",
    })
    assert resp.status_code == 200
    data = resp.json()
    types = {c["path"]: c["type"] for c in data["changes"]}
    assert types["b"] == "changed"
    assert types["c"] == "removed"
    assert types["d"] == "added"
    assert "1 added" in data["summary"]
    assert "1 removed" in data["summary"]
    assert "1 changed" in data["summary"]
    assert data["diff_text"]  # non-empty unified diff


def test_json_nested_diff() -> None:
    left = json.dumps({"user": {"name": "Alice", "age": 30}})
    right = json.dumps({"user": {"name": "Bob", "age": 30, "email": "bob@x.com"}})
    resp = client.post("/api/compare/responses", json={
        "left": left, "right": right, "format": "json",
    })
    assert resp.status_code == 200
    data = resp.json()
    types = {c["path"]: c["type"] for c in data["changes"]}
    assert types["user.name"] == "changed"
    assert types["user.email"] == "added"
    # age unchanged — should not appear
    assert "user.age" not in types


def test_text_line_diff() -> None:
    left = "line1\nline2\nline3"
    right = "line1\nmodified\nline3\nline4"
    resp = client.post("/api/compare/responses", json={
        "left": left, "right": right, "format": "text",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["changes"]) > 0
    assert data["diff_text"]


def test_identical_responses() -> None:
    body = json.dumps({"status": "ok", "data": [1, 2, 3]})
    resp = client.post("/api/compare/responses", json={
        "left": body, "right": body, "format": "json",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["changes"] == []
    assert data["summary"] == "Responses are identical"


def test_json_array_diff() -> None:
    left = json.dumps([1, 2, 3])
    right = json.dumps([1, 2, 3, 4])
    resp = client.post("/api/compare/responses", json={
        "left": left, "right": right, "format": "json",
    })
    assert resp.status_code == 200
    data = resp.json()
    types = {c["path"]: c["type"] for c in data["changes"]}
    assert types["[3]"] == "added"


def test_invalid_json_falls_back_to_text() -> None:
    resp = client.post("/api/compare/responses", json={
        "left": "not json", "right": "also not json", "format": "json",
    })
    assert resp.status_code == 200
    data = resp.json()
    # Should still produce a result (text diff fallback)
    assert "summary" in data
