"""Load test comparison — compute deltas between two runs."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class RunStats(BaseModel):
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    avg_latency_ms: float = 0
    min_latency_ms: float = 0
    max_latency_ms: float = 0
    p50_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    actual_rps: float = 0
    duration_seconds: float = 0


class CompareRunsRequest(BaseModel):
    left: RunStats
    right: RunStats


class MetricDelta(BaseModel):
    name: str
    left: float
    right: float
    delta: float
    delta_pct: float
    improved: bool


class CompareRunsResult(BaseModel):
    metrics: list[MetricDelta]


_LOWER_IS_BETTER = {"avg_latency_ms", "min_latency_ms", "max_latency_ms",
                     "p50_ms", "p95_ms", "p99_ms", "failed"}
_HIGHER_IS_BETTER = {"total_requests", "successful", "actual_rps"}


@router.post("/compare-runs", response_model=CompareRunsResult)
async def compare_runs(req: CompareRunsRequest) -> CompareRunsResult:
    fields = [
        "total_requests", "successful", "failed",
        "avg_latency_ms", "min_latency_ms", "max_latency_ms",
        "p50_ms", "p95_ms", "p99_ms", "actual_rps", "duration_seconds",
    ]
    metrics: list[MetricDelta] = []
    for name in fields:
        lv = getattr(req.left, name)
        rv = getattr(req.right, name)
        delta = rv - lv
        delta_pct = (delta / lv * 100) if lv != 0 else 0.0
        if name in _LOWER_IS_BETTER:
            improved = delta < 0
        elif name in _HIGHER_IS_BETTER:
            improved = delta > 0
        else:
            improved = delta >= 0
        metrics.append(MetricDelta(
            name=name,
            left=float(lv),
            right=float(rv),
            delta=round(delta, 4),
            delta_pct=round(delta_pct, 2),
            improved=improved,
        ))

    return CompareRunsResult(metrics=metrics)
