"""Record-and-replay mock server.

Proxies requests to a real target, records every interaction, then
replays them from memory (or disk) as a standalone mock server.
Interactions are persisted under ``~/.theridion/mock_recordings/``.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .. import storage

router = APIRouter(prefix="/api/mock/record", tags=["mock-record"])

HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RecordedInteraction(BaseModel):
    """A single recorded request/response pair."""

    method: str
    path: str
    query: str = ""
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: str | None = None
    status: int
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: str = ""
    elapsed_ms: float = 0.0
    timestamp: float = 0.0


class RecordStartInput(BaseModel):
    target_url: str = Field(..., min_length=1)
    port: int = 9000


class RecordStartOutput(BaseModel):
    session_id: str
    port: int
    target_url: str


class RecordStopOutput(BaseModel):
    session_id: str
    interaction_count: int
    file: str


class InteractionsOutput(BaseModel):
    session_id: str | None = None
    interactions: list[RecordedInteraction]
    recordings: list[str] = Field(default_factory=list)


class ReplayStartInput(BaseModel):
    recording_id: str | None = None
    interactions: list[RecordedInteraction] | None = None
    port: int = 9001
    fuzzy_query: bool = False


class ReplayStartOutput(BaseModel):
    port: int
    route_count: int


class ReplayStatusOutput(BaseModel):
    running: bool
    port: int | None = None
    route_count: int = 0


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------


class _RecordHandle:
    def __init__(
        self,
        session_id: str,
        port: int,
        target_url: str,
        server: uvicorn.Server,
    ) -> None:
        self.session_id = session_id
        self.port = port
        self.target_url = target_url.rstrip("/")
        self.server = server
        self.interactions: list[RecordedInteraction] = []


class _ReplayHandle:
    def __init__(self, port: int, route_count: int, server: uvicorn.Server) -> None:
        self.port = port
        self.route_count = route_count
        self.server = server


_record_session: _RecordHandle | None = None
_replay_handle: _ReplayHandle | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _recordings_dir() -> Path:
    d = storage.home_dir() / "mock_recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _save_recording(session_id: str, interactions: list[RecordedInteraction]) -> Path:
    path = _recordings_dir() / f"{session_id}.json"
    data = [ix.model_dump() for ix in interactions]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _load_recording(recording_id: str) -> list[RecordedInteraction]:
    path = _recordings_dir() / f"{recording_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"recording {recording_id} not found")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [RecordedInteraction(**item) for item in raw]


# ---------------------------------------------------------------------------
# Recording proxy app
# ---------------------------------------------------------------------------


def _build_record_app(handle: _RecordHandle) -> Starlette:
    async def proxy(request: Request) -> Response:
        raw_body = await request.body()
        rel_path = request.path_params.get("path", "")
        target = f"{handle.target_url}/{rel_path}"
        query = str(request.url.query) if request.url.query else ""
        if query:
            target = f"{target}?{query}"

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=60) as client:
                resp = await client.request(
                    method=request.method,
                    url=target,
                    headers={
                        k: v
                        for k, v in request.headers.items()
                        if k.lower() not in {"host", "content-length"}
                    },
                    content=raw_body,
                )
        except httpx.RequestError as exc:
            return Response(str(exc), status_code=502)

        elapsed = (time.perf_counter() - started) * 1000

        interaction = RecordedInteraction(
            method=request.method,
            path=f"/{rel_path}",
            query=query,
            request_headers={k: v for k, v in request.headers.items()},
            request_body=raw_body.decode("utf-8", errors="replace") if raw_body else None,
            status=resp.status_code,
            response_headers={k: v for k, v in resp.headers.items()},
            response_body=resp.text,
            elapsed_ms=round(elapsed, 2),
            timestamp=time.time(),
        )
        handle.interactions.append(interaction)

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers={k: v for k, v in resp.headers.items() if k.lower() != "content-encoding"},
        )

    return Starlette(routes=[Route("/{path:path}", proxy, methods=list(HTTP_METHODS))])


# ---------------------------------------------------------------------------
# Replay app
# ---------------------------------------------------------------------------


def _build_replay_app(
    interactions: list[RecordedInteraction],
    fuzzy_query: bool = False,
) -> Starlette:
    """Build a Starlette app that serves recorded responses.

    Matching: method + path. If *fuzzy_query* is False (default), query string
    must also match exactly. When fuzzy, query params are ignored.
    """
    lookup: dict[tuple[str, str, str], RecordedInteraction] = {}
    lookup_fuzzy: dict[tuple[str, str], RecordedInteraction] = {}

    for ix in interactions:
        key = (ix.method.upper(), ix.path, ix.query)
        if key not in lookup:
            lookup[key] = ix
        fuzzy_key = (ix.method.upper(), ix.path)
        if fuzzy_key not in lookup_fuzzy:
            lookup_fuzzy[fuzzy_key] = ix

    async def handler(request: Request) -> Response:
        method = request.method.upper()
        path = f"/{request.path_params.get('path', '')}"
        query = str(request.url.query) if request.url.query else ""

        ix = lookup.get((method, path, query))
        if ix is None and fuzzy_query:
            ix = lookup_fuzzy.get((method, path))
        if ix is None:
            return Response(
                content=json.dumps({"error": "no matching recorded interaction"}),
                status_code=404,
                headers={"content-type": "application/json"},
            )
        resp_headers = {
            k: v
            for k, v in ix.response_headers.items()
            if k.lower() not in {"content-encoding", "transfer-encoding", "content-length"}
        }
        return Response(
            content=ix.response_body,
            status_code=ix.status,
            headers=resp_headers,
        )

    return Starlette(routes=[Route("/{path:path}", handler, methods=list(HTTP_METHODS))])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/start", response_model=RecordStartOutput)
async def record_start(body: RecordStartInput) -> RecordStartOutput:
    global _record_session
    if _record_session is not None:
        raise HTTPException(status_code=409, detail="recording already in progress")

    port = body.port or _pick_free_port()
    session_id = str(uuid.uuid4())
    placeholder = _RecordHandle(session_id, port, body.target_url, server=None)  # type: ignore[arg-type]
    app = _build_record_app(placeholder)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    placeholder.server = server
    _record_session = placeholder

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(20):
        if server.started:
            break
        await asyncio.sleep(0.05)

    return RecordStartOutput(session_id=session_id, port=port, target_url=body.target_url)


@router.post("/stop", response_model=RecordStopOutput)
async def record_stop() -> RecordStopOutput:
    global _record_session
    if _record_session is None:
        raise HTTPException(status_code=404, detail="no recording in progress")

    handle = _record_session
    _record_session = None
    handle.server.should_exit = True

    file = _save_recording(handle.session_id, handle.interactions)
    return RecordStopOutput(
        session_id=handle.session_id,
        interaction_count=len(handle.interactions),
        file=file.name,
    )


@router.get("/interactions", response_model=InteractionsOutput)
async def record_interactions(recording_id: str | None = None) -> InteractionsOutput:
    # If a recording_id is given, load from disk
    if recording_id:
        interactions = _load_recording(recording_id)
        return InteractionsOutput(
            session_id=recording_id,
            interactions=interactions,
        )
    # If there's an active session, return live interactions
    if _record_session is not None:
        return InteractionsOutput(
            session_id=_record_session.session_id,
            interactions=list(_record_session.interactions),
        )
    # List all recordings
    recordings = [p.stem for p in _recordings_dir().glob("*.json")]
    return InteractionsOutput(
        session_id=None,
        interactions=[],
        recordings=recordings,
    )


# ---- Replay ---------------------------------------------------------------


replay_router = APIRouter(prefix="/api/mock/replay", tags=["mock-replay"])


@replay_router.post("/start", response_model=ReplayStartOutput)
async def replay_start(body: ReplayStartInput) -> ReplayStartOutput:
    global _replay_handle
    if _replay_handle is not None:
        raise HTTPException(status_code=409, detail="replay server already running")

    # Resolve interactions — either from input or from a saved recording
    if body.interactions:
        interactions = body.interactions
    elif body.recording_id:
        interactions = _load_recording(body.recording_id)
    else:
        raise HTTPException(
            status_code=400,
            detail="provide either recording_id or interactions",
        )

    port = body.port or _pick_free_port()
    app = _build_replay_app(interactions, fuzzy_query=body.fuzzy_query)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    handle = _ReplayHandle(port=port, route_count=len(interactions), server=server)
    _replay_handle = handle

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(20):
        if server.started:
            break
        await asyncio.sleep(0.05)

    return ReplayStartOutput(port=port, route_count=len(interactions))


@replay_router.post("/stop")
async def replay_stop() -> dict[str, str]:
    global _replay_handle
    if _replay_handle is None:
        raise HTTPException(status_code=404, detail="no replay server running")
    _replay_handle.server.should_exit = True
    port = _replay_handle.port
    _replay_handle = None
    return {"status": "stopped", "port": str(port)}


@replay_router.get("/status", response_model=ReplayStatusOutput)
async def replay_status() -> ReplayStatusOutput:
    if _replay_handle is None:
        return ReplayStatusOutput(running=False)
    return ReplayStatusOutput(
        running=True,
        port=_replay_handle.port,
        route_count=_replay_handle.route_count,
    )
