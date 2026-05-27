"""Response timeline — track response snapshots over time per request."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..storage import home_dir

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


class ResponseSnapshot(BaseModel):
    timestamp: float
    status: int
    body_hash: str
    body_preview: str = ""
    headers_hash: str = ""
    elapsed_ms: float = 0
    body_size: int = 0
    changes: list[str] = Field(default_factory=list)


class RequestTimeline(BaseModel):
    request_id: str
    snapshots: list[ResponseSnapshot] = Field(default_factory=list)


def _dir() -> Path:
    d = home_dir() / "timeline"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(request_id: str) -> Path:
    safe = request_id.replace("/", "_").replace("..", "")
    return _dir() / f"{safe}.json"


class RecordInput(BaseModel):
    request_id: str
    status: int
    body: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    elapsed_ms: float = 0


@router.post("/record", response_model=RequestTimeline)
def record_snapshot(body: RecordInput) -> RequestTimeline:
    import hashlib
    p = _path_for(body.request_id)
    tl = RequestTimeline(request_id=body.request_id)
    if p.exists():
        try:
            tl = RequestTimeline(**json.loads(p.read_text()))
        except Exception:
            pass

    body_hash = hashlib.sha256(body.body.encode()).hexdigest()[:16]
    headers_hash = hashlib.sha256(json.dumps(body.headers, sort_keys=True).encode()).hexdigest()[:16]

    changes: list[str] = []
    if tl.snapshots:
        prev = tl.snapshots[-1]
        if prev.status != body.status:
            changes.append(f"status {prev.status}→{body.status}")
        if prev.body_hash != body_hash:
            changes.append("body changed")
        if prev.headers_hash != headers_hash:
            changes.append("headers changed")

    snap = ResponseSnapshot(
        timestamp=time.time(),
        status=body.status,
        body_hash=body_hash,
        body_preview=body.body[:200],
        headers_hash=headers_hash,
        elapsed_ms=body.elapsed_ms,
        body_size=len(body.body.encode()),
        changes=changes,
    )
    tl.snapshots.append(snap)
    # Keep last 100 snapshots
    tl.snapshots = tl.snapshots[-100:]

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tl.model_dump(mode="json"), indent=2))
    return tl


@router.get("/{request_id}", response_model=RequestTimeline)
def get_timeline(request_id: str) -> RequestTimeline:
    p = _path_for(request_id)
    if not p.exists():
        return RequestTimeline(request_id=request_id)
    try:
        return RequestTimeline(**json.loads(p.read_text()))
    except Exception:
        return RequestTimeline(request_id=request_id)
