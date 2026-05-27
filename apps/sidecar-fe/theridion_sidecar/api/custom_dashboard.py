"""Custom dashboard — compute metrics from request data."""

from __future__ import annotations

import re
import statistics
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class MetricFilter(BaseModel):
    status_gte: int | None = None
    status_lt: int | None = None
    url_pattern: str | None = None


class MetricDefinition(BaseModel):
    name: str
    type: Literal["avg", "count", "p95", "max", "min", "sum"]
    field: Literal["elapsed_ms", "status", "body_size"]
    filter: MetricFilter | None = None


class DataPoint(BaseModel):
    elapsed_ms: float = 0
    status: int = 200
    body_size: int = 0
    url: str = ""
    timestamp: float = 0


class DashboardRequest(BaseModel):
    metrics: list[MetricDefinition] = Field(..., min_length=1)
    data: list[DataPoint] = Field(default_factory=list)


class MetricResult(BaseModel):
    name: str
    value: float


class DashboardResult(BaseModel):
    results: list[MetricResult]


def _filter_data(data: list[DataPoint], f: MetricFilter | None) -> list[DataPoint]:
    if not f:
        return data
    result = data
    if f.status_gte is not None:
        result = [d for d in result if d.status >= f.status_gte]
    if f.status_lt is not None:
        result = [d for d in result if d.status < f.status_lt]
    if f.url_pattern:
        try:
            pattern = re.compile(f.url_pattern)
            result = [d for d in result if pattern.search(d.url)]
        except re.error:
            pass
    return result


def _percentile(sorted_data: list[float], p: float) -> float:
    if not sorted_data:
        return 0
    k = (len(sorted_data) - 1) * (p / 100)
    f_idx = int(k)
    c = f_idx + 1
    if c >= len(sorted_data):
        return sorted_data[f_idx]
    d = k - f_idx
    return sorted_data[f_idx] + d * (sorted_data[c] - sorted_data[f_idx])


@router.post("/compute", response_model=DashboardResult)
async def compute_dashboard(req: DashboardRequest) -> DashboardResult:
    results: list[MetricResult] = []

    for metric in req.metrics:
        filtered = _filter_data(req.data, metric.filter)
        values = [getattr(d, metric.field) for d in filtered]

        if not values:
            results.append(MetricResult(name=metric.name, value=0))
            continue

        if metric.type == "avg":
            v = statistics.mean(values)
        elif metric.type == "count":
            v = float(len(values))
        elif metric.type == "p95":
            v = _percentile(sorted(values), 95)
        elif metric.type == "max":
            v = float(max(values))
        elif metric.type == "min":
            v = float(min(values))
        elif metric.type == "sum":
            v = float(sum(values))
        else:
            v = 0

        results.append(MetricResult(name=metric.name, value=round(v, 4)))

    return DashboardResult(results=results)
