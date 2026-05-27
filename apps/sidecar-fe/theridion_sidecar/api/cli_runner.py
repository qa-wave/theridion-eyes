"""CLI-style collection runner with formatted terminal output and trace files."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import environments, storage
from ..assertions import AssertionResult, ResponseData, evaluate_all
from ..models import CollectionItem
from ..trace_viewer import generate_trace_html
from .runner import RunInput, RunRequestResult, _collect_requests

router = APIRouter(prefix="/api/runner", tags=["cli-runner"])

# ANSI color codes
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _trace_dir() -> Path:
    """Directory for storing trace files."""
    d = storage.home_dir() / "traces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _format_time(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.2f}s"


def _format_result_line(result: RunRequestResult) -> str:
    """Format a single request result as a CLI line."""
    if result.error:
        icon = f"{_RED}\u2717{_RESET}"
        suffix = f"{_RED}{result.error}{_RESET}"
    elif result.assertions_failed > 0:
        icon = f"{_RED}\u2717{_RESET}"
        total_a = result.assertions_passed + result.assertions_failed
        suffix = f"{_RED}[{result.assertions_failed}/{total_a} assertions failed]{_RESET}"
    else:
        icon = f"{_GREEN}\u2713{_RESET}"
        if result.assertions_passed > 0:
            suffix = f"{_GREEN}[{result.assertions_passed} assertions passed]{_RESET}"
        else:
            suffix = f"{_GREEN}OK{_RESET}"

    time_str = f"{_DIM}({_format_time(result.elapsed_ms)}){_RESET}"
    method = result.method.upper()
    return f"  {icon} {method} {result.request_name} {time_str} {suffix}"


def _format_summary(passed: int, failed: int, skipped: int, total_ms: float) -> str:
    """Format the summary line."""
    parts: list[str] = []
    if passed:
        parts.append(f"{_GREEN}{passed} passed{_RESET}")
    if failed:
        parts.append(f"{_RED}{failed} failed{_RESET}")
    if skipped:
        parts.append(f"{_YELLOW}{skipped} skipped{_RESET}")

    time_str = _format_time(total_ms)
    return f"\n{_BOLD}Results:{_RESET} {', '.join(parts)} {_DIM}({time_str} total){_RESET}"


class CliRunOutput(BaseModel):
    output: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    total_ms: float = 0


class CliRunWithTraceOutput(BaseModel):
    output: str
    trace_path: str
    trace_id: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    total_ms: float = 0


class TraceHtmlOutput(BaseModel):
    html: str


import httpx


async def _execute_collection(collection_id: str, body: RunInput) -> tuple[list[RunRequestResult], str, float]:
    """Execute a collection and return (results, collection_name, total_ms)."""
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    env = environments.get(body.environment_id) if body.environment_id else None
    if body.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")

    coll_vars: dict[str, str] | None = None
    if coll.variables:
        enabled = {v.name: v.value for v in coll.variables if v.enabled}
        if enabled:
            coll_vars = enabled

    requests = _collect_requests(coll.items)
    results: list[RunRequestResult] = []
    total_elapsed = 0.0

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

    return results, coll.name, round(total_elapsed, 2)


def _build_cli_output(results: list[RunRequestResult], collection_name: str, total_ms: float) -> CliRunOutput:
    """Build the CLI formatted output string."""
    lines: list[str] = []
    lines.append(f"\n{_BOLD}Running: {collection_name}{_RESET}\n")

    passed = 0
    failed = 0
    skipped = 0

    for r in results:
        lines.append(_format_result_line(r))
        if r.error or r.assertions_failed > 0:
            failed += 1
        else:
            passed += 1

    lines.append(_format_summary(passed, failed, skipped, total_ms))

    return CliRunOutput(
        output="\n".join(lines),
        passed=passed,
        failed=failed,
        skipped=skipped,
        total_ms=total_ms,
    )


@router.post("/cli", response_model=CliRunOutput)
async def run_cli(collection_id: str, body: RunInput) -> CliRunOutput:
    """Run a collection and return CLI-formatted output."""
    results, coll_name, total_ms = await _execute_collection(collection_id, body)
    return _build_cli_output(results, coll_name, total_ms)


@router.post("/cli/trace", response_model=CliRunWithTraceOutput)
async def run_cli_with_trace(collection_id: str, body: RunInput) -> CliRunWithTraceOutput:
    """Run a collection, return CLI output and save a trace file."""
    results, coll_name, total_ms = await _execute_collection(collection_id, body)
    cli_output = _build_cli_output(results, coll_name, total_ms)

    # Save trace file
    trace_id = str(uuid.uuid4())
    trace_data = {
        "id": trace_id,
        "collection_name": coll_name,
        "timestamp": time.time(),
        "total_ms": total_ms,
        "results": [r.model_dump(mode="json") for r in results],
    }

    trace_path = _trace_dir() / f"{trace_id}.json"
    trace_path.write_text(json.dumps(trace_data, indent=2, ensure_ascii=False), encoding="utf-8")

    return CliRunWithTraceOutput(
        output=cli_output.output,
        trace_path=str(trace_path),
        trace_id=trace_id,
        passed=cli_output.passed,
        failed=cli_output.failed,
        skipped=cli_output.skipped,
        total_ms=total_ms,
    )


@router.get("/trace/{trace_id}")
async def download_trace(trace_id: str) -> FileResponse:
    """Download a trace file by ID."""
    trace_path = _trace_dir() / f"{trace_id}.json"
    if not trace_path.exists():
        raise HTTPException(status_code=404, detail="trace not found")
    return FileResponse(
        path=str(trace_path),
        media_type="application/json",
        filename=f"trace-{trace_id}.json",
    )


@router.post("/trace/html", response_model=TraceHtmlOutput)
async def trace_to_html(trace_id: str) -> TraceHtmlOutput:
    """Convert a saved trace to a self-contained HTML viewer."""
    trace_path = _trace_dir() / f"{trace_id}.json"
    if not trace_path.exists():
        raise HTTPException(status_code=404, detail="trace not found")

    data = json.loads(trace_path.read_text(encoding="utf-8"))
    html = generate_trace_html(
        collection_name=data["collection_name"],
        results=data["results"],
        elapsed_ms=data["total_ms"],
    )
    return TraceHtmlOutput(html=html)
