"""Error pattern analysis — cluster errors by type, detect bursts."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class ErrorEntry(BaseModel):
    timestamp: float
    url: str
    status: int
    error: str | None = None


class ErrorPatternsRequest(BaseModel):
    entries: list[ErrorEntry] = Field(..., min_length=1)


class PatternResult(BaseModel):
    type: str
    count: int
    urls: list[str]
    first_seen: float
    last_seen: float
    burst: bool


class ErrorPatternsResult(BaseModel):
    patterns: list[PatternResult]
    total_errors: int
    error_rate: float


@router.post("/error-patterns", response_model=ErrorPatternsResult)
async def error_patterns(req: ErrorPatternsRequest) -> ErrorPatternsResult:
    # Only look at errors (status >= 400 or has error text)
    error_entries = [
        e for e in req.entries
        if e.status >= 400 or e.error
    ]

    # Group by error type
    groups: dict[str, list[ErrorEntry]] = defaultdict(list)
    for entry in error_entries:
        key = entry.error if entry.error else f"HTTP {entry.status}"
        groups[key].append(entry)

    patterns: list[PatternResult] = []
    for error_type, entries in groups.items():
        timestamps = sorted(e.timestamp for e in entries)
        urls = list({e.url for e in entries})[:10]

        # Detect burst: if more than 5 errors within 10 seconds
        burst = False
        if len(timestamps) >= 5:
            for i in range(len(timestamps) - 4):
                if timestamps[i + 4] - timestamps[i] <= 10:
                    burst = True
                    break

        patterns.append(PatternResult(
            type=error_type,
            count=len(entries),
            urls=urls,
            first_seen=timestamps[0] if timestamps else 0,
            last_seen=timestamps[-1] if timestamps else 0,
            burst=burst,
        ))

    total_errors = len(error_entries)
    error_rate = (
        total_errors / len(req.entries) * 100
        if req.entries else 0
    )

    return ErrorPatternsResult(
        patterns=sorted(patterns, key=lambda p: p.count, reverse=True),
        total_errors=total_errors,
        error_rate=round(error_rate, 2),
    )
