"""Mock HTTP server management endpoints.

Starts a lightweight Starlette server on a random port with configurable
routes that return static responses. Useful for testing against fake APIs.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from typing import Any

import uvicorn
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

router = APIRouter(prefix="/api/mock", tags=["mock"])

# In-memory registry of running mock servers.
_servers: dict[int, _MockHandle] = {}


class MockRoute(BaseModel):
    """A single route definition for the mock server."""

    path: str = Field(..., min_length=1)
    method: str = "GET"
    status: int = 200
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    content_type: str = "application/json"


class MockStartRequest(BaseModel):
    routes: list[MockRoute] = Field(..., min_length=1)
    port: int | None = None


class MockStartResponse(BaseModel):
    port: int
    route_count: int


class MockStatusResponse(BaseModel):
    servers: list[MockServerInfo]


class MockServerInfo(BaseModel):
    port: int
    route_count: int


class _MockHandle:
    """Tracks a running mock server so we can shut it down."""

    def __init__(self, port: int, route_count: int, server: uvicorn.Server) -> None:
        self.port = port
        self.route_count = route_count
        self.server = server


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_app(routes: list[MockRoute]) -> Starlette:
    starlette_routes: list[Route] = []
    for r in routes:
        body_content = r.body
        status_code = r.status
        resp_headers = dict(r.headers)
        content_type = r.content_type

        def make_handler(
            body: str, status: int, hdrs: dict[str, str], ct: str
        ):
            async def handler(request: Request) -> Response:
                return Response(
                    content=body,
                    status_code=status,
                    headers={**hdrs, "content-type": ct},
                )
            return handler

        starlette_routes.append(
            Route(
                r.path,
                make_handler(body_content, status_code, resp_headers, content_type),
                methods=[r.method.upper()],
            )
        )
    return Starlette(routes=starlette_routes)


@router.post("/start", response_model=MockStartResponse)
async def start_mock(req: MockStartRequest) -> MockStartResponse:
    port = req.port or _pick_free_port()
    if port in _servers:
        raise HTTPException(status_code=409, detail=f"mock server already running on port {port}")

    app = _build_app(req.routes)
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)

    handle = _MockHandle(port=port, route_count=len(req.routes), server=server)
    _servers[port] = handle

    # Run in a background thread so we don't block.
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Brief wait for the server to bind.
    for _ in range(20):
        if server.started:
            break
        await asyncio.sleep(0.05)

    return MockStartResponse(port=port, route_count=len(req.routes))


class MockStopRequest(BaseModel):
    port: int


@router.post("/stop")
async def stop_mock(req: MockStopRequest) -> dict[str, str]:
    handle = _servers.pop(req.port, None)
    if handle is None:
        raise HTTPException(status_code=404, detail=f"no mock server on port {req.port}")
    handle.server.should_exit = True
    return {"status": "stopped", "port": str(req.port)}


@router.get("/status", response_model=MockStatusResponse)
async def mock_status() -> MockStatusResponse:
    infos = [
        MockServerInfo(port=h.port, route_count=h.route_count)
        for h in _servers.values()
    ]
    return MockStatusResponse(servers=infos)
