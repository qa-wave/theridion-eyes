"""gRPC endpoint tests: load-proto, reflect, describe, invoke.

Covers:
  - /api/grpc/load-proto  — parse .proto content without a live server
  - /api/grpc/reflect     — server reflection against live echo server
  - /api/grpc/describe    — method field describe against live echo server
  - /api/grpc/invoke      — unary call against live echo server
  - TLS config model      — channel helper validates TLS model
  - Error handling        — 422 validation, 502 connection errors

The `grpc_echo_port` fixture starts a real gRPC server (with reflection
enabled) that all live-server tests use.
"""

from __future__ import annotations

import concurrent.futures
import socket
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"
ECHO_PROTO = FIXTURES / "echo.proto"


# ---------------------------------------------------------------------------
# Fixture: live gRPC echo server
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def grpc_echo_port():
    """Start an in-process gRPC echo server and return its port.

    The server has reflection enabled. Torn down after all tests in module.
    """
    # Ensure generated stubs exist
    sys.path.insert(0, str(FIXTURES))
    from grpc_echo_server import create_server  # type: ignore[import-untyped]

    port = _free_port()
    server = create_server(port=port)
    # Give it a moment to start
    time.sleep(0.2)
    yield port
    server.stop(grace=0)


# ---------------------------------------------------------------------------
# /api/grpc/load-proto
# ---------------------------------------------------------------------------


