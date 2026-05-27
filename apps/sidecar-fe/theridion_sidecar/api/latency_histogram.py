"""Latency histogram — compute histogram buckets from latency values."""

from __future__ import annotations

import math
import statistics

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class LatencyHistogramRequest(BaseModel):
    latency_ms: list[float] = Field(..., min_length=1)
    buckets: int = Field(default=10, ge=2, le=100)


class HistogramBucket(BaseModel):
    min: float
    max: float
    count: int


class LatencyHistogramResult(BaseModel):
    buckets: list[HistogramBucket]
    total: int
    mean: float
    stddev: float


@router.post("/latency-histogram", response_model=LatencyHistogramResult)
async def latency_histogram(req: LatencyHistogramRequest) -> LatencyHistogramResult:
    data = req.latency_ms
    total = len(data)
    lo = min(data)
    hi = max(data)
    mean = statistics.mean(data)
    stddev = statistics.stdev(data) if total > 1 else 0.0

    width = (hi - lo) / req.buckets if hi > lo else 1.0
    bucket_list: list[HistogramBucket] = []
    for i in range(req.buckets):
        b_min = lo + i * width
        b_max = lo + (i + 1) * width
        count = sum(1 for v in data if b_min <= v < b_max) if i < req.buckets - 1 else sum(1 for v in data if b_min <= v <= b_max)
        bucket_list.append(HistogramBucket(min=round(b_min, 2), max=round(b_max, 2), count=count))

    return LatencyHistogramResult(
        buckets=bucket_list,
        total=total,
        mean=round(mean, 2),
        stddev=round(stddev, 2),
    )
