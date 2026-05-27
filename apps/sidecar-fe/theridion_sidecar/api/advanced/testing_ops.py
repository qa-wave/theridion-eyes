"""Snapshot comparison, JSON diff, and flow runner endpoints."""

from __future__ import annotations

import copy
import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ... import environments, storage
from ...assertions import Assertion, AssertionResult, ResponseData, evaluate_all
from ...models import AuthConfig, HttpMethod, RequestCapture
from ..requests import _apply_auth
from .security_ops import _write_json_atomic

router = APIRouter()


# ---- Semantic diff + snapshots -------------------------------------------


class JsonDiffInput(BaseModel):
    left: str
    right: str
    ignore_paths: list[str] = Field(default_factory=list)
    unordered_arrays: bool = True


class JsonDifference(BaseModel):
    path: str
    kind: Literal["added", "removed", "changed"]
    left: Any = None
    right: Any = None


class JsonDiffOutput(BaseModel):
    equal: bool
    differences: list[JsonDifference]


class SnapshotWriteInput(BaseModel):
    value: str
    metadata: dict[str, str] = Field(default_factory=dict)


class SnapshotCompareInput(BaseModel):
    value: str
    ignore_paths: list[str] = Field(default_factory=list)
    unordered_arrays: bool = True


class SnapshotCompareOutput(BaseModel):
    exists: bool
    diff: JsonDiffOutput | None = None


