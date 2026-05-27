"""Idempotency check — send same request twice, compare results."""

from __future__ import annotations

import hashlib

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/test", tags=["test"])


class IdempotencyRequest(BaseModel):
    url: str = Field(..., min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None


class ResponseSnapshot(BaseModel):
    status: int
    body_hash: str


class IdempotencyResult(BaseModel):
    first: ResponseSnapshot
    second: ResponseSnapshot
    idempotent: bool
    differences: list[str]


@router.post("/idempotency", response_model=IdempotencyResult)
async def idempotency_check(req: IdempotencyRequest) -> IdempotencyResult:
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            content = req.body.encode() if req.body else None
            r1 = await client.request(method=req.method, url=req.url,
                                       headers=req.headers, content=content)
            r2 = await client.request(method=req.method, url=req.url,
                                       headers=req.headers, content=content)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    h1 = hashlib.sha256(r1.content).hexdigest()[:16]
    h2 = hashlib.sha256(r2.content).hexdigest()[:16]

    differences: list[str] = []
    if r1.status_code != r2.status_code:
        differences.append(f"status: {r1.status_code} vs {r2.status_code}")
    if h1 != h2:
        differences.append("body content differs")

    return IdempotencyResult(
        first=ResponseSnapshot(status=r1.status_code, body_hash=h1),
        second=ResponseSnapshot(status=r2.status_code, body_hash=h2),
        idempotent=len(differences) == 0,
        differences=differences,
    )
