"""Semantic diff — deep JSON comparison with ignore-keys support.

Endpoint:
- POST /api/diff/semantic — parse two JSON bodies, deep compare, and
  return structured change list.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/diff", tags=["diff"])

# Keys commonly containing non-deterministic values.
_DEFAULT_IGNORE = frozenset({
    "timestamp", "timestamps", "created_at", "updated_at",
    "modified_at", "date", "datetime",
    "trace_id", "traceId", "request_id", "requestId",
    "correlation_id", "correlationId", "x-request-id",
})


class DiffChange(BaseModel):
    path: str
    type: Literal["added", "removed", "changed"]
    old_value: Any = None
    new_value: Any = None


class SemanticDiffInput(BaseModel):
    body_a: str
    body_b: str
    ignore_keys: list[str] = Field(default_factory=list)
    ignore_array_order: bool = False


class SemanticDiffOutput(BaseModel):
    identical: bool
    changes: list[DiffChange] = Field(default_factory=list)


def _deep_compare(
    a: Any,
    b: Any,
    path: str,
    ignore: frozenset[str],
    ignore_array_order: bool,
) -> list[DiffChange]:
    """Recursively compare two values and collect differences."""
    changes: list[DiffChange] = []

    if isinstance(a, dict) and isinstance(b, dict):
        all_keys = set(a.keys()) | set(b.keys())
        for key in sorted(all_keys):
            if key in ignore:
                continue
            child_path = f"{path}.{key}" if path else key
            if key not in a:
                changes.append(DiffChange(
                    path=child_path, type="added", new_value=b[key],
                ))
            elif key not in b:
                changes.append(DiffChange(
                    path=child_path, type="removed", old_value=a[key],
                ))
            else:
                changes.extend(
                    _deep_compare(a[key], b[key], child_path, ignore, ignore_array_order)
                )
    elif isinstance(a, list) and isinstance(b, list):
        if ignore_array_order:
            # Sort-then-compare for order-independent matching.
            try:
                sorted_a = sorted(a, key=lambda x: json.dumps(x, sort_keys=True, default=str))
                sorted_b = sorted(b, key=lambda x: json.dumps(x, sort_keys=True, default=str))
                a, b = sorted_a, sorted_b
            except TypeError:
                pass  # Fall through to positional comparison.

        max_len = max(len(a), len(b))
        for i in range(max_len):
            child_path = f"{path}[{i}]"
            if i >= len(a):
                changes.append(DiffChange(
                    path=child_path, type="added", new_value=b[i],
                ))
            elif i >= len(b):
                changes.append(DiffChange(
                    path=child_path, type="removed", old_value=a[i],
                ))
            else:
                changes.extend(
                    _deep_compare(a[i], b[i], child_path, ignore, ignore_array_order)
                )
    else:
        if a != b:
            changes.append(DiffChange(
                path=path or "$", type="changed", old_value=a, new_value=b,
            ))

    return changes


@router.post("/semantic", response_model=SemanticDiffOutput)
async def semantic_diff(body: SemanticDiffInput) -> SemanticDiffOutput:
    try:
        a = json.loads(body.body_a)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"body_a is not valid JSON: {e}") from e

    try:
        b = json.loads(body.body_b)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"body_b is not valid JSON: {e}") from e

    ignore = _DEFAULT_IGNORE | frozenset(body.ignore_keys)
    changes = _deep_compare(a, b, "$", ignore, body.ignore_array_order)

    return SemanticDiffOutput(identical=len(changes) == 0, changes=changes)
