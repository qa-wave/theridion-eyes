"""cURL history log — save and retrieve curl commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from theridion_sidecar import storage

router = APIRouter(prefix="/api/log", tags=["log"])


class CurlLogRequest(BaseModel):
    method: str = "GET"
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None


class CurlLogEntry(BaseModel):
    timestamp: str
    curl: str


class CurlLogResult(BaseModel):
    entries: list[CurlLogEntry]


def _to_curl(method: str, url: str, headers: dict[str, str], body: str | None) -> str:
    parts = [f"curl -X {method}"]
    for k, v in headers.items():
        parts.append(f"-H '{k}: {v}'")
    if body:
        escaped = body.replace("'", "'\\''")
        parts.append(f"-d '{escaped}'")
    parts.append(f"'{url}'")
    return " \\\n  ".join(parts)


def _log_path():
    return storage.home_dir() / "curl_history.jsonl"


@router.post("/curl", response_model=CurlLogEntry)
async def log_curl(req: CurlLogRequest) -> CurlLogEntry:
    curl = _to_curl(req.method, req.url, req.headers, req.body)
    ts = datetime.now(timezone.utc).isoformat()
    entry = CurlLogEntry(timestamp=ts, curl=curl)

    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": ts, "curl": curl}) + "\n")

    return entry


@router.get("/curl", response_model=CurlLogResult)
async def get_curl_log(
    limit: int = Query(default=50, ge=1, le=500),
) -> CurlLogResult:
    path = _log_path()
    entries: list[CurlLogEntry] = []

    if path.exists():
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        for line in lines[-limit:]:
            try:
                data = json.loads(line)
                entries.append(CurlLogEntry(**data))
            except (json.JSONDecodeError, KeyError):
                continue

    return CurlLogResult(entries=entries)
