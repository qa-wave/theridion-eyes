"""gRPC endpoints: proto loading, reflection, unary invocation, TLS.

Implements:
  POST /api/grpc/load-proto  — parse .proto file content, return services/methods
  POST /api/grpc/reflect     — server reflection against a live gRPC server
  POST /api/grpc/describe    — describe a single method's input/output fields
  POST /api/grpc/invoke      — execute a unary RPC call

TLS support: pass tls=true and optionally ca_cert / client_cert / client_key
(PEM strings) in reflect, describe, and invoke requests to use a secure channel.
"""

from __future__ import annotations

import base64
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/grpc", tags=["grpc"])


# ---- Models ----------------------------------------------------------------

class TlsConfig(BaseModel):
    """Optional TLS configuration for channel creation."""
    enabled: bool = False
    # PEM-encoded root CA certificate (for server verification). If omitted,
    # the default system CAs are used when enabled=True.
    ca_cert: str | None = None
    # mTLS: PEM-encoded client certificate + private key.
    client_cert: str | None = None
    client_key: str | None = None


class GrpcLoadProtoRequest(BaseModel):
    """Load services/methods from a .proto file text without a live server."""
    proto_content: str = Field(..., min_length=1)
    # Optional extra .proto files that the main proto imports.
    # Keys are logical filenames, values are .proto text.
    imports: dict[str, str] = Field(default_factory=dict)


class GrpcReflectRequest(BaseModel):
    host: str = Field(..., min_length=1)
    tls: TlsConfig = Field(default_factory=TlsConfig)
    metadata: dict[str, str] = Field(default_factory=dict)


class GrpcMethodInfo(BaseModel):
    name: str
    input_type: str = ""
    output_type: str = ""
    client_streaming: bool = False
    server_streaming: bool = False

    @property
    def is_streaming(self) -> bool:
        return self.client_streaming or self.server_streaming

    model_config = {"populate_by_name": True}


class GrpcService(BaseModel):
    name: str
    methods: list[GrpcMethodInfo] = Field(default_factory=list)


class GrpcReflectResponse(BaseModel):
    services: list[GrpcService]


class GrpcDescribeRequest(BaseModel):
    host: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)
    method: str = Field(..., min_length=1)
    tls: TlsConfig = Field(default_factory=TlsConfig)
    metadata: dict[str, str] = Field(default_factory=dict)


class GrpcFieldDescriptor(BaseModel):
    name: str
    type: str
    label: str = "optional"
    type_name: str | None = None
    fields: list[GrpcFieldDescriptor] | None = None


class GrpcDescribeResponse(BaseModel):
    input_type: str
    output_type: str
    input_fields: list[GrpcFieldDescriptor]
    template: dict[str, Any]


GrpcFieldDescriptor.model_rebuild()


class GrpcInvokeRequest(BaseModel):
    host: str = Field(..., min_length=1)
    service: str = Field(..., min_length=1)
    method: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    tls: TlsConfig = Field(default_factory=TlsConfig)


class GrpcInvokeResponse(BaseModel):
    ok: bool
    result: Any = None
    error: str | None = None
    elapsed_ms: float = 0
    status_code: str | None = None
    trailers: dict[str, str] = Field(default_factory=dict)


# ---- Helpers ---------------------------------------------------------------

# Protobuf field type number to human-readable name mapping
_PROTO_TYPE_MAP: dict[int, str] = {
    1: "double",
    2: "float",
    3: "int64",
    4: "uint64",
    5: "int32",
    6: "fixed64",
    7: "fixed32",
    8: "bool",
    9: "string",
    10: "group",
    11: "message",
    12: "bytes",
    13: "uint32",
    14: "enum",
    15: "sfixed32",
    16: "sfixed64",
    17: "sint32",
    18: "sint64",
}

_PROTO_LABEL_MAP: dict[int, str] = {
    1: "optional",
    2: "required",
    3: "repeated",
}

# Default values per proto type for template generation
_PROTO_DEFAULTS: dict[str, Any] = {
    "string": "",
    "bool": False,
    "int32": 0,
    "int64": 0,
    "uint32": 0,
    "uint64": 0,
    "sint32": 0,
    "sint64": 0,
    "fixed32": 0,
    "fixed64": 0,
    "sfixed32": 0,
    "sfixed64": 0,
    "float": 0.0,
    "double": 0.0,
    "bytes": "",
    "enum": 0,
}


