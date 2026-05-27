"""JMS client: STOMP-over-61616 bridge to ActiveMQ Artemis (or any STOMP broker)."""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any
from urllib.parse import urlparse

import stomp
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/jms", tags=["jms"])

# ── Models ────────────────────────────────────────────────────────────────────


class JmsSendInput(BaseModel):
    broker_url: str  # stomp://host:port or stomp+ssl://host:port
    queue: str  # destination name, e.g. "orders.new"
    message: str  # message body (string / JSON string)
    headers: dict[str, str] = {}
    username: str = "admin"
    password: str = "admin"


class JmsSendOutput(BaseModel):
    status: str
    destination: str


class JmsReceiveInput(BaseModel):
    broker_url: str
    queue: str
    max_messages: int = 10
    timeout_ms: int = 5000
    username: str = "admin"
    password: str = "admin"


class JmsMessage(BaseModel):
    body: str
    headers: dict[str, Any] = {}


class JmsReceiveOutput(BaseModel):
    status: str
    messages: list[JmsMessage] = []
    count: int = 0
    error: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_url(broker_url: str) -> tuple[str, int]:
    """Return (host, port) from stomp://host:port or plain host:port."""
    if "://" in broker_url:
        parsed = urlparse(broker_url)
        return parsed.hostname or "127.0.0.1", parsed.port or 61616
    parts = broker_url.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 61616
    return host, port


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/send", response_model=JmsSendOutput)
async def jms_send(body: JmsSendInput) -> JmsSendOutput:
    host, port = _parse_url(body.broker_url)
    destination = f"/queue/{body.queue}"

    # Content-type hint; persistent:true ensures durable delivery to ANYCAST queues
    # even when no subscriber is active at send time.
    headers: dict[str, str] = {
        "content-type": "application/json",
        "persistent": "true",
    }
    headers.update(body.headers)

    errors: list[str] = []

    class _ErrListener(stomp.ConnectionListener):
        def on_error(self, frame: stomp.utils.Frame) -> None:
            errors.append(frame.body)

    conn = stomp.Connection([(host, port)])
    conn.set_listener("", _ErrListener())
    conn.connect(body.username, body.password, wait=True)
    try:
        conn.send(destination, body.message, headers=headers)
        if errors:
            raise RuntimeError(errors[0])
    finally:
        conn.disconnect()

    return JmsSendOutput(status="sent", destination=destination)


@router.post("/receive", response_model=JmsReceiveOutput)
async def jms_receive(body: JmsReceiveInput) -> JmsReceiveOutput:
    host, port = _parse_url(body.broker_url)
    destination = f"/queue/{body.queue}"
    timeout_s = body.timeout_ms / 1000.0

    msg_queue: queue.Queue[JmsMessage] = queue.Queue()
    errors: list[str] = []

    class _Listener(stomp.ConnectionListener):
        def on_message(self, frame: stomp.utils.Frame) -> None:
            msg_queue.put(JmsMessage(body=frame.body, headers=dict(frame.headers)))

        def on_error(self, frame: stomp.utils.Frame) -> None:
            errors.append(frame.body)

    conn = stomp.Connection([(host, port)])
    conn.set_listener("", _Listener())
    conn.connect(body.username, body.password, wait=True)
    conn.subscribe(destination, id=1, ack="auto")

    deadline = time.monotonic() + timeout_s
    collected: list[JmsMessage] = []

    try:
        while len(collected) < body.max_messages:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                msg = msg_queue.get(timeout=min(remaining, 0.2))
                collected.append(msg)
            except queue.Empty:
                pass
    finally:
        conn.disconnect()

    if errors:
        return JmsReceiveOutput(status="error", error=errors[0])

    return JmsReceiveOutput(status="ok", messages=collected, count=len(collected))