def _parse_json_payload(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc


def _remove_path(data: Any, path: str) -> None:
    if not path:
        return
    parts = path.strip("$.").split(".")
    current = data
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return
    last = parts[-1]
    if isinstance(current, dict):
        current.pop(last, None)
    elif isinstance(current, list) and last.isdigit():
        index = int(last)
        if 0 <= index < len(current):
            current.pop(index)


def _normalize_json(value: Any, ignore_paths: list[str], unordered_arrays: bool) -> Any:
    data = copy.deepcopy(value)
    for path in ignore_paths:
        _remove_path(data, path)

    def normalize(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: normalize(v) for k, v in sorted(node.items())}
        if isinstance(node, list):
            normalized = [normalize(v) for v in node]
            if unordered_arrays:
                return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
            return normalized
        return node

    return normalize(data)


def _diff_values(left: Any, right: Any, path: str = "$") -> list[JsonDifference]:
    if type(left) is not type(right):
        return [JsonDifference(path=path, kind="changed", left=left, right=right)]
    if isinstance(left, dict):
        out: list[JsonDifference] = []
        keys = set(left) | set(right)
        for key in sorted(keys):
            child_path = f"{path}.{key}"
            if key not in left:
                out.append(JsonDifference(path=child_path, kind="added", right=right[key]))
            elif key not in right:
                out.append(JsonDifference(path=child_path, kind="removed", left=left[key]))
            else:
                out.extend(_diff_values(left[key], right[key], child_path))
        return out
    if isinstance(left, list):
        out = []
        for idx in range(max(len(left), len(right))):
            child_path = f"{path}[{idx}]"
            if idx >= len(left):
                out.append(JsonDifference(path=child_path, kind="added", right=right[idx]))
            elif idx >= len(right):
                out.append(JsonDifference(path=child_path, kind="removed", left=left[idx]))
            else:
                out.extend(_diff_values(left[idx], right[idx], child_path))
        return out
    if left != right:
        return [JsonDifference(path=path, kind="changed", left=left, right=right)]
    return []


@router.post("/diff/json", response_model=JsonDiffOutput)
def diff_json(body: JsonDiffInput) -> JsonDiffOutput:
    left = _normalize_json(
        _parse_json_payload(body.left), body.ignore_paths, body.unordered_arrays
    )
    right = _normalize_json(
        _parse_json_payload(body.right), body.ignore_paths, body.unordered_arrays
    )
    differences = _diff_values(left, right)
    return JsonDiffOutput(equal=len(differences) == 0, differences=differences)


def _snapshot_path(name: str) -> Path:
    if not re.match(r"^[A-Za-z0-9_.-]{1,160}$", name):
        raise HTTPException(status_code=400, detail="invalid snapshot name")
    directory = storage.home_dir() / "snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{name}.json"


@router.put("/snapshots/{name}")
def write_snapshot(name: str, body: SnapshotWriteInput) -> dict[str, str]:
    payload = {
        "value": _parse_json_payload(body.value),
        "metadata": body.metadata,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    _write_json_atomic(_snapshot_path(name), payload)
    return {"name": name, "status": "saved"}


@router.post("/snapshots/{name}/compare", response_model=SnapshotCompareOutput)
def compare_snapshot(name: str, body: SnapshotCompareInput) -> SnapshotCompareOutput:
    path = _snapshot_path(name)
    if not path.exists():
        return SnapshotCompareOutput(exists=False)
    stored = json.loads(path.read_text(encoding="utf-8"))
    left = json.dumps(stored.get("value"))
    diff = diff_json(
        JsonDiffInput(
            left=left,
            right=body.value,
            ignore_paths=body.ignore_paths,
            unordered_arrays=body.unordered_arrays,
        )
    )
    return SnapshotCompareOutput(exists=True, diff=diff)


# ---- Flow runner, cleanup hooks, data sets, and trace timeline ------------


class FlowStep(BaseModel):
    id: str | None = None
    name: str = "Request"
    method: HttpMethod = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    assertions: list[Assertion] = Field(default_factory=list)
    captures: list[RequestCapture] = Field(default_factory=list)
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)


class FlowRunInput(BaseModel):
    environment_id: str | None = None
    dataset: list[dict[str, str]] = Field(default_factory=lambda: [{}])
    steps: list[FlowStep] = Field(..., min_length=1)
    cleanup_steps: list[FlowStep] = Field(default_factory=list)


class FlowStepResult(BaseModel):
    step_id: str
    name: str
    status: int | None = None
    elapsed_ms: float = 0
    error: str | None = None
    captured_values: dict[str, str] = Field(default_factory=dict)
    assertion_results: list[AssertionResult] = Field(default_factory=list)


class FlowTraceEvent(BaseModel):
    dataset_index: int
    step_id: str
    phase: Literal["request", "assertions", "capture", "cleanup"]
    started_at: str
    ended_at: str
    elapsed_ms: float
    status: int | None = None
    error: str | None = None


class FlowDatasetResult(BaseModel):
    index: int
    runtime: dict[str, str]
    steps: list[FlowStepResult]
    cleanup: list[FlowStepResult]


class FlowRunOutput(BaseModel):
    datasets: list[FlowDatasetResult]
    trace: list[FlowTraceEvent]
    passed_assertions: int
    failed_assertions: int


def _substitute_dict_extra(
    values: dict[str, str], env: environments.Environment | None, runtime: dict[str, str]
) -> dict[str, str]:
    return {key: environments.substitute(value, env, runtime) for key, value in values.items()}


def _auth_with_runtime(
    auth: AuthConfig | None, env: environments.Environment | None, runtime: dict[str, str]
) -> AuthConfig | None:
    if auth is None:
        return None
    data = auth.model_dump()
    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = environments.substitute(value, env, runtime)
    return AuthConfig(**data)


def _extract_json_path(data: Any, path: str) -> str | None:
    current = data
    if not path:
        return None
    for part in path.split("."):
        match = re.match(r"^(\w+)\[(\d+)]$", part)
        if match:
            key, index = match.group(1), int(match.group(2))
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return json.dumps(current) if isinstance(current, (dict, list)) else str(current)


def _capture_values(
    captures: list[RequestCapture], status: int, headers: dict[str, str], body: str
) -> dict[str, str]:
    out: dict[str, str] = {}
    for capture in captures:
        if capture.source == "status":
            out[capture.name] = str(status)
        elif capture.source == "header":
            needle = capture.path.lower()
            out[capture.name] = next((v for k, v in headers.items() if k.lower() == needle), "")
        else:
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                out[capture.name] = ""
            else:
                out[capture.name] = _extract_json_path(payload, capture.path) or ""
    return out


async def _run_flow_step(
    step: FlowStep,
    env: environments.Environment | None,
    runtime: dict[str, str],
    phase: Literal["request", "cleanup"],
) -> tuple[FlowStepResult, FlowTraceEvent]:
    step_id = step.id or str(uuid.uuid4())
    start_dt = datetime.now(tz=UTC)
    started = time.perf_counter()
    result = FlowStepResult(step_id=step_id, name=step.name)
    try:
        resolved_url = environments.substitute(step.url, env, runtime)
        headers = _substitute_dict_extra(step.headers, env, runtime)
        body = environments.substitute(step.body, env, runtime) if step.body is not None else None
        query: dict[str, str] = {}
        auth = _auth_with_runtime(step.auth, env, runtime)
        if auth and auth.type != "none":
            _apply_auth(auth, headers, query, env)
        async with httpx.AsyncClient(http2=True, timeout=step.timeout_seconds) as client:
            response = await client.request(
                method=step.method,
                url=resolved_url,
                headers=headers,
                params=query or None,
                content=body.encode("utf-8") if body is not None else None,
            )
        elapsed = (time.perf_counter() - started) * 1000
        result.status = response.status_code
        result.elapsed_ms = round(elapsed, 2)
        response_headers = dict(response.headers)
        result.captured_values = _capture_values(
            step.captures, response.status_code, response_headers, response.text
        )
        runtime.update(result.captured_values)
        if step.assertions:
            result.assertion_results = evaluate_all(
                step.assertions,
                ResponseData(
                    status=response.status_code,
                    headers=response_headers,
                    body=response.text,
                    elapsed_ms=elapsed,
                ),
            )
    except httpx.RequestError as exc:
        result.error = f"transport error: {exc}"
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    end_dt = datetime.now(tz=UTC)
    event = FlowTraceEvent(
        dataset_index=-1,
        step_id=step_id,
        phase=phase,
        started_at=start_dt.isoformat(),
        ended_at=end_dt.isoformat(),
        elapsed_ms=result.elapsed_ms,
        status=result.status,
        error=result.error,
    )
    return result, event


@router.post("/flows/run", response_model=FlowRunOutput)
async def run_flow(body: FlowRunInput) -> FlowRunOutput:
    env = environments.get(body.environment_id) if body.environment_id else None
    if body.environment_id and env is None:
        raise HTTPException(status_code=404, detail="environment not found")
    dataset = body.dataset or [{}]
    datasets: list[FlowDatasetResult] = []
    trace: list[FlowTraceEvent] = []
    passed = 0
    failed = 0
    for index, row in enumerate(dataset):
        runtime = dict(row)
        step_results: list[FlowStepResult] = []
        cleanup_results: list[FlowStepResult] = []
        try:
            for step in body.steps:
                result, event = await _run_flow_step(step, env, runtime, "request")
                event.dataset_index = index
                trace.append(event)
                step_results.append(result)
                passed += sum(1 for assertion in result.assertion_results if assertion.passed)
                failed += sum(1 for assertion in result.assertion_results if not assertion.passed)
        finally:
            for cleanup in body.cleanup_steps:
                result, event = await _run_flow_step(cleanup, env, runtime, "cleanup")
                event.dataset_index = index
                trace.append(event)
                cleanup_results.append(result)
        datasets.append(
            FlowDatasetResult(
                index=index,
                runtime=runtime,
                steps=step_results,
                cleanup=cleanup_results,
            )
        )
    return FlowRunOutput(
        datasets=datasets,
        trace=trace,
        passed_assertions=passed,
        failed_assertions=failed,
    )
