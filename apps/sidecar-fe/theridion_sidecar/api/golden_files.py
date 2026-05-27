"""Golden file storage and comparison for response regression detection.

Stores baseline ("golden") responses and compares future responses against
them to detect regressions. File-backed in ~/.theridion/golden_files/.
"""

from __future__ import annotations

import difflib
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from theridion_sidecar import storage

router = APIRouter(prefix="/api/golden", tags=["golden-files"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GoldenFile(BaseModel):
    id: str
    name: str
    request_id: str | None = None
    collection_id: str | None = None
    url: str
    method: str
    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    body_size: int = 0
    created_at: float = 0.0
    description: str = ""


class SaveGoldenInput(BaseModel):
    name: str = ""
    request_id: str | None = None
    collection_id: str | None = None
    url: str
    method: str = "GET"
    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    description: str = ""


class CompareInput(BaseModel):
    golden_id: str
    current: CurrentResponse


class CurrentResponse(BaseModel):
    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""


class AutoCompareInput(BaseModel):
    url: str
    method: str = "GET"
    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""


class HeaderChange(BaseModel):
    key: str
    type: str  # "added", "removed", "changed"
    golden_value: str | None = None
    current_value: str | None = None


class BodyDiff(BaseModel):
    additions: int = 0
    deletions: int = 0
    changes: list[str] = Field(default_factory=list)


class CompareOutput(BaseModel):
    match: bool
    status_match: bool
    body_match: bool
    header_changes: list[HeaderChange] = Field(default_factory=list)
    body_diff: BodyDiff = Field(default_factory=BodyDiff)
    score: float = 1.0


class AutoCompareOutput(BaseModel):
    found: bool = False
    golden_id: str | None = None
    golden_name: str | None = None
    comparison: CompareOutput | None = None


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _golden_dir() -> Path:
    d = storage.home_dir() / "golden_files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(golden_id: str) -> Path:
    # Validate UUID format
    safe = uuid.UUID(golden_id)
    return _golden_dir() / f"{safe}.json"


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically via temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load(golden_id: str) -> GoldenFile:
    path = _path_for(golden_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Golden file {golden_id} not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    return GoldenFile(**data)


def _list_all() -> list[GoldenFile]:
    d = _golden_dir()
    results: list[GoldenFile] = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append(GoldenFile(**data))
        except (json.JSONDecodeError, ValueError):
            continue
    return results


# ---------------------------------------------------------------------------
# Comparison logic
# ---------------------------------------------------------------------------


def _compare_responses(golden: GoldenFile, current: CurrentResponse) -> CompareOutput:
    status_match = golden.status == current.status

    # Header comparison
    header_changes: list[HeaderChange] = []
    golden_headers = {k.lower(): v for k, v in golden.headers.items()}
    current_headers = {k.lower(): v for k, v in current.headers.items()}

    for key, val in golden_headers.items():
        if key not in current_headers:
            header_changes.append(HeaderChange(
                key=key, type="removed", golden_value=val, current_value=None
            ))
        elif current_headers[key] != val:
            header_changes.append(HeaderChange(
                key=key, type="changed", golden_value=val, current_value=current_headers[key]
            ))
    for key, val in current_headers.items():
        if key not in golden_headers:
            header_changes.append(HeaderChange(
                key=key, type="added", golden_value=None, current_value=val
            ))

    # Body comparison
    golden_body = golden.body
    current_body = current.body
    body_match = golden_body == current_body

    # Generate diff lines
    body_diff = BodyDiff()
    if not body_match:
        golden_lines = golden_body.splitlines(keepends=True)
        current_lines = current_body.splitlines(keepends=True)
        diff = list(difflib.unified_diff(golden_lines, current_lines, n=3))
        additions = 0
        deletions = 0
        changes: list[str] = []
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        body_diff.additions = additions
        body_diff.deletions = deletions
        # Include up to 20 diff lines for display
        body_diff.changes = [l.rstrip("\n") for l in diff[:20]]

    # Calculate similarity score
    if golden_body and current_body:
        ratio = difflib.SequenceMatcher(None, golden_body, current_body).ratio()
    elif golden_body == current_body:
        ratio = 1.0
    else:
        ratio = 0.0

    # Weighted score: status 30%, headers 20%, body 50%
    status_score = 1.0 if status_match else 0.0
    header_score = 1.0 if not header_changes else max(0.0, 1.0 - len(header_changes) * 0.1)
    body_score = ratio

    score = status_score * 0.3 + header_score * 0.2 + body_score * 0.5

    match = status_match and body_match and not header_changes

    return CompareOutput(
        match=match,
        status_match=status_match,
        body_match=body_match,
        header_changes=header_changes,
        body_diff=body_diff,
        score=round(score, 4),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/save", response_model=GoldenFile)
async def save_golden(inp: SaveGoldenInput) -> GoldenFile:
    """Save a response as a golden file baseline."""
    golden_id = str(uuid.uuid4())
    golden = GoldenFile(
        id=golden_id,
        name=inp.name or f"{inp.method} {inp.url}",
        request_id=inp.request_id,
        collection_id=inp.collection_id,
        url=inp.url,
        method=inp.method,
        status=inp.status,
        headers=inp.headers,
        body=inp.body,
        body_size=len(inp.body.encode("utf-8")),
        created_at=time.time(),
        description=inp.description,
    )
    _atomic_write(_path_for(golden_id), golden.model_dump())
    return golden


@router.get("", response_model=list[GoldenFile])
async def list_golden() -> list[GoldenFile]:
    """List all golden files."""
    return _list_all()


@router.get("/{golden_id}", response_model=GoldenFile)
async def get_golden(golden_id: str) -> GoldenFile:
    """Get a specific golden file."""
    return _load(golden_id)


@router.delete("/{golden_id}")
async def delete_golden(golden_id: str) -> dict[str, str]:
    """Delete a golden file."""
    path = _path_for(golden_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Golden file {golden_id} not found")
    path.unlink()
    return {"status": "deleted", "id": golden_id}


@router.post("/compare", response_model=CompareOutput)
async def compare_golden(inp: CompareInput) -> CompareOutput:
    """Compare a current response against a stored golden file."""
    golden = _load(inp.golden_id)
    return _compare_responses(golden, inp.current)


@router.post("/auto-compare", response_model=AutoCompareOutput)
async def auto_compare(inp: AutoCompareInput) -> AutoCompareOutput:
    """Find a matching golden file by URL/method and compare."""
    all_golden = _list_all()

    # Find golden file matching URL and method
    matching: GoldenFile | None = None
    for g in all_golden:
        if g.url == inp.url and g.method.upper() == inp.method.upper():
            matching = g
            break

    if not matching:
        return AutoCompareOutput(found=False)

    current = CurrentResponse(
        status=inp.status,
        headers=inp.headers,
        body=inp.body,
    )
    comparison = _compare_responses(matching, current)

    return AutoCompareOutput(
        found=True,
        golden_id=matching.id,
        golden_name=matching.name,
        comparison=comparison,
    )
