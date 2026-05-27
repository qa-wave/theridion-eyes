"""Load testing with ramp patterns — linear, step, spike, soak."""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/loadtest", tags=["loadtest"])


class PatternLoadTestRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    ramp_pattern: Literal["linear", "step", "spike", "soak"] = "linear"
    max_concurrency: int = Field(default=10, ge=1, le=500)
    duration_seconds: float = Field(default=10.0, gt=0, le=300)


class PhaseResult(BaseModel):
    name: str
    concurrency: int
    duration_s: float
    rps: float


class PatternLoadTestResult(BaseModel):
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
    pattern: str
    phases: list[PhaseResult]


def _percentile(sorted_data: list[float], p: float) -> float:
    if not sorted_data:
        return 0
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])


def _plan_phases(
    pattern: str, max_conc: int, duration: float,
) -> list[tuple[str, int, float]]:
    """Return list of (name, concurrency, phase_duration)."""
    if pattern == "step":
        steps = min(4, max_conc)
        per_step = duration / steps
        return [
            (f"step-{i+1}", max(1, max_conc * (i + 1) // steps), per_step)
            for i in range(steps)
        ]
    if pattern == "spike":
        ramp = duration * 0.3
        spike = duration * 0.2
        cool = duration * 0.5
        return [
            ("ramp", max(1, max_conc // 2), ramp),
            ("spike", max_conc, spike),
            ("cooldown", max(1, max_conc // 4), cool),
        ]
    if pattern == "soak":
        return [("soak", max_conc, duration)]
    # linear
    steps = min(5, max_conc)
    per_step = duration / steps
    return [
        (f"ramp-{i+1}", max(1, max_conc * (i + 1) // steps), per_step)
        for i in range(steps)
    ]


async def _fire(
    client: httpx.AsyncClient, method: str, url: str,
    headers: dict[str, str], body: str | None,
    deadline: float, latencies: list[float], errors: list[str],
) -> None:
    while time.monotonic() < deadline:
        start = time.perf_counter()
        try:
            await client.request(method=method, url=url, headers=headers,
                                 content=body.encode() if body else None)
            latencies.append((time.perf_counter() - start) * 1000)
        except httpx.RequestError as exc:
            latencies.append((time.perf_counter() - start) * 1000)
            errors.append(type(exc).__name__)


@router.post("/run-pattern", response_model=PatternLoadTestResult)
async def run_pattern_loadtest(req: PatternLoadTestRequest) -> PatternLoadTestResult:
    phases_plan = _plan_phases(req.ramp_pattern, req.max_concurrency, req.duration_seconds)
    all_latencies: list[float] = []
    all_errors: list[str] = []
    phase_results: list[PhaseResult] = []
    total_start = time.perf_counter()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for name, conc, dur in phases_plan:
            phase_lat: list[float] = []
            phase_err: list[str] = []
            deadline = time.monotonic() + dur
            tasks = [
                asyncio.create_task(
                    _fire(client, req.method, req.url, req.headers, req.body,
                          deadline, phase_lat, phase_err)
                )
                for _ in range(conc)
            ]
            await asyncio.gather(*tasks)
            all_latencies.extend(phase_lat)
            all_errors.extend(phase_err)
            rps = len(phase_lat) / dur if dur > 0 else 0
            phase_results.append(PhaseResult(
                name=name, concurrency=conc,
                duration_s=round(dur, 2), rps=round(rps, 2),
            ))

    actual_duration = time.perf_counter() - total_start
    total = len(all_latencies)
    error_count = len(all_errors)
    error_summary: dict[str, int] = {}
    for e in all_errors:
        error_summary[e] = error_summary.get(e, 0) + 1

    if total == 0:
        return PatternLoadTestResult(
            total_requests=0, successful=0, failed=0, error_count=0,
            avg_latency_ms=0, min_latency_ms=0, max_latency_ms=0,
            p50_ms=0, p95_ms=0, p99_ms=0, actual_rps=0,
            duration_seconds=round(actual_duration, 2),
            pattern=req.ramp_pattern, phases=phase_results,
        )

    sorted_lat = sorted(all_latencies)
    return PatternLoadTestResult(
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
        pattern=req.ramp_pattern,
        phases=phase_results,
    )