def _create_channel(host: str, tls: TlsConfig) -> Any:
    """Create a grpc.Channel — secure or insecure based on tls config."""
    import grpc

    if not tls.enabled:
        return grpc.insecure_channel(host)

    # Build SSL channel credentials
    root_certificates: bytes | None = tls.ca_cert.encode() if tls.ca_cert else None
    private_key: bytes | None = tls.client_key.encode() if tls.client_key else None
    certificate_chain: bytes | None = tls.client_cert.encode() if tls.client_cert else None

    creds = grpc.ssl_channel_credentials(
        root_certificates=root_certificates,
        private_key=private_key,
        certificate_chain=certificate_chain,
    )
    return grpc.secure_channel(host, creds)


def _parse_field_descriptors(
    fd_proto: Any,
    msg_type_name: str,
    visited: set[str] | None = None,
) -> list[GrpcFieldDescriptor]:
    """Walk a FileDescriptorProto to extract fields for a given message type.

    Handles nested messages up to a reasonable depth to avoid cycles.
    """
    if visited is None:
        visited = set()
    # Prevent infinite recursion on self-referencing messages
    if msg_type_name in visited:
        return []
    visited = visited | {msg_type_name}

    # Strip leading dot for matching
    bare = msg_type_name.lstrip(".")
    # Look through all message types in the file descriptor
    target = None
    for mt in fd_proto.message_type:
        full = f"{fd_proto.package}.{mt.name}" if fd_proto.package else mt.name
        if full == bare or mt.name == bare:
            target = mt
            break
        # Check nested types
        found = _find_nested(mt, bare, fd_proto.package)
        if found is not None:
            target = found
            break

    if target is None:
        return []

    result: list[GrpcFieldDescriptor] = []
    for f in target.field:
        type_str = _PROTO_TYPE_MAP.get(f.type, f"unknown({f.type})")
        label_str = _PROTO_LABEL_MAP.get(f.label, "optional")
        nested: list[GrpcFieldDescriptor] | None = None
        type_name: str | None = f.type_name.lstrip(".") if f.type_name else None
        if f.type == 11 and f.type_name:  # message type
            nested = _parse_field_descriptors(fd_proto, f.type_name, visited)
        result.append(GrpcFieldDescriptor(
            name=f.name,
            type=type_str,
            label=label_str,
            type_name=type_name,
            fields=nested if nested else None,
        ))
    return result


def _find_nested(msg: Any, target_name: str, package: str) -> Any:
    """Recursively search nested message types."""
    for nested in msg.nested_type:
        full = f"{package}.{msg.name}.{nested.name}" if package else f"{msg.name}.{nested.name}"
        if full == target_name or nested.name == target_name:
            return nested
        found = _find_nested(nested, target_name, package)
        if found is not None:
            return found
    return None


def _build_template(fields: list[GrpcFieldDescriptor]) -> dict[str, Any]:
    """Generate a template JSON object from field descriptors."""
    template: dict[str, Any] = {}
    for f in fields:
        if f.type == "message" and f.fields:
            val = _build_template(f.fields)
            template[f.name] = [val] if f.label == "repeated" else val
        else:
            default = _PROTO_DEFAULTS.get(f.type, "")
            template[f.name] = [default] if f.label == "repeated" else default
    return template


def _extract_services_from_fd(fd_proto: Any) -> list[GrpcService]:
    """Extract GrpcService list from a FileDescriptorProto."""
    services = []
    pkg = fd_proto.package
    for svc_desc in fd_proto.service:
        full_svc_name = f"{pkg}.{svc_desc.name}" if pkg else svc_desc.name
        methods = []
        for m in svc_desc.method:
            methods.append(GrpcMethodInfo(
                name=m.name,
                input_type=m.input_type.lstrip("."),
                output_type=m.output_type.lstrip("."),
                client_streaming=m.client_streaming,
                server_streaming=m.server_streaming,
            ))
        services.append(GrpcService(name=full_svc_name, methods=methods))
    return services


# ---- Endpoints -------------------------------------------------------------

