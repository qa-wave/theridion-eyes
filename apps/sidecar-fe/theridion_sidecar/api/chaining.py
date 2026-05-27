"""Request chaining — response value capture via JSONPath / header / status.

This endpoint wraps the standard execute flow and adds a post-execution
capture step: after the response arrives, configured capture rules
extract values that can feed into subsequent requests.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments
from ..models import AuthConfig
from .requests import ExecuteResponse, TimingBreakdown, _apply_auth

router = APIRouter(prefix="/api/requests", tags=["requests"])


class CaptureRule(BaseModel):
    """A single capture rule applied after the response is received."""

    name: str = Field(..., min_length=1)
    source: Literal["body", "header", "status"] = "body"
    # For body: a simple dot-notation JSONPath (e.g. "data.token").
    # For header: the header name.
    # For status: unused.
    path: str = ""


class ExecuteWithCapturesRequest(BaseModel):
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    follow_redirects: bool = True
    environment_id: str | None = None
    captures: list[CaptureRule] = Field(default_factory=list)


class ExecuteWithCapturesResponse(BaseModel):
    status: int
    status_text: str
    headers: dict[str, str]
    body: str
    body_size_bytes: int
    elapsed_ms: float
    timing: TimingBreakdown | None = None
    final_url: str
    resolved_url: str | None = None
    captured_values: dict[str, str] = Field(default_factory=dict)


def _resolve_json_path(data: Any, path: str) -> str | None:
    """Resolve a simple dot-notation path, returning string or None."""
    if not path:
        return None
    current = data
    for part in path.split("."):
        bracket = re.match(r"^(\w+)\[(\d+)]$", part)
        if bracket:
            key, idx = bracket.group(1), int(bracket.group(2))
            if isinstance(current, dict) and key in current:
                current = current[key]
                if isinstance(current, list) and 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None
            else:
                return None
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return str(current)


@router.post("/execute-chain", response_model=ExecuteWithCapturesResponse)
async def execute_with_captures(req: ExecuteWithCapturesRequest) -> ExecuteWithCapturesResponse:
    env = environments.get(req.environment_id) if req.environment_id else None
    if req.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")

    resolved_url = environments.substitute(req.url, env)
    resolved_headers = environments.substitute_dict(req.headers, env)
    resolved_body = (
        environments.substitute(req.body, env) if req.body is not None else None
    )
    resolved_query = environments.substitute_dict(req.query, env)

    if req.auth and req.auth.type != "none":
        _apply_auth(req.auth, resolved_headers, resolved_query, env)

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
                content=resolved_body.encode("utf-8") if resolved_body is not None else None,
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"transport error: {exc}") from exc

    elapsed_ms = (time.perf_counter() - started) * 1000
    timing = TimingBreakdown(total_ms=round(elapsed_ms, 2))

    # Extract captured values
    captured: dict[str, str] = {}
    resp_headers = dict(response.headers)
    resp_body = response.text

    for rule in req.captures:
        if rule.source == "status":
            captured[rule.name] = str(response.status_code)
        elif rule.source == "header":
            # Case-insensitive header lookup
            key_lower = rule.path.lower()
            val = next(
                (v for k, v in resp_headers.items() if k.lower() == key_lower),
                "",
            )
            captured[rule.name] = val
        elif rule.source == "body":
            try:
                data = json.loads(resp_body)
                val = _resolve_json_path(data, rule.path)
                captured[rule.name] = val if val is not None else ""
            except (json.JSONDecodeError, ValueError):
                captured[rule.name] = ""

    return ExecuteWithCapturesResponse(
        status=response.status_code,
        status_text=response.reason_phrase or "",
        headers=resp_headers,
        body=resp_body,
        body_size_bytes=len(response.content),
        elapsed_ms=round(elapsed_ms, 2),
        timing=timing,
        final_url=str(response.url),
        resolved_url=resolved_url if env is not None else None,
        captured_values=captured,
    )


# ---- Standalone extraction (no HTTP call) ----------------------------------


class ExtractInput(BaseModel):
    """Extract values from an already-received response."""

    response_body: str = ""
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_status: int = 200
    rules: list[CaptureRule] = Field(default_factory=list)


class ExtractOutput(BaseModel):
    extracted: dict[str, str | None] = Field(default_factory=dict)


@router.post("/extract", response_model=ExtractOutput)
def extract_values(body: ExtractInput) -> ExtractOutput:
    """Apply capture rules to a response without executing a request.

    Useful for request chaining UI: the user sends a request, gets a
    response, then configures extractors against the live data.
    """
    extracted: dict[str, str | None] = {}
    for rule in body.rules:
        if rule.source == "status":
            extracted[rule.name] = str(body.response_status)
        elif rule.source == "header":
            key_lower = rule.path.lower()
            val = next(
                (v for k, v in body.response_headers.items() if k.lower() == key_lower),
                None,
            )
            extracted[rule.name] = val
        elif rule.source == "body":
            try:
                data = json.loads(body.response_body)
                val = _resolve_json_path(data, rule.path)
                extracted[rule.name] = val
            except (json.JSONDecodeError, ValueError):
                extracted[rule.name] = None
    return ExtractOutput(extracted=extracted)
