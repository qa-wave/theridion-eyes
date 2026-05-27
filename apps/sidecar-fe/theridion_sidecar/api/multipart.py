"""Multipart/form-data request execution endpoint.

Accepts form fields (key/value pairs and base64-encoded file content)
and sends them as a multipart/form-data request via httpx.
"""

from __future__ import annotations

import base64
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments
from ..models import AuthConfig
from .requests import ExecuteResponse, TimingBreakdown, _apply_auth

router = APIRouter(prefix="/api/requests", tags=["requests"])

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


class FormField(BaseModel):
    """A single form field — either a text value or a file (base64)."""

    key: str
    value: str = ""
    # When is_file=True, value holds base64-encoded content.
    is_file: bool = False
    filename: str | None = None
    content_type: str | None = None


class ExecuteMultipartRequest(BaseModel):
    method: HttpMethod = "POST"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    fields: list[FormField] = Field(default_factory=list)
    auth: AuthConfig | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    follow_redirects: bool = True
    environment_id: str | None = None


@router.post("/execute-multipart", response_model=ExecuteResponse)
async def execute_multipart(req: ExecuteMultipartRequest) -> ExecuteResponse:
    env = environments.get(req.environment_id) if req.environment_id else None
    if req.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")

    resolved_url = environments.substitute(req.url, env)
    resolved_headers = environments.substitute_dict(req.headers, env)
    resolved_query = environments.substitute_dict(req.query, env)

    if req.auth and req.auth.type != "none":
        _apply_auth(req.auth, resolved_headers, resolved_query, env)

    # Build multipart files list for httpx.
    files: list[tuple[str, tuple[str | None, bytes, str]]] = []
    data: dict[str, str] = {}

    for field in req.fields:
        key = environments.substitute(field.key, env)
        if field.is_file:
            raw = base64.b64decode(field.value)
            fname = field.filename or "upload"
            ct = field.content_type or "application/octet-stream"
            files.append((key, (fname, raw, ct)))
        else:
            val = environments.substitute(field.value, env)
            data[key] = val

    started = time.perf_counter()
    try:
        transport = httpx.AsyncHTTPTransport(http2=True)
        async with httpx.AsyncClient(
            transport=transport,
            timeout=req.timeout_seconds,
            follow_redirects=req.follow_redirects,
        ) as client:
            response = await client.request(
                method=req.method,
                url=resolved_url,
                headers=resolved_headers,
                params=resolved_query or None,
                data=data if data else None,
                files=files if files else None,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"transport error: {exc}") from exc

    finished = time.perf_counter()
    elapsed_ms = (finished - started) * 1000

    timing = TimingBreakdown(total_ms=round(elapsed_ms, 2))

    return ExecuteResponse(
        status=response.status_code,
        status_text=response.reason_phrase or "",
        headers=dict(response.headers),
        body=response.text,
        body_size_bytes=len(response.content),
        elapsed_ms=round(elapsed_ms, 2),
        timing=timing,
        final_url=str(response.url),
        resolved_url=resolved_url if env is not None else None,
    )
