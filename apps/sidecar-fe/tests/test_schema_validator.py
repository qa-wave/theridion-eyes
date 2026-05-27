"""Tests for JSON Schema validation, generation, and diff endpoints."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


# ---- Validate --------------------------------------------------------------


def test_valid_body(client: TestClient) -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"],
    }
    resp = client.post(
        "/api/schema/validate",
        json={"body": json.dumps({"name": "Alice", "age": 30}), "schema": schema},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == []


def test_invalid_body_missing_required(client: TestClient) -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }
    resp = client.post(
        "/api/schema/validate",
        json={"body": json.dumps({}), "schema": schema},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert len(data["errors"]) >= 1
    assert any("name" in e["message"] for e in data["errors"])
    # schema_path should be present
    assert all("schema_path" in e for e in data["errors"])


def test_invalid_body_wrong_type(client: TestClient) -> None:
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
    resp = client.post(
        "/api/schema/validate",
        json={"body": json.dumps({"count": "not-a-number"}), "schema": schema},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any("count" in e["path"] for e in data["errors"])


def test_invalid_body_extra_via_additional_properties(client: TestClient) -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "additionalProperties": False,
    }
    resp = client.post(
        "/api/schema/validate",
        json={"body": json.dumps({"name": "Bob", "extra": 1}), "schema": schema},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any("extra" in e["message"] for e in data["errors"])


def test_validate_with_schema_as_string(client: TestClient) -> None:
    schema = json.dumps({"type": "integer"})
    resp = client.post(
        "/api/schema/validate",
        json={"body": "42", "schema": schema},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_validate_draft_2020_12(client: TestClient) -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"x": {"type": "number"}},
        "required": ["x"],
    }
    resp = client.post(
        "/api/schema/validate",
        json={"body": json.dumps({"x": 3.14}), "schema": schema},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_validate_invalid_schema(client: TestClient) -> None:
    resp = client.post(
        "/api/schema/validate",
        json={"body": "{}", "schema": {"type": "not-a-type"}},
    )
    assert resp.status_code == 400
    assert "Invalid JSON Schema" in resp.json()["detail"]


def test_validate_invalid_body_json(client: TestClient) -> None:
    resp = client.post(
        "/api/schema/validate",
        json={"body": "{broken", "schema": {"type": "object"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert len(data["errors"]) >= 1


# ---- Generate --------------------------------------------------------------


def test_generate_schema_basic(client: TestClient) -> None:
    body = {"name": "Alice", "age": 30, "active": True, "tags": ["a", "b"]}
    resp = client.post("/api/schema/generate", json={"body": json.dumps(body)})
    assert resp.status_code == 200
    data = resp.json()
    schema = data["schema"]
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert schema["properties"]["age"]["type"] == "integer"
    assert schema["properties"]["active"]["type"] == "boolean"
    assert schema["properties"]["tags"]["type"] == "array"
    assert "name" in schema["required"]


def test_generate_schema_detects_formats(client: TestClient) -> None:
    body = {
        "email": "alice@example.com",
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "date": "2025-01-15",
        "url": "https://example.com",
    }
    resp = client.post("/api/schema/generate", json={"body": json.dumps(body)})
    assert resp.status_code == 200
    props = resp.json()["schema"]["properties"]
    assert props["email"].get("format") == "email"
    assert props["id"].get("format") == "uuid"
    assert props["date"].get("format") == "date"
    assert props["url"].get("format") == "uri"


def test_generate_then_validate(client: TestClient) -> None:
    """Generated schema should validate the source body."""
    body_str = json.dumps({"x": 1, "y": "hello"})
    gen_resp = client.post("/api/schema/generate", json={"body": body_str})
    assert gen_resp.status_code == 200
    schema = gen_resp.json()["schema"]

    val_resp = client.post(
        "/api/schema/validate", json={"body": body_str, "schema": schema}
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["valid"] is True


# ---- Diff ------------------------------------------------------------------


def test_diff_added_field(client: TestClient) -> None:
    old = {"type": "object", "properties": {"a": {"type": "string"}}}
    new = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
    }
    resp = client.post("/api/schema/diff", json={"old": old, "new": new})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["added"]) == 1
    assert data["added"][0]["path"] == "$.b"
    assert data["removed"] == []


def test_diff_removed_field(client: TestClient) -> None:
    old = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
    }
    new = {"type": "object", "properties": {"a": {"type": "string"}}}
    resp = client.post("/api/schema/diff", json={"old": old, "new": new})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["removed"]) == 1
    assert data["removed"][0]["path"] == "$.b"


def test_diff_changed_field(client: TestClient) -> None:
    old = {"type": "object", "properties": {"a": {"type": "string"}}}
    new = {"type": "object", "properties": {"a": {"type": "integer"}}}
    resp = client.post("/api/schema/diff", json={"old": old, "new": new})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["changed"]) == 1
    assert "type" in data["changed"][0]["detail"]


def test_diff_no_changes(client: TestClient) -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    resp = client.post("/api/schema/diff", json={"old": schema, "new": schema})
    assert resp.status_code == 200
    data = resp.json()
    assert data["added"] == []
    assert data["removed"] == []
    assert data["changed"] == []


def test_diff_with_string_schemas(client: TestClient) -> None:
    old = json.dumps({"type": "object", "properties": {"x": {"type": "string"}}})
    new = json.dumps(
        {"type": "object", "properties": {"x": {"type": "string"}, "y": {"type": "number"}}}
    )
    resp = client.post("/api/schema/diff", json={"old": old, "new": new})
    assert resp.status_code == 200
    assert len(resp.json()["added"]) == 1
