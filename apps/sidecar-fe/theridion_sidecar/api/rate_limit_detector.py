"""Rate limit detector — analyze response headers for rate limiting info."""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from email.utils import parsedate_to_datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ratelimit", tags=["ratelimit"])

# In-memory tracking store: url_hash -> list of tracking entries
_tracking_store: dict[str, list[dict]] = defaultdict(list)
MAX_HISTORY = 100


class AnalyzeInput(BaseModel):
    headers: dict[str, str] = Field(..., description="Response headers to analyze")


class AnalyzeOutput(BaseModel):
    detected: bool = False
    limit: int | None = None
    remaining: int | None = None
    reset_at: str | None = None
    reset_seconds: int | None = None
    retry_after: int | None = None
    policy: str | None = None
    provider: str | None = None
    percentage_used: float | None = None
    headers_found: list[str] = Field(default_factory=list)


class TrackInput(BaseModel):
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)


class TrackOutput(BaseModel):
    url_hash: str
    tracked: bool


class StatusEntry(BaseModel):
    url_hash: str
    url: str
    limit: int | None = None
    remaining: int | None = None
    reset_seconds: int | None = None
    percentage_used: float | None = None
    last_seen: float


class StatusOutput(BaseModel):
    entries: list[StatusEntry]


class HistoryPoint(BaseModel):
    timestamp: float
    limit: int | None = None
    remaining: int | None = None
    percentage_used: float | None = None


class HistoryOutput(BaseModel):
    url_hash: str
    points: list[HistoryPoint]


# Header pattern groups (case-insensitive matching)
_LIMIT_HEADERS = [
    "x-ratelimit-limit",
    "ratelimit-limit",
    "x-rate-limit-limit",
]

_REMAINING_HEADERS = [
    "x-ratelimit-remaining",
    "ratelimit-remaining",
    "x-rate-limit-remaining",
]

_RESET_HEADERS = [
    "x-ratelimit-reset",
    "ratelimit-reset",
    "x-rate-limit-reset",
]

_POLICY_HEADERS = [
    "x-ratelimit-policy",
    "ratelimit-policy",
]

# Known provider patterns based on header combinations
_PROVIDER_PATTERNS: dict[str, list[str]] = {
    "GitHub": ["x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"],
    "Twitter/X": ["x-rate-limit-limit", "x-rate-limit-remaining", "x-rate-limit-reset"],
    "IETF Standard": ["ratelimit-limit", "ratelimit-remaining", "ratelimit-reset"],
}


