"""Redirect chain tracer — follow redirects manually and record each hop."""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class RedirectChainRequest(BaseModel):
    url: str = Field(..., min_length=1)
    max_hops: int = Field(default=20, ge=1, le=50)
    headers: dict[str, str] = Field(default_factory=dict)


class HopEntry(BaseModel):
    status: int
    url: str
    elapsed_ms: float
    headers: dict[str, str]


class RedirectChainResult(BaseModel):
    hops: list[HopEntry]
    total_hops: int
    total_ms: float


@router.post("/redirect-chain", response_model=RedirectChainResult)
async def redirect_chain(req: RedirectChainRequest) -> RedirectChainResult:
    hops: list[HopEntry] = []
    current_url = req.url
    total_start = time.perf_counter()

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            for _ in range(req.max_hops):
                start = time.perf_counter()
                resp = await client.get(current_url, headers=req.headers)
                elapsed = (time.perf_counter() - start) * 1000

                resp_headers = dict(resp.headers)
                hops.append(HopEntry(
                    status=resp.status_code,
                    url=current_url,
                    elapsed_ms=round(elapsed, 2),
                    headers=resp_headers,
                ))

                if resp.status_code not in (301, 302, 303, 307, 308):
                    break

                location = resp.headers.get("location")
                if not location:
                    break
                # Handle relative redirects
                current_url = str(resp.url.join(location))
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Request failed: {exc}") from exc

    total_ms = (time.perf_counter() - total_start) * 1000
    return RedirectChainResult(
        hops=hops,
        total_hops=len(hops),
        total_ms=round(total_ms, 2),
    )
