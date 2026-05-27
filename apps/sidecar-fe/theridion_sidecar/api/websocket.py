"""WebSocket proxy — connect to a remote WS server, relay messages.

The frontend connects to the sidecar's WS endpoint, which in turn
connects to the target server. Messages are relayed bidirectionally.
This keeps the frontend simple (no direct WS from the browser to
arbitrary origins, avoiding CORS and mixed-content issues).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

router = APIRouter(tags=["websocket"])


class WsMessage(BaseModel):
    direction: str  # "sent" | "received"
    data: str
    timestamp: float
    size_bytes: int


@router.websocket("/api/ws/proxy")
async def ws_proxy(ws: WebSocket) -> None:
    """Proxy WebSocket connections to a remote server.

    Protocol:
    1. Client sends a JSON connect message: {"url": "ws://...", "headers": {...}}
    2. Sidecar connects to the target, sends back {"type": "connected"}
    3. Bidirectional relay: client ↔ sidecar ↔ target
    4. Either side closing terminates both connections.
    """
    await ws.accept()

    try:
        # Wait for connect instruction.
        init_raw = await ws.receive_text()
        init = json.loads(init_raw)
        target_url = init.get("url", "")
        headers = init.get("headers", {})

        if not target_url:
            await ws.send_json({"type": "error", "message": "No URL provided"})
            await ws.close()
            return

        # Connect to the remote server.
        try:
            remote = await websockets.connect(
                target_url,
                additional_headers=headers,
                open_timeout=10,
            )
        except Exception as e:
            await ws.send_json({
                "type": "error",
                "message": f"Failed to connect: {e}",
            })
            await ws.close()
            return

        await ws.send_json({"type": "connected", "url": target_url})

        # Relay messages bidirectionally.
        async def client_to_remote() -> None:
            try:
                while True:
                    data = await ws.receive_text()
                    msg = json.loads(data)
                    if msg.get("type") == "send":
                        payload = msg.get("data", "")
                        await remote.send(payload)
                    elif msg.get("type") == "close":
                        await remote.close()
                        break
            except WebSocketDisconnect:
                await remote.close()

        async def remote_to_client() -> None:
            try:
                async for message in remote:
                    text = message if isinstance(message, str) else message.decode("utf-8", errors="replace")
                    await ws.send_json({
                        "type": "message",
                        "data": text,
                        "timestamp": time.time() * 1000,
                        "size_bytes": len(text.encode("utf-8")),
                    })
            except websockets.ConnectionClosed:
                pass
            finally:
                await ws.send_json({"type": "disconnected"})

        # Run both directions concurrently.
        done, pending = await asyncio.wait(
            [
                asyncio.create_task(client_to_remote()),
                asyncio.create_task(remote_to_client()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
