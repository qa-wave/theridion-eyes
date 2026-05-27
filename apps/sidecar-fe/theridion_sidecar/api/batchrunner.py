"""Batch runner — execute a collection with a CSV/JSON dataset."""

from __future__ import annotations

import csv
import io
import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments, storage
from ..assertions import AssertionResult, ResponseData, evaluate_all
from ..models import CollectionItem

router = APIRouter(prefix="/api/batch", tags=["batch"])


class BatchInput(BaseModel):
    collection_id: str
    environment_id: str | None = None
    dataset: list[dict[str, str]] = Field(default_factory=list)
    dataset_csv: str | None = None  # Alternative: raw CSV string


class RowResult(BaseModel):
    row_index: int
    variables: dict[str, str]
    request_results: list[dict[str, Any]] = Field(default_factory=list)
    passed: int = 0
    failed: int = 0
    errors: int = 0


class BatchOutput(BaseModel):
    total_rows: int = 0
    total_requests: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_errors: int = 0
    elapsed_ms: float = 0
    rows: list[RowResult] = Field(default_factory=list)


def _parse_csv(raw: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw))
    return [dict(row) for row in reader]


def _flatten(items: list[CollectionItem]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for it in items:
        if it.is_folder:
            out.extend(_flatten(it.items))
        else:
            out.append(it)
    return out


@router.post("/run", response_model=BatchOutput)
async def run_batch(body: BatchInput) -> BatchOutput:
    coll = storage.get(body.collection_id)
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")

    dataset = body.dataset
    if body.dataset_csv:
        dataset = _parse_csv(body.dataset_csv)
    if not dataset:
        raise HTTPException(status_code=400, detail="Empty dataset")

    env = environments.get(body.environment_id) if body.environment_id else None
    requests = _flatten(coll.items)
    started = time.perf_counter()

    output = BatchOutput(total_rows=len(dataset), total_requests=len(requests) * len(dataset))
    for row_idx, row_vars in enumerate(dataset):
        row_result = RowResult(row_index=row_idx, variables=row_vars)
        for req in requests:
            if not req.url:
                row_result.errors += 1
                row_result.request_results.append({"name": req.name, "error": "No URL"})
                continue

            # Substitute with row vars as extra
            url = environments.substitute(req.url, env, row_vars)
            headers = {k: environments.substitute(v, env, row_vars) for k, v in req.headers.items()}
            req_body = environments.substitute(req.body, env, row_vars) if req.body else None

            try:
                async with httpx.AsyncClient(http2=True, timeout=30, follow_redirects=True) as client:
                    response = await client.request(
                        method=req.method or "GET", url=url, headers=headers,
                        content=req_body.encode() if req_body else None,
                    )
                elapsed_ms = 0  # simplified

                # Assertions
                a_passed = a_failed = 0
                if req.assertions:
                    results = evaluate_all(req.assertions, ResponseData(
                        status=response.status_code, headers=dict(response.headers),
                        body=response.text, elapsed_ms=elapsed_ms,
                    ))
                    a_passed = sum(1 for r in results if r.passed)
                    a_failed = len(results) - a_passed

                row_result.passed += a_passed + (1 if response.status_code < 400 else 0)
                row_result.failed += a_failed + (1 if response.status_code >= 400 else 0)
                row_result.request_results.append({
                    "name": req.name, "status": response.status_code,
                    "assertions_passed": a_passed, "assertions_failed": a_failed,
                })
            except Exception as e:
                row_result.errors += 1
                row_result.request_results.append({"name": req.name, "error": str(e)})

        output.rows.append(row_result)
        output.total_passed += row_result.passed
        output.total_failed += row_result.failed
        output.total_errors += row_result.errors

    output.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return output
