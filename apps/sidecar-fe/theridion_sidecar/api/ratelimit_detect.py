"""Rate limit detection — send requests until 429."""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/test", tags=["test"])


class RateLimitRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    max_requests: int = Field(default=100, ge=1, le=1000)


class RateLimitResult(BaseModel):
    limit: int | None = None
    window_seconds: int | None = None
    requests_sent: int
    first_429_at: int | None = None
    headers_found: dict[str, str]


@router.post("/ratelimit", response_model=RateLimitResult)
async def ratelimit_detect(req: RateLimitRequest) -> RateLimitResult:
    first_429_at: int | None = None
    headers_found: dict[str, str] = {}
    requests_sent = 0

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for i in range(req.max_requests):
            try:
                resp = await client.request(
                    method=req.method, url=req.url, headers=req.headers,
                )
                requests_sent += 1

                if resp.status_code == 429:
                    first_429_at = i + 1
                    # Capture rate limit headers
                    for hdr in resp.headers:
                        lower = hdr.lower()
                        if lower.startswith("x-ratelimit") or lower == "retry-after":
                            headers_found[hdr] = resp.headers[hdr]
                    break
            except httpx.RequestError:
                requests_sent += 1
                break

    limit: int | None = None
    window: int | None = None
    for k, v in headers_found.items():
        kl = k.lower()
        if kl in ("x-ratelimit-limit", "x-rate-limit-limit"):
            try:
                limit = int(v)
            except ValueError:
                pass
        if kl in ("x-ratelimit-reset", "x-rate-limit-reset", "retry-after"):
            try:
                window = int(v)
            except ValueError:
                pass

    return RateLimitResult(
        limit=limit,
        window_seconds=window,
        requests_sent=requests_sent,
        first_429_at=first_429_at,
        headers_found=headers_found,
    )
