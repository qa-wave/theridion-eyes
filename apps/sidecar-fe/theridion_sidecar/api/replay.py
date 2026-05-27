"""Traffic Replay: HAR import + replay + diff engine.

Accepts HAR JSON or an existing collection, replays every request via
httpx, and deep-diffs original vs replayed responses.  The diff engine
walks both JSON trees and reports added / removed / changed paths,
honouring an ignore-list for inherently volatile fields like Date
headers and trace IDs.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage

router = APIRouter(prefix="/api/replay", tags=["replay"])


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------

class ReplayInput(BaseModel):
    har_content: str  # Raw HAR JSON
    environment_id: str | None = None
    collection_name: str = "HAR Replay"
    ignore_paths: list[str] = Field(default_factory=lambda: [
        "$.headers.Date",
        "$.headers.X-Request-Id",
        "$.body.timestamp",
        "$.body.request_id",
        "$.body.trace_id",
    ])


class CollectionReplayInput(BaseModel):
    collection_id: str
    environment_id: str | None = None


class ReplayDiff(BaseModel):
    request_name: str
    method: str
    url: str
    original_status: int
    replay_status: int
    status_match: bool
    body_match: bool
    body_diffs: list[dict[str, Any]]  # [{path, original, replayed}]
    header_diffs: list[dict[str, Any]]
    original_elapsed_ms: float
    replay_elapsed_ms: float


class ReplayOutput(BaseModel):
    total_requests: int
    replayed: int
    matches: int
    diffs: int
    errors: int
    results: list[ReplayDiff]
    collection_id: str | None = None
    elapsed_ms: float


# ---------------------------------------------------------------------------
# JSON deep-diff
# ---------------------------------------------------------------------------

def _normalize_ignore(paths: list[str]) -> set[str]:
    """Strip leading ``$.`` so we can match raw dotted paths."""
    out: set[str] = set()
    for p in paths:
        cleaned = p.lstrip("$").lstrip(".")
        if cleaned:
            out.add(cleaned)
    return out


def _deep_diff(
    original: Any,
    replayed: Any,
    prefix: str = "",
    ignore: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Walk two JSON-like trees and return a list of diffs."""
    ignore = ignore or set()
    diffs: list[dict[str, Any]] = []

    if prefix in ignore:
        return diffs

    if isinstance(original, dict) and isinstance(replayed, dict):
        all_keys = set(original.keys()) | set(replayed.keys())
        for key in sorted(all_keys):
            child_path = f"{prefix}.{key}" if prefix else key
            if child_path in ignore:
                continue
            if key not in original:
                diffs.append({"path": child_path, "original": None, "replayed": replayed[key]})
            elif key not in replayed:
                diffs.append({"path": child_path, "original": original[key], "replayed": None})
            else:
                diffs.extend(_deep_diff(original[key], replayed[key], child_path, ignore))
    elif isinstance(original, list) and isinstance(replayed, list):
        for i in range(max(len(original), len(replayed))):
            child_path = f"{prefix}[{i}]"
            if i >= len(original):
                diffs.append({"path": child_path, "original": None, "replayed": replayed[i]})
            elif i >= len(replayed):
                diffs.append({"path": child_path, "original": original[i], "replayed": None})
            else:
                diffs.extend(_deep_diff(original[i], replayed[i], child_path, ignore))
    elif original != replayed:
        diffs.append({"path": prefix or "$", "original": original, "replayed": replayed})

    return diffs


# ---------------------------------------------------------------------------
# HAR parsing helpers
# ---------------------------------------------------------------------------

