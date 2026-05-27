"""Kafka client endpoints — connect, list topics, produce, consume."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/kafka", tags=["kafka"])


class KafkaConnectInput(BaseModel):
    bootstrap_servers: str = Field(..., min_length=1)


class TopicInfo(BaseModel):
    name: str
    partitions: int


class TopicListOutput(BaseModel):
    topics: list[TopicInfo]


class ProduceInput(BaseModel):
    bootstrap_servers: str
    topic: str
    key: str | None = None
    value: str
    headers: dict[str, str] = Field(default_factory=dict)


class ProduceOutput(BaseModel):
    topic: str
    partition: int
    offset: int
    timestamp: int


class ConsumeInput(BaseModel):
    bootstrap_servers: str
    topic: str
    group_id: str | None = None
    max_messages: int = Field(default=10, ge=1, le=100)
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    auto_offset_reset: str = Field(default="latest", pattern="^(latest|earliest)$")


class ConsumedMessage(BaseModel):
    topic: str
    partition: int
    offset: int
    key: str | None
    value: str
    timestamp: int
    headers: dict[str, str]


class ConsumeOutput(BaseModel):
    messages: list[ConsumedMessage]
    count: int


@router.post("/topics", response_model=TopicListOutput)
async def list_topics(body: KafkaConnectInput) -> TopicListOutput:
    try:
        admin = AIOKafkaAdminClient(bootstrap_servers=body.bootstrap_servers)
        await admin.start()
        try:
            metadata = await admin.describe_cluster()
            topics_meta = await admin.list_topics()
            topics = []
            for name in sorted(topics_meta):
                if name.startswith("__"):
                    continue
                desc = await admin.describe_topics([name])
                partitions = len(desc[0].get("partitions", [])) if desc else 0
                topics.append(TopicInfo(name=name, partitions=partitions))
            return TopicListOutput(topics=topics)
        finally:
            await admin.close()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kafka error: {e}") from e


async def _produce_message(body: ProduceInput) -> ProduceOutput:
    """Internal helper: produce a Kafka message without HTTP error wrapping."""
    producer = AIOKafkaProducer(bootstrap_servers=body.bootstrap_servers)
    await producer.start()
    try:
        kafka_headers = [(k, v.encode("utf-8")) for k, v in body.headers.items()]
        result = await producer.send_and_wait(
            body.topic,
            key=body.key.encode("utf-8") if body.key else None,
            value=body.value.encode("utf-8"),
            headers=kafka_headers or None,
        )
        return ProduceOutput(
            topic=result.topic,
            partition=result.partition,
            offset=result.offset,
            timestamp=result.timestamp,
        )
    finally:
        await producer.stop()


@router.post("/produce", response_model=ProduceOutput)
async def produce(body: ProduceInput) -> ProduceOutput:
    try:
        return await _produce_message(body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kafka produce error: {e}") from e


@router.post("/consume", response_model=ConsumeOutput)
async def consume(body: ConsumeInput) -> ConsumeOutput:
    try:
        consumer = AIOKafkaConsumer(
            body.topic,
            bootstrap_servers=body.bootstrap_servers,
            group_id=body.group_id or f"theridion-{int(time.time())}",
            auto_offset_reset=body.auto_offset_reset,
            enable_auto_commit=False,
        )
        await consumer.start()
        try:
            messages: list[ConsumedMessage] = []
            deadline = time.time() + body.timeout_seconds
            while len(messages) < body.max_messages and time.time() < deadline:
                remaining = max(0.1, deadline - time.time())
                batch = await consumer.getmany(
                    timeout_ms=int(remaining * 1000),
                    max_records=body.max_messages - len(messages),
                )
                for tp, records in batch.items():
                    for record in records:
                        hdrs = {}
                        if record.headers:
                            for k, v in record.headers:
                                hdrs[k] = v.decode("utf-8", errors="replace") if v else ""
                        messages.append(ConsumedMessage(
                            topic=record.topic,
                            partition=record.partition,
                            offset=record.offset,
                            key=record.key.decode("utf-8", errors="replace") if record.key else None,
                            value=record.value.decode("utf-8", errors="replace") if record.value else "",
                            timestamp=record.timestamp,
                            headers=hdrs,
                        ))
                if not batch:
                    break
            return ConsumeOutput(messages=messages, count=len(messages))
        finally:
            await consumer.stop()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kafka consume error: {e}") from e
