"""Multi-environment parallel runner.

Execute the same request (or collection) against multiple environments
simultaneously and compare results side-by-side.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from theridion_sidecar import environments, storage

router = APIRouter(prefix="/api/runner/multi-env", tags=["multi-env-runner"])


# ---- Models -----------------------------------------------------------------


class RequestTemplate(BaseModel):
    method: str = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None


class SingleRequestInput(BaseModel):
    request: RequestTemplate
    environment_ids: list[str] = Field(..., min_length=2)
    collection_id: str | None = None


class CollectionRunInput(BaseModel):
    collection_id: str = Field(..., min_length=1)
    environment_ids: list[str] = Field(..., min_length=2)


class EnvRequestResult(BaseModel):
    env_id: str
    env_name: str
    status: int | None = None
    elapsed_ms: float = 0
    body_preview: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    body_size: int = 0


class ComparisonSummary(BaseModel):
    all_same_status: bool = False
    fastest_env: str = ""
    slowest_env: str = ""
    response_size_diff: bool = False


class SingleRequestOutput(BaseModel):
    results: list[EnvRequestResult]
    comparison: ComparisonSummary


class CollectionRequestRow(BaseModel):
    request_name: str
    results: list[EnvRequestResult]
    comparison: ComparisonSummary


class CollectionRunOutput(BaseModel):
    rows: list[CollectionRequestRow]
    summary: ComparisonSummary


# ---- Legacy models (backwards compat with /api/test/multi-env) ---------------


class LegacyMultiEnvRequest(BaseModel):
    collection_id: str = Field(..., min_length=1)
    environment_ids: list[str] = Field(..., min_length=1)


class LegacyEnvRunResult(BaseModel):
    env_name: str
    env_id: str
    passed: int
    failed: int
    errors: int
    elapsed_ms: float


class LegacyRequestStatusRow(BaseModel):
    request_name: str
    statuses: dict[str, int]


class LegacyMultiEnvResult(BaseModel):
    results: list[LegacyEnvRunResult]
    comparison: list[LegacyRequestStatusRow]


# ---- Helpers -----------------------------------------------------------------


def _flatten_requests(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recursively flatten collection items into a list of requests."""
    result: list[dict[str, Any]] = []
    for item in items:
        if item.get("is_folder"):
            result.extend(_flatten_requests(item.get("items", [])))
        else:
            result.append(item)
    return result


def _build_comparison(results: list[EnvRequestResult]) -> ComparisonSummary:
    """Build comparison summary from a list of per-env results."""
    successful = [r for r in results if r.error is None and r.status is not None]
    if not successful:
        return ComparisonSummary()

    statuses = {r.status for r in successful}
    all_same_status = len(statuses) == 1

    fastest = min(successful, key=lambda r: r.elapsed_ms)
    slowest = max(successful, key=lambda r: r.elapsed_ms)

    sizes = {r.body_size for r in successful}
    response_size_diff = len(sizes) > 1

    return ComparisonSummary(
        all_same_status=all_same_status,
        fastest_env=fastest.env_name,
        slowest_env=slowest.env_name,
        response_size_diff=response_size_diff,
    )


