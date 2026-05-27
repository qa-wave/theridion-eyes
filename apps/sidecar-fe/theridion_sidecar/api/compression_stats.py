"""Compression analysis — compare wire vs decoded body size."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class CompressionRequest(BaseModel):
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)


class CompressionResult(BaseModel):
    encoding: str | None
    wire_size: int
    decoded_size: int
    ratio: float
    compressed: bool


@router.post("/compression", response_model=CompressionResult)
async def compression_stats(req: CompressionRequest) -> CompressionResult:
    headers = {**req.headers, "Accept-Encoding": "gzip, deflate, br"}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(req.url, headers=headers)

        encoding = resp.headers.get("content-encoding")
        content_length = resp.headers.get("content-length")
        decoded_body = resp.content
        decoded_size = len(decoded_body)

        wire_size = int(content_length) if content_length else decoded_size
        ratio = round(wire_size / decoded_size, 4) if decoded_size > 0 else 1.0
        compressed = encoding is not None and encoding.lower() in ("gzip", "deflate", "br", "zstd")

        return CompressionResult(
            encoding=encoding,
            wire_size=wire_size,
            decoded_size=decoded_size,
            ratio=ratio,
            compressed=compressed,
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Request failed: {exc}") from exc
