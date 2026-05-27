"""Environment comparison — diff two environments side by side."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments

router = APIRouter(prefix="/api/envdiff", tags=["envdiff"])


class VarDiff(BaseModel):
    name: str
    left_value: str | None = None
    right_value: str | None = None
    status: str  # "same", "changed", "left_only", "right_only"


class EnvDiffOutput(BaseModel):
    left_name: str
    right_name: str
    diffs: list[VarDiff] = Field(default_factory=list)
    total: int = 0
    changed: int = 0
    added: int = 0
    removed: int = 0


class DiffInput(BaseModel):
    left_id: str
    right_id: str


@router.post("/compare", response_model=EnvDiffOutput)
def compare_envs(body: DiffInput) -> EnvDiffOutput:
    left = environments.get(body.left_id)
    right = environments.get(body.right_id)
    if not left:
        raise HTTPException(status_code=404, detail=f"Left environment {body.left_id} not found")
    if not right:
        raise HTTPException(status_code=404, detail=f"Right environment {body.right_id} not found")

    left_vars = {v.name: v.value for v in left.variables if v.enabled}
    right_vars = {v.name: v.value for v in right.variables if v.enabled}
    all_names = sorted(set(left_vars) | set(right_vars))

    diffs: list[VarDiff] = []
    changed = added = removed = 0

    for name in all_names:
        lv = left_vars.get(name)
        rv = right_vars.get(name)
        if lv is not None and rv is not None:
            status = "same" if lv == rv else "changed"
            if status == "changed":
                changed += 1
        elif lv is not None:
            status = "left_only"
            removed += 1
        else:
            status = "right_only"
            added += 1
        diffs.append(VarDiff(name=name, left_value=lv, right_value=rv, status=status))

    return EnvDiffOutput(
        left_name=left.name, right_name=right.name,
        diffs=diffs, total=len(diffs),
        changed=changed, added=added, removed=removed,
    )
