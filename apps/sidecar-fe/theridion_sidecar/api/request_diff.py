"""Compare two saved requests and return structured diff."""

from __future__ import annotations

import difflib
import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import storage
from ..storage import _walk

router = APIRouter(prefix="/api/requests", tags=["request-diff"])


# ---- Input / Output models ---------------------------------------------------


class RequestRef(BaseModel):
    collection_id: str
    request_id: str


class DiffInput(BaseModel):
    left: RequestRef
    right: RequestRef


class UrlDiff(BaseModel):
    left: str
    right: str


class HeaderChange(BaseModel):
    name: str
    type: Literal["added", "removed", "changed"]
    left_value: str | None = None
    right_value: str | None = None


class BodyDiff(BaseModel):
    format: Literal["json", "text"]
    changes: list[dict[str, Any]]
    unified: str


class AuthDiff(BaseModel):
    left_type: str
    right_type: str
    details: str


class DiffOutput(BaseModel):
    method_changed: bool
    url_diff: UrlDiff | None = None
    header_changes: list[HeaderChange]
    body_diff: BodyDiff | None = None
    auth_diff: AuthDiff | None = None
    summary: str


# ---- Helpers -----------------------------------------------------------------


def _find_request(collection_id: str, request_id: str):
    """Load a request item from storage, raise HTTPException if not found."""
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found")
    for item in _walk(coll.items):
        if not item.is_folder and item.id == request_id:
            return item
    raise HTTPException(status_code=404, detail=f"Request {request_id} not found in collection {collection_id}")


def _diff_headers(left: dict[str, str], right: dict[str, str]) -> list[HeaderChange]:
    changes: list[HeaderChange] = []
    all_keys = sorted(set(left.keys()) | set(right.keys()))
    for key in all_keys:
        if key not in left:
            changes.append(HeaderChange(name=key, type="added", left_value=None, right_value=right[key]))
        elif key not in right:
            changes.append(HeaderChange(name=key, type="removed", left_value=left[key], right_value=None))
        elif left[key] != right[key]:
            changes.append(HeaderChange(name=key, type="changed", left_value=left[key], right_value=right[key]))
    return changes


def _diff_body(left_body: str | None, right_body: str | None) -> BodyDiff | None:
    left_str = left_body or ""
    right_str = right_body or ""
    if left_str == right_str:
        return None

    # Try JSON structural diff
    try:
        left_obj = json.loads(left_str)
        right_obj = json.loads(right_str)
        changes = _json_structural_diff(left_obj, right_obj, "$")
        unified = "\n".join(
            difflib.unified_diff(
                json.dumps(left_obj, indent=2).splitlines(),
                json.dumps(right_obj, indent=2).splitlines(),
                fromfile="left",
                tofile="right",
                lineterm="",
            )
        )
        return BodyDiff(format="json", changes=changes, unified=unified)
    except (json.JSONDecodeError, ValueError):
        pass

    # Fall back to line diff
    unified = "\n".join(
        difflib.unified_diff(
            left_str.splitlines(),
            right_str.splitlines(),
            fromfile="left",
            tofile="right",
            lineterm="",
        )
    )
    return BodyDiff(format="text", changes=[{"type": "text_diff"}], unified=unified)


def _json_structural_diff(left: Any, right: Any, path: str) -> list[dict[str, Any]]:
    """Recursively compare two JSON values, returning a list of changes."""
    changes: list[dict[str, Any]] = []
    if type(left) != type(right):
        changes.append({"path": path, "type": "type_changed", "left": repr(left), "right": repr(right)})
        return changes
    if isinstance(left, dict):
        all_keys = sorted(set(left.keys()) | set(right.keys()))
        for key in all_keys:
            child_path = f"{path}.{key}"
            if key not in left:
                changes.append({"path": child_path, "type": "added", "value": right[key]})
            elif key not in right:
                changes.append({"path": child_path, "type": "removed", "value": left[key]})
            else:
                changes.extend(_json_structural_diff(left[key], right[key], child_path))
    elif isinstance(left, list):
        for i in range(max(len(left), len(right))):
            child_path = f"{path}[{i}]"
            if i >= len(left):
                changes.append({"path": child_path, "type": "added", "value": right[i]})
            elif i >= len(right):
                changes.append({"path": child_path, "type": "removed", "value": left[i]})
            else:
                changes.extend(_json_structural_diff(left[i], right[i], child_path))
    else:
        if left != right:
            changes.append({"path": path, "type": "changed", "left": left, "right": right})
    return changes


def _diff_auth(left_auth, right_auth) -> AuthDiff | None:
    left_type = left_auth.type if left_auth else "none"
    right_type = right_auth.type if right_auth else "none"
    if left_type == right_type == "none":
        return None

    left_dict = left_auth.model_dump() if left_auth else {"type": "none"}
    right_dict = right_auth.model_dump() if right_auth else {"type": "none"}

    if left_dict == right_dict:
        return None

    details_parts: list[str] = []
    if left_type != right_type:
        details_parts.append(f"Type changed from '{left_type}' to '{right_type}'")
    else:
        # Same type, different values
        for key in sorted(set(left_dict.keys()) | set(right_dict.keys())):
            if key == "type":
                continue
            lv = left_dict.get(key)
            rv = right_dict.get(key)
            if lv != rv:
                details_parts.append(f"{key}: '{lv}' -> '{rv}'")

    return AuthDiff(
        left_type=left_type,
        right_type=right_type,
        details="; ".join(details_parts) if details_parts else "values differ",
    )


# ---- Endpoint ----------------------------------------------------------------


@router.post("/diff", response_model=DiffOutput)
async def diff_requests(payload: DiffInput) -> DiffOutput:
    """Compare two saved requests and return a structured diff."""
    left_item = _find_request(payload.left.collection_id, payload.left.request_id)
    right_item = _find_request(payload.right.collection_id, payload.right.request_id)

    left_method = left_item.method or "GET"
    right_method = right_item.method or "GET"
    method_changed = left_method != right_method

    left_url = left_item.url or ""
    right_url = right_item.url or ""
    url_diff = UrlDiff(left=left_url, right=right_url) if left_url != right_url else None

    header_changes = _diff_headers(left_item.headers, right_item.headers)
    body_diff = _diff_body(left_item.body, right_item.body)
    auth_diff = _diff_auth(left_item.auth, right_item.auth)

    # Build summary
    change_count = 0
    if method_changed:
        change_count += 1
    if url_diff:
        change_count += 1
    change_count += len(header_changes)
    if body_diff:
        change_count += 1
    if auth_diff:
        change_count += 1

    if change_count == 0:
        summary = "No changes"
    elif change_count == 1:
        summary = "1 change found"
    else:
        summary = f"{change_count} changes found"

    return DiffOutput(
        method_changed=method_changed,
        url_diff=url_diff,
        header_changes=header_changes,
        body_diff=body_diff,
        auth_diff=auth_diff,
        summary=summary,
    )
