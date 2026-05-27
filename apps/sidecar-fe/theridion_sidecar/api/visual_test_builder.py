"""Visual test builder: store/retrieve test step sequences."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/test-builder", tags=["test-builder"])


class TestStep(BaseModel):
    type: str  # "request" | "delay" | "assert" | "loop" | "condition"
    config: dict = {}


class TestBuilderData(BaseModel):
    steps: list[TestStep] = []
    version: int = 1


def _path(collection_id: str) -> Path:
    return storage.home_dir() / "test-builders" / f"{collection_id}.json"


@router.get("/{collection_id}", response_model=TestBuilderData)
async def get_test_builder(collection_id: str) -> TestBuilderData:
    p = _path(collection_id)
    if not p.exists():
        return TestBuilderData()
    data = json.loads(p.read_text(encoding="utf-8"))
    return TestBuilderData(**data)


@router.put("/{collection_id}", response_model=TestBuilderData)
async def put_test_builder(collection_id: str, body: TestBuilderData) -> TestBuilderData:
    p = _path(collection_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.model_dump_json(indent=2), encoding="utf-8")
    return body