class TestLoadProto:
    def test_load_simple_proto(self, client: TestClient) -> None:
        """Load echo.proto and get back service list."""
        proto_content = ECHO_PROTO.read_text()
        resp = client.post(
            "/api/grpc/load-proto",
            json={"proto_content": proto_content},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "services" in data
        services = data["services"]
        assert len(services) >= 1
        names = [s["name"] for s in services]
        assert any("EchoService" in n for n in names)

    def test_load_proto_returns_methods(self, client: TestClient) -> None:
        """Returned service should include SayHello and Ping methods."""
        proto_content = ECHO_PROTO.read_text()
        resp = client.post(
            "/api/grpc/load-proto",
            json={"proto_content": proto_content},
        )
        assert resp.status_code == 200
        services = resp.json()["services"]
        echo_svc = next(s for s in services if "EchoService" in s["name"])
        method_names = [m["name"] for m in echo_svc["methods"]]
        assert "SayHello" in method_names
        assert "Ping" in method_names

    def test_load_proto_method_types(self, client: TestClient) -> None:
        """SayHello should report correct input/output types."""
        proto_content = ECHO_PROTO.read_text()
        resp = client.post(
            "/api/grpc/load-proto",
            json={"proto_content": proto_content},
        )
        assert resp.status_code == 200
        services = resp.json()["services"]
        echo_svc = next(s for s in services if "EchoService" in s["name"])
        say_hello = next(m for m in echo_svc["methods"] if m["name"] == "SayHello")
        assert "HelloRequest" in say_hello["input_type"]
        assert "HelloReply" in say_hello["output_type"]

    def test_load_proto_streaming_flag(self, client: TestClient) -> None:
        """ServerStream method should have server_streaming=True."""
        proto_content = ECHO_PROTO.read_text()
        resp = client.post(
            "/api/grpc/load-proto",
            json={"proto_content": proto_content},
        )
        assert resp.status_code == 200
        services = resp.json()["services"]
        echo_svc = next(s for s in services if "EchoService" in s["name"])
        stream_method = next(
            (m for m in echo_svc["methods"] if m["name"] == "ServerStream"), None
        )
        assert stream_method is not None
        assert stream_method["server_streaming"] is True
        assert stream_method["client_streaming"] is False

    def test_load_proto_invalid_syntax(self, client: TestClient) -> None:
        """Malformed .proto should return 422."""
        resp = client.post(
            "/api/grpc/load-proto",
            json={"proto_content": "this is not valid proto syntax !@#$"},
        )
        assert resp.status_code == 422

    def test_load_proto_empty_content_rejected(self, client: TestClient) -> None:
        """Empty proto_content should fail pydantic validation."""
        resp = client.post(
            "/api/grpc/load-proto",
            json={"proto_content": ""},
        )
        assert resp.status_code == 422

    def test_load_proto_missing_content_rejected(self, client: TestClient) -> None:
        """Missing proto_content field should fail."""
        resp = client.post("/api/grpc/load-proto", json={})
        assert resp.status_code == 422

    def test_load_proto_with_import(self, client: TestClient) -> None:
        """Proto with an import dependency resolved via the imports dict."""
        dep_proto = 'syntax = "proto3";\npackage dep;\nmessage DepMsg { string val = 1; }\n'
        main_proto = (
            'syntax = "proto3";\npackage main;\nimport "dep.proto";\n'
            "service MyService { rpc Call (dep.DepMsg) returns (dep.DepMsg); }\n"
        )
        resp = client.post(
            "/api/grpc/load-proto",
            json={
                "proto_content": main_proto,
                "imports": {"dep.proto": dep_proto},
            },
        )
        assert resp.status_code == 200
        services = resp.json()["services"]
        assert any("MyService" in s["name"] for s in services)


# ---------------------------------------------------------------------------
# /api/grpc/reflect
# ---------------------------------------------------------------------------


class TestReflect:
    def test_reflect_against_echo_server(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Live reflection against echo server returns EchoService."""
        resp = client.post(
            "/api/grpc/reflect",
            json={"host": f"localhost:{grpc_echo_port}"},
        )
        assert resp.status_code == 200, resp.text
        services = resp.json()["services"]
        assert len(services) >= 1
        names = [s["name"] for s in services]
        assert any("EchoService" in n for n in names)

    def test_reflect_returns_methods_for_echo(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Reflected EchoService should include SayHello and Ping."""
        resp = client.post(
            "/api/grpc/reflect",
            json={"host": f"localhost:{grpc_echo_port}"},
        )
        assert resp.status_code == 200
        services = resp.json()["services"]
        echo = next(s for s in services if "EchoService" in s["name"])
        method_names = [m["name"] for m in echo["methods"]]
        assert "SayHello" in method_names
        assert "Ping" in method_names

    def test_reflect_bad_host_returns_502(self, client: TestClient) -> None:
        """Unreachable host returns 502."""
        resp = client.post(
            "/api/grpc/reflect",
            json={"host": "localhost:19999"},
        )
        assert resp.status_code == 502
        assert "gRPC reflection error" in resp.json()["detail"]

    def test_reflect_validates_empty_host(self, client: TestClient) -> None:
        resp = client.post("/api/grpc/reflect", json={"host": ""})
        assert resp.status_code == 422

    def test_reflect_validates_missing_host(self, client: TestClient) -> None:
        resp = client.post("/api/grpc/reflect", json={})
        assert resp.status_code == 422

    def test_reflect_with_tls_disabled(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Explicitly tls.enabled=False should still work (insecure channel)."""
        resp = client.post(
            "/api/grpc/reflect",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "tls": {"enabled": False},
            },
        )
        assert resp.status_code == 200

    def test_reflect_with_metadata(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Custom metadata should not break reflection."""
        resp = client.post(
            "/api/grpc/reflect",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "metadata": {"x-custom-header": "test-value"},
            },
        )
        # Echo server ignores metadata — should still succeed
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /api/grpc/describe
# ---------------------------------------------------------------------------


class TestDescribe:
    def test_describe_say_hello(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Describe SayHello method returns input/output types and template."""
        resp = client.post(
            "/api/grpc/describe",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "SayHello",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "input_type" in data
        assert "output_type" in data
        assert "input_fields" in data
        assert "template" in data
        assert "HelloRequest" in data["input_type"]
        assert "HelloReply" in data["output_type"]

    def test_describe_template_has_name_field(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Template for SayHello should include 'name' (string) field."""
        resp = client.post(
            "/api/grpc/describe",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "SayHello",
            },
        )
        assert resp.status_code == 200
        template = resp.json()["template"]
        assert "name" in template
        assert template["name"] == ""

    def test_describe_bad_host_returns_502(self, client: TestClient) -> None:
        resp = client.post(
            "/api/grpc/describe",
            json={
                "host": "localhost:19999",
                "service": "echo.EchoService",
                "method": "SayHello",
            },
        )
        assert resp.status_code == 502

    def test_describe_unknown_method_returns_404(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        resp = client.post(
            "/api/grpc/describe",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "NonExistentMethod",
            },
        )
        assert resp.status_code == 404

    def test_describe_validates_empty_service(self, client: TestClient) -> None:
        resp = client.post(
            "/api/grpc/describe",
            json={
                "host": "localhost:50051",
                "service": "",
                "method": "SayHello",
            },
        )
        assert resp.status_code == 422

    def test_describe_validates_empty_method(self, client: TestClient) -> None:
        resp = client.post(
            "/api/grpc/describe",
            json={
                "host": "localhost:50051",
                "service": "echo.EchoService",
                "method": "",
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# /api/grpc/invoke
# ---------------------------------------------------------------------------


class TestInvoke:
    def test_unary_say_hello(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """SayHello unary call returns greeting message."""
        resp = client.post(
            "/api/grpc/invoke",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "SayHello",
                "payload": {"name": "World"},
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["result"] is not None
        result = data["result"]
        assert "message" in result
        assert "World" in result["message"]

    def test_unary_ping(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Ping echoes back the payload."""
        resp = client.post(
            "/api/grpc/invoke",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "Ping",
                "payload": {"payload": "hello-ping"},
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["result"]["payload"] == "hello-ping"

    def test_unary_elapsed_ms_positive(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """elapsed_ms should be a positive float."""
        resp = client.post(
            "/api/grpc/invoke",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "SayHello",
                "payload": {"name": "Test"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["elapsed_ms"] > 0

    def test_unary_status_code_ok(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Successful invocation should report status_code='OK'."""
        resp = client.post(
            "/api/grpc/invoke",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "Ping",
                "payload": {"payload": "x"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status_code"] == "OK"

    def test_invoke_bad_host_returns_error_json(self, client: TestClient) -> None:
        """Bad host returns ok=False in response body (not HTTP 5xx)."""
        resp = client.post(
            "/api/grpc/invoke",
            json={
                "host": "localhost:19999",
                "service": "echo.EchoService",
                "method": "SayHello",
                "payload": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error"] is not None

    def test_invoke_with_metadata(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Metadata dict should not break unary call."""
        resp = client.post(
            "/api/grpc/invoke",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "SayHello",
                "payload": {"name": "Meta"},
                "metadata": {"x-request-id": "abc123"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invoke_validates_empty_host(self, client: TestClient) -> None:
        resp = client.post(
            "/api/grpc/invoke",
            json={"host": "", "service": "svc", "method": "m"},
        )
        assert resp.status_code == 422

    def test_invoke_empty_payload_ok(
        self, client: TestClient, grpc_echo_port: int
    ) -> None:
        """Empty payload dict should be accepted (all fields default)."""
        resp = client.post(
            "/api/grpc/invoke",
            json={
                "host": f"localhost:{grpc_echo_port}",
                "service": "echo.EchoService",
                "method": "SayHello",
                "payload": {},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# TLS config model
# ---------------------------------------------------------------------------


class TestTlsConfig:
    def test_tls_config_defaults(self) -> None:
        """Default TlsConfig should have enabled=False."""
        from theridion_sidecar.api.grpc_api import TlsConfig

        cfg = TlsConfig()
        assert cfg.enabled is False
        assert cfg.ca_cert is None
        assert cfg.client_cert is None
        assert cfg.client_key is None

    def test_create_channel_insecure_when_disabled(self) -> None:
        """_create_channel returns insecure channel when tls.enabled=False."""
        import grpc

        from theridion_sidecar.api.grpc_api import TlsConfig, _create_channel

        channel = _create_channel("localhost:50099", TlsConfig(enabled=False))
        assert channel is not None
        channel.close()

    def test_create_channel_secure_with_tls_enabled(self) -> None:
        """_create_channel returns a secure channel when tls.enabled=True.

        We can't verify the connection (no cert), but object creation should
        not raise.
        """
        from theridion_sidecar.api.grpc_api import TlsConfig, _create_channel

        # grpc.ssl_channel_credentials with no root certs uses system CAs
        channel = _create_channel("localhost:50099", TlsConfig(enabled=True))
        assert channel is not None
        channel.close()

    def test_reflect_accepts_tls_config(self, client: TestClient) -> None:
        """POST /api/grpc/reflect accepts nested tls object without 422."""
        resp = client.post(
            "/api/grpc/reflect",
            json={
                "host": "localhost:19999",
                "tls": {"enabled": True, "ca_cert": None},
            },
        )
        # Will be 502 (no server) but NOT 422 (model valid)
        assert resp.status_code == 502

    def test_invoke_accepts_tls_config(self, client: TestClient) -> None:
        """POST /api/grpc/invoke accepts nested tls object without 422."""
        resp = client.post(
            "/api/grpc/invoke",
            json={
                "host": "localhost:19999",
                "service": "echo.EchoService",
                "method": "SayHello",
                "tls": {"enabled": True},
            },
        )
        # ok=False but HTTP 200 (invoke errors are returned in body)
        assert resp.status_code == 200
        assert resp.json()["ok"] is False


# ---------------------------------------------------------------------------
# Helper function tests (regression)
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_build_template_produces_defaults(self) -> None:
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

    def test_build_template_nested_message(self) -> None:
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

    def test_proto_type_map_coverage(self) -> None:
        from theridion_sidecar.api.grpc_api import _PROTO_TYPE_MAP

        for i in range(1, 19):
            assert i in _PROTO_TYPE_MAP, f"Type {i} missing from _PROTO_TYPE_MAP"

    def test_extract_services_from_fd(self) -> None:
        """_extract_services_from_fd returns correct structure."""
        from google.protobuf import descriptor_pb2

        from theridion_sidecar.api.grpc_api import _extract_services_from_fd

        # Build a minimal FileDescriptorProto in memory
        fd = descriptor_pb2.FileDescriptorProto()
        fd.name = "test.proto"
        fd.syntax = "proto3"
        fd.package = "mypack"

        svc = fd.service.add()
        svc.name = "MyService"
        m = svc.method.add()
        m.name = "DoThing"
        m.input_type = ".mypack.DoThingRequest"
        m.output_type = ".mypack.DoThingResponse"
        m.client_streaming = False
        m.server_streaming = True

        services = _extract_services_from_fd(fd)
        assert len(services) == 1
        assert services[0].name == "mypack.MyService"
        assert len(services[0].methods) == 1
        method = services[0].methods[0]
        assert method.name == "DoThing"
        assert method.server_streaming is True
        assert method.client_streaming is False
        assert "DoThingRequest" in method.input_type
