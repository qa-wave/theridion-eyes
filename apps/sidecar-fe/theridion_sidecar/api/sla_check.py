"""SLA check — evaluate latency/error rules against collected data."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class SlaRule(BaseModel):
    metric: Literal["p95", "p99", "p50", "avg", "max", "error_rate"]
    operator: Literal["lt", "gt", "lte", "gte"]
    value: float


class SlaCheckRequest(BaseModel):
    latencies: list[float] = Field(default_factory=list)
    error_count: int = 0
    total: int = 0
    rules: list[SlaRule] = Field(..., min_length=1)


class SlaRuleResult(BaseModel):
    rule: SlaRule
    actual: float
    passed: bool


class SlaCheckResult(BaseModel):
    passed: bool
    results: list[SlaRuleResult]


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


def _evaluate(op: str, actual: float, threshold: float) -> bool:
    if op == "lt":
        return actual < threshold
    if op == "gt":
        return actual > threshold
    if op == "lte":
        return actual <= threshold
    if op == "gte":
        return actual >= threshold
    return False


@router.post("/sla-check", response_model=SlaCheckResult)
async def sla_check(req: SlaCheckRequest) -> SlaCheckResult:
    sorted_lat = sorted(req.latencies) if req.latencies else []

    metrics: dict[str, float] = {
        "p50": _percentile(sorted_lat, 50),
        "p95": _percentile(sorted_lat, 95),
        "p99": _percentile(sorted_lat, 99),
        "avg": sum(sorted_lat) / len(sorted_lat) if sorted_lat else 0,
        "max": max(sorted_lat) if sorted_lat else 0,
        "error_rate": (req.error_count / req.total * 100) if req.total > 0 else 0,
    }

    results: list[SlaRuleResult] = []
    all_passed = True
    for rule in req.rules:
        actual = metrics.get(rule.metric, 0)
        passed = _evaluate(rule.operator, actual, rule.value)
        if not passed:
            all_passed = False
        results.append(SlaRuleResult(
            rule=rule,
            actual=round(actual, 4),
            passed=passed,
        ))

    return SlaCheckResult(passed=all_passed, results=results)
