"""Response comparison — deep-diff two response bodies (JSON or text)."""

from __future__ import annotations

import difflib
import json
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareInput(BaseModel):
    left: str
    right: str
    format: Literal["json", "text"] = "json"


class ChangeEntry(BaseModel):
    path: str
    type: Literal["added", "removed", "changed"]
    old_value: str | None = None
    new_value: str | None = None


class CompareOutput(BaseModel):
    summary: str
    changes: list[ChangeEntry] = Field(default_factory=list)
    diff_text: str = ""


def _deep_diff(
    left: object,
    right: object,
    prefix: str = "",
) -> list[ChangeEntry]:
    """Recursively diff two JSON-compatible objects."""
    changes: list[ChangeEntry] = []

    if isinstance(left, dict) and isinstance(right, dict):
        all_keys = sorted(set(left) | set(right))
        for key in all_keys:
            path = f"{prefix}.{key}" if prefix else key
            if key not in left:
                changes.append(ChangeEntry(
                    path=path,
                    type="added",
                    new_value=json.dumps(right[key], default=str),
                ))
            elif key not in right:
                changes.append(ChangeEntry(
                    path=path,
                    type="removed",
                    old_value=json.dumps(left[key], default=str),
                ))
            else:
                changes.extend(_deep_diff(left[key], right[key], path))
    elif isinstance(left, list) and isinstance(right, list):
        max_len = max(len(left), len(right))
        for i in range(max_len):
            path = f"{prefix}[{i}]"
            if i >= len(left):
                changes.append(ChangeEntry(
                    path=path,
                    type="added",
                    new_value=json.dumps(right[i], default=str),
                ))
            elif i >= len(right):
                changes.append(ChangeEntry(
                    path=path,
                    type="removed",
                    old_value=json.dumps(left[i], default=str),
                ))
            else:
                changes.extend(_deep_diff(left[i], right[i], path))
    elif left != right:
        changes.append(ChangeEntry(
            path=prefix or "$",
            type="changed",
            old_value=json.dumps(left, default=str),
            new_value=json.dumps(right, default=str),
        ))

    return changes


def _build_summary(changes: list[ChangeEntry]) -> str:
    added = sum(1 for c in changes if c.type == "added")
    removed = sum(1 for c in changes if c.type == "removed")
    changed = sum(1 for c in changes if c.type == "changed")
    if added == 0 and removed == 0 and changed == 0:
        return "Responses are identical"
    parts: list[str] = []
    if added:
        parts.append(f"{added} added")
    if removed:
        parts.append(f"{removed} removed")
    if changed:
        parts.append(f"{changed} changed")
    return ", ".join(parts)


@router.post("/responses", response_model=CompareOutput)
def compare_responses(body: CompareInput) -> CompareOutput:
    if body.format == "json":
        try:
            left_obj = json.loads(body.left)
            right_obj = json.loads(body.right)
        except json.JSONDecodeError:
            # Fall back to text diff if JSON parsing fails.
            return _text_diff(body.left, body.right)

        changes = _deep_diff(left_obj, right_obj)
        diff_lines = list(difflib.unified_diff(
            json.dumps(left_obj, indent=2, default=str).splitlines(keepends=True),
            json.dumps(right_obj, indent=2, default=str).splitlines(keepends=True),
            fromfile="left",
            tofile="right",
        ))
        return CompareOutput(
            summary=_build_summary(changes),
            changes=changes,
            diff_text="".join(diff_lines),
        )

    return _text_diff(body.left, body.right)


def _text_diff(left: str, right: str) -> CompareOutput:
    diff_lines = list(difflib.unified_diff(
        left.splitlines(keepends=True),
        right.splitlines(keepends=True),
        fromfile="left",
        tofile="right",
    ))
    # Build change entries from unified diff lines.
    changes: list[ChangeEntry] = []
    line_no = 0
    for line in diff_lines:
        if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue
        if line.startswith("-"):
            changes.append(ChangeEntry(
                path=f"line {line_no}",
                type="removed",
                old_value=line[1:].rstrip("\n"),
            ))
            line_no += 1
        elif line.startswith("+"):
            changes.append(ChangeEntry(
                path=f"line {line_no}",
                type="added",
                new_value=line[1:].rstrip("\n"),
            ))
            line_no += 1
        else:
            line_no += 1

    return CompareOutput(
        summary=_build_summary(changes),
        changes=changes,
        diff_text="".join(diff_lines),
    )
