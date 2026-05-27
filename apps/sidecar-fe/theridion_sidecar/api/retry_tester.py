"""Retry tester — send request N times with delay to test recovery."""

from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/test", tags=["test"])


class RetryTestRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    attempts: int = Field(default=3, ge=1, le=50)
    delay_ms: int = Field(default=1000, ge=0, le=30000)
    expected_recovery_after: int = Field(default=1, ge=1)


class AttemptResult(BaseModel):
    attempt: int
    status: int | None = None
    elapsed_ms: float
    error: str | None = None


class RetryTestResult(BaseModel):
    attempts: list[AttemptResult]
    recovered: bool
    recovered_at: int | None = None


@router.post("/retry", response_model=RetryTestResult)
async def retry_test(req: RetryTestRequest) -> RetryTestResult:
    results: list[AttemptResult] = []
    recovered = False
    recovered_at: int | None = None

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for i in range(req.attempts):
            if i > 0 and req.delay_ms > 0:
                await asyncio.sleep(req.delay_ms / 1000)

            start = time.perf_counter()
            try:
                resp = await client.request(
                    method=req.method, url=req.url, headers=req.headers,
                    content=req.body.encode() if req.body else None,
                )
                elapsed = (time.perf_counter() - start) * 1000
                results.append(AttemptResult(
                    attempt=i + 1, status=resp.status_code,
                    elapsed_ms=round(elapsed, 2),
                ))
                if not recovered and resp.status_code < 400:
                    recovered = True
                    recovered_at = i + 1
            except httpx.RequestError as exc:
                elapsed = (time.perf_counter() - start) * 1000
                results.append(AttemptResult(
                    attempt=i + 1, elapsed_ms=round(elapsed, 2),
                    error=str(exc),
                ))

    return RetryTestResult(
        attempts=results, recovered=recovered, recovered_at=recovered_at,
    )
