"""API governance: lint OpenAPI specs for naming conventions and best practices."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/governance", tags=["api-governance"])


class GovernanceRule(BaseModel):
    rule: str
    passed: bool
    message: str


class GovernanceInput(BaseModel):
    spec: str  # OpenAPI JSON string


class GovernanceOutput(BaseModel):
    score: int = 100
    rules: list[GovernanceRule] = []


@router.post("/lint", response_model=GovernanceOutput)
async def lint_spec(body: GovernanceInput) -> GovernanceOutput:
    try:
        spec = json.loads(body.spec)
    except json.JSONDecodeError:
        return GovernanceOutput(score=0, rules=[GovernanceRule(
            rule="valid_json", passed=False, message="Spec is not valid JSON"
        )])

    rules: list[GovernanceRule] = []
    deductions = 0

    # Check info section
    info = spec.get("info", {})
    if info.get("title"):
        rules.append(GovernanceRule(rule="has_title", passed=True, message="Spec has a title"))
    else:
        rules.append(GovernanceRule(rule="has_title", passed=False, message="Missing info.title"))
        deductions += 10

    if info.get("version"):
        rules.append(GovernanceRule(rule="has_version", passed=True, message="Spec has version"))
    else:
        rules.append(GovernanceRule(rule="has_version", passed=False, message="Missing info.version"))
        deductions += 10

    if info.get("description"):
        rules.append(GovernanceRule(rule="has_description", passed=True, message="Spec has description"))
    else:
        rules.append(GovernanceRule(rule="has_description", passed=False, message="Missing info.description"))
        deductions += 5

    # Check paths naming
    paths = spec.get("paths", {})
    bad_paths = [p for p in paths if re.search(r"[A-Z]", p.split("{")[0])]
    if bad_paths:
        rules.append(GovernanceRule(
            rule="lowercase_paths", passed=False,
            message=f"Uppercase in paths: {', '.join(bad_paths[:5])}",
        ))
        deductions += 15
    else:
        rules.append(GovernanceRule(rule="lowercase_paths", passed=True, message="All paths are lowercase"))

    # Check for operationId
    missing_op_ids = 0
    for path_item in paths.values():
        if isinstance(path_item, dict):
            for method in ("get", "post", "put", "delete", "patch"):
                op = path_item.get(method)
                if op and not op.get("operationId"):
                    missing_op_ids += 1
    if missing_op_ids:
        rules.append(GovernanceRule(
            rule="operation_ids", passed=False,
            message=f"{missing_op_ids} operations missing operationId",
        ))
        deductions += min(missing_op_ids * 2, 20)
    else:
        rules.append(GovernanceRule(rule="operation_ids", passed=True, message="All operations have operationId"))

    score = max(0, 100 - deductions)
    return GovernanceOutput(score=score, rules=rules)
