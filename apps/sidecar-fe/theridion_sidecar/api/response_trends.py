"""Response trends analysis — body size trend over snapshots."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from theridion_sidecar import storage

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class ResponseTrendsRequest(BaseModel):
    request_id: str = Field(..., min_length=1)
    max_snapshots: int = Field(default=50, ge=1, le=500)


class ResponseTrendsResult(BaseModel):
    sizes: list[int]
    timestamps: list[float]
    trend: Literal["growing", "stable", "shrinking"]


def _compute_trend(sizes: list[int]) -> Literal["growing", "stable", "shrinking"]:
    if len(sizes) < 2:
        return "stable"
    first_half = sizes[: len(sizes) // 2]
    second_half = sizes[len(sizes) // 2 :]
    avg_first = sum(first_half) / len(first_half)
    avg_second = sum(second_half) / len(second_half)
    if avg_second > avg_first * 1.1:
        return "growing"
    if avg_second < avg_first * 0.9:
        return "shrinking"
    return "stable"


@router.post("/response-trends", response_model=ResponseTrendsResult)
async def response_trends(req: ResponseTrendsRequest) -> ResponseTrendsResult:
    timeline_dir = storage.home_dir() / "timeline"
    timeline_file = timeline_dir / f"{req.request_id}.json"

    sizes: list[int] = []
    timestamps: list[float] = []

    if timeline_file.exists():
        import json

        data = json.loads(timeline_file.read_text(encoding="utf-8"))
        snapshots = data.get("snapshots", [])[-req.max_snapshots :]
        for snap in snapshots:
            sizes.append(snap.get("body_size", 0))
            timestamps.append(snap.get("timestamp", 0))

    return ResponseTrendsResult(
        sizes=sizes,
        timestamps=timestamps,
        trend=_compute_trend(sizes),
    )
