"""Connection stats — measure connection reuse over N requests."""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class ConnectionStatsRequest(BaseModel):
    url: str = Field(..., min_length=1)
    num_requests: int = Field(default=10, ge=1, le=200)
    headers: dict[str, str] = Field(default_factory=dict)


class ConnectionStatsResult(BaseModel):
    total_requests: int
    connections_opened: int
    reuse_rate: float
    avg_latency_ms: float


@router.post("/connection-stats", response_model=ConnectionStatsResult)
async def connection_stats(req: ConnectionStatsRequest) -> ConnectionStatsResult:
    latencies: list[float] = []
    connection_ids: set[int] = set()

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for _ in range(req.num_requests):
                start = time.perf_counter()
                resp = await client.get(req.url, headers=req.headers)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)

                # Track unique stream IDs as proxy for connections
                stream = resp.stream
                if stream is not None:
                    connection_ids.add(id(stream))
                else:
                    connection_ids.add(id(resp))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Request failed: {exc}") from exc

    total = len(latencies)
    connections = max(1, len(connection_ids))
    reuse = round(1 - (connections / total), 4) if total > 0 else 0.0
    avg_lat = round(sum(latencies) / total, 2) if total > 0 else 0.0

    return ConnectionStatsResult(
        total_requests=total,
        connections_opened=connections,
        reuse_rate=reuse,
        avg_latency_ms=avg_lat,
    )