def _normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Normalize header keys to lowercase for matching."""
    return {k.lower(): v for k, v in headers.items()}


def _parse_reset(value: str) -> tuple[str | None, int | None]:
    """Parse reset value. Returns (reset_at ISO string, reset_seconds)."""
    # Try as unix timestamp
    try:
        ts = int(value)
        now = int(time.time())
        if ts > now:
            # It's a unix timestamp in the future
            from datetime import datetime, timezone
            reset_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            reset_seconds = ts - now
            return reset_at, reset_seconds
        else:
            # Might be seconds remaining (common with some APIs)
            return None, ts
    except ValueError:
        pass

    # Try as HTTP-date
    try:
        dt = parsedate_to_datetime(value)
        reset_at = dt.isoformat()
        reset_seconds = max(0, int(dt.timestamp() - time.time()))
        return reset_at, reset_seconds
    except (ValueError, TypeError):
        pass

    return None, None


def _parse_retry_after(value: str) -> int | None:
    """Parse Retry-After header (seconds or HTTP-date)."""
    # Try as integer seconds
    try:
        return int(value)
    except ValueError:
        pass

    # Try as HTTP-date
    try:
        dt = parsedate_to_datetime(value)
        return max(0, int(dt.timestamp() - time.time()))
    except (ValueError, TypeError):
        pass

    return None


def _detect_provider(lower_headers: dict[str, str]) -> str | None:
    """Detect API provider based on header patterns."""
    header_keys = set(lower_headers.keys())
    for provider, patterns in _PROVIDER_PATTERNS.items():
        if all(p in header_keys for p in patterns):
            return provider
    return None


def _url_hash(url: str) -> str:
    """Create a short hash for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def _analyze_headers(headers: dict[str, str]) -> AnalyzeOutput:
    """Core analysis logic used by both analyze and track endpoints."""
    lower = _normalize_headers(headers)
    headers_found: list[str] = []

    limit: int | None = None
    remaining: int | None = None
    reset_at: str | None = None
    reset_seconds: int | None = None
    retry_after: int | None = None
    policy: str | None = None

    # Find limit
    for h in _LIMIT_HEADERS:
        if h in lower:
            try:
                limit = int(lower[h])
                headers_found.append(h)
            except ValueError:
                # Some APIs use "100, 100;window=60" format
                try:
                    limit = int(lower[h].split(",")[0].strip())
                    headers_found.append(h)
                except ValueError:
                    pass
            break

    # Find remaining
    for h in _REMAINING_HEADERS:
        if h in lower:
            try:
                remaining = int(lower[h])
                headers_found.append(h)
            except ValueError:
                pass
            break

    # Find reset
    for h in _RESET_HEADERS:
        if h in lower:
            reset_at, reset_seconds = _parse_reset(lower[h])
            headers_found.append(h)
            break

    # Retry-After
    if "retry-after" in lower:
        retry_after = _parse_retry_after(lower["retry-after"])
        headers_found.append("retry-after")

    # Policy
    for h in _POLICY_HEADERS:
        if h in lower:
            policy = lower[h]
            headers_found.append(h)
            break

    # Detect provider
    provider = _detect_provider(lower)

    # Calculate percentage used
    percentage_used: float | None = None
    if limit is not None and remaining is not None and limit > 0:
        percentage_used = round(((limit - remaining) / limit) * 100, 1)

    detected = len(headers_found) > 0

    return AnalyzeOutput(
        detected=detected,
        limit=limit,
        remaining=remaining,
        reset_at=reset_at,
        reset_seconds=reset_seconds,
        retry_after=retry_after,
        policy=policy,
        provider=provider,
        percentage_used=percentage_used,
        headers_found=headers_found,
    )


@router.post("/analyze", response_model=AnalyzeOutput)
async def analyze_rate_limit(req: AnalyzeInput) -> AnalyzeOutput:
    """Analyze response headers for rate limit information."""
    return _analyze_headers(req.headers)


@router.post("/track", response_model=TrackOutput)
async def track_rate_limit(req: TrackInput) -> TrackOutput:
    """Track rate limit state for a URL over time."""
    url_hash = _url_hash(req.url)
    result = _analyze_headers(req.headers)

    entry = {
        "timestamp": time.time(),
        "url": req.url,
        "limit": result.limit,
        "remaining": result.remaining,
        "reset_seconds": result.reset_seconds,
        "percentage_used": result.percentage_used,
    }

    history = _tracking_store[url_hash]
    history.append(entry)
    if len(history) > MAX_HISTORY:
        _tracking_store[url_hash] = history[-MAX_HISTORY:]

    return TrackOutput(url_hash=url_hash, tracked=result.detected)


@router.get("/status", response_model=StatusOutput)
async def get_rate_limit_status() -> StatusOutput:
    """Get current rate limit status for all tracked URLs."""
    entries: list[StatusEntry] = []
    for url_hash, history in _tracking_store.items():
        if not history:
            continue
        latest = history[-1]
        entries.append(StatusEntry(
            url_hash=url_hash,
            url=latest["url"],
            limit=latest["limit"],
            remaining=latest["remaining"],
            reset_seconds=latest["reset_seconds"],
            percentage_used=latest["percentage_used"],
            last_seen=latest["timestamp"],
        ))
    # Sort by last_seen descending
    entries.sort(key=lambda e: e.last_seen, reverse=True)
    return StatusOutput(entries=entries)


@router.get("/history/{url_hash}", response_model=HistoryOutput)
async def get_rate_limit_history(url_hash: str) -> HistoryOutput:
    """Get rate limit usage history for a URL (last 100 data points)."""
    history = _tracking_store.get(url_hash, [])
    points = [
        HistoryPoint(
            timestamp=entry["timestamp"],
            limit=entry["limit"],
            remaining=entry["remaining"],
            percentage_used=entry["percentage_used"],
        )
        for entry in history
    ]
    return HistoryOutput(url_hash=url_hash, points=points)
