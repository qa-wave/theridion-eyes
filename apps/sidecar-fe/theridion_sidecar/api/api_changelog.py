"""API changelog detector — compare current responses against stored snapshots."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import storage
from ..environments import get as get_env, substitute
from .timeline import _path_for as timeline_path_for, RequestTimeline

router = APIRouter(prefix="/api/changelog", tags=["changelog"])


class FieldChange(BaseModel):
    path: str
    type: str  # "added", "removed", "type_changed", "value_changed"
    old_value: str | None = None
    new_value: str | None = None


class ChangelogEntry(BaseModel):
    request_name: str
    changes: list[FieldChange] = Field(default_factory=list)
    breaking: bool = False


class ChangelogResult(BaseModel):
    collection_name: str
    entries: list[ChangelogEntry] = Field(default_factory=list)
    breaking_changes: int = 0
    total_changes: int = 0
    timestamp: float = 0


class DetectInput(BaseModel):
    collection_id: str
    environment_id: str | None = None


def _diff_json(old: Any, new: Any, prefix: str = "$") -> list[FieldChange]:
    """Recursively compare two JSON structures and return field-level changes."""
    changes: list[FieldChange] = []
    if type(old) != type(new):
        changes.append(FieldChange(
            path=prefix,
            type="type_changed",
            old_value=type(old).__name__,
            new_value=type(new).__name__,
        ))
        return changes

    if isinstance(old, dict) and isinstance(new, dict):
        all_keys = set(old.keys()) | set(new.keys())
        for key in sorted(all_keys):
            child_path = f"{prefix}.{key}"
            if key not in old:
                changes.append(FieldChange(path=child_path, type="added", new_value=_summarize(new[key])))
            elif key not in new:
                changes.append(FieldChange(path=child_path, type="removed", old_value=_summarize(old[key])))
            else:
                changes.extend(_diff_json(old[key], new[key], child_path))
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) > 0 and len(new) > 0:
            changes.extend(_diff_json(old[0], new[0], f"{prefix}[0]"))
        elif len(old) == 0 and len(new) > 0:
            changes.append(FieldChange(path=prefix, type="added", new_value=f"array({len(new)} items)"))
        elif len(old) > 0 and len(new) == 0:
            changes.append(FieldChange(path=prefix, type="removed", old_value=f"array({len(old)} items)"))
    else:
        if type(old).__name__ != type(new).__name__:
            changes.append(FieldChange(
                path=prefix,
                type="type_changed",
                old_value=type(old).__name__,
                new_value=type(new).__name__,
            ))
    return changes


def _summarize(val: Any) -> str:
    if isinstance(val, dict):
        return f"object({len(val)} keys)"
    if isinstance(val, list):
        return f"array({len(val)} items)"
    return str(val)[:100]


def _flatten_requests(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("is_folder"):
            out.extend(_flatten_requests(item.get("items", [])))
        else:
            out.append(item)
    return out


@router.post("/detect", response_model=ChangelogResult)
async def detect_changes(body: DetectInput) -> ChangelogResult:
    coll = storage.get(body.collection_id)
    if coll is None:
        return ChangelogResult(collection_name="unknown", timestamp=time.time())

    env = get_env(body.environment_id) if body.environment_id else None

    items = _flatten_requests([it.model_dump() for it in coll.items])
    entries: list[ChangelogEntry] = []
    total_breaking = 0
    total_changes = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for item in items:
            url = substitute(item.get("url", ""), env)
            method = item.get("method", "GET")
            name = item.get("name", url)
            req_id = item.get("id", "")
            if not url:
                continue

            # Get previous snapshot
            tl_path = timeline_path_for(req_id)
            prev_body_str: str | None = None
            if tl_path.exists():
                try:
                    tl = RequestTimeline(**json.loads(tl_path.read_text()))
                    if tl.snapshots:
                        prev_body_str = tl.snapshots[-1].body_preview
                except Exception:
                    pass

            # Execute current request
            try:
                headers_raw = item.get("headers", {})
                if isinstance(headers_raw, str):
                    try:
                        headers_raw = json.loads(headers_raw)
                    except Exception:
                        headers_raw = {}
                headers_sub = {k: substitute(str(v), env) for k, v in headers_raw.items()}
                resp = await client.request(method, url, headers=headers_sub, timeout=15)
                try:
                    current_json = resp.json()
                except Exception:
                    current_json = None
            except Exception:
                continue

            if prev_body_str and current_json is not None:
                try:
                    prev_json = json.loads(prev_body_str)
                except Exception:
                    prev_json = None

                if prev_json is not None:
                    changes = _diff_json(prev_json, current_json)
                    is_breaking = any(c.type in ("removed", "type_changed") for c in changes)
                    if changes:
                        entries.append(ChangelogEntry(
                            request_name=name,
                            changes=changes,
                            breaking=is_breaking,
                        ))
                        total_changes += len(changes)
                        if is_breaking:
                            total_breaking += 1

    return ChangelogResult(
        collection_name=coll.name,
        entries=entries,
        breaking_changes=total_breaking,
        total_changes=total_changes,
        timestamp=time.time(),
    )
