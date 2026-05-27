"""Persistent request history with search, filtering, and stats.

History is stored as a JSON-lines file at ``$THERIDION_HOME/history.jsonl``.
Each line is a self-contained JSON object representing one executed request.
A maximum of 1000 entries are kept (FIFO — oldest trimmed first).
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from theridion_sidecar.storage import home_dir

router = APIRouter(prefix="/api/history", tags=["history"])

MAX_ENTRIES = 1000
BODY_MAX_BYTES = 10_000  # truncate request/response bodies to 10 KB


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class HistoryEntryCreate(BaseModel):
    """Payload accepted by POST /api/history."""

    method: str
    url: str
    status: int
    elapsed_ms: float
    timestamp: float
    request_body: str | None = None
    response_body: str | None = None
    request_headers: dict[str, str] = Field(default_factory=dict)
    response_headers: dict[str, str] = Field(default_factory=dict)


class HistoryEntry(BaseModel):
    """Full history entry as stored on disk."""

    id: str
    method: str
    url: str
    status: int
    elapsed_ms: float
    timestamp: float
    request_body: str | None = None
    response_body: str | None = None
    request_headers: dict[str, str] = Field(default_factory=dict)
    response_headers: dict[str, str] = Field(default_factory=dict)


class HistoryEntrySummary(BaseModel):
    """Lightweight view returned by list endpoint (no bodies)."""

    id: str
    method: str
    url: str
    status: int
    elapsed_ms: float
    timestamp: float


class HistoryListResponse(BaseModel):
    entries: list[HistoryEntrySummary]
    total: int


class HistoryStats(BaseModel):
    total: int
    avg_response_time_ms: float
    status_distribution: dict[str, int]
    top_endpoints: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _history_path() -> Path:
    d = home_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "history.jsonl"


def _read_all() -> list[dict[str, Any]]:
    """Read all history entries from the JSONL file."""
    p = _history_path()
    if not p.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _write_all(entries: list[dict[str, Any]]) -> None:
    """Atomically rewrite the JSONL file."""
    p = _history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix="history.", suffix=".jsonl.tmp", dir=str(p.parent),
    )
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, p)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _truncate(text: str | None) -> str | None:
    if text is None:
        return None
    if len(text) > BODY_MAX_BYTES:
        return text[:BODY_MAX_BYTES]
    return text


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
def record_entry(payload: HistoryEntryCreate) -> HistoryEntry:
    """Record a new history entry."""
    entry = HistoryEntry(
        id=str(uuid.uuid4()),
        method=payload.method.upper(),
        url=payload.url,
        status=payload.status,
        elapsed_ms=payload.elapsed_ms,
        timestamp=payload.timestamp,
        request_body=_truncate(payload.request_body),
        response_body=_truncate(payload.response_body),
        request_headers=payload.request_headers,
        response_headers=payload.response_headers,
    )
    entries = _read_all()
    entries.insert(0, entry.model_dump())
    # FIFO trim
    if len(entries) > MAX_ENTRIES:
        entries = entries[:MAX_ENTRIES]
    _write_all(entries)
    return entry


@router.get("", response_model=HistoryListResponse)
def list_entries(
    method: str | None = Query(None),
    status: int | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> HistoryListResponse:
    """List history entries with optional filters."""
    entries = _read_all()

    # Filter by method
    if method:
        m = method.upper()
        entries = [e for e in entries if e.get("method", "").upper() == m]

    # Filter by status class (e.g. 200 matches exact, or pass 2/3/4/5 for class)
    if status is not None:
        if status < 10:
            # Status class: 2 → 2xx, 4 → 4xx
            entries = [e for e in entries if e.get("status", 0) // 100 == status]
        else:
            entries = [e for e in entries if e.get("status") == status]

    # Keyword search in URL or method
    if search:
        q = search.lower()
        entries = [
            e for e in entries
            if q in e.get("url", "").lower() or q in e.get("method", "").lower()
        ]

    total = len(entries)
    page = entries[offset:offset + limit]

    summaries = [
        HistoryEntrySummary(
            id=e["id"],
            method=e["method"],
            url=e["url"],
            status=e["status"],
            elapsed_ms=e["elapsed_ms"],
            timestamp=e["timestamp"],
        )
        for e in page
    ]
    return HistoryListResponse(entries=summaries, total=total)


@router.get("/stats", response_model=HistoryStats)
def get_stats() -> HistoryStats:
    """Return aggregate stats over all history entries."""
    entries = _read_all()
    total = len(entries)
    if total == 0:
        return HistoryStats(
            total=0,
            avg_response_time_ms=0.0,
            status_distribution={},
            top_endpoints=[],
        )

    avg_ms = sum(e.get("elapsed_ms", 0) for e in entries) / total

    status_counter: Counter[str] = Counter()
    for e in entries:
        s = e.get("status", 0)
        bucket = f"{s // 100}xx"
        status_counter[bucket] += 1

    endpoint_counter: Counter[str] = Counter()
    for e in entries:
        key = f"{e.get('method', '?')} {e.get('url', '?')}"
        endpoint_counter[key] += 1

    top = [
        {"endpoint": k, "count": v}
        for k, v in endpoint_counter.most_common(10)
    ]

    return HistoryStats(
        total=total,
        avg_response_time_ms=round(avg_ms, 2),
        status_distribution=dict(status_counter),
        top_endpoints=top,
    )


@router.get("/{entry_id}", response_model=HistoryEntry)
def get_entry(entry_id: str) -> HistoryEntry:
    """Get a single history entry with full bodies."""
    entries = _read_all()
    for e in entries:
        if e.get("id") == entry_id:
            return HistoryEntry(**e)
    raise HTTPException(status_code=404, detail=f"history entry {entry_id} not found")


@router.delete("", status_code=204)
def clear_all() -> None:
    """Delete all history entries."""
    p = _history_path()
    if p.exists():
        p.unlink()


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: str) -> None:
    """Delete a single history entry."""
    entries = _read_all()
    new_entries = [e for e in entries if e.get("id") != entry_id]
    if len(new_entries) == len(entries):
        raise HTTPException(status_code=404, detail=f"history entry {entry_id} not found")
    _write_all(new_entries)
