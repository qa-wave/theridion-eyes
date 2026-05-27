"""MQTT client endpoints — publish, subscribe, list retained messages."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

import paho.mqtt.client as paho
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/mqtt", tags=["mqtt"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class MqttPublishInput(BaseModel):
    broker: str = Field(default="127.0.0.1")
    port: int = Field(default=1883)
    topic: str = Field(..., min_length=1)
    payload: str = Field(default="")
    qos: int = Field(default=0, ge=0, le=2)
    retain: bool = Field(default=False)


class MqttPublishOutput(BaseModel):
    ok: bool
    topic: str
    qos: int
    retain: bool
    mid: int | None = None


class MqttSubscribeInput(BaseModel):
    broker: str = Field(default="127.0.0.1")
    port: int = Field(default=1883)
    topic: str = Field(..., min_length=1)
    qos: int = Field(default=0, ge=0, le=2)
    max_messages: int = Field(default=10, ge=1, le=200)
    timeout_seconds: float = Field(default=5.0, gt=0, le=60)


class MqttMessage(BaseModel):
    topic: str
    payload: str
    qos: int
    retain: bool


class MqttSubscribeOutput(BaseModel):
    messages: list[MqttMessage]
    count: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_messages(
    broker: str,
    port: int,
    topic: str,
    qos: int,
    max_messages: int,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    """Blocking helper — connects, subscribes, collects up to max_messages."""
    collected: list[dict[str, Any]] = []
    msg_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    connect_event = threading.Event()
    error_holder: list[str] = []

    def on_connect(client: paho.Client, userdata: Any, flags: Any, rc: int, props: Any = None) -> None:  # noqa: ARG001
        if rc == 0:
            client.subscribe(topic, qos=qos)
            connect_event.set()
        else:
            error_holder.append(f"CONNACK rc={rc}")
            connect_event.set()

    def on_message(client: paho.Client, userdata: Any, message: paho.MQTTMessage) -> None:  # noqa: ARG001
        msg_queue.put({
            "topic": message.topic,
            "payload": message.payload.decode("utf-8", errors="replace"),
            "qos": message.qos,
            "retain": bool(message.retain),
        })

    client = paho.Client(
        callback_api_version=paho.CallbackAPIVersion.VERSION2,
        client_id=f"theridion-sub-{int(time.time() * 1000)}",
        clean_session=True,
    )
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(broker, port, keepalive=10)
    client.loop_start()

    # Wait for connection / subscription
    connect_event.wait(timeout=5.0)
    if error_holder:
        client.loop_stop()
        client.disconnect()
        raise RuntimeError(error_holder[0])

    deadline = time.monotonic() + timeout_seconds
    while len(collected) < max_messages and time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        try:
            msg = msg_queue.get(timeout=remaining)
            collected.append(msg)
        except queue.Empty:
            break

    client.loop_stop()
    client.disconnect()
    return collected


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/publish", response_model=MqttPublishOutput)
async def mqtt_publish(body: MqttPublishInput) -> MqttPublishOutput:
    """Publish a single MQTT message and wait for broker acknowledgement."""
    import asyncio

    loop = asyncio.get_event_loop()

    def _publish() -> tuple[bool, int | None]:
        publish_event = threading.Event()
        result_holder: list[Any] = [True, None]
        error_holder: list[str] = []

        def on_connect(client: paho.Client, userdata: Any, flags: Any, rc: int, props: Any = None) -> None:  # noqa: ARG001
            if rc == 0:
                info = client.publish(
                    body.topic,
                    payload=body.payload.encode("utf-8"),
                    qos=body.qos,
                    retain=body.retain,
                )
                result_holder[1] = info.mid
                if body.qos == 0:
                    publish_event.set()
            else:
                error_holder.append(f"CONNACK rc={rc}")
                publish_event.set()

        def on_publish(client: paho.Client, userdata: Any, mid: int, *args: Any) -> None:  # noqa: ARG001
            publish_event.set()

        client = paho.Client(
            callback_api_version=paho.CallbackAPIVersion.VERSION2,
            client_id=f"theridion-pub-{int(time.time() * 1000)}",
            clean_session=True,
        )
        client.on_connect = on_connect
        client.on_publish = on_publish

        client.connect(body.broker, body.port, keepalive=10)
        client.loop_start()
        publish_event.wait(timeout=10.0)
        client.loop_stop()
        client.disconnect()

        if error_holder:
            raise RuntimeError(error_holder[0])
        return bool(result_holder[0]), result_holder[1]

    try:
        ok, mid = await loop.run_in_executor(None, _publish)
        return MqttPublishOutput(
            ok=ok,
            topic=body.topic,
            qos=body.qos,
            retain=body.retain,
            mid=mid,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MQTT publish error: {e}") from e


@router.post("/subscribe", response_model=MqttSubscribeOutput)
async def mqtt_subscribe(body: MqttSubscribeInput) -> MqttSubscribeOutput:
    """Subscribe to a topic and collect up to max_messages within timeout."""
    import asyncio

    loop = asyncio.get_event_loop()

    def _sub() -> list[dict[str, Any]]:
        return _collect_messages(
            broker=body.broker,
            port=body.port,
            topic=body.topic,
            qos=body.qos,
            max_messages=body.max_messages,
            timeout_seconds=body.timeout_seconds,
        )

    try:
        msgs = await loop.run_in_executor(None, _sub)
        return MqttSubscribeOutput(
            messages=[MqttMessage(**m) for m in msgs],
            count=len(msgs),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MQTT subscribe error: {e}") from e
