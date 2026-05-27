"""Throughput timeline — aggregate request entries into 1-second windows."""

from __future__ import annotations

import statistics

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class TimelineEntry(BaseModel):
    timestamp: float
    latency_ms: float
    success: bool = True


class ThroughputTimelineRequest(BaseModel):
    entries: list[TimelineEntry] = Field(..., min_length=1)


class WindowResult(BaseModel):
    timestamp: float
    rps: int
    avg_latency: float
    error_count: int


class ThroughputTimelineResult(BaseModel):
    windows: list[WindowResult]


@router.post("/throughput-timeline", response_model=ThroughputTimelineResult)
async def throughput_timeline(req: ThroughputTimelineRequest) -> ThroughputTimelineResult:
    entries = sorted(req.entries, key=lambda e: e.timestamp)

    # Group into 1-second windows
    buckets: dict[int, list[TimelineEntry]] = {}
    for entry in entries:
        bucket_key = int(entry.timestamp)
        buckets.setdefault(bucket_key, []).append(entry)

    windows: list[WindowResult] = []
    for ts in sorted(buckets):
        bucket = buckets[ts]
        latencies = [e.latency_ms for e in bucket]
        error_count = sum(1 for e in bucket if not e.success)
        windows.append(WindowResult(
            timestamp=float(ts),
            rps=len(bucket),
            avg_latency=round(statistics.mean(latencies), 2),
            error_count=error_count,
        ))

    return ThroughputTimelineResult(windows=windows)
