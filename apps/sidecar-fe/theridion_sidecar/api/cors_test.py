"""CORS preflight test — send OPTIONS and analyze response."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/security", tags=["security"])


class CorsTestRequest(BaseModel):
    url: str = Field(..., min_length=1)
    origin: str = Field(default="https://example.com")


class CorsTestResult(BaseModel):
    allowed: bool
    allow_origin: str | None = None
    allow_methods: str | None = None
    allow_headers: str | None = None
    allow_credentials: str | None = None
    max_age: str | None = None
    issues: list[str]


@router.post("/cors-test", response_model=CorsTestResult)
async def cors_test(req: CorsTestRequest) -> CorsTestResult:
    issues: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.options(
                req.url,
                headers={
                    "Origin": req.origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Content-Type, Authorization",
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    headers = resp.headers
    acao = headers.get("access-control-allow-origin")
    acam = headers.get("access-control-allow-methods")
    acah = headers.get("access-control-allow-headers")
    acac = headers.get("access-control-allow-credentials")
    max_age = headers.get("access-control-max-age")

    allowed = acao is not None

    if not acao:
        issues.append("No Access-Control-Allow-Origin header — CORS not enabled")
    elif acao == "*":
        issues.append("Wildcard origin (*) — any site can make requests")
        if acac and acac.lower() == "true":
            issues.append("Credentials allowed with wildcard origin — security risk")
    elif acao != req.origin:
        issues.append(f"Origin {req.origin} not allowed (allowed: {acao})")
        allowed = False

    if not acam:
        issues.append("No Access-Control-Allow-Methods header")
    if not acah:
        issues.append("No Access-Control-Allow-Headers header")

    return CorsTestResult(
        allowed=allowed,
        allow_origin=acao,
        allow_methods=acam,
        allow_headers=acah,
        allow_credentials=acac,
        max_age=max_age,
        issues=issues,
    )