@router.post("/load-proto", response_model=GrpcReflectResponse)
async def load_proto(req: GrpcLoadProtoRequest) -> GrpcReflectResponse:
    """Parse a .proto file and return the list of services and their methods.

    Does not require a live gRPC server — useful for offline development
    or when the target server doesn't support reflection.
    """
    try:
        from google.protobuf import descriptor_pb2
        from grpc_tools import protoc  # type: ignore[import-untyped]
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="grpcio-tools not installed",
        ) from exc

    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write main .proto file
        main_proto = Path(tmpdir) / "main.proto"
        main_proto.write_text(req.proto_content)

        # Write any import dependencies
        for filename, content in req.imports.items():
            # Sanitize filename — only allow relative paths within tmpdir
            safe_name = Path(filename).name
            (Path(tmpdir) / safe_name).write_text(content)

        # Compile to FileDescriptorSet
        descriptor_file = Path(tmpdir) / "descriptor.pb"
        result = protoc.main([
            "grpc_tools.protoc",
            f"--proto_path={tmpdir}",
            f"--descriptor_set_out={descriptor_file}",
            "--include_imports",
            str(main_proto),
        ])

        if result != 0:
            raise HTTPException(
                status_code=422,
                detail="Failed to parse .proto file — check syntax",
            )

        # Load FileDescriptorSet
        fds = descriptor_pb2.FileDescriptorSet()
        fds.ParseFromString(descriptor_file.read_bytes())

        all_services: list[GrpcService] = []
        for fd in fds.file:
            all_services.extend(_extract_services_from_fd(fd))

        return GrpcReflectResponse(services=all_services)


@router.post("/reflect", response_model=GrpcReflectResponse)
async def reflect(req: GrpcReflectRequest) -> GrpcReflectResponse:
    try:
        import grpc
        from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="grpcio / grpcio-reflection not installed",
        ) from exc

    try:
        channel = _create_channel(req.host, req.tls)
        stub = reflection_pb2_grpc.ServerReflectionStub(channel)

        # Build metadata list
        call_metadata = list(req.metadata.items()) if req.metadata else []

        # List services
        request = reflection_pb2.ServerReflectionRequest(
            list_services=""
        )
        responses = stub.ServerReflectionInfo(iter([request]), metadata=call_metadata)
        services: list[GrpcService] = []
        for resp in responses:
            for svc in resp.list_services_response.service:
                if svc.name.startswith("grpc.reflection"):
                    continue
                # Get methods for each service
                method_req = reflection_pb2.ServerReflectionRequest(
                    file_containing_symbol=svc.name
                )
                method_responses = stub.ServerReflectionInfo(
                    iter([method_req]), metadata=call_metadata
                )
                methods: list[GrpcMethodInfo] = []
                for mr in method_responses:
                    if mr.HasField("file_descriptor_response"):
                        from google.protobuf import descriptor_pb2

                        for fd_bytes in mr.file_descriptor_response.file_descriptor_proto:
                            fd = descriptor_pb2.FileDescriptorProto()
                            fd.ParseFromString(fd_bytes)
                            for service_desc in fd.service:
                                if service_desc.name == svc.name.split(".")[-1]:
                                    methods = [
                                        GrpcMethodInfo(
                                            name=m.name,
                                            input_type=m.input_type.lstrip("."),
                                            output_type=m.output_type.lstrip("."),
                                            client_streaming=m.client_streaming,
                                            server_streaming=m.server_streaming,
                                        )
                                        for m in service_desc.method
                                    ]
                services.append(GrpcService(name=svc.name, methods=methods))
        channel.close()
        return GrpcReflectResponse(services=services)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"gRPC reflection error: {exc}") from exc


