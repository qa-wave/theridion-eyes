"""API versioning: deep diff two OpenAPI specs."""

from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/versioning", tags=["api-versioning"])


class VersionDiffInput(BaseModel):
    v1_spec: str
    v2_spec: str


class VersionDiffOutput(BaseModel):
    breaking_changes: list[str] = []
    non_breaking: list[str] = []
    added: list[str] = []
    removed: list[str] = []
    summary: str = ""


@router.post("/compare", response_model=VersionDiffOutput)
async def compare_versions(body: VersionDiffInput) -> VersionDiffOutput:
    try:
        v1 = json.loads(body.v1_spec)
        v2 = json.loads(body.v2_spec)
    except json.JSONDecodeError as e:
        return VersionDiffOutput(summary=f"JSON parse error: {e}")

    v1_paths = set(v1.get("paths", {}).keys())
    v2_paths = set(v2.get("paths", {}).keys())

    added_paths = sorted(v2_paths - v1_paths)
    removed_paths = sorted(v1_paths - v2_paths)

    breaking: list[str] = []
    non_breaking: list[str] = []

    for p in removed_paths:
        breaking.append(f"Removed path: {p}")

    for p in v1_paths & v2_paths:
        v1_methods = set(k for k in v1["paths"][p] if k in ("get", "post", "put", "delete", "patch"))
        v2_methods = set(k for k in v2["paths"][p] if k in ("get", "post", "put", "delete", "patch"))
        for m in v1_methods - v2_methods:
            breaking.append(f"Removed method {m.upper()} on {p}")
        for m in v2_methods - v1_methods:
            non_breaking.append(f"Added method {m.upper()} on {p}")

    summary_parts = []
    if added_paths:
        summary_parts.append(f"{len(added_paths)} paths added")
    if removed_paths:
        summary_parts.append(f"{len(removed_paths)} paths removed")
    if breaking:
        summary_parts.append(f"{len(breaking)} breaking changes")
    if not summary_parts:
        summary_parts.append("No changes detected")

    return VersionDiffOutput(
        breaking_changes=breaking,
        non_breaking=non_breaking,
        added=added_paths,
        removed=removed_paths,
        summary=", ".join(summary_parts),
    )
