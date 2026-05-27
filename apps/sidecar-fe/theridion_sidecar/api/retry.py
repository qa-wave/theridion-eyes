"""Configurable request retry with backoff strategies.

Wraps the normal execute flow with retry logic for transient errors
(429, 500, 502, 503, 504). Supports fixed, linear, exponential, and
jitter backoff strategies, plus Retry-After header respect.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .requests import ExecuteRequest, ExecuteResponse, execute

router = APIRouter(prefix="/api/requests", tags=["requests"])

BackoffStrategy = Literal["fixed", "linear", "exponential", "jitter"]


class RetryConfig(BaseModel):
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_on: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])
    backoff_strategy: BackoffStrategy = "exponential"
    backoff_base_ms: int = Field(default=1000, ge=0, le=60000)
    backoff_max_ms: int = Field(default=30000, ge=0, le=120000)


class ExecuteWithRetryRequest(ExecuteRequest):
    """Normal execute params plus retry configuration."""

    retry: RetryConfig = Field(default_factory=RetryConfig)


class AttemptInfo(BaseModel):
    attempt: int
    status: int
    elapsed_ms: float
    waited_ms: float


class ExecuteWithRetryResponse(BaseModel):
    final_response: ExecuteResponse
    attempts: list[AttemptInfo]
    total_elapsed_ms: float
    retried: bool


def compute_backoff_ms(
    strategy: BackoffStrategy,
    attempt: int,
    base_ms: int,
    max_ms: int,
) -> float:
    """Compute wait time in ms for the given attempt number (1-based)."""
    if strategy == "fixed":
        raw = base_ms
    elif strategy == "linear":
        raw = base_ms * attempt
    elif strategy == "exponential":
        raw = base_ms * (2 ** attempt)
    elif strategy == "jitter":
        raw = base_ms * (2 ** attempt) + random.uniform(0, base_ms)
    else:
        raw = base_ms
    return min(raw, max_ms)


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    """Extract Retry-After header value in milliseconds, if present."""
    val = headers.get("retry-after") or headers.get("Retry-After")
    if val is None:
        return None
    try:
        seconds = float(val)
        return seconds * 1000
    except ValueError:
        return None


@router.post("/execute-with-retry", response_model=ExecuteWithRetryResponse)
async def execute_with_retry(req: ExecuteWithRetryRequest) -> ExecuteWithRetryResponse:
    rc = req.retry
    attempts: list[AttemptInfo] = []
    total_start = time.perf_counter()

    # Build the base execute request (strip retry config).
    base_req = ExecuteRequest(
        method=req.method,
        url=req.url,
        headers=req.headers,
        query=req.query,
        body=req.body,
        auth=req.auth,
        timeout_seconds=req.timeout_seconds,
        follow_redirects=req.follow_redirects,
        environment_id=req.environment_id,
        collection_id=req.collection_id,
        client_cert=req.client_cert,
        client_key=req.client_key,
        ca_bundle_path=req.ca_bundle_path,
        verify_ssl=req.verify_ssl,
    )

    last_response: ExecuteResponse | None = None

    for attempt_num in range(1, rc.max_retries + 1):
        attempt_start = time.perf_counter()
        try:
            response = await execute(base_req)
        except HTTPException as exc:
            # Transport-level error from the execute function (502).
            # Treat as retryable if 502 is in retry_on list.
            elapsed = (time.perf_counter() - attempt_start) * 1000
            if exc.status_code in rc.retry_on and attempt_num < rc.max_retries:
                wait_ms = compute_backoff_ms(
                    rc.backoff_strategy, attempt_num, rc.backoff_base_ms, rc.backoff_max_ms,
                )
                attempts.append(AttemptInfo(
                    attempt=attempt_num, status=exc.status_code,
                    elapsed_ms=round(elapsed, 2), waited_ms=round(wait_ms, 2),
                ))
                await asyncio.sleep(wait_ms / 1000)
                continue
            # Final attempt or non-retryable transport error — re-raise.
            raise

        elapsed = (time.perf_counter() - attempt_start) * 1000
        last_response = response

        # Check if we should retry.
        if response.status not in rc.retry_on or attempt_num >= rc.max_retries:
            attempts.append(AttemptInfo(
                attempt=attempt_num, status=response.status,
                elapsed_ms=round(elapsed, 2), waited_ms=0,
            ))
            break

        # Determine wait time: Retry-After header takes priority.
        retry_after_ms = _parse_retry_after(response.headers)
        if retry_after_ms is not None:
            wait_ms = min(retry_after_ms, rc.backoff_max_ms)
        else:
            wait_ms = compute_backoff_ms(
                rc.backoff_strategy, attempt_num, rc.backoff_base_ms, rc.backoff_max_ms,
            )

        attempts.append(AttemptInfo(
            attempt=attempt_num, status=response.status,
            elapsed_ms=round(elapsed, 2), waited_ms=round(wait_ms, 2),
        ))
        await asyncio.sleep(wait_ms / 1000)

    total_elapsed = (time.perf_counter() - total_start) * 1000

    if last_response is None:
        raise HTTPException(status_code=502, detail="all retry attempts failed with transport errors")

    return ExecuteWithRetryResponse(
        final_response=last_response,
        attempts=attempts,
        total_elapsed_ms=round(total_elapsed, 2),
        retried=len(attempts) > 1,
    )