@router.post("/describe", response_model=GrpcDescribeResponse)
async def describe(req: GrpcDescribeRequest) -> GrpcDescribeResponse:
    """Describe a gRPC method's input/output message types.

    Returns field descriptors and a template JSON object suitable for
    populating the request payload editor.
    """
    try:
        import grpc
        from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="grpcio / grpcio-reflection not installed",
        ) from exc

    try:
        channel = _create_channel(req.host, req.tls)
        stub = reflection_pb2_grpc.ServerReflectionStub(channel)

        call_metadata = list(req.metadata.items()) if req.metadata else []

        # Resolve the file descriptor for the service
        file_req = reflection_pb2.ServerReflectionRequest(
            file_containing_symbol=req.service
        )
        responses = stub.ServerReflectionInfo(iter([file_req]), metadata=call_metadata)

        input_type = ""
        output_type = ""
        fd_proto = None

        for resp in responses:
            if resp.HasField("file_descriptor_response"):
                from google.protobuf import descriptor_pb2

                for fd_bytes in resp.file_descriptor_response.file_descriptor_proto:
                    fd = descriptor_pb2.FileDescriptorProto()
                    fd.ParseFromString(fd_bytes)
                    for service_desc in fd.service:
                        short_name = req.service.split(".")[-1]
                        if service_desc.name == short_name:
                            for m in service_desc.method:
                                if m.name == req.method:
                                    input_type = m.input_type.lstrip(".")
                                    output_type = m.output_type.lstrip(".")
                                    fd_proto = fd
                                    break

        channel.close()

        if fd_proto is None or not input_type:
            raise HTTPException(
                status_code=404,
                detail=f"Method {req.service}/{req.method} not found via reflection",
            )

        input_fields = _parse_field_descriptors(fd_proto, input_type)
        template = _build_template(input_fields)

        return GrpcDescribeResponse(
            input_type=input_type,
            output_type=output_type,
            input_fields=input_fields,
            template=template,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"gRPC describe error: {exc}",
        ) from exc


@router.post("/invoke", response_model=GrpcInvokeResponse)
async def invoke(req: GrpcInvokeRequest) -> GrpcInvokeResponse:
    try:
        import grpc
        from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
        from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc
    except ImportError as exc:
        raise HTTPException(
            status_code=501,
            detail="grpcio / grpcio-reflection not installed",
        ) from exc

    started = time.perf_counter()
    try:
        channel = _create_channel(req.host, req.tls)
        stub = reflection_pb2_grpc.ServerReflectionStub(channel)

        # Build metadata list
        call_metadata = list(req.metadata.items()) if req.metadata else None

        # Resolve the file descriptor for the service
        file_req = reflection_pb2.ServerReflectionRequest(
            file_containing_symbol=req.service
        )
        responses = stub.ServerReflectionInfo(iter([file_req]))

        pool = descriptor_pool.DescriptorPool()
        for resp in responses:
            if resp.HasField("file_descriptor_response"):
                for fd_bytes in resp.file_descriptor_response.file_descriptor_proto:
                    fd_proto = descriptor_pb2.FileDescriptorProto()
                    fd_proto.ParseFromString(fd_bytes)
                    try:
                        pool.Add(fd_proto)
                    except Exception:
                        pass

        # Find the method descriptor
        svc_desc = pool.FindServiceByName(req.service)
        method_desc = svc_desc.FindMethodByName(req.method)

        # Build request message.
        # protobuf >= 4.x: GetMessageClass replaces the deprecated GetPrototype.
        # Fall back to the old API for compatibility with older environments.
        def _get_msg_class(descriptor: Any) -> Any:
            if hasattr(message_factory, "GetMessageClass"):
                return message_factory.GetMessageClass(descriptor)
            # Legacy path (protobuf < 4)
            factory = message_factory.MessageFactory(pool=pool)
            return factory.GetPrototype(descriptor)  # type: ignore[attr-defined]

        request_class = _get_msg_class(method_desc.input_type)
        response_class = _get_msg_class(method_desc.output_type)

        request_msg = request_class()
        if req.payload:
            json_format.ParseDict(req.payload, request_msg)

        # Make the unary call; capture trailing metadata
        full_method = f"/{req.service}/{req.method}"
        call_future = channel.unary_unary(
            full_method,
            request_serializer=lambda x: x.SerializeToString(),
            response_deserializer=response_class.FromString,
        ).future(request_msg, timeout=req.timeout_seconds, metadata=call_metadata)

        response_msg = call_future.result()

        # Extract trailing metadata
        trailers: dict[str, str] = {}
        for k, v in (call_future.trailing_metadata() or []):
            trailers[k] = v

        elapsed = (time.perf_counter() - started) * 1000
        result = json_format.MessageToDict(response_msg)
        channel.close()

        return GrpcInvokeResponse(
            ok=True,
            result=result,
            elapsed_ms=round(elapsed, 2),
            status_code="OK",
            trailers=trailers,
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        # Extract gRPC status code if available
        status_code: str | None = None
        try:
            import grpc
            if hasattr(exc, "code"):
                status_code = str(exc.code())
        except Exception:
            pass
        return GrpcInvokeResponse(
            ok=False,
            error=str(exc),
            elapsed_ms=round(elapsed, 2),
            status_code=status_code,
        )
