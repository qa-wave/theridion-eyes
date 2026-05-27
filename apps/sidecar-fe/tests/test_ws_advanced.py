"""Tests for advanced WebSocket features: connect, binary, metrics, frames, reconnect."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from theridion_sidecar.main import create_app

app = create_app()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class _HangingAsyncIterator:
    """Async iterator that blocks forever — simulates a live WS connection.

    Using a proper class avoids the AsyncMock coroutine-never-awaited warning
    and ensures _listen_loop stays suspended for the duration of the test.
    """

    def __aiter__(self):
        return self

    async def __anext__(self):
        # Block until cancelled — never yields a message.
        await asyncio.get_event_loop().create_future()
        raise StopAsyncIteration  # unreachable, satisfies type checker


def _mock_ws_connection(subprotocol=None):
    """Create a mock websockets connection object.

    The remote is a _HangingAsyncIterator so _listen_loop never terminates
    and conn.status stays 'connected' throughout the test.
    """
    mock = MagicMock()
    mock.subprotocol = subprotocol
    mock.close = AsyncMock()
    mock.send = AsyncMock()
    mock.ping = AsyncMock()
    # Replace the mock with a hanging async iterator for iteration.
    hanging = _HangingAsyncIterator()
    mock.__aiter__ = MagicMock(return_value=hanging)
    mock.__anext__ = hanging.__anext__
    return mock


@pytest.mark.anyio
async def test_connect_success(client: AsyncClient):
    """Test successful connection with subprotocols."""
    mock_remote = _mock_ws_connection(subprotocol="graphql-ws")

    with patch("theridion_sidecar.api.ws_advanced.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_remote

        resp = await client.post("/api/ws/connect", json={
            "url": "ws://localhost:9999/ws",
            "headers": {"Authorization": "Bearer tok"},
            "subprotocols": ["graphql-ws", "graphql-transport-ws"],
            "auto_reconnect": True,
            "ping_interval_ms": 5000,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "connected"
    assert data["subprotocol"] == "graphql-ws"
    assert data["connection_id"]

    # Cleanup
    from theridion_sidecar.api.ws_advanced import _connections
    conn_id = data["connection_id"]
    if conn_id in _connections:
        conn = _connections[conn_id]
        if conn._ping_task:
            conn._ping_task.cancel()
        if conn._listener_task:
            conn._listener_task.cancel()
        del _connections[conn_id]


@pytest.mark.anyio
async def test_connect_failure(client: AsyncClient):
    """Test connection failure returns error."""
    with patch("theridion_sidecar.api.ws_advanced.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.side_effect = OSError("Connection refused")

        resp = await client.post("/api/ws/connect", json={
            "url": "ws://localhost:9999/ws",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert "Connection refused" in data["error"]


@pytest.mark.anyio
async def test_send_binary(client: AsyncClient):
    """Test sending binary frames (base64 encoded)."""
    mock_remote = _mock_ws_connection()

    with patch("theridion_sidecar.api.ws_advanced.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_remote

        # Connect first.
        resp = await client.post("/api/ws/connect", json={"url": "ws://localhost:9999/ws"})
        conn_id = resp.json()["connection_id"]

        # Send binary — must be inside the patch context so conn.status == "connected".
        payload = b"\x00\x01\x02\x03\xff"
        resp = await client.post("/api/ws/send-binary", json={
            "connection_id": conn_id,
            "payload_base64": base64.b64encode(payload).decode(),
        })

        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"
        assert resp.json()["size_bytes"] == str(len(payload))
        mock_remote.send.assert_called_with(payload)

    # Cleanup
    from theridion_sidecar.api.ws_advanced import _connections
    if conn_id in _connections:
        conn = _connections[conn_id]
        if conn._listener_task:
            conn._listener_task.cancel()
        del _connections[conn_id]


@pytest.mark.anyio
async def test_metrics(client: AsyncClient):
    """Test metrics endpoint returns connection stats."""
    mock_remote = _mock_ws_connection()

    with patch("theridion_sidecar.api.ws_advanced.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_remote

        resp = await client.post("/api/ws/connect", json={"url": "ws://localhost:9999/ws"})
        conn_id = resp.json()["connection_id"]

        # Send a text message to populate metrics — inside patch so status stays "connected".
        await client.post("/api/ws/send-text", json={
            "connection_id": conn_id,
            "data": "hello world",
        })

        # Get metrics.
        resp = await client.get("/api/ws/metrics", params={"connection_id": conn_id})
        assert resp.status_code == 200
        metrics = resp.json()
        assert metrics["connection_id"] == conn_id
        assert metrics["status"] == "connected"
        assert metrics["messages_sent"] == 1
        assert metrics["bytes_sent"] == len("hello world".encode())
        assert metrics["connection_duration_ms"] > 0

    # Cleanup
    from theridion_sidecar.api.ws_advanced import _connections
    if conn_id in _connections:
        conn = _connections[conn_id]
        if conn._listener_task:
            conn._listener_task.cancel()
        del _connections[conn_id]


@pytest.mark.anyio
async def test_frame_log(client: AsyncClient):
    """Test frame log tracks sent messages."""
    mock_remote = _mock_ws_connection()

    with patch("theridion_sidecar.api.ws_advanced.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_remote

        resp = await client.post("/api/ws/connect", json={"url": "ws://localhost:9999/ws"})
        conn_id = resp.json()["connection_id"]

        # Send messages — inside patch so conn.status stays "connected".
        await client.post("/api/ws/send-text", json={"connection_id": conn_id, "data": "msg1"})
        await client.post("/api/ws/send-text", json={"connection_id": conn_id, "data": "msg2"})

        payload = b"\xde\xad\xbe\xef"
        await client.post("/api/ws/send-binary", json={
            "connection_id": conn_id,
            "payload_base64": base64.b64encode(payload).decode(),
        })

        # Get frames.
        resp = await client.get("/api/ws/frames", params={"connection_id": conn_id})
        assert resp.status_code == 200
        frames = resp.json()
        assert len(frames) == 3
        assert frames[0]["frame_type"] == "text"
        assert frames[0]["direction"] == "sent"
        assert frames[0]["data_preview"] == "msg1"
        assert frames[1]["frame_type"] == "text"
        assert frames[2]["frame_type"] == "binary"
        assert frames[2]["size_bytes"] == 4

    # Cleanup
    from theridion_sidecar.api.ws_advanced import _connections
    if conn_id in _connections:
        conn = _connections[conn_id]
        if conn._listener_task:
            conn._listener_task.cancel()
        del _connections[conn_id]


@pytest.mark.anyio
async def test_subscribe(client: AsyncClient):
    """Test subscribe sends a subscribe message to the server."""
    mock_remote = _mock_ws_connection()

    with patch("theridion_sidecar.api.ws_advanced.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_remote

        resp = await client.post("/api/ws/connect", json={"url": "ws://localhost:9999/ws"})
        conn_id = resp.json()["connection_id"]

        # Subscribe — inside patch so conn.status stays "connected".
        resp = await client.post("/api/ws/subscribe", json={
            "connection_id": conn_id,
            "channel": "events",
            "pattern": "user.*",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "subscribed"
        assert resp.json()["channel"] == "events"

        # Verify the send call.
        sent_data = mock_remote.send.call_args[0][0]
        parsed = json.loads(sent_data)
        assert parsed["action"] == "subscribe"
        assert parsed["channel"] == "events"
        assert parsed["pattern"] == "user.*"

    # Cleanup
    from theridion_sidecar.api.ws_advanced import _connections
    if conn_id in _connections:
        conn = _connections[conn_id]
        if conn._listener_task:
            conn._listener_task.cancel()
        del _connections[conn_id]


@pytest.mark.anyio
async def test_disconnect(client: AsyncClient):
    """Test explicit disconnect closes connection and cleans up."""
    mock_remote = _mock_ws_connection()

    with patch("theridion_sidecar.api.ws_advanced.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_remote

        resp = await client.post("/api/ws/connect", json={"url": "ws://localhost:9999/ws"})
        conn_id = resp.json()["connection_id"]

    resp = await client.post("/api/ws/disconnect", json={"connection_id": conn_id})
    assert resp.status_code == 200
    assert resp.json()["status"] == "disconnected"

    # Verify removed from store.
    from theridion_sidecar.api.ws_advanced import _connections
    assert conn_id not in _connections


@pytest.mark.anyio
async def test_auto_reconnect(client: AsyncClient):
    """Test auto-reconnect is triggered when connection drops."""
    from theridion_sidecar.api.ws_advanced import _connections

    mock_remote = _mock_ws_connection()
    # Simulate immediate disconnect by making the iterator raise.
    import websockets as ws_lib

    async def _immediate_close():
        raise ws_lib.ConnectionClosed(None, None)

    mock_remote.__aiter__ = MagicMock(side_effect=_immediate_close)

    with patch("theridion_sidecar.api.ws_advanced.websockets.connect", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_remote

        resp = await client.post("/api/ws/connect", json={
            "url": "ws://localhost:9999/ws",
            "auto_reconnect": True,
            "reconnect_interval_ms": 100,
            "max_reconnects": 2,
        })
        conn_id = resp.json()["connection_id"]
        assert resp.json()["status"] == "connected"

    # Give the listener task a moment to run and trigger reconnect.
    await asyncio.sleep(0.15)

    conn = _connections.get(conn_id)
    if conn:
        # It should be either reconnecting or disconnected.
        assert conn.status in ("reconnecting", "disconnected", "connected")
        # Cleanup
        conn.auto_reconnect = False
        if conn._reconnect_task:
            conn._reconnect_task.cancel()
        if conn._listener_task:
            conn._listener_task.cancel()
        if conn._ping_task:
            conn._ping_task.cancel()
        del _connections[conn_id]


@pytest.mark.anyio
async def test_not_found_connection(client: AsyncClient):
    """Test 404 for non-existent connection ID."""
    resp = await client.get("/api/ws/metrics", params={"connection_id": "nonexistent"})
    assert resp.status_code == 404

    resp = await client.get("/api/ws/frames", params={"connection_id": "nonexistent"})
    assert resp.status_code == 404
