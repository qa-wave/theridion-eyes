"""User simulation — each virtual user has own httpx client with cookies."""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/loadtest", tags=["loadtest"])


class UserSimulationRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    num_users: int = Field(default=5, ge=1, le=100)
    duration_s: float = Field(default=10.0, gt=0, le=300)
    think_time_ms: int = Field(default=0, ge=0, le=10000)


class UserStats(BaseModel):
    user_id: int
    requests: int
    avg_latency_ms: float
    errors: int


class UserSimulationResult(BaseModel):
    total_requests: int
    total_errors: int
    avg_latency_ms: float
    duration_seconds: float
    per_user: list[UserStats]


async def _user_loop(
    user_id: int, req: UserSimulationRequest, deadline: float,
    stats: UserStats,
) -> None:
    latencies: list[float] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        while time.monotonic() < deadline:
            start = time.perf_counter()
            try:
                await client.request(
                    method=req.method, url=req.url, headers=req.headers,
                    content=req.body.encode() if req.body else None,
                )
                latencies.append((time.perf_counter() - start) * 1000)
            except httpx.RequestError:
                latencies.append((time.perf_counter() - start) * 1000)
                stats.errors += 1
            if req.think_time_ms > 0:
                await asyncio.sleep(req.think_time_ms / 1000)

    stats.requests = len(latencies)
    stats.avg_latency_ms = round(statistics.mean(latencies), 2) if latencies else 0


@router.post("/simulate-users", response_model=UserSimulationResult)
async def simulate_users(req: UserSimulationRequest) -> UserSimulationResult:
    deadline = time.monotonic() + req.duration_s
    started = time.perf_counter()

    user_stats = [
        UserStats(user_id=i, requests=0, avg_latency_ms=0, errors=0)
        for i in range(req.num_users)
    ]
    tasks = [
        asyncio.create_task(_user_loop(i, req, deadline, user_stats[i]))
        for i in range(req.num_users)
    ]
    await asyncio.gather(*tasks)

    actual_duration = time.perf_counter() - started
    total_requests = sum(u.requests for u in user_stats)
    total_errors = sum(u.errors for u in user_stats)
    all_avg = (
        round(sum(u.avg_latency_ms * u.requests for u in user_stats) / total_requests, 2)
        if total_requests > 0 else 0
    )

    return UserSimulationResult(
        total_requests=total_requests,
        total_errors=total_errors,
        avg_latency_ms=all_avg,
        duration_seconds=round(actual_duration, 2),
        per_user=user_stats,
    )
