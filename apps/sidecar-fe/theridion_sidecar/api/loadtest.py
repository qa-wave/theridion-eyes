"""Load testing endpoint.

Fires concurrent HTTP requests using asyncio + httpx, collects latency
stats, and returns a summary with percentiles.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/loadtest", tags=["loadtest"])


class LoadTestRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    concurrency: int = Field(default=10, ge=1, le=500)
    duration_seconds: float = Field(default=10.0, gt=0, le=300)
    rps_limit: float | None = None


class LoadTestResult(BaseModel):
    total_requests: int
    successful: int
    failed: int
    error_count: int
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    actual_rps: float
    duration_seconds: float
    errors: dict[str, int] = Field(default_factory=dict)


async def _worker(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None,
    deadline: float,
    rps_delay: float | None,
    latencies: list[float],
    errors: list[str],
) -> None:
    """Single worker loop that fires requests until the deadline."""
    while time.monotonic() < deadline:
        start = time.perf_counter()
        try:
            await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body.encode("utf-8") if body else None,
            )
            latencies.append((time.perf_counter() - start) * 1000)
        except httpx.RequestError as exc:
            latencies.append((time.perf_counter() - start) * 1000)
            errors.append(type(exc).__name__)
        if rps_delay:
            await asyncio.sleep(rps_delay)


@router.post("/run", response_model=LoadTestResult)
async def run_loadtest(req: LoadTestRequest) -> LoadTestResult:
    rps_delay: float | None = None
    if req.rps_limit and req.rps_limit > 0:
        # Spread the delay across workers
        rps_delay = req.concurrency / req.rps_limit

    latencies: list[float] = []
    errors: list[str] = []

    deadline = time.monotonic() + req.duration_seconds
    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        tasks = [
            asyncio.create_task(
                _worker(
                    client, req.method, req.url, req.headers,
                    req.body, deadline, rps_delay, latencies, errors,
                )
            )
            for _ in range(req.concurrency)
        ]
        await asyncio.gather(*tasks)

    actual_duration = time.perf_counter() - started
    total = len(latencies)

    if total == 0:
        return LoadTestResult(
            total_requests=0,
            successful=0,
            failed=0,
            error_count=0,
            avg_latency_ms=0,
            min_latency_ms=0,
            max_latency_ms=0,
            p50_ms=0,
            p95_ms=0,
            p99_ms=0,
            actual_rps=0,
            duration_seconds=round(actual_duration, 2),
        )

    sorted_lat = sorted(latencies)
    error_count = len(errors)
    error_summary: dict[str, int] = {}
    for e in errors:
        error_summary[e] = error_summary.get(e, 0) + 1

    return LoadTestResult(
        total_requests=total,
        successful=total - error_count,
        failed=error_count,
        error_count=error_count,
        avg_latency_ms=round(statistics.mean(sorted_lat), 2),
        min_latency_ms=round(sorted_lat[0], 2),
        max_latency_ms=round(sorted_lat[-1], 2),
        p50_ms=round(_percentile(sorted_lat, 50), 2),
        p95_ms=round(_percentile(sorted_lat, 95), 2),
        p99_ms=round(_percentile(sorted_lat, 99), 2),
        actual_rps=round(total / actual_duration, 2) if actual_duration > 0 else 0,
        duration_seconds=round(actual_duration, 2),
        errors=error_summary,
    )


def _percentile(sorted_data: list[float], p: float) -> float:
    """Calculate the p-th percentile from pre-sorted data."""
    if not sorted_data:
        return 0
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])
