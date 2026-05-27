"""Request pipeline — define ordered sequences of requests with conditions,
delays, variable passing, and retry logic.

This is the Playwright-style test runner: a pipeline is a named sequence
of steps that references saved requests from collections. Each step can
extract values, apply conditions, introduce delays, and control failure
behaviour (stop / continue / retry).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments, storage
from ..models import AuthConfig
from .chaining import _resolve_json_path
from .requests import _apply_auth

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


# ---- Models ----------------------------------------------------------------


class Extractor(BaseModel):
    """Pull a value from a step's response into the pipeline variable bag."""

    name: str = Field(..., min_length=1)
    source: Literal["body", "header", "status"] = "body"
    path: str = ""


class PipelineStep(BaseModel):
    request_id: str
    collection_id: str
    delay_ms: int = Field(default=0, ge=0)
    condition: str | None = None
    extractors: list[Extractor] = Field(default_factory=list)
    on_fail: Literal["stop", "continue", "retry"] = "stop"
    retry_count: int = Field(default=1, ge=1, le=10)


class Pipeline(BaseModel):
    name: str = Field(..., min_length=1)
    steps: list[PipelineStep] = Field(..., min_length=1)
    variables: dict[str, str] = Field(default_factory=dict)
    environment_id: str | None = None


class StepResult(BaseModel):
    step_index: int
    request_id: str
    collection_id: str
    status: int | None = None
    elapsed_ms: float = 0
    passed: bool = False
    error: str | None = None
    captured: dict[str, str] = Field(default_factory=dict)
    attempts: int = 1
    skipped: bool = False


class PipelineResult(BaseModel):
    results: list[StepResult]
    total_ms: float
    passed: int
    failed: int
    variables: dict[str, str] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    step_index: int
    field: str
    message: str


class ValidateOutput(BaseModel):
    valid: bool
    issues: list[ValidationIssue]


class PipelineTemplate(BaseModel):
    name: str
    description: str
    steps: list[dict[str, Any]]


# ---- Condition evaluator ---------------------------------------------------


def _evaluate_condition(expr: str, variables: dict[str, str], last_status: int | None) -> bool:
    """Evaluate a simple condition expression.

    Supported forms:
      - ``status == 200``
      - ``status != 500``
      - ``variable.token != ""``
      - ``variable.count == "3"``

    Returns True when no expression is given.
    """
    if not expr or not expr.strip():
        return True

    expr = expr.strip()

    # status comparison
    m = re.match(r"^status\s*(==|!=|>=|<=|>|<)\s*(\d+)$", expr)
    if m:
        if last_status is None:
            return False
        op, val = m.group(1), int(m.group(2))
        if op == "==":
            return last_status == val
        if op == "!=":
            return last_status != val
        if op == ">=":
            return last_status >= val
        if op == "<=":
            return last_status <= val
        if op == ">":
            return last_status > val
        if op == "<":
            return last_status < val

    # variable comparison
    m = re.match(r'^variable\.(\w+)\s*(==|!=)\s*"(.*)"$', expr)
    if m:
        var_name, op, expected = m.group(1), m.group(2), m.group(3)
        actual = variables.get(var_name, "")
        if op == "==":
            return actual == expected
        return actual != expected

    # Unrecognised expression — fail closed
    return False


# ---- Request resolution + execution helper ---------------------------------


def _resolve_request(collection_id: str, request_id: str):
    """Find a request item from a collection. Returns (CollectionItem, Collection)."""
    try:
        col = storage.get(collection_id)
    except (ValueError, OSError):
        return None, None
    if col is None:
        return None, None

    def _find(items, rid):
        for item in items:
            if not item.is_folder and item.id == rid:
                return item
            if item.is_folder:
                found = _find(item.items, rid)
                if found is not None:
                    return found
        return None

    req = _find(col.items, request_id)
    return req, col


def _substitute(value: str, env, variables: dict[str, str]) -> str:
    """Apply environment + pipeline variable substitution."""
    result = environments.substitute(value, env, variables)
    return result


