"""Performance Budget monitoring — define response time and size budgets per
endpoint and get alerts when they're exceeded.

Storage: ~/.theridion/perf_budgets.json (budgets)
         ~/.theridion/perf_violations.json (recent violations, capped at 50)
"""

from __future__ import annotations

import fnmatch
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from theridion_sidecar import storage

router = APIRouter(prefix="/api/perf", tags=["perf-budget"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Budget(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    url_pattern: str
    method: str | None = None
    max_time_ms: int
    max_size_bytes: int | None = None
    p95_time_ms: int | None = None
    alert_threshold: int = 3
    name: str = ""


class BudgetCreate(BaseModel):
    url_pattern: str
    method: str | None = None
    max_time_ms: int
    max_size_bytes: int | None = None
    p95_time_ms: int | None = None
    alert_threshold: int = 3
    name: str = ""


class BudgetUpdate(BaseModel):
    url_pattern: str | None = None
    method: str | None = None
    max_time_ms: int | None = None
    max_size_bytes: int | None = None
    p95_time_ms: int | None = None
    alert_threshold: int | None = None
    name: str | None = None


class CheckInput(BaseModel):
    url: str
    method: str | None = None
    elapsed_ms: float
    body_size: int | None = None


class Violation(BaseModel):
    budget_id: str
    budget_name: str
    metric: str
    actual: float
    threshold: float
    exceeded_by_percent: float
    url: str
    method: str | None = None
    timestamp: float = Field(default_factory=time.time)


class CheckOutput(BaseModel):
    violations: list[Violation] = Field(default_factory=list)
    passed: list[str] = Field(default_factory=list)


class AutoBudgetInput(BaseModel):
    """Input for auto-budget generation from history data."""

    history: list[dict[str, Any]] = Field(default_factory=list)
    multiplier: float = 1.5


class AutoBudgetOutput(BaseModel):
    suggested: list[Budget] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

_BUDGETS_FILE = "perf_budgets.json"
_VIOLATIONS_FILE = "perf_violations.json"
_MAX_VIOLATIONS = 50


def _budgets_path() -> Path:
    return storage.home_dir() / _BUDGETS_FILE


def _violations_path() -> Path:
    return storage.home_dir() / _VIOLATIONS_FILE


def _load_budgets() -> list[Budget]:
    p = _budgets_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [Budget(**b) for b in data]
    except (json.JSONDecodeError, TypeError):
        return []


def _save_budgets(budgets: list[Budget]) -> None:
    p = _budgets_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps([b.model_dump() for b in budgets], indent=2),
        encoding="utf-8",
    )


def _load_violations() -> list[Violation]:
    p = _violations_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [Violation(**v) for v in data]
    except (json.JSONDecodeError, TypeError):
        return []


def _save_violations(violations: list[Violation]) -> None:
    p = _violations_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Keep only last N
    trimmed = violations[-_MAX_VIOLATIONS:]
    p.write_text(
        json.dumps([v.model_dump() for v in trimmed], indent=2),
        encoding="utf-8",
    )


def _matches(pattern: str, url: str) -> bool:
    """Check if url matches a glob or regex pattern."""
    # Try regex first (patterns starting with ^ or containing unescaped regex chars)
    if pattern.startswith("^") or pattern.startswith("(?"):
        try:
            return bool(re.search(pattern, url))
        except re.error:
            pass
    # Fallback to glob matching
    return fnmatch.fnmatch(url, pattern)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/budgets")
async def list_budgets() -> list[Budget]:
    return _load_budgets()


@router.post("/budgets", status_code=201)
async def create_budget(body: BudgetCreate) -> Budget:
    budgets = _load_budgets()
    budget = Budget(**body.model_dump())
    budgets.append(budget)
    _save_budgets(budgets)
    return budget


@router.put("/budgets/{budget_id}")
async def update_budget(budget_id: str, body: BudgetUpdate) -> Budget:
    budgets = _load_budgets()
    for i, b in enumerate(budgets):
        if b.id == budget_id:
            updates = body.model_dump(exclude_none=True)
            merged = b.model_dump()
            merged.update(updates)
            budgets[i] = Budget(**merged)
            _save_budgets(budgets)
            return budgets[i]
    raise HTTPException(status_code=404, detail="Budget not found")


@router.delete("/budgets/{budget_id}", status_code=204)
async def delete_budget(budget_id: str) -> None:
    budgets = _load_budgets()
    new_budgets = [b for b in budgets if b.id != budget_id]
    if len(new_budgets) == len(budgets):
        raise HTTPException(status_code=404, detail="Budget not found")
    _save_budgets(new_budgets)


@router.post("/check")
async def check_budget(body: CheckInput) -> CheckOutput:
    budgets = _load_budgets()
    violations: list[Violation] = []
    passed: list[str] = []

    for budget in budgets:
        # Check if URL matches
        if not _matches(budget.url_pattern, body.url):
            continue
        # Check method filter
        if budget.method and body.method and budget.method.upper() != body.method.upper():
            continue

        violated = False

        # Check max_time_ms
        if body.elapsed_ms > budget.max_time_ms:
            exceeded = ((body.elapsed_ms - budget.max_time_ms) / budget.max_time_ms) * 100
            v = Violation(
                budget_id=budget.id,
                budget_name=budget.name or budget.url_pattern,
                metric="max_time_ms",
                actual=body.elapsed_ms,
                threshold=float(budget.max_time_ms),
                exceeded_by_percent=round(exceeded, 1),
                url=body.url,
                method=body.method,
            )
            violations.append(v)
            violated = True

        # Check p95_time_ms
        if budget.p95_time_ms and body.elapsed_ms > budget.p95_time_ms:
            exceeded = ((body.elapsed_ms - budget.p95_time_ms) / budget.p95_time_ms) * 100
            v = Violation(
                budget_id=budget.id,
                budget_name=budget.name or budget.url_pattern,
                metric="p95_time_ms",
                actual=body.elapsed_ms,
                threshold=float(budget.p95_time_ms),
                exceeded_by_percent=round(exceeded, 1),
                url=body.url,
                method=body.method,
            )
            violations.append(v)
            violated = True

        # Check max_size_bytes
        if budget.max_size_bytes and body.body_size is not None:
            if body.body_size > budget.max_size_bytes:
                exceeded = ((body.body_size - budget.max_size_bytes) / budget.max_size_bytes) * 100
                v = Violation(
                    budget_id=budget.id,
                    budget_name=budget.name or budget.url_pattern,
                    metric="max_size_bytes",
                    actual=float(body.body_size),
                    threshold=float(budget.max_size_bytes),
                    exceeded_by_percent=round(exceeded, 1),
                    url=body.url,
                    method=body.method,
                )
                violations.append(v)
                violated = True

        if not violated:
            passed.append(budget.id)

    # Persist violations
    if violations:
        existing = _load_violations()
        existing.extend(violations)
        _save_violations(existing)

    return CheckOutput(violations=violations, passed=passed)


@router.get("/violations")
async def get_violations() -> list[Violation]:
    return _load_violations()


@router.post("/auto-budget")
async def auto_budget(body: AutoBudgetInput) -> AutoBudgetOutput:
    """Auto-generate budgets from response history.

    Expects history as list of dicts with keys: url, method, elapsed_ms, body_size.
    Groups by (url, method), computes p95 response time, suggests budget at multiplier * p95.
    """
    if not body.history:
        return AutoBudgetOutput(suggested=[])

    # Group by URL+method
    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for entry in body.history:
        url = entry.get("url", "")
        method = entry.get("method")
        key = (url, method)
        groups.setdefault(key, []).append(entry)

    suggested: list[Budget] = []
    for (url, method), entries in groups.items():
        times = sorted(e.get("elapsed_ms", 0) for e in entries if e.get("elapsed_ms"))
        if not times:
            continue
        # p95
        idx = int(len(times) * 0.95)
        idx = min(idx, len(times) - 1)
        p95 = times[idx]
        max_time = int(p95 * body.multiplier)

        # Size p95
        sizes = sorted(e.get("body_size", 0) for e in entries if e.get("body_size"))
        max_size = None
        if sizes:
            size_idx = int(len(sizes) * 0.95)
            size_idx = min(size_idx, len(sizes) - 1)
            max_size = int(sizes[size_idx] * body.multiplier)

        budget = Budget(
            url_pattern=url,
            method=method,
            max_time_ms=max_time,
            max_size_bytes=max_size,
            p95_time_ms=int(p95),
            name=f"Auto: {method or 'ANY'} {url}",
        )
        suggested.append(budget)

    return AutoBudgetOutput(suggested=suggested)