def _parse_har_entries(har_json: str) -> list[dict[str, Any]]:
    """Extract a flat list of replay-able entries from HAR JSON."""
    try:
        har = json.loads(har_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid HAR JSON: {exc}") from exc

    log = har.get("log", har)  # some HARs nest under "log"
    raw_entries = log.get("entries", [])
    if not raw_entries:
        raise HTTPException(status_code=400, detail="HAR contains no entries")

    entries: list[dict[str, Any]] = []
    for idx, entry in enumerate(raw_entries):
        req = entry.get("request", {})
        resp = entry.get("response", {})
        method = req.get("method", "GET").upper()
        url = req.get("url", "")
        if not url:
            continue

        # Headers as dict (last value wins for dupes).
        headers: dict[str, str] = {}
        for h in req.get("headers", []):
            headers[h["name"]] = h["value"]

        # Request body (postData).
        body: str | None = None
        post = req.get("postData")
        if post:
            body = post.get("text")

        # Original response.
        resp_status = resp.get("status", 0)
        resp_headers: dict[str, str] = {}
        for h in resp.get("headers", []):
            resp_headers[h["name"]] = h["value"]
        resp_body = ""
        content = resp.get("content", {})
        if content:
            resp_body = content.get("text", "")

        elapsed_ms = entry.get("time", 0.0)

        entries.append({
            "name": f"{method} {url.split('?')[0].split('/')[-1] or url}" if idx == 0 else f"{method} {url.split('?')[0].split('/')[-1] or url}",
            "method": method,
            "url": url,
            "headers": headers,
            "body": body,
            "original_status": resp_status,
            "original_headers": resp_headers,
            "original_body": resp_body,
            "original_elapsed_ms": elapsed_ms,
        })
    return entries


# ---------------------------------------------------------------------------
# Replay engine
# ---------------------------------------------------------------------------

async def _replay_entries(
    entries: list[dict[str, Any]],
    ignore_paths: list[str],
) -> tuple[list[ReplayDiff], int, int, int]:
    """Replay each entry via httpx and diff against originals.

    Returns (results, matches, diffs, errors).
    """
    ignore = _normalize_ignore(ignore_paths)
    body_ignore = {p.removeprefix("body.") for p in ignore if p.startswith("body.")}
    header_ignore = {p.removeprefix("headers.") for p in ignore if p.startswith("headers.")}

    results: list[ReplayDiff] = []
    matches = 0
    diffs_count = 0
    errors = 0

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for entry in entries:
            try:
                t0 = time.perf_counter()
                resp = await client.request(
                    method=entry["method"],
                    url=entry["url"],
                    headers=entry.get("headers", {}),
                    content=entry.get("body"),
                )
                replay_elapsed = (time.perf_counter() - t0) * 1000.0
            except Exception:
                errors += 1
                results.append(ReplayDiff(
                    request_name=entry.get("name", entry["url"]),
                    method=entry["method"],
                    url=entry["url"],
                    original_status=entry.get("original_status", 0),
                    replay_status=0,
                    status_match=False,
                    body_match=False,
                    body_diffs=[],
                    header_diffs=[],
                    original_elapsed_ms=entry.get("original_elapsed_ms", 0),
                    replay_elapsed_ms=0,
                ))
                continue

            status_match = entry.get("original_status", 0) == resp.status_code

            # Body diff.
            original_body_parsed: Any = entry.get("original_body", "")
            replay_body_text = resp.text
            replay_body_parsed: Any = replay_body_text
            try:
                original_body_parsed = json.loads(entry.get("original_body", ""))
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                replay_body_parsed = json.loads(replay_body_text)
            except (json.JSONDecodeError, TypeError):
                pass

            body_diffs = _deep_diff(original_body_parsed, replay_body_parsed, "", body_ignore)
            body_match = len(body_diffs) == 0

            # Header diff.
            orig_headers = entry.get("original_headers", {})
            replay_headers = dict(resp.headers)
            header_diffs = _deep_diff(orig_headers, replay_headers, "", header_ignore)

            if status_match and body_match:
                matches += 1
            else:
                diffs_count += 1

            results.append(ReplayDiff(
                request_name=entry.get("name", entry["url"]),
                method=entry["method"],
                url=entry["url"],
                original_status=entry.get("original_status", 0),
                replay_status=resp.status_code,
                status_match=status_match,
                body_match=body_match,
                body_diffs=body_diffs,
                header_diffs=header_diffs,
                original_elapsed_ms=entry.get("original_elapsed_ms", 0),
                replay_elapsed_ms=round(replay_elapsed, 2),
            ))

    return results, matches, diffs_count, errors


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/from-har")
async def replay_from_har(inp: ReplayInput) -> ReplayOutput:
    """Parse a HAR file and replay all entries, diffing against originals."""
    t0 = time.perf_counter()
    entries = _parse_har_entries(inp.har_content)
    results, matches, diffs_count, errors = await _replay_entries(entries, inp.ignore_paths)
    elapsed = (time.perf_counter() - t0) * 1000.0

    return ReplayOutput(
        total_requests=len(entries),
        replayed=len(results),
        matches=matches,
        diffs=diffs_count,
        errors=errors,
        results=results,
        collection_id=None,
        elapsed_ms=round(elapsed, 2),
    )


@router.post("/run-collection")
async def replay_collection(inp: CollectionReplayInput) -> ReplayOutput:
    """Replay all requests in a collection and diff against last responses."""
    t0 = time.perf_counter()
    try:
        coll = storage.get(inp.collection_id)
    except (ValueError, KeyError):
        coll = None
    if coll is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Flatten items (including nested folders) into replay entries.
    entries: list[dict[str, Any]] = []

    def _flatten(items: list[Any]) -> None:
        for item in items:
            if item.is_folder:
                _flatten(item.items)
            elif item.url:
                entries.append({
                    "name": item.name,
                    "method": item.method or "GET",
                    "url": item.url,
                    "headers": dict(item.headers) if item.headers else {},
                    "body": item.body,
                    "original_status": 0,
                    "original_headers": {},
                    "original_body": "",
                    "original_elapsed_ms": 0,
                })

    _flatten(coll.items)

    results, matches, diffs_count, errors = await _replay_entries(entries, [])
    elapsed = (time.perf_counter() - t0) * 1000.0

    return ReplayOutput(
        total_requests=len(entries),
        replayed=len(results),
        matches=matches,
        diffs=diffs_count,
        errors=errors,
        results=results,
        collection_id=inp.collection_id,
        elapsed_ms=round(elapsed, 2),
    )
