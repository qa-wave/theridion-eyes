"""Tests for Spin schema compliance validation — JSON Schema, OpenAPI, AsyncAPI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theridion_sidecar.spin.schema import (
    _inline_refs,
    _resolve_openapi_schema_ref,
    validate_asyncapi_message,
    validate_json_schema,
    validate_openapi_response,
    validate_payload,
)


# ── JSON Schema ───────────────────────────────────────────────────────────────

def test_json_schema_valid():
    schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["id", "name"],
    }
    ok, errors = validate_json_schema({"id": 1, "name": "Alice"}, schema)
    assert ok is True
    assert errors == []


def test_json_schema_missing_required():
    schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
        "required": ["id"],
    }
    ok, errors = validate_json_schema({"name": "Alice"}, schema)
    assert ok is False
    assert errors


def test_json_schema_wrong_type():
    schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
    ok, errors = validate_json_schema({"count": "not-a-number"}, schema)
    assert ok is False


def test_json_schema_nested_valid():
    schema = {
        "type": "object",
        "properties": {
            "order": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
            }
        },
        "required": ["order"],
    }
    ok, errors = validate_json_schema({"order": {"status": "pending"}}, schema)
    assert ok is True


def test_json_schema_array_type():
    schema = {"type": "array", "items": {"type": "string"}}
    ok, _ = validate_json_schema(["a", "b", "c"], schema)
    assert ok is True
    ok2, errors2 = validate_json_schema(["a", 1], schema)
    assert ok2 is False


# ── $ref resolution ───────────────────────────────────────────────────────────

def test_resolve_ref_simple():
    spec: dict = {
        "components": {
            "schemas": {
                "User": {"type": "object", "properties": {"id": {"type": "integer"}}}
            }
        }
    }
    resolved = _resolve_openapi_schema_ref(spec, "#/components/schemas/User")
    assert resolved["type"] == "object"


def test_resolve_ref_invalid():
    spec: dict = {}
    resolved = _resolve_openapi_schema_ref(spec, "#/components/schemas/Missing")
    assert resolved == {}


def test_inline_refs_basic():
    spec: dict = {
        "components": {
            "schemas": {
                "Name": {"type": "string"}
            }
        }
    }
    schema = {"properties": {"name": {"$ref": "#/components/schemas/Name"}}}
    inlined = _inline_refs(schema, spec)
    assert inlined["properties"]["name"]["type"] == "string"


# ── OpenAPI validation ────────────────────────────────────────────────────────

@pytest.fixture()
def openapi_spec(tmp_path: Path) -> str:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/orders": {
                "post": {
                    "operationId": "createOrder",
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "integer"},
                                            "status": {"type": "string"},
                                        },
                                        "required": ["id", "status"],
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
    }
    spec_file = tmp_path / "openapi.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    return str(spec_file)


def test_openapi_validate_by_operation_id_pass(openapi_spec: str):
    ok, errors = validate_openapi_response(
        {"id": 1, "status": "pending"},
        openapi_spec,
        operation_id="createOrder",
        status_code=201,
    )
    assert ok is True
    assert errors == []


def test_openapi_validate_by_operation_id_fail(openapi_spec: str):
    ok, errors = validate_openapi_response(
        {"name": "no id"},  # missing required 'id' and 'status'
        openapi_spec,
        operation_id="createOrder",
        status_code=201,
    )
    assert ok is False
    assert errors


def test_openapi_missing_spec_file():
    ok, errors = validate_openapi_response(
        {},
        "/no/such/file.json",
        operation_id="createOrder",
    )
    assert ok is False
    assert errors


def test_openapi_unknown_operation_id(openapi_spec: str):
    ok, errors = validate_openapi_response(
        {},
        openapi_spec,
        operation_id="nonexistentOp",
    )
    assert ok is False
    assert errors


# ── AsyncAPI validation ───────────────────────────────────────────────────────

@pytest.fixture()
def asyncapi_spec(tmp_path: Path) -> str:
    spec = {
        "asyncapi": "2.6.0",
        "info": {"title": "Test Events", "version": "1.0.0"},
        "channels": {
            "order.created": {
                "publish": {
                    "message": {
                        "payload": {
                            "type": "object",
                            "properties": {
                                "order_id": {"type": "string"},
                                "total": {"type": "number"},
                            },
                            "required": ["order_id"],
                        }
                    }
                }
            }
        },
    }
    spec_file = tmp_path / "asyncapi.yaml"
    import yaml
    spec_file.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return str(spec_file)


def test_asyncapi_validate_pass(asyncapi_spec: str):
    ok, errors = validate_asyncapi_message(
        {"order_id": "ORD-001", "total": 99.99},
        asyncapi_spec,
        channel_name="order.created",
        operation="publish",
    )
    assert ok is True


def test_asyncapi_validate_fail_missing_field(asyncapi_spec: str):
    ok, errors = validate_asyncapi_message(
        {"total": 99.99},  # missing required 'order_id'
        asyncapi_spec,
        channel_name="order.created",
    )
    assert ok is False
    assert errors


def test_asyncapi_missing_channel(asyncapi_spec: str):
    ok, errors = validate_asyncapi_message(
        {},
        asyncapi_spec,
        channel_name="nonexistent.channel",
    )
    assert ok is False
    assert errors


# ── Unified validate_payload dispatcher ───────────────────────────────────────

def test_validate_payload_jsonschema():
    ok, errors = validate_payload(
        {"id": 1},
        "jsonschema",
        raw_schema={"type": "object", "properties": {"id": {"type": "integer"}}},
    )
    assert ok is True


def test_validate_payload_jsonschema_no_schema():
    ok, errors = validate_payload({"id": 1}, "jsonschema", raw_schema=None)
    assert ok is False
    assert "raw_schema" in errors[0]


def test_validate_payload_openapi(openapi_spec: str):
    # The fixture spec has createOrder with a 201 response
    ok, errors = validate_openapi_response(
        {"id": 1, "status": "ok"},
        openapi_spec,
        operation_id="createOrder",
        status_code=201,
    )
    assert ok is True, f"Errors: {errors}"


def test_validate_payload_unknown_ref():
    ok, errors = validate_payload({}, "unknown://foo")
    assert ok is False
    assert "Unknown" in errors[0]
