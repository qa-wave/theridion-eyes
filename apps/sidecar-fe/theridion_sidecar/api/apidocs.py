"""API Documentation viewer — parse and render OpenAPI specs."""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/apidocs", tags=["apidocs"])


class Endpoint(BaseModel):
    path: str
    method: str
    summary: str = ""
    description: str = ""
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ApiDoc(BaseModel):
    title: str = ""
    version: str = ""
    description: str = ""
    base_url: str = ""
    endpoints: list[Endpoint] = Field(default_factory=list)


class ParseInput(BaseModel):
    content: str | None = None
    url: str | None = None


@router.post("/parse", response_model=ApiDoc)
async def parse_spec(body: ParseInput) -> ApiDoc:
    raw = body.content
    if not raw and body.url:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(body.url)
                raw = r.text
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
    if not raw:
        raise HTTPException(status_code=400, detail="Provide content or url")

    try:
        spec = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import yaml
            spec = yaml.safe_load(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="Cannot parse as JSON or YAML")

    info = spec.get("info", {})
    servers = spec.get("servers", [])
    base = servers[0].get("url", "") if servers else ""

    endpoints: list[Endpoint] = []
    for path, methods in spec.get("paths", {}).items():
        for method, detail in methods.items():
            if method.startswith("x-") or method == "parameters":
                continue
            endpoints.append(Endpoint(
                path=path, method=method.upper(),
                summary=detail.get("summary", ""),
                description=detail.get("description", ""),
                parameters=detail.get("parameters", []),
                request_body=detail.get("requestBody"),
                responses=detail.get("responses", {}),
                tags=detail.get("tags", []),
            ))

    return ApiDoc(
        title=info.get("title", ""),
        version=info.get("version", ""),
        description=info.get("description", ""),
        base_url=base,
        endpoints=endpoints,
    )
