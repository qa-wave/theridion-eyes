"""Advanced WebSocket features: auto-reconnect, binary frames, ping/pong, metrics.

Provides REST endpoints that manage WebSocket connections with enhanced
capabilities beyond the basic proxy relay in websocket.py.
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import websockets
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ws", tags=["websocket-advanced"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class WsConnectRequest(BaseModel):
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    subprotocols: list[str] = Field(default_factory=list)
    auto_reconnect: bool = False
    reconnect_interval_ms: int = 3000
    max_reconnects: int = 5
    ping_interval_ms: int | None = None


class WsConnectResponse(BaseModel):
    connection_id: str
    status: str  # "connected" | "error"
    subprotocol: str | None = None
    error: str | None = None


class WsSendBinaryRequest(BaseModel):
    connection_id: str
    payload_base64: str


class WsSubscribeRequest(BaseModel):
    connection_id: str
    channel: str
    pattern: str | None = None


class WsMetrics(BaseModel):
    connection_id: str
    status: str  # "connected" | "disconnected" | "reconnecting"
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    connection_duration_ms: float = 0
    reconnect_count: int = 0
    last_ping_rtt_ms: float | None = None
    avg_ping_rtt_ms: float | None = None


class FrameEntry(BaseModel):
    timestamp: float
    direction: str  # "sent" | "received"
    frame_type: str  # "text" | "binary" | "ping" | "pong" | "close"
    size_bytes: int
    data_preview: str | None = None  # first 200 chars/bytes for text


# ---------------------------------------------------------------------------
# Connection state
# ---------------------------------------------------------------------------


@dataclass
class WsConnection:
    id: str
    url: str
    headers: dict[str, str]
    subprotocols: list[str]
    auto_reconnect: bool
    reconnect_interval_ms: int
    max_reconnects: int
    ping_interval_ms: int | None

    remote: Any | None = None
    status: str = "connecting"
    subprotocol: str | None = None
    connected_at: float = 0.0

    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    reconnect_count: int = 0

    ping_rtts: list[float] = field(default_factory=list)
    last_ping_rtt_ms: float | None = None

    frames: deque[FrameEntry] = field(default_factory=lambda: deque(maxlen=100))
    subscriptions: list[str] = field(default_factory=list)

    _listener_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _ping_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _reconnect_task: asyncio.Task[None] | None = field(default=None, repr=False)


# Global store of active connections.
_connections: dict[str, WsConnection] = {}


def _get_conn(connection_id: str) -> WsConnection:
    conn = _connections.get(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection {connection_id} not found")
    return conn


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


async def _listen_loop(conn: WsConnection) -> None:
    """Listen for incoming messages from the remote server."""
    try:
        async for message in conn.remote:
            if isinstance(message, bytes):
                frame_type = "binary"
                size = len(message)
                preview = base64.b64encode(message[:150]).decode()
            else:
                frame_type = "text"
                size = len(message.encode("utf-8"))
                preview = message[:200]

            conn.messages_received += 1
            conn.bytes_received += size
            conn.frames.append(FrameEntry(
                timestamp=time.time() * 1000,
                direction="received",
                frame_type=frame_type,
                size_bytes=size,
                data_preview=preview,
            ))
    except websockets.ConnectionClosed:
        pass
    except Exception:
        pass
    finally:
        conn.status = "disconnected"
        conn.frames.append(FrameEntry(
            timestamp=time.time() * 1000,
            direction="received",
            frame_type="close",
            size_bytes=0,
            data_preview=None,
        ))
        if conn.auto_reconnect and conn.reconnect_count < conn.max_reconnects:
            conn.status = "reconnecting"
            conn._reconnect_task = asyncio.create_task(_reconnect_loop(conn))


async def _reconnect_loop(conn: WsConnection) -> None:
    """Attempt to reconnect with exponential-ish backoff."""
    while conn.reconnect_count < conn.max_reconnects:
        await asyncio.sleep(conn.reconnect_interval_ms / 1000.0)
        conn.reconnect_count += 1
        try:
            remote = await websockets.connect(
                conn.url,
                additional_headers=conn.headers,
                subprotocols=[websockets.Subprotocol(s) for s in conn.subprotocols] if conn.subprotocols else None,
                open_timeout=10,
            )
            conn.remote = remote
            conn.status = "connected"
            conn.connected_at = time.time()
            conn.subprotocol = str(remote.subprotocol) if remote.subprotocol else None
            conn._listener_task = asyncio.create_task(_listen_loop(conn))
            if conn.ping_interval_ms:
                conn._ping_task = asyncio.create_task(_ping_loop(conn))
            return
        except Exception:
            continue
    conn.status = "disconnected"


async def _ping_loop(conn: WsConnection) -> None:
    """Send periodic pings and measure RTT."""
    try:
        while conn.status == "connected" and conn.remote:
            start = time.time()
            pong_waiter = await conn.remote.ping()
            await pong_waiter
            rtt = (time.time() - start) * 1000
            conn.last_ping_rtt_ms = rtt
            conn.ping_rtts.append(rtt)
            # Keep max 50 RTT samples.
            if len(conn.ping_rtts) > 50:
                conn.ping_rtts = conn.ping_rtts[-50:]

            conn.frames.append(FrameEntry(
                timestamp=time.time() * 1000,
                direction="sent",
                frame_type="ping",
                size_bytes=0,
                data_preview=f"RTT={rtt:.1f}ms",
            ))
            conn.frames.append(FrameEntry(
                timestamp=time.time() * 1000,
                direction="received",
                frame_type="pong",
                size_bytes=0,
                data_preview=f"RTT={rtt:.1f}ms",
            ))

            interval = conn.ping_interval_ms / 1000.0 if conn.ping_interval_ms else 30.0
            await asyncio.sleep(interval)
    except (websockets.ConnectionClosed, asyncio.CancelledError):
        pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/connect", response_model=WsConnectResponse)
async def ws_connect(req: WsConnectRequest) -> WsConnectResponse:
    """Open an enhanced WebSocket connection with auto-reconnect and ping support."""
    conn_id = str(uuid.uuid4())
    conn = WsConnection(
        id=conn_id,
        url=req.url,
        headers=req.headers,
        subprotocols=req.subprotocols,
        auto_reconnect=req.auto_reconnect,
        reconnect_interval_ms=req.reconnect_interval_ms,
        max_reconnects=req.max_reconnects,
        ping_interval_ms=req.ping_interval_ms,
    )
    _connections[conn_id] = conn

    try:
        remote = await websockets.connect(
            req.url,
            additional_headers=req.headers,
            subprotocols=[websockets.Subprotocol(s) for s in req.subprotocols] if req.subprotocols else None,
            open_timeout=10,
        )
        conn.remote = remote
        conn.status = "connected"
        conn.connected_at = time.time()
        conn.subprotocol = str(remote.subprotocol) if remote.subprotocol else None

        # Start listener.
        conn._listener_task = asyncio.create_task(_listen_loop(conn))

        # Start ping loop if configured.
        if req.ping_interval_ms:
            conn._ping_task = asyncio.create_task(_ping_loop(conn))

        return WsConnectResponse(
            connection_id=conn_id,
            status="connected",
            subprotocol=conn.subprotocol,
        )
    except Exception as e:
        conn.status = "disconnected"
        del _connections[conn_id]
        return WsConnectResponse(
            connection_id=conn_id,
            status="error",
            error=str(e),
        )


@router.post("/send-binary")
async def ws_send_binary(req: WsSendBinaryRequest) -> dict[str, str]:
    """Send a binary frame (base64-encoded payload) to the remote server."""
    conn = _get_conn(req.connection_id)
    if conn.status != "connected" or not conn.remote:
        raise HTTPException(status_code=400, detail="Connection is not active")

    try:
        payload = base64.b64decode(req.payload_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 payload")

    await conn.remote.send(payload)
    conn.messages_sent += 1
    conn.bytes_sent += len(payload)
    conn.frames.append(FrameEntry(
        timestamp=time.time() * 1000,
        direction="sent",
        frame_type="binary",
        size_bytes=len(payload),
        data_preview=base64.b64encode(payload[:150]).decode(),
    ))
    return {"status": "sent", "size_bytes": str(len(payload))}


@router.post("/send-text")
async def ws_send_text(body: dict[str, str]) -> dict[str, str]:
    """Send a text frame."""
    connection_id = body.get("connection_id", "")
    data = body.get("data", "")
    conn = _get_conn(connection_id)
    if conn.status != "connected" or not conn.remote:
        raise HTTPException(status_code=400, detail="Connection is not active")

    await conn.remote.send(data)
    size = len(data.encode("utf-8"))
    conn.messages_sent += 1
    conn.bytes_sent += size
    conn.frames.append(FrameEntry(
        timestamp=time.time() * 1000,
        direction="sent",
        frame_type="text",
        size_bytes=size,
        data_preview=data[:200],
    ))
    return {"status": "sent", "size_bytes": str(size)}


@router.get("/metrics")
async def ws_metrics(connection_id: str) -> WsMetrics:
    """Get connection metrics: messages, bytes, duration, reconnects, latency."""
    conn = _get_conn(connection_id)
    duration = 0.0
    if conn.connected_at > 0:
        duration = (time.time() - conn.connected_at) * 1000

    avg_rtt: float | None = None
    if conn.ping_rtts:
        avg_rtt = sum(conn.ping_rtts) / len(conn.ping_rtts)

    return WsMetrics(
        connection_id=conn.id,
        status=conn.status,
        messages_sent=conn.messages_sent,
        messages_received=conn.messages_received,
        bytes_sent=conn.bytes_sent,
        bytes_received=conn.bytes_received,
        connection_duration_ms=duration,
        reconnect_count=conn.reconnect_count,
        last_ping_rtt_ms=conn.last_ping_rtt_ms,
        avg_ping_rtt_ms=avg_rtt,
    )


@router.post("/subscribe")
async def ws_subscribe(req: WsSubscribeRequest) -> dict[str, str]:
    """Subscribe to a topic/channel (sends a subscribe message to the server)."""
    conn = _get_conn(req.connection_id)
    if conn.status != "connected" or not conn.remote:
        raise HTTPException(status_code=400, detail="Connection is not active")

    import json
    subscribe_msg = json.dumps({
        "action": "subscribe",
        "channel": req.channel,
        **({"pattern": req.pattern} if req.pattern else {}),
    })
    await conn.remote.send(subscribe_msg)
    conn.subscriptions.append(req.channel)
    conn.messages_sent += 1
    size = len(subscribe_msg.encode("utf-8"))
    conn.bytes_sent += size
    conn.frames.append(FrameEntry(
        timestamp=time.time() * 1000,
        direction="sent",
        frame_type="text",
        size_bytes=size,
        data_preview=subscribe_msg[:200],
    ))
    return {"status": "subscribed", "channel": req.channel}


@router.get("/frames")
async def ws_frames(connection_id: str) -> list[FrameEntry]:
    """Get the frame log (last 100 frames)."""
    conn = _get_conn(connection_id)
    return list(conn.frames)


@router.post("/disconnect")
async def ws_disconnect(body: dict[str, str]) -> dict[str, str]:
    """Close an advanced WebSocket connection."""
    connection_id = body.get("connection_id", "")
    conn = _get_conn(connection_id)

    # Cancel background tasks.
    if conn._ping_task and not conn._ping_task.done():
        conn._ping_task.cancel()
    if conn._listener_task and not conn._listener_task.done():
        conn._listener_task.cancel()
    if conn._reconnect_task and not conn._reconnect_task.done():
        conn._reconnect_task.cancel()

    # Disable auto-reconnect so listener cleanup doesn't trigger it.
    conn.auto_reconnect = False

    if conn.remote:
        try:
            await conn.remote.close()
        except Exception:
            pass

    conn.status = "disconnected"
    del _connections[connection_id]
    return {"status": "disconnected"}


@router.get("/connections")
async def ws_list_connections() -> list[dict[str, str]]:
    """List all active advanced WebSocket connections."""
    return [
        {"connection_id": c.id, "url": c.url, "status": c.status}
        for c in _connections.values()
    ]
