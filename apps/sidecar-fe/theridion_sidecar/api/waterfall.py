"""Waterfall timing — approximate request phases from httpx."""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class WaterfallRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None


class WaterfallPhase(BaseModel):
    name: str
    start_ms: float
    duration_ms: float


class WaterfallResult(BaseModel):
    phases: list[WaterfallPhase]
    total_ms: float
    url: str


@router.post("/waterfall", response_model=WaterfallResult)
async def waterfall(req: WaterfallRequest) -> WaterfallResult:
    try:
        start = time.perf_counter()
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.request(
                method=req.method, url=req.url, headers=req.headers,
                content=req.body.encode() if req.body else None,
            )
        total = (time.perf_counter() - start) * 1000

        # httpx doesn't expose per-phase timing directly, so we approximate
        # using the elapsed attribute and reasonable estimates
        elapsed_ms = resp.elapsed.total_seconds() * 1000 if resp.elapsed else total

        # Approximate phase breakdown
        dns_est = min(elapsed_ms * 0.1, 50)
        connect_est = min(elapsed_ms * 0.15, 100)
        tls_est = min(elapsed_ms * 0.2, 150) if req.url.startswith("https") else 0
        remaining = elapsed_ms - dns_est - connect_est - tls_est
        ttfb_est = max(remaining * 0.7, 0)
        download_est = max(remaining * 0.3, 0)

        cursor = 0.0
        phases: list[WaterfallPhase] = []

        phases.append(WaterfallPhase(name="dns", start_ms=round(cursor, 2), duration_ms=round(dns_est, 2)))
        cursor += dns_est

        phases.append(WaterfallPhase(name="connect", start_ms=round(cursor, 2), duration_ms=round(connect_est, 2)))
        cursor += connect_est

        if tls_est > 0:
            phases.append(WaterfallPhase(name="tls", start_ms=round(cursor, 2), duration_ms=round(tls_est, 2)))
            cursor += tls_est

        phases.append(WaterfallPhase(name="ttfb", start_ms=round(cursor, 2), duration_ms=round(ttfb_est, 2)))
        cursor += ttfb_est

        phases.append(WaterfallPhase(name="download", start_ms=round(cursor, 2), duration_ms=round(download_est, 2)))

        return WaterfallResult(
            phases=phases,
            total_ms=round(total, 2),
            url=req.url,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
