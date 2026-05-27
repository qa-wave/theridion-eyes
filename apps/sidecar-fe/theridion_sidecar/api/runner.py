"""Collection runner — execute all requests in a collection sequentially."""

from __future__ import annotations

import datetime
import logging
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import cookies, environments, storage
from ..assertions import AssertionResult, ResponseData, evaluate_all
from ..models import CollectionItem

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runner", tags=["runner"])


class RunRequestResult(BaseModel):
    request_id: str
    request_name: str
    method: str
    url: str
    status: int | None = None
    elapsed_ms: float = 0
    error: str | None = None
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    assertions_passed: int = 0
    assertions_failed: int = 0


class RunCollectionOutput(BaseModel):
    collection_id: str
    collection_name: str
    results: list[RunRequestResult] = Field(default_factory=list)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_assertions: int = 0
    passed_assertions: int = 0
    failed_assertions: int = 0
    total_elapsed_ms: float = 0


class RunInput(BaseModel):
    environment_id: str | None = None


def _collect_requests(items: list[CollectionItem]) -> list[CollectionItem]:
    """Flatten the tree into a list of leaf requests (depth-first)."""
    out: list[CollectionItem] = []
    for it in items:
        if it.is_folder:
            out.extend(_collect_requests(it.items))
        else:
            out.append(it)
    return out


@router.post("/{collection_id}/run", response_model=RunCollectionOutput)
async def run_collection(collection_id: str, body: RunInput) -> RunCollectionOutput:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    env = environments.get(body.environment_id) if body.environment_id else None
    if body.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")

    # Extract collection-level variables once for all requests.
    coll_vars: dict[str, str] | None = None
    if coll.variables:
        enabled = {v.name: v.value for v in coll.variables if v.enabled}
        if enabled:
            coll_vars = enabled

    requests = _collect_requests(coll.items)
    results: list[RunRequestResult] = []
    total_elapsed = 0.0
    successful = 0
    total_a_passed = 0
    total_a_failed = 0

    for req in requests:
        if not req.url:
            results.append(RunRequestResult(
                request_id=req.id,
                request_name=req.name,
                method=req.method or "GET",
                url="",
                error="No URL specified",
            ))
            continue

        resolved_url = environments.substitute(req.url, env, collection_vars=coll_vars)
        resolved_headers = environments.substitute_dict(req.headers, env, collection_vars=coll_vars)
        resolved_body = (
            environments.substitute(req.body, env, collection_vars=coll_vars) if req.body else None
        )

        # Auth injection.
        resolved_query: dict[str, str] = {}
        if req.auth and req.auth.type != "none":
            from .requests import _apply_auth
            _apply_auth(req.auth, resolved_headers, resolved_query, env, collection_vars=coll_vars)

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                http2=True,
                timeout=30,
                follow_redirects=True,
            ) as client:
                response = await client.request(
                    method=req.method or "GET",
                    url=resolved_url,
                    headers=resolved_headers,
                    params=resolved_query or None,
                    content=resolved_body.encode("utf-8") if resolved_body else None,
                )
            elapsed = (time.perf_counter() - started) * 1000

            # Evaluate assertions.
            a_results: list[AssertionResult] = []
            if req.assertions:
                resp_data = ResponseData(
                    status=response.status_code,
                    headers=dict(response.headers),
                    body=response.text,
                    elapsed_ms=elapsed,
                )
                a_results = evaluate_all(req.assertions, resp_data)

            a_passed = sum(1 for r in a_results if r.passed)
            a_failed = len(a_results) - a_passed
            total_a_passed += a_passed
            total_a_failed += a_failed

            results.append(RunRequestResult(
                request_id=req.id,
                request_name=req.name,
                method=req.method or "GET",
                url=req.url,
                status=response.status_code,
                elapsed_ms=round(elapsed, 2),
                assertion_results=a_results,
                assertions_passed=a_passed,
                assertions_failed=a_failed,
            ))
            successful += 1
            total_elapsed += elapsed

        except httpx.RequestError as exc:
            elapsed = (time.perf_counter() - started) * 1000
            results.append(RunRequestResult(
                request_id=req.id,
                request_name=req.name,
                method=req.method or "GET",
                url=req.url,
                error=f"transport error: {exc}",
                elapsed_ms=round(elapsed, 2),
            ))
            total_elapsed += elapsed

    output = RunCollectionOutput(
        collection_id=coll.id,
        collection_name=coll.name,
        results=results,
        total_requests=len(requests),
        successful_requests=successful,
        failed_requests=len(requests) - successful,
        total_assertions=total_a_passed + total_a_failed,
        passed_assertions=total_a_passed,
        failed_assertions=total_a_failed,
        total_elapsed_ms=round(total_elapsed, 2),
    )

    # Emit cross-module events (fire-and-forget; never fail the runner).
    _emit_run_events(output)

    return output


def _emit_run_events(output: RunCollectionOutput) -> None:
    """Write cross-module event files for the run result."""
    from .events import write_event

    workspace = storage.home_dir()
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Always emit a run.completed event.
    event_type = "run.completed"
    if output.failed_requests > 0 or output.failed_assertions > 0:
        event_type = "test.failed"

    summary = (
        f"{output.collection_name}: "
        f"{output.successful_requests}/{output.total_requests} passed, "
        f"{output.passed_assertions}/{output.total_assertions} assertions OK"
    )
    try:
        write_event(workspace, {
            "version": "1",
            "type": event_type,
            "source": "runner",
            "timestamp": ts,
            "context": {
                "collection_id": output.collection_id,
                "summary": summary,
            },
            "actions": [],
        })
    except Exception as exc:
        _log.warning("event write failed (non-critical): %s", exc)


class RunWithTraceOutput(BaseModel):
    run: RunCollectionOutput
    trace_html: str


@router.post("/{collection_id}/run-with-trace", response_model=RunWithTraceOutput)
async def run_with_trace(collection_id: str, body: RunInput) -> RunWithTraceOutput:
    """Run a collection and return results together with a self-contained
    HTML trace viewer."""
    run_output = await run_collection(collection_id, body)

    from ..trace_viewer import generate_trace_html

    trace_html = generate_trace_html(
        collection_name=run_output.collection_name,
        results=[r.model_dump(mode="json") for r in run_output.results],
        elapsed_ms=run_output.total_elapsed_ms,
    )
    return RunWithTraceOutput(run=run_output, trace_html=trace_html)
