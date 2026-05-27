"""Spin — automated backend testing API router.

Endpoints:
    POST /api/spin/scenarios/run          Run a .spin.yaml scenario
    GET  /api/spin/scenarios              List .spin.yaml files in workspace
    POST /api/spin/workflow/dry-run       Validate workflow YAML without running
    POST /api/spin/contract/verify        Pact provider verification
    POST /api/spin/contract/record        Start recording a contract
    POST /api/spin/schemas/validate       Validate payload against OpenAPI/AsyncAPI/protobuf
    POST /api/spin/database/snapshot      Take DB table snapshot
    POST /api/spin/database/compare       Compare current state against snapshot
    POST /api/spin/performance/probe      Lightweight performance smoke check
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/spin", tags=["spin"])


# ── Request / Response models ─────────────────────────────────────────────────

class ScenarioRunInput(BaseModel):
    scenario_path: str
    env_vars: dict[str, Any] = Field(default_factory=dict)


class ScenarioListOutput(BaseModel):
    scenarios: list[dict[str, Any]]
    workspace_dir: str


class WorkflowDryRunInput(BaseModel):
    content: str  # Raw YAML string


class WorkflowDryRunOutput(BaseModel):
    valid: bool
    errors: list[str]
    step_count: int
    scenario_name: str | None


class ContractVerifyInput(BaseModel):
    contract_path: str
    provider_url: str
    provider_state_handler_url: str | None = None


class ContractRecordInput(BaseModel):
    consumer: str
    provider: str
    base_url: str
    interactions: list[dict[str, Any]] = Field(default_factory=list)
    output_path: str


class ContractRecordOutput(BaseModel):
    output_path: str
    interaction_count: int
    ok: bool
    error: str | None = None


class SchemaValidateInput(BaseModel):
    payload: Any
    schema_ref: str  # "openapi://opId", "asyncapi://channel", "jsonschema", "protobuf://Msg"
    spec_path: str | None = None
    raw_schema: dict[str, Any] | None = None


class SchemaValidateOutput(BaseModel):
    valid: bool
    errors: list[str]


class DbSnapshotInput(BaseModel):
    connection_string: str
    table: str


class DbSnapshotOutput(BaseModel):
    table: str
    row_count: int
    sample_rows: list[dict[str, Any]]
    snapshot: dict[str, Any]


class DbCompareInput(BaseModel):
    connection_string: str
    table: str
    snapshot_before: dict[str, Any]
    expected_delta: int


class DbCompareOutput(BaseModel):
    passed: bool
    expected_delta: int
    actual_delta: int
    rows_before: int
    rows_after: int
    diff: dict[str, Any]


class PerfProbeInput(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    target_rps: int = Field(default=10, ge=1, le=100)
    duration_seconds: int = Field(default=10, ge=5, le=30)
    expected_status: int = 200
    p95_threshold_ms: float | None = None
    error_rate_threshold: float = 0.05


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/scenarios/run")
async def run_scenario(body: ScenarioRunInput) -> dict[str, Any]:
    """Execute a .spin.yaml scenario file and return structured run results."""
    from ..spin.runner import load_scenario, run_scenario as _run

    try:
        scenario = load_scenario(body.scenario_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse scenario: {exc}") from exc

    result = await _run(scenario, env_vars=body.env_vars)
    return result.model_dump()


@router.get("/scenarios")
async def list_scenarios(workspace_dir: str = "") -> ScenarioListOutput:
    """List all .spin.yaml files found under the workspace directory."""
    from ..spin.workflow import list_scenario_files
    from .. import storage

    if not workspace_dir:
        workspace_dir = str(storage.home_dir())

    scenarios = list_scenario_files(workspace_dir)
    return ScenarioListOutput(scenarios=scenarios, workspace_dir=workspace_dir)


@router.post("/workflow/dry-run")
async def dry_run_workflow(body: WorkflowDryRunInput) -> WorkflowDryRunOutput:
    """Parse and validate a workflow YAML string without executing it."""
    from ..spin.workflow import parse_workflow_yaml, validate_workflow, WorkflowValidationError

    try:
        scenario = parse_workflow_yaml(body.content)
    except WorkflowValidationError as exc:
        return WorkflowDryRunOutput(
            valid=False,
            errors=[str(exc)],
            step_count=0,
            scenario_name=None,
        )
    except Exception as exc:
        return WorkflowDryRunOutput(
            valid=False,
            errors=[f"Parse error: {exc}"],
            step_count=0,
            scenario_name=None,
        )

    errors = validate_workflow(scenario)
    return WorkflowDryRunOutput(
        valid=len(errors) == 0,
        errors=errors,
        step_count=len(scenario.steps),
        scenario_name=scenario.name,
    )


@router.post("/contract/verify")
async def verify_contract(body: ContractVerifyInput) -> dict[str, Any]:
    """Run Pact provider verification against a real provider URL."""
    from ..spin.contract import verify_contract as _verify

    result = await _verify(
        contract_path=body.contract_path,
        provider_url=body.provider_url,
        provider_state_handler_url=body.provider_state_handler_url,
    )
    return result.model_dump()


@router.post("/contract/record", response_model=ContractRecordOutput)
async def record_contract(body: ContractRecordInput) -> ContractRecordOutput:
    """Record HTTP interactions against a provider and write a Pact V2 .contract.json.

    Pass interactions as list of dicts with keys:
        method, path, query?, request_headers?, request_body?, provider_state?, description?
    """
    from ..spin.contract import ContractRecorder

    recorder = ContractRecorder(
        consumer=body.consumer,
        provider=body.provider,
        base_url=body.base_url,
    )

    errors: list[str] = []
    for idx, interaction in enumerate(body.interactions):
        try:
            await recorder.record(
                method=interaction.get("method", "GET"),
                path=interaction.get("path", "/"),
                request_headers=interaction.get("request_headers"),
                request_body=interaction.get("request_body"),
                query=interaction.get("query"),
                provider_state=interaction.get("provider_state"),
                description=interaction.get("description"),
            )
        except Exception as exc:
            errors.append(f"interaction[{idx}]: {exc}")

    if errors:
        return ContractRecordOutput(
            output_path=body.output_path,
            interaction_count=len(recorder.interactions),
            ok=False,
            error="; ".join(errors),
        )

    try:
        out_path = recorder.save(body.output_path)
        return ContractRecordOutput(
            output_path=str(out_path),
            interaction_count=len(recorder.interactions),
            ok=True,
        )
    except Exception as exc:
        return ContractRecordOutput(
            output_path=body.output_path,
            interaction_count=len(recorder.interactions),
            ok=False,
            error=str(exc),
        )


@router.post("/schemas/validate", response_model=SchemaValidateOutput)
async def validate_schema(body: SchemaValidateInput) -> SchemaValidateOutput:
    """Validate a payload against OpenAPI, AsyncAPI, JSON Schema, or protobuf."""
    from ..spin.schema import validate_payload

    ok, errors = validate_payload(
        payload=body.payload,
        schema_ref=body.schema_ref,
        spec_path=body.spec_path,
        raw_schema=body.raw_schema,
    )
    return SchemaValidateOutput(valid=ok, errors=errors)


@router.post("/database/snapshot", response_model=DbSnapshotOutput)
async def db_snapshot(body: DbSnapshotInput) -> DbSnapshotOutput:
    """Capture a DB table snapshot (row count + sample)."""
    from ..spin.database import take_snapshot

    try:
        snapshot = take_snapshot(body.connection_string, body.table)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DbSnapshotOutput(
        table=body.table,
        row_count=snapshot["row_count"],
        sample_rows=snapshot["sample_rows"],
        snapshot=snapshot,
    )


@router.post("/database/compare", response_model=DbCompareOutput)
async def db_compare(body: DbCompareInput) -> DbCompareOutput:
    """Compare current DB table state against a previous snapshot."""
    from ..spin.database import compare_snapshot, count_rows, diff_snapshots, take_snapshot

    try:
        after_snapshot = take_snapshot(body.connection_string, body.table)
        ok, actual_delta = compare_snapshot(
            body.connection_string,
            body.table,
            body.snapshot_before,
            body.expected_delta,
        )
        diff = diff_snapshots(body.snapshot_before, after_snapshot)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DbCompareOutput(
        passed=ok,
        expected_delta=body.expected_delta,
        actual_delta=actual_delta,
        rows_before=body.snapshot_before.get("row_count", 0),
        rows_after=after_snapshot["row_count"],
        diff=diff,
    )


@router.post("/performance/probe")
async def performance_probe(body: PerfProbeInput) -> dict[str, Any]:
    """Run a lightweight performance smoke probe (max 100 RPS, 30 s)."""
    from ..spin.performance import run_smoke_probe

    result = await run_smoke_probe(
        url=body.url,
        method=body.method,
        headers=body.headers,
        body=body.body,
        target_rps=body.target_rps,
        duration_seconds=body.duration_seconds,
        expected_status=body.expected_status,
        p95_threshold_ms=body.p95_threshold_ms,
        error_rate_threshold=body.error_rate_threshold,
    )
    return result
