"""Contract drift detection — deep compare JSON structure."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/test", tags=["test"])


class ContractDriftRequest(BaseModel):
    current_body: str
    baseline_body: str


class DriftEntry(BaseModel):
    path: str
    type: Literal["added", "removed", "type_changed"]
    old_type: str | None = None
    new_type: str | None = None


class ContractDriftResult(BaseModel):
    drifts: list[DriftEntry]
    breaking: bool
    drift_count: int


def _type_name(v: object) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def _compare(baseline: object, current: object, path: str, drifts: list[DriftEntry]) -> None:
    if isinstance(baseline, dict) and isinstance(current, dict):
        all_keys = set(baseline.keys()) | set(current.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}" if path else key
            if key not in baseline:
                drifts.append(DriftEntry(path=child_path, type="added"))
            elif key not in current:
                drifts.append(DriftEntry(path=child_path, type="removed"))
            else:
                _compare(baseline[key], current[key], child_path, drifts)
    elif isinstance(baseline, list) and isinstance(current, list):
        # Compare first element structure if available
        if baseline and current:
            _compare(baseline[0], current[0], f"{path}[0]", drifts)
        elif baseline and not current:
            drifts.append(DriftEntry(path=f"{path}[0]", type="removed"))
        elif not baseline and current:
            drifts.append(DriftEntry(path=f"{path}[0]", type="added"))
    else:
        bt = _type_name(baseline)
        ct = _type_name(current)
        if bt != ct:
            drifts.append(DriftEntry(
                path=path, type="type_changed", old_type=bt, new_type=ct,
            ))


@router.post("/contract-drift", response_model=ContractDriftResult)
async def contract_drift(req: ContractDriftRequest) -> ContractDriftResult:
    try:
        baseline = json.loads(req.baseline_body)
        current = json.loads(req.current_body)
    except json.JSONDecodeError as exc:
        return ContractDriftResult(
            drifts=[DriftEntry(path="$", type="type_changed",
                               old_type="json", new_type=f"parse_error: {exc}")],
            breaking=True,
            drift_count=1,
        )

    drifts: list[DriftEntry] = []
    _compare(baseline, current, "$", drifts)

    breaking = any(d.type in ("removed", "type_changed") for d in drifts)

    return ContractDriftResult(
        drifts=drifts,
        breaking=breaking,
        drift_count=len(drifts),
    )
