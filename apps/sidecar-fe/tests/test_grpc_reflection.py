"""Tests for gRPC reflection and describe endpoints.

These tests mock grpcio internals so they run without a live gRPC server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---- /api/grpc/reflect -----------------------------------------------------


def test_reflect_returns_502_on_connection_error(client: TestClient) -> None:
    """A bad host should yield a 502 with a meaningful error message."""
    mock_channel = MagicMock()
    mock_stub = MagicMock()
    mock_stub.ServerReflectionInfo.side_effect = ConnectionRefusedError("mocked")

    with (
        patch("grpc.insecure_channel", return_value=mock_channel),
        patch(
            "grpc_reflection.v1alpha.reflection_pb2_grpc.ServerReflectionStub",
            return_value=mock_stub,
        ),
    ):
        resp = client.post("/api/grpc/reflect", json={"host": "badhost:9999"})
    assert resp.status_code == 502
    body = resp.json()
    assert "detail" in body
    assert "gRPC reflection error" in body["detail"]


def test_reflect_validates_empty_host(client: TestClient) -> None:
    """An empty host string should be rejected by pydantic validation."""
    resp = client.post("/api/grpc/reflect", json={"host": ""})
    assert resp.status_code == 422


def test_reflect_validates_missing_host(client: TestClient) -> None:
    """Missing host field should fail validation."""
    resp = client.post("/api/grpc/reflect", json={})
    assert resp.status_code == 422


# ---- /api/grpc/describe ---------------------------------------------------


def test_describe_returns_502_on_connection_error(client: TestClient) -> None:
    """A bad host should yield a 502."""
    mock_channel = MagicMock()
    mock_stub = MagicMock()
    mock_stub.ServerReflectionInfo.side_effect = ConnectionRefusedError("mocked")

    with (
        patch("grpc.insecure_channel", return_value=mock_channel),
        patch(
            "grpc_reflection.v1alpha.reflection_pb2_grpc.ServerReflectionStub",
            return_value=mock_stub,
        ),
    ):
        resp = client.post("/api/grpc/describe", json={
            "host": "badhost:9999",
            "service": "example.Greeter",
            "method": "SayHello",
        })
    assert resp.status_code == 502
    body = resp.json()
    assert "detail" in body


def test_describe_validates_empty_fields(client: TestClient) -> None:
    """Empty required fields should fail validation."""
    resp = client.post("/api/grpc/describe", json={
        "host": "",
        "service": "example.Greeter",
        "method": "SayHello",
    })
    assert resp.status_code == 422

    resp = client.post("/api/grpc/describe", json={
        "host": "localhost:50051",
        "service": "",
        "method": "SayHello",
    })
    assert resp.status_code == 422

    resp = client.post("/api/grpc/describe", json={
        "host": "localhost:50051",
        "service": "example.Greeter",
        "method": "",
    })
    assert resp.status_code == 422


def test_describe_validates_missing_fields(client: TestClient) -> None:
    """Missing required fields should fail validation."""
    resp = client.post("/api/grpc/describe", json={
        "host": "localhost:50051",
        "service": "example.Greeter",
    })
    assert resp.status_code == 422


# ---- /api/grpc/invoke (existing, regression) --------------------------------


def test_invoke_validates_empty_host(client: TestClient) -> None:
    """Empty host should fail validation for invoke too."""
    resp = client.post("/api/grpc/invoke", json={
        "host": "",
        "service": "svc",
        "method": "m",
    })
    assert resp.status_code == 422


# ---- Helpers for field descriptor parsing ----------------------------------


def test_build_template_produces_defaults() -> None:
    """_build_template should produce a dict with sensible zero-values."""
    from theridion_sidecar.api.grpc_api import GrpcFieldDescriptor, _build_template

    fields = [
        GrpcFieldDescriptor(name="name", type="string", label="optional"),
        GrpcFieldDescriptor(name="age", type="int32", label="optional"),
        GrpcFieldDescriptor(name="active", type="bool", label="optional"),
        GrpcFieldDescriptor(name="score", type="double", label="optional"),
        GrpcFieldDescriptor(name="tags", type="string", label="repeated"),
    ]
    template = _build_template(fields)
    assert template == {
        "name": "",
        "age": 0,
        "active": False,
        "score": 0.0,
        "tags": [""],
    }


def test_build_template_nested_message() -> None:
    """Nested message fields should produce nested dicts."""
    from theridion_sidecar.api.grpc_api import GrpcFieldDescriptor, _build_template

    inner = [
        GrpcFieldDescriptor(name="street", type="string", label="optional"),
        GrpcFieldDescriptor(name="city", type="string", label="optional"),
    ]
    fields = [
        GrpcFieldDescriptor(name="name", type="string", label="optional"),
        GrpcFieldDescriptor(
            name="address", type="message", label="optional",
            type_name="example.Address", fields=inner,
        ),
    ]
    template = _build_template(fields)
    assert template == {
        "name": "",
        "address": {"street": "", "city": ""},
    }


def test_build_template_repeated_message() -> None:
    """Repeated message fields should produce a list with one template entry."""
    from theridion_sidecar.api.grpc_api import GrpcFieldDescriptor, _build_template

    inner = [GrpcFieldDescriptor(name="value", type="int32", label="optional")]
    fields = [
        GrpcFieldDescriptor(
            name="items", type="message", label="repeated",
            type_name="example.Item", fields=inner,
        ),
    ]
    template = _build_template(fields)
    assert template == {"items": [{"value": 0}]}


def test_proto_type_map_coverage() -> None:
    """All standard proto types should be in the type map."""
    from theridion_sidecar.api.grpc_api import _PROTO_TYPE_MAP

    # Proto field types 1-18 should all be mapped
    for i in range(1, 19):
        assert i in _PROTO_TYPE_MAP, f"Type {i} missing from _PROTO_TYPE_MAP"
