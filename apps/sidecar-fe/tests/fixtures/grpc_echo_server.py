"""Minimal gRPC echo server for testing.

Implements EchoService from echo.proto using a ThreadPoolExecutor.
Supports gRPC reflection so tests can call /api/grpc/reflect against it.

Usage (standalone):
    python grpc_echo_server.py --port 50099

Usage from pytest (via test_grpc.py's grpc_echo_port fixture):
    The fixture calls create_server(port) and stops it after module.
"""

from __future__ import annotations

import concurrent.futures
import importlib
import importlib.util
import sys
import types
from pathlib import Path

HERE = Path(__file__).parent
GENERATED = HERE / "_generated"

# Package name under which the stubs are registered in sys.modules.
# We use a flat namespace to avoid any relative-import complexity.
_PB2_MOD = "theridion_grpc_echo_pb2"
_GRPC_MOD = "theridion_grpc_echo_pb2_grpc"


def _ensure_generated() -> None:
    """Compile echo.proto to *_pb2 stubs in GENERATED/ if not present."""
    if (GENERATED / "echo_pb2.py").exists():
        return

    GENERATED.mkdir(exist_ok=True)
    (GENERATED / "__init__.py").touch()

    from grpc_tools import protoc  # type: ignore[import-untyped]

    ret = protoc.main([
        "grpc_tools.protoc",
        f"--proto_path={HERE}",
        f"--python_out={GENERATED}",
        f"--grpc_python_out={GENERATED}",
        str(HERE / "echo.proto"),
    ])
    if ret != 0:
        raise RuntimeError("protoc failed to compile echo.proto")

    # The grpc_tools plugin emits bare `import echo_pb2` which only resolves
    # if that name is in sys.modules. Rewrite to the stable module name we
    # register in sys.modules before executing this file.
    # grpc_tools <= 1.59 used `from . import echo_pb2`
    # grpc_tools >= 1.60 uses  `import echo_pb2 as echo__pb2`
    grpc_file = GENERATED / "echo_pb2_grpc.py"
    content = grpc_file.read_text()
    # Handle both import styles
    content = content.replace(
        "from . import echo_pb2 as echo__pb2",
        f"import {_PB2_MOD} as echo__pb2",
    )
    content = content.replace(
        "import echo_pb2 as echo__pb2",
        f"import {_PB2_MOD} as echo__pb2",
    )
    grpc_file.write_text(content)


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # register BEFORE exec so circular refs work
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _load_stubs() -> tuple[types.ModuleType, types.ModuleType]:
    """Return (echo_pb2, echo_pb2_grpc), compiling proto on first call."""
    _ensure_generated()

    if _PB2_MOD not in sys.modules:
        _load_module(_PB2_MOD, GENERATED / "echo_pb2.py")
    if _GRPC_MOD not in sys.modules:
        _load_module(_GRPC_MOD, GENERATED / "echo_pb2_grpc.py")

    return sys.modules[_PB2_MOD], sys.modules[_GRPC_MOD]


class _EchoServicer:
    """Concrete implementation of EchoService."""

    def SayHello(self, request, context):  # type: ignore[override]
        pb2, _ = _load_stubs()
        msg = f"Hello, {request.name}!" if request.name else "Hello!"
        return pb2.HelloReply(message=msg, ok=True)

    def Ping(self, request, context):  # type: ignore[override]
        pb2, _ = _load_stubs()
        return pb2.PingReply(payload=request.payload, elapsed_ms=0.1)

    def ServerStream(self, request, context):  # type: ignore[override]
        pb2, _ = _load_stubs()
        count = max(1, request.count) if request.count else 3
        for i in range(count):
            yield pb2.HelloReply(
                message=f"stream {i}: Hello, {request.name}!", ok=True
            )


def create_server(port: int = 50099) -> object:
    """Create, start, and return a gRPC server with reflection enabled."""
    import grpc
    from grpc_reflection.v1alpha import reflection

    pb2, pb2_grpc = _load_stubs()

    server = grpc.server(concurrent.futures.ThreadPoolExecutor(max_workers=4))
    pb2_grpc.add_EchoServiceServicer_to_server(_EchoServicer(), server)

    service_names = (
        pb2.DESCRIPTOR.services_by_name["EchoService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server


if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=50099)
    args = parser.parse_args()
    srv = create_server(args.port)
    print(f"Echo gRPC server on :{args.port} (Ctrl+C to stop)")
    srv.wait_for_termination()
