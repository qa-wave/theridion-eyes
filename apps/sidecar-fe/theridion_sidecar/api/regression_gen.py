"""Regression test suite generator — auto-generate assertions from current API behavior."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import storage
from ..environments import get as get_env, substitute

router = APIRouter(prefix="/api/test", tags=["regression"])


class GenerateInput(BaseModel):
    environment_id: str | None = None


class GeneratedAssertion(BaseModel):
    type: str
    expected: str
    path: str = ""
    operator: str = "eq"


class RequestAssertions(BaseModel):
    request_id: str
    request_name: str
    assertions: list[GeneratedAssertion] = Field(default_factory=list)


class RegressionOutput(BaseModel):
    collection_name: str
    total_assertions: int = 0
    requests_processed: int = 0
    request_assertions: list[RequestAssertions] = Field(default_factory=list)


def _flatten_requests(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("is_folder"):
            out.extend(_flatten_requests(item.get("items", [])))
        else:
            out.append(item)
    return out


def _generate_assertions(status: int, body: str, content_type: str, elapsed_ms: float) -> list[GeneratedAssertion]:
    """Generate baseline assertions from a successful response."""
    assertions: list[GeneratedAssertion] = []

    # Status code match
    assertions.append(GeneratedAssertion(
        type="status",
        expected=str(status),
        operator="eq",
    ))

    # Content-Type match
    if content_type:
        assertions.append(GeneratedAssertion(
            type="header_equals",
            expected=content_type.split(";")[0].strip(),
            path="content-type",
            operator="contains",
        ))

    # Response time within 2x current
    max_time = max(int(elapsed_ms * 2), 1000)
    assertions.append(GeneratedAssertion(
        type="response_time",
        expected=str(max_time),
        operator="lt",
    ))

    # JSON structure assertions
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            for key in list(data.keys())[:20]:
                assertions.append(GeneratedAssertion(
                    type="json_path",
                    expected="exists",
                    path=f"$.{key}",
                    operator="exists",
                ))
                if isinstance(data[key], list):
                    assertions.append(GeneratedAssertion(
                        type="json_path",
                        expected=str(len(data[key])),
                        path=f"$.{key}.length()",
                        operator="gte",
                    ))
        elif isinstance(data, list):
            assertions.append(GeneratedAssertion(
                type="body_contains",
                expected="[",
                operator="contains",
            ))
    except (json.JSONDecodeError, ValueError):
        pass

    return assertions


@router.post("/generate-regression/{collection_id}", response_model=RegressionOutput)
async def generate_regression(collection_id: str, body: GenerateInput) -> RegressionOutput:
    coll = storage.get(collection_id)
    if coll is None:
        return RegressionOutput(collection_name="unknown")

    env = get_env(body.environment_id) if body.environment_id else None

    items = _flatten_requests([it.model_dump() for it in coll.items])
    result_assertions: list[RequestAssertions] = []
    total = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for item in items:
            url = substitute(item.get("url", ""), env)
            method = item.get("method", "GET")
            name = item.get("name", url)
            req_id = item.get("id", "")
            if not url:
                continue

            try:
                headers_raw = item.get("headers", {})
                if isinstance(headers_raw, str):
                    try:
                        headers_raw = json.loads(headers_raw)
                    except Exception:
                        headers_raw = {}
                headers_sub = {k: substitute(str(v), env) for k, v in headers_raw.items()}
                start = time.monotonic()
                resp = await client.request(method, url, headers=headers_sub, timeout=15)
                elapsed = (time.monotonic() - start) * 1000
            except Exception:
                continue

            if resp.status_code >= 400:
                continue

            content_type = resp.headers.get("content-type", "")
            assertions = _generate_assertions(resp.status_code, resp.text, content_type, elapsed)

            if assertions:
                result_assertions.append(RequestAssertions(
                    request_id=req_id,
                    request_name=name,
                    assertions=assertions,
                ))
                total += len(assertions)

    return RegressionOutput(
        collection_name=coll.name,
        total_assertions=total,
        requests_processed=len(result_assertions),
        request_assertions=result_assertions,
    )