def _extract_values(
    extractors: list[Extractor],
    status: int,
    headers: dict[str, str],
    body: str,
) -> dict[str, str]:
    captured: dict[str, str] = {}
    for ext in extractors:
        if ext.source == "status":
            captured[ext.name] = str(status)
        elif ext.source == "header":
            key_lower = ext.path.lower()
            val = next(
                (v for k, v in headers.items() if k.lower() == key_lower),
                "",
            )
            captured[ext.name] = val
        elif ext.source == "body":
            try:
                data = json.loads(body)
                val = _resolve_json_path(data, ext.path)
                captured[ext.name] = val if val is not None else ""
            except (json.JSONDecodeError, ValueError):
                captured[ext.name] = ""
    return captured


async def _execute_request(
    req_item,
    env,
    variables: dict[str, str],
) -> tuple[int, dict[str, str], str, float]:
    """Execute a single request and return (status, headers, body, elapsed_ms)."""
    url = _substitute(req_item.url or "", env, variables)
    headers = {k: _substitute(v, env, variables) for k, v in (req_item.headers or {}).items()}
    body = _substitute(req_item.body, env, variables) if req_item.body else None
    query: dict[str, str] = {}

    auth = req_item.auth
    if auth and auth.type != "none":
        _apply_auth(auth, headers, query, env)

    started = time.perf_counter()
    async with httpx.AsyncClient(http2=True, timeout=30.0) as client:
        response = await client.request(
            method=req_item.method or "GET",
            url=url,
            headers=headers,
            params=query or None,
            content=body.encode("utf-8") if body else None,
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return response.status_code, dict(response.headers), response.text, elapsed_ms


# ---- Endpoints -------------------------------------------------------------


@router.post("/execute", response_model=PipelineResult)
async def execute_pipeline(pipeline: Pipeline) -> PipelineResult:
    """Execute a pipeline: run steps sequentially with variable passing,
    conditions, delays, and retry logic."""
    env = None
    if pipeline.environment_id:
        env = environments.get(pipeline.environment_id)
        if env is None:
            raise HTTPException(status_code=404, detail="environment not found")

    variables = dict(pipeline.variables)
    results: list[StepResult] = []
    last_status: int | None = None
    pipeline_start = time.perf_counter()
    stop = False

    for idx, step in enumerate(pipeline.steps):
        if stop:
            results.append(StepResult(
                step_index=idx,
                request_id=step.request_id,
                collection_id=step.collection_id,
                skipped=True,
            ))
            continue

        # Check condition (before request resolution — skip early if unmet)
        if step.condition and not _evaluate_condition(step.condition, variables, last_status):
            results.append(StepResult(
                step_index=idx,
                request_id=step.request_id,
                collection_id=step.collection_id,
                skipped=True,
            ))
            continue

        # Resolve the saved request
        req_item, col = _resolve_request(step.collection_id, step.request_id)
        if req_item is None:
            result = StepResult(
                step_index=idx,
                request_id=step.request_id,
                collection_id=step.collection_id,
                error=f"request {step.request_id} not found in collection {step.collection_id}",
            )
            results.append(result)
            if step.on_fail == "stop":
                stop = True
            continue

        # Apply delay
        if step.delay_ms > 0:
            await asyncio.sleep(step.delay_ms / 1000.0)

        # Execute with retry logic
        attempts = 0
        max_attempts = step.retry_count if step.on_fail == "retry" else 1
        step_result: StepResult | None = None

        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                status, resp_headers, resp_body, elapsed = await _execute_request(
                    req_item, env, variables
                )
                captured = _extract_values(step.extractors, status, resp_headers, resp_body)
                variables.update(captured)
                last_status = status

                passed = 200 <= status < 400
                step_result = StepResult(
                    step_index=idx,
                    request_id=step.request_id,
                    collection_id=step.collection_id,
                    status=status,
                    elapsed_ms=elapsed,
                    passed=passed,
                    captured=captured,
                    attempts=attempts,
                )
                if passed:
                    break
                # Not passed — retry if applicable
                if step.on_fail == "retry" and attempt < max_attempts - 1:
                    continue
                break
            except httpx.RequestError as exc:
                step_result = StepResult(
                    step_index=idx,
                    request_id=step.request_id,
                    collection_id=step.collection_id,
                    error=f"transport error: {exc}",
                    attempts=attempts,
                )
                if step.on_fail == "retry" and attempt < max_attempts - 1:
                    continue
                break

        assert step_result is not None
        results.append(step_result)

        if not step_result.passed and step_result.error is None and step_result.status is not None:
            if step.on_fail == "stop":
                stop = True
        elif step_result.error is not None:
            if step.on_fail == "stop":
                stop = True

    total_ms = round((time.perf_counter() - pipeline_start) * 1000, 2)
    passed_count = sum(1 for r in results if r.passed)
    failed_count = sum(1 for r in results if not r.passed and not r.skipped)

    return PipelineResult(
        results=results,
        total_ms=total_ms,
        passed=passed_count,
        failed=failed_count,
        variables=variables,
    )


@router.post("/validate", response_model=ValidateOutput)
def validate_pipeline(pipeline: Pipeline) -> ValidateOutput:
    """Validate a pipeline definition — check request IDs exist, etc."""
    issues: list[ValidationIssue] = []

    for idx, step in enumerate(pipeline.steps):
        req_item, col = _resolve_request(step.collection_id, step.request_id)
        if col is None:
            issues.append(ValidationIssue(
                step_index=idx,
                field="collection_id",
                message=f"collection '{step.collection_id}' not found",
            ))
        elif req_item is None:
            issues.append(ValidationIssue(
                step_index=idx,
                field="request_id",
                message=f"request '{step.request_id}' not found in collection '{step.collection_id}'",
            ))

        if step.condition:
            # Validate condition syntax
            status_pat = re.match(r"^status\s*(==|!=|>=|<=|>|<)\s*(\d+)$", step.condition.strip())
            var_pat = re.match(r'^variable\.(\w+)\s*(==|!=)\s*"(.*)"$', step.condition.strip())
            if not status_pat and not var_pat:
                issues.append(ValidationIssue(
                    step_index=idx,
                    field="condition",
                    message=f"unrecognised condition syntax: '{step.condition}'",
                ))

        if step.delay_ms < 0:
            issues.append(ValidationIssue(
                step_index=idx,
                field="delay_ms",
                message="delay_ms must be non-negative",
            ))

        for ext_idx, ext in enumerate(step.extractors):
            if not ext.name.strip():
                issues.append(ValidationIssue(
                    step_index=idx,
                    field=f"extractors[{ext_idx}].name",
                    message="extractor name must not be empty",
                ))

    return ValidateOutput(valid=len(issues) == 0, issues=issues)


@router.get("/templates", response_model=list[PipelineTemplate])
def get_templates() -> list[PipelineTemplate]:
    """Return built-in pipeline templates for quick start."""
    return [
        PipelineTemplate(
            name="Auth Flow",
            description="Login, then use the token for an authenticated request",
            steps=[
                {
                    "request_id": "",
                    "collection_id": "",
                    "delay_ms": 0,
                    "condition": None,
                    "extractors": [
                        {"name": "token", "source": "body", "path": "data.token"},
                    ],
                    "on_fail": "stop",
                    "retry_count": 1,
                },
                {
                    "request_id": "",
                    "collection_id": "",
                    "delay_ms": 0,
                    "condition": 'variable.token != ""',
                    "extractors": [],
                    "on_fail": "stop",
                    "retry_count": 1,
                },
            ],
        ),
        PipelineTemplate(
            name="CRUD Flow",
            description="Create, Read, Update, Delete a resource end-to-end",
            steps=[
                {
                    "request_id": "",
                    "collection_id": "",
                    "delay_ms": 0,
                    "condition": None,
                    "extractors": [
                        {"name": "resource_id", "source": "body", "path": "id"},
                    ],
                    "on_fail": "stop",
                    "retry_count": 1,
                },
                {
                    "request_id": "",
                    "collection_id": "",
                    "delay_ms": 100,
                    "condition": "status == 201",
                    "extractors": [],
                    "on_fail": "stop",
                    "retry_count": 1,
                },
                {
                    "request_id": "",
                    "collection_id": "",
                    "delay_ms": 0,
                    "condition": "status == 200",
                    "extractors": [],
                    "on_fail": "continue",
                    "retry_count": 1,
                },
                {
                    "request_id": "",
                    "collection_id": "",
                    "delay_ms": 0,
                    "condition": None,
                    "extractors": [],
                    "on_fail": "stop",
                    "retry_count": 1,
                },
            ],
        ),
        PipelineTemplate(
            name="Health Check",
            description="Verify a single endpoint is reachable, with retry on failure",
            steps=[
                {
                    "request_id": "",
                    "collection_id": "",
                    "delay_ms": 0,
                    "condition": None,
                    "extractors": [],
                    "on_fail": "retry",
                    "retry_count": 3,
                },
            ],
        ),
    ]
