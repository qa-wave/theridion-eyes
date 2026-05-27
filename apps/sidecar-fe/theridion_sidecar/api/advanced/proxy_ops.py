"""Proxy recorder and mock-from-collection endpoints."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
import uvicorn
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from ... import storage
from ...models import CollectionItem

router = APIRouter()

HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


class ProxyStartInput(BaseModel):
    target_base_url: str = Field(..., min_length=1)
    port: int | None = None


class ProxyStartOutput(BaseModel):
    session_id: str
    port: int
    target_base_url: str


class ProxyStatusOutput(BaseModel):
    sessions: list[ProxyStartOutput]


class _ProxyHandle:
    def __init__(
        self,
        session_id: str,
        port: int,
        target_base_url: str,
        server: uvicorn.Server,
    ) -> None:
        self.session_id = session_id
        self.port = port
        self.target_base_url = target_base_url.rstrip("/")
        self.server = server
        self.entries: list[dict[str, Any]] = []


_proxy_sessions: dict[str, _ProxyHandle] = {}


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_proxy_app(handle: _ProxyHandle) -> Starlette:
    async def proxy(request: Request) -> Response:
        raw_body = await request.body()
        target = f"{handle.target_base_url}/{request.path_params.get('path', '')}"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=60) as client:
                response = await client.request(
                    method=request.method,
                    url=target,
                    headers={
                        key: value
                        for key, value in request.headers.items()
                        if key.lower() not in {"host", "content-length"}
                    },
                    content=raw_body,
                )
        except httpx.RequestError as exc:
            return Response(str(exc), status_code=502)
        elapsed = (time.perf_counter() - started) * 1000
        handle.entries.append(
            {
                "startedDateTime": datetime.now(tz=UTC).isoformat(),
                "time": round(elapsed, 2),
                "request": {
                    "method": request.method,
                    "url": target,
                    "headers": [{"name": k, "value": v} for k, v in request.headers.items()],
                    "postData": {"text": raw_body.decode("utf-8", errors="replace")},
                },
                "response": {
                    "status": response.status_code,
                    "statusText": response.reason_phrase,
                    "headers": [{"name": k, "value": v} for k, v in response.headers.items()],
                    "content": {"text": response.text, "size": len(response.content)},
                },
            }
        )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers={k: v for k, v in response.headers.items() if k.lower() != "content-encoding"},
        )

    return Starlette(routes=[Route("/{path:path}", proxy, methods=list(HTTP_METHODS))])


@router.post("/proxy/start", response_model=ProxyStartOutput)
async def start_proxy(body: ProxyStartInput) -> ProxyStartOutput:
    port = body.port or _pick_free_port()
    if any(handle.port == port for handle in _proxy_sessions.values()):
        raise HTTPException(status_code=409, detail=f"proxy already running on port {port}")
    session_id = str(uuid.uuid4())
    placeholder = _ProxyHandle(session_id, port, body.target_base_url, server=None)  # type: ignore[arg-type]
    app = _build_proxy_app(placeholder)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    placeholder.server = server
    _proxy_sessions[session_id] = placeholder
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(20):
        if server.started:
            break
        await asyncio.sleep(0.05)
    return ProxyStartOutput(session_id=session_id, port=port, target_base_url=body.target_base_url)


@router.get("/proxy/status", response_model=ProxyStatusOutput)
def proxy_status() -> ProxyStatusOutput:
    return ProxyStatusOutput(
        sessions=[
            ProxyStartOutput(
                session_id=handle.session_id,
                port=handle.port,
                target_base_url=handle.target_base_url,
            )
            for handle in _proxy_sessions.values()
        ]
    )


@router.post("/proxy/{session_id}/stop")
def stop_proxy(session_id: str) -> dict[str, str]:
    handle = _proxy_sessions.pop(session_id, None)
    if handle is None:
        raise HTTPException(status_code=404, detail="proxy session not found")
    handle.server.should_exit = True
    return {"status": "stopped", "session_id": session_id}


@router.get("/proxy/{session_id}/har")
def proxy_har(session_id: str) -> dict[str, Any]:
    handle = _proxy_sessions.get(session_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="proxy session not found")
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "Theridion proxy recorder", "version": "0.0.1"},
            "entries": handle.entries,
        }
    }


# ---- Mock from collection -------------------------------------------------


def _flatten_requests(items: list[CollectionItem]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for item in items:
        if item.is_folder:
            out.extend(_flatten_requests(item.items))
        else:
            out.append(item)
    return out


def _looks_like_json(value: str) -> bool:
    try:
        json.loads(value)
        return True
    except json.JSONDecodeError:
        return False


@router.post("/mock/start-from-collection/{collection_id}")
async def start_mock_from_collection(collection_id: str, port: int | None = None) -> Any:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    from ..mock import MockRoute, MockStartRequest, start_mock

    routes: list[MockRoute] = []
    for req in _flatten_requests(coll.items):
        if not req.url:
            continue
        parsed = urlsplit(req.url)
        response_body = (
            req.examples[0].body
            if req.examples and req.examples[0].body is not None
            else req.body or json.dumps({"request": req.name})
        )
        routes.append(
            MockRoute(
                path=parsed.path or "/",
                method=req.method or "GET",
                status=200,
                body=response_body,
                content_type=(
                    "application/json" if _looks_like_json(response_body) else "text/plain"
                ),
            )
        )
    if not routes:
        raise HTTPException(status_code=400, detail="collection has no mockable requests")
    return await start_mock(MockStartRequest(routes=routes, port=port))
