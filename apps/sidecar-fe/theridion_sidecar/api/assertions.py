"""Assertion evaluation API endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..assertions import (
    Assertion,
    AssertionResult,
    ResponseData,
    evaluate_all,
)

router = APIRouter(prefix="/api/assertions", tags=["assertions"])


class EvaluateInput(BaseModel):
    assertions: list[Assertion]
    response: ResponseData


class EvaluateOutput(BaseModel):
    results: list[AssertionResult]
    passed: int
    failed: int
    total: int


@router.post("/evaluate", response_model=EvaluateOutput)
def evaluate_endpoint(body: EvaluateInput) -> EvaluateOutput:
    results = evaluate_all(body.assertions, body.response)
    passed = sum(1 for r in results if r.passed)
    return EvaluateOutput(
        results=results,
        passed=passed,
        failed=len(results) - passed,
        total=len(results),
    )
