"""Data loop: run a collection for each row in a dataset."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/test", tags=["data-loop"])


class DataSource(BaseModel):
    type: str = "json"  # "csv" | "json"
    data: str  # CSV string or JSON array string


class DataLoopInput(BaseModel):
    collection_id: str
    datasource: DataSource
    loop_variable: str = "row"


class RowResult(BaseModel):
    row_index: int
    variables: dict[str, str] = {}
    status: str = "ok"
    error: str | None = None


class DataLoopOutput(BaseModel):
    total_rows: int = 0
    results: list[RowResult] = []


def _parse_rows(ds: DataSource) -> list[dict[str, str]]:
    if ds.type == "csv":
        reader = csv.DictReader(io.StringIO(ds.data))
        return [dict(r) for r in reader]
    else:
        parsed = json.loads(ds.data)
        if isinstance(parsed, list):
            return [{str(k): str(v) for k, v in (row if isinstance(row, dict) else {}).items()} for row in parsed]
        return []


@router.post("/data-loop", response_model=DataLoopOutput)
async def data_loop(body: DataLoopInput) -> DataLoopOutput:
    rows = _parse_rows(body.datasource)
    results: list[RowResult] = []
    for i, row in enumerate(rows):
        results.append(RowResult(row_index=i, variables=row))
    return DataLoopOutput(total_rows=len(rows), results=results)
