"""AI-powered test generation via Ollama (local) or cloud LLMs.

Endpoints:
- GET  /api/ai/settings — current AI config
- PUT  /api/ai/settings — update AI config
- GET  /api/ai/ping — test Ollama connection
- GET  /api/ai/models — list available Ollama models
- POST /api/ai/testgen — generate assertions from request+response
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import settings as settings_store
from ..assertions import Assertion

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ---- Settings CRUD -------------------------------------------------------

@router.get("/settings", response_model=settings_store.AISettings)
def get_ai_settings() -> settings_store.AISettings:
    return settings_store.load().ai


@router.put("/settings", response_model=settings_store.AISettings)
def update_ai_settings(body: settings_store.AISettings) -> settings_store.AISettings:
    s = settings_store.load()
    s.ai = body
    settings_store.save(s)
    return s.ai


# ---- Ollama connectivity --------------------------------------------------

@router.get("/ping")
async def ping_ollama() -> dict[str, Any]:
    ai = settings_store.load().ai
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{ai.ollama_base_url}/api/version")
            return {"ok": True, "version": r.json().get("version", "unknown")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/models")
async def list_models() -> dict[str, Any]:
    ai = settings_store.load().ai
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{ai.ollama_base_url}/api/tags")
            models = r.json().get("models", [])
            return {
                "models": [
                    {"name": m["name"], "size": m.get("size", 0)}
                    for m in models
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}") from e


# ---- AI test generation ---------------------------------------------------

class TestGenInput(BaseModel):
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    request_body: str | None = None
    response_status: int = 200
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: str = ""
    category: str = "smoke"  # smoke, health, regression, edge


class TestGenOutput(BaseModel):
    assertions: list[Assertion]
    explanation: str = ""


PROMPT_TEMPLATE = """You are an API testing expert. Analyze this HTTP request and response, then generate test assertions.

REQUEST:
{method} {url}
Headers: {req_headers}
Body: {req_body}

RESPONSE:
Status: {status}
Headers: {resp_headers}
Body (first 2000 chars): {resp_body}

Test category: {category}

Generate a JSON array of assertion objects. Each assertion has:
- "type": one of "status", "response_time", "json_path", "header_exists", "header_equals", "body_contains", "body_regex"
- "expected": the expected value (string)
- "path": for json_path/header types, the path/header name
- "operator": for json_path: "eq", "neq", "gt", "lt", "gte", "lte", "contains", "exists"

For "{category}" tests, generate {count} relevant assertions.

Respond with ONLY valid JSON array, no markdown, no explanation outside the array.
"""

CATEGORY_COUNTS = {"health": 3, "smoke": 5, "regression": 8, "edge": 6}


@router.post("/testgen", response_model=TestGenOutput)
async def generate_tests(body: TestGenInput) -> TestGenOutput:
    ai = settings_store.load().ai

    prompt = PROMPT_TEMPLATE.format(
        method=body.method,
        url=body.url,
        req_headers=json.dumps(body.headers)[:500],
        req_body=(body.request_body or "")[:1000],
        status=body.response_status,
        resp_headers=json.dumps(body.response_headers)[:500],
        resp_body=body.response_body[:2000],
        category=body.category,
        count=CATEGORY_COUNTS.get(body.category, 5),
    )

    if ai.provider == "ollama":
        assertions, explanation = await _call_ollama(ai, prompt)
    else:
        raise HTTPException(status_code=501, detail=f"Provider '{ai.provider}' not yet implemented — use Ollama")

    return TestGenOutput(assertions=assertions, explanation=explanation)


# ---- Heuristic "smart" assertion generator (no LLM needed) ---------------

class SmartSuggestInput(BaseModel):
    method: str = "GET"
    url: str = ""
    status: int = 200
    response_body: str = ""
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_time_ms: float | None = None


class SmartSuggestOutput(BaseModel):
    assertions: list[Assertion]


@router.post("/suggest-from-response", response_model=SmartSuggestOutput)
async def suggest_from_response(body: SmartSuggestInput) -> SmartSuggestOutput:
    """Generate smart assertions purely from heuristics — no Ollama needed."""
    assertions: list[Assertion] = []

    # 1. Always: status code assertion.
    assertions.append(Assertion(
        type="status", expected=str(body.status),
    ))

    # 2. Content-Type header.
    ct = body.response_headers.get("content-type") or body.response_headers.get("Content-Type")
    if ct:
        assertions.append(Assertion(
            type="header_equals", expected=ct.split(";")[0].strip(),
            path="content-type",
        ))

    # 3. Rate-limit headers.
    for hdr in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"):
        val = None
        for k in body.response_headers:
            if k.lower() == hdr:
                val = k
                break
        if val:
            assertions.append(Assertion(
                type="header_exists", path=val,
            ))

    # 4. Cache-Control header.
    for k in body.response_headers:
        if k.lower() == "cache-control":
            assertions.append(Assertion(
                type="header_exists", path=k,
            ))
            break

    # 5. JSON body heuristics.
    parsed = None
    try:
        parsed = json.loads(body.response_body)
    except (json.JSONDecodeError, ValueError):
        pass

    if parsed is not None:
        if isinstance(parsed, dict):
            # Check top-level keys exist.
            for key in list(parsed.keys())[:10]:
                assertions.append(Assertion(
                    type="json_path", path=key, operator="exists",
                ))
        elif isinstance(parsed, list):
            # Array non-empty check.
            assertions.append(Assertion(
                type="body_regex", expected=r"^\[.+\]$",
            ))
            # First item key checks.
            if parsed and isinstance(parsed[0], dict):
                for key in list(parsed[0].keys())[:5]:
                    assertions.append(Assertion(
                        type="json_path", path=f"0.{key}", operator="exists",
                    ))

    # 6. Response time — 2x actual (if provided).
    if body.response_time_ms is not None and body.response_time_ms > 0:
        limit = round(body.response_time_ms * 2)
        assertions.append(Assertion(
            type="response_time", expected=str(limit),
        ))

    return SmartSuggestOutput(assertions=assertions)


async def _call_ollama(ai: settings_store.AISettings, prompt: str) -> tuple[list[Assertion], str]:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{ai.ollama_base_url}/api/generate",
                json={
                    "model": ai.ollama_model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                },
            )
        result = r.json()
        response_text = result.get("response", "")

        # Parse the JSON response.
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON array from response.
            import re
            match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
            else:
                return [], f"Could not parse LLM response: {response_text[:200]}"

        # Normalize — could be array or object with array.
        if isinstance(parsed, dict):
            parsed = parsed.get("assertions", parsed.get("tests", []))
        if not isinstance(parsed, list):
            return [], f"Unexpected response format: {type(parsed)}"

        assertions = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                assertions.append(Assertion(
                    type=item.get("type", "status"),
                    expected=str(item.get("expected", "")),
                    path=str(item.get("path", "")),
                    operator=str(item.get("operator", "eq")),
                ))
            except Exception:
                continue

        return assertions, f"Generated {len(assertions)} assertions via {ai.ollama_model}"

    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot connect to Ollama at {ai.ollama_base_url}. Is it running?",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}") from e