async def _execute_request_for_env(
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None,
    env_id: str,
    env_name: str,
    collection_vars: dict[str, str] | None = None,
) -> EnvRequestResult:
    """Execute a single request with env variable substitution."""
    env_obj = environments.get(env_id)

    resolved_url = environments.substitute(url, env_obj, collection_vars=collection_vars)
    resolved_headers = environments.substitute_dict(headers, env_obj, collection_vars=collection_vars)
    resolved_body = (
        environments.substitute(body, env_obj, collection_vars=collection_vars)
        if body
        else None
    )

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.request(
                method=method,
                url=resolved_url,
                headers=resolved_headers,
                content=resolved_body.encode() if resolved_body else None,
            )
        elapsed = (time.perf_counter() - start) * 1000
        body_text = resp.text
        return EnvRequestResult(
            env_id=env_id,
            env_name=env_name,
            status=resp.status_code,
            elapsed_ms=round(elapsed, 2),
            body_preview=body_text[:500],
            headers=dict(resp.headers),
            body_size=len(body_text),
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return EnvRequestResult(
            env_id=env_id,
            env_name=env_name,
            elapsed_ms=round(elapsed, 2),
            error=str(exc),
        )


# ---- Endpoints ---------------------------------------------------------------


@router.post("", response_model=SingleRequestOutput)
async def run_single_request(body: SingleRequestInput) -> SingleRequestOutput:
    """Execute a single request against multiple environments in parallel."""
    if len(body.environment_ids) < 2:
        raise HTTPException(status_code=422, detail="At least 2 environments required")

    # Resolve env names
    env_names: dict[str, str] = {}
    for eid in body.environment_ids:
        env_obj = environments.get(eid)
        if env_obj is None:
            raise HTTPException(status_code=404, detail=f"Environment {eid} not found")
        env_names[eid] = env_obj.name

    # Load collection vars if specified
    collection_vars: dict[str, str] | None = None
    if body.collection_id:
        col_path = storage.collections_dir() / f"{body.collection_id}.json"
        if col_path.exists():
            col_data = json.loads(col_path.read_text(encoding="utf-8"))
            collection_vars = col_data.get("variables", {})

    tasks = [
        _execute_request_for_env(
            method=body.request.method,
            url=body.request.url,
            headers=body.request.headers,
            body=body.request.body,
            env_id=eid,
            env_name=env_names[eid],
            collection_vars=collection_vars,
        )
        for eid in body.environment_ids
    ]
    results = await asyncio.gather(*tasks)
    comparison = _build_comparison(list(results))

    return SingleRequestOutput(results=list(results), comparison=comparison)


@router.post("/collection", response_model=CollectionRunOutput)
async def run_collection(body: CollectionRunInput) -> CollectionRunOutput:
    """Run an entire collection against multiple environments in parallel."""
    if len(body.environment_ids) < 2:
        raise HTTPException(status_code=422, detail="At least 2 environments required")

    col_path = storage.collections_dir() / f"{body.collection_id}.json"
    if not col_path.exists():
        raise HTTPException(status_code=404, detail="Collection not found")

    collection = json.loads(col_path.read_text(encoding="utf-8"))
    collection_vars: dict[str, str] | None = collection.get("variables")
    requests = _flatten_requests(collection.get("items", []))

    # Resolve env names
    env_names: dict[str, str] = {}
    for eid in body.environment_ids:
        env_obj = environments.get(eid)
        if env_obj is None:
            raise HTTPException(status_code=404, detail=f"Environment {eid} not found")
        env_names[eid] = env_obj.name

    rows: list[CollectionRequestRow] = []
    all_results: list[EnvRequestResult] = []

    for req_item in requests:
        name = req_item.get("name", req_item.get("url", "unnamed"))
        method = req_item.get("method", "GET")
        url = req_item.get("url", "")
        headers = req_item.get("headers", {})
        req_body = req_item.get("body")

        tasks = [
            _execute_request_for_env(
                method=method,
                url=url,
                headers=headers,
                body=req_body,
                env_id=eid,
                env_name=env_names[eid],
                collection_vars=collection_vars,
            )
            for eid in body.environment_ids
        ]
        results = list(await asyncio.gather(*tasks))
        comparison = _build_comparison(results)
        rows.append(CollectionRequestRow(
            request_name=name, results=results, comparison=comparison,
        ))
        all_results.extend(results)

    overall = _build_comparison(all_results)
    return CollectionRunOutput(rows=rows, summary=overall)


# ---- Legacy endpoint (backwards compat) --------------------------------------


legacy_router = APIRouter(prefix="/api/test", tags=["test"])


async def _run_env_legacy(
    collection: dict[str, Any], env_id: str, env_name: str,
) -> tuple[LegacyEnvRunResult, dict[str, int]]:
    """Run all requests in collection against one environment (legacy)."""
    requests = _flatten_requests(collection.get("items", []))
    passed = 0
    failed = 0
    errors = 0
    statuses: dict[str, int] = {}
    start = time.perf_counter()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for req_item in requests:
            url = req_item.get("url", "")
            method = req_item.get("method", "GET")
            headers = req_item.get("headers", {})
            body = req_item.get("body")
            name = req_item.get("name", url)

            try:
                env_obj = environments.get(env_id)
                if env_obj:
                    url = environments.substitute(url, env_obj)
                    headers = environments.substitute_dict(headers, env_obj)
                    if body:
                        body = environments.substitute(body, env_obj)
            except Exception:
                pass

            try:
                resp = await client.request(
                    method=method, url=url, headers=headers,
                    content=body.encode() if body else None,
                )
                statuses[name] = resp.status_code
                if resp.status_code < 400:
                    passed += 1
                else:
                    failed += 1
            except Exception:
                errors += 1
                statuses[name] = 0

    elapsed = (time.perf_counter() - start) * 1000
    return (
        LegacyEnvRunResult(
            env_name=env_name, env_id=env_id,
            passed=passed, failed=failed, errors=errors,
            elapsed_ms=round(elapsed, 2),
        ),
        statuses,
    )


@legacy_router.post("/multi-env", response_model=LegacyMultiEnvResult)
async def multi_env_runner_legacy(req: LegacyMultiEnvRequest) -> LegacyMultiEnvResult:
    """Legacy endpoint — kept for backwards compatibility with existing UI."""
    col_path = storage.collections_dir() / f"{req.collection_id}.json"
    if not col_path.exists():
        raise HTTPException(status_code=404, detail="Collection not found")

    collection = json.loads(col_path.read_text(encoding="utf-8"))

    env_names: dict[str, str] = {}
    for eid in req.environment_ids:
        env_obj = environments.get(eid)
        env_names[eid] = env_obj.name if env_obj else eid

    tasks = [
        _run_env_legacy(collection, eid, env_names[eid])
        for eid in req.environment_ids
    ]
    raw_results = await asyncio.gather(*tasks)

    results: list[LegacyEnvRunResult] = []
    all_statuses: dict[str, dict[str, int]] = {}
    for env_result, statuses in raw_results:
        results.append(env_result)
        all_statuses[env_result.env_id] = statuses

    all_request_names: list[str] = []
    for _, statuses in raw_results:
        for name in statuses:
            if name not in all_request_names:
                all_request_names.append(name)

    comparison: list[LegacyRequestStatusRow] = []
    for name in all_request_names:
        row_statuses = {
            eid: all_statuses.get(eid, {}).get(name, 0)
            for eid in req.environment_ids
        }
        comparison.append(LegacyRequestStatusRow(
            request_name=name, statuses=row_statuses,
        ))

    return LegacyMultiEnvResult(results=results, comparison=comparison)
