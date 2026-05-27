"""Request Body Diff — compare two request bodies with structural awareness.

Supports JSON (structural diff with paths), XML (element-level), and plain
text (unified diff). Auto-detection inspects content to pick the right mode.
"""

from __future__ import annotations

import difflib
import json
import re
from typing import Any, Literal
from xml.etree import ElementTree as ET

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/diff", tags=["diff"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class BodyDiffInput(BaseModel):
    left: str
    right: str
    format: Literal["json", "xml", "text", "auto"] = "auto"


class StructuralChange(BaseModel):
    path: str
    type: Literal["added", "removed", "changed"]
    old: Any = None
    new: Any = None


class DiffStats(BaseModel):
    additions: int = 0
    deletions: int = 0
    modifications: int = 0


class BodyDiffOutput(BaseModel):
    format_detected: str
    structural_changes: list[StructuralChange] = Field(default_factory=list)
    unified_diff: str = ""
    stats: DiffStats = Field(default_factory=DiffStats)


class FormatInput(BaseModel):
    body: str
    format: Literal["json", "xml", "auto"] = "auto"


class FormatOutput(BaseModel):
    formatted: str
    format_detected: str


class MergeInput(BaseModel):
    base: str
    left: str
    right: str
    format: Literal["json", "xml", "text", "auto"] = "auto"


class MergeConflict(BaseModel):
    path: str
    base_value: Any = None
    left_value: Any = None
    right_value: Any = None


class MergeOutput(BaseModel):
    merged: str
    conflicts: list[MergeConflict] = Field(default_factory=list)
    format_detected: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_format(content: str) -> str:
    """Heuristic format detection."""
    stripped = content.strip()
    if not stripped:
        return "text"
    # JSON check
    if stripped.startswith(("{", "[")):
        try:
            json.loads(stripped)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass
    # XML check
    if stripped.startswith("<"):
        try:
            ET.fromstring(stripped)
            return "xml"
        except ET.ParseError:
            pass
    return "text"


def _json_structural_diff(
    left: Any, right: Any, path: str = "$"
) -> list[StructuralChange]:
    """Recursively diff two JSON values, returning changes with paths."""
    changes: list[StructuralChange] = []

    if isinstance(left, dict) and isinstance(right, dict):
        all_keys = set(left.keys()) | set(right.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}"
            if key not in left:
                changes.append(
                    StructuralChange(path=child_path, type="added", new=right[key])
                )
            elif key not in right:
                changes.append(
                    StructuralChange(path=child_path, type="removed", old=left[key])
                )
            else:
                changes.extend(
                    _json_structural_diff(left[key], right[key], child_path)
                )
    elif isinstance(left, list) and isinstance(right, list):
        max_len = max(len(left), len(right))
        for i in range(max_len):
            child_path = f"{path}[{i}]"
            if i >= len(left):
                changes.append(
                    StructuralChange(path=child_path, type="added", new=right[i])
                )
            elif i >= len(right):
                changes.append(
                    StructuralChange(path=child_path, type="removed", old=left[i])
                )
            else:
                changes.extend(
                    _json_structural_diff(left[i], right[i], child_path)
                )
    elif left != right:
        changes.append(
            StructuralChange(path=path, type="changed", old=left, new=right)
        )

    return changes


def _xml_element_path(elem: ET.Element, parent_path: str = "") -> str:
    tag = re.sub(r"\{[^}]+\}", "", elem.tag)
    return f"{parent_path}/{tag}" if parent_path else f"/{tag}"


def _xml_structural_diff(
    left: ET.Element, right: ET.Element, path: str = ""
) -> list[StructuralChange]:
    """Element-level diff for XML trees."""
    changes: list[StructuralChange] = []
    left_path = _xml_element_path(left, path)
    right_path = _xml_element_path(right, path)

    if left.tag != right.tag:
        changes.append(
            StructuralChange(
                path=left_path, type="changed", old=left.tag, new=right.tag
            )
        )
        return changes

    current_path = left_path

    # Compare text
    lt = (left.text or "").strip()
    rt = (right.text or "").strip()
    if lt != rt:
        changes.append(
            StructuralChange(path=f"{current_path}/text()", type="changed", old=lt, new=rt)
        )

    # Compare attributes
    left_attrs = left.attrib
    right_attrs = right.attrib
    all_attrs = set(left_attrs.keys()) | set(right_attrs.keys())
    for attr in sorted(all_attrs):
        attr_path = f"{current_path}/@{attr}"
        if attr not in left_attrs:
            changes.append(
                StructuralChange(path=attr_path, type="added", new=right_attrs[attr])
            )
        elif attr not in right_attrs:
            changes.append(
                StructuralChange(path=attr_path, type="removed", old=left_attrs[attr])
            )
        elif left_attrs[attr] != right_attrs[attr]:
            changes.append(
                StructuralChange(
                    path=attr_path, type="changed",
                    old=left_attrs[attr], new=right_attrs[attr],
                )
            )

    # Compare children
    left_children = list(left)
    right_children = list(right)
    max_len = max(len(left_children), len(right_children))
    for i in range(max_len):
        if i >= len(left_children):
            rc = right_children[i]
            rc_path = _xml_element_path(rc, current_path)
            changes.append(
                StructuralChange(
                    path=rc_path, type="added",
                    new=ET.tostring(rc, encoding="unicode"),
                )
            )
        elif i >= len(right_children):
            lc = left_children[i]
            lc_path = _xml_element_path(lc, current_path)
            changes.append(
                StructuralChange(
                    path=lc_path, type="removed",
                    old=ET.tostring(lc, encoding="unicode"),
                )
            )
        else:
            changes.extend(
                _xml_structural_diff(left_children[i], right_children[i], current_path)
            )

    return changes


def _unified_diff(left: str, right: str) -> str:
    """Standard unified diff."""
    left_lines = left.splitlines(keepends=True)
    right_lines = right.splitlines(keepends=True)
    diff = difflib.unified_diff(left_lines, right_lines, fromfile="left", tofile="right")
    return "".join(diff)


def _prettify_json(s: str) -> str:
    return json.dumps(json.loads(s), indent=2, ensure_ascii=False)


def _prettify_xml(s: str) -> str:
    root = ET.fromstring(s)
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")


def _compute_stats(changes: list[StructuralChange]) -> DiffStats:
    additions = sum(1 for c in changes if c.type == "added")
    deletions = sum(1 for c in changes if c.type == "removed")
    modifications = sum(1 for c in changes if c.type == "changed")
    return DiffStats(additions=additions, deletions=deletions, modifications=modifications)


def _text_stats(unified: str) -> DiffStats:
    additions = 0
    deletions = 0
    for line in unified.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return DiffStats(additions=additions, deletions=deletions, modifications=0)


# ---------------------------------------------------------------------------
# Three-way merge helpers
# ---------------------------------------------------------------------------


def _merge_json(base: Any, left: Any, right: Any, path: str = "$") -> tuple[Any, list[MergeConflict]]:
    """Three-way merge for JSON. Returns (merged, conflicts)."""
    conflicts: list[MergeConflict] = []

    if base == left and base == right:
        return base, []
    if base == left:
        return right, []
    if base == right:
        return left, []

    # Both changed — try recursive merge for dicts
    if isinstance(base, dict) and isinstance(left, dict) and isinstance(right, dict):
        merged = {}
        all_keys = set(base.keys()) | set(left.keys()) | set(right.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}"
            bv = base.get(key)
            lv = left.get(key)
            rv = right.get(key)
            m, c = _merge_json(bv, lv, rv, child_path)
            merged[key] = m
            conflicts.extend(c)
        return merged, conflicts

    # Both changed to different values — conflict
    if left == right:
        return left, []

    conflicts.append(
        MergeConflict(path=path, base_value=base, left_value=left, right_value=right)
    )
    # Default: prefer left
    return left, conflicts


def _merge_text(base: str, left: str, right: str) -> tuple[str, list[MergeConflict]]:
    """Line-based three-way merge for text."""
    base_lines = base.splitlines(keepends=True)
    left_lines = left.splitlines(keepends=True)
    right_lines = right.splitlines(keepends=True)

    # Simple approach: if left == base, take right. If right == base, take left.
    # Otherwise line-by-line.
    if base_lines == left_lines:
        return right, []
    if base_lines == right_lines:
        return left, []

    # Use difflib to merge
    conflicts: list[MergeConflict] = []
    merged_lines: list[str] = []

    # Get ops for left and right vs base
    sm_left = difflib.SequenceMatcher(None, base_lines, left_lines)
    sm_right = difflib.SequenceMatcher(None, base_lines, right_lines)

    # Simplistic: if both modified differently, mark conflict
    left_changes = set()
    for tag, i1, i2, _j1, _j2 in sm_left.get_opcodes():
        if tag != "equal":
            for i in range(i1, i2):
                left_changes.add(i)

    right_changes = set()
    for tag, i1, i2, _j1, _j2 in sm_right.get_opcodes():
        if tag != "equal":
            for i in range(i1, i2):
                right_changes.add(i)

    overlap = left_changes & right_changes
    if overlap:
        conflicts.append(
            MergeConflict(
                path=f"lines {min(overlap)+1}-{max(overlap)+1}",
                base_value="".join(base_lines[i] for i in sorted(overlap)),
                left_value="".join(left_lines[i] for i in sorted(overlap) if i < len(left_lines)),
                right_value="".join(right_lines[i] for i in sorted(overlap) if i < len(right_lines)),
            )
        )

    # For output, prefer left version
    merged_lines = left_lines
    return "".join(merged_lines), conflicts


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/bodies", response_model=BodyDiffOutput)
async def diff_bodies(inp: BodyDiffInput) -> BodyDiffOutput:
    """Compare two request bodies with format-aware structural diff."""
    fmt = inp.format if inp.format != "auto" else _detect_format(inp.left)

    structural: list[StructuralChange] = []

    if fmt == "json":
        try:
            left_obj = json.loads(inp.left)
            right_obj = json.loads(inp.right)
            structural = _json_structural_diff(left_obj, right_obj)
        except (json.JSONDecodeError, ValueError):
            fmt = "text"

    if fmt == "xml":
        try:
            left_tree = ET.fromstring(inp.left)
            right_tree = ET.fromstring(inp.right)
            structural = _xml_structural_diff(left_tree, right_tree)
        except ET.ParseError:
            fmt = "text"

    unified = _unified_diff(inp.left, inp.right)

    if structural:
        stats = _compute_stats(structural)
    else:
        stats = _text_stats(unified)

    return BodyDiffOutput(
        format_detected=fmt,
        structural_changes=structural,
        unified_diff=unified,
        stats=stats,
    )


@router.post("/format", response_model=FormatOutput)
async def format_body(inp: FormatInput) -> FormatOutput:
    """Prettify a request body (JSON or XML)."""
    fmt = inp.format if inp.format != "auto" else _detect_format(inp.body)

    if fmt == "json":
        try:
            formatted = _prettify_json(inp.body)
            return FormatOutput(formatted=formatted, format_detected="json")
        except (json.JSONDecodeError, ValueError):
            pass

    if fmt == "xml":
        try:
            formatted = _prettify_xml(inp.body)
            return FormatOutput(formatted=formatted, format_detected="xml")
        except ET.ParseError:
            pass

    # Fallback: return as-is
    return FormatOutput(formatted=inp.body, format_detected="text")


@router.post("/merge", response_model=MergeOutput)
async def merge_bodies(inp: MergeInput) -> MergeOutput:
    """Three-way merge: base + left + right → merged with conflicts."""
    fmt = inp.format if inp.format != "auto" else _detect_format(inp.base)

    if fmt == "json":
        try:
            base_obj = json.loads(inp.base)
            left_obj = json.loads(inp.left)
            right_obj = json.loads(inp.right)
            merged_obj, conflicts = _merge_json(base_obj, left_obj, right_obj)
            merged_str = json.dumps(merged_obj, indent=2, ensure_ascii=False)
            return MergeOutput(merged=merged_str, conflicts=conflicts, format_detected="json")
        except (json.JSONDecodeError, ValueError):
            fmt = "text"

    if fmt == "xml":
        # XML merge falls back to text-based merge
        fmt = "text"

    # Text merge
    merged, conflicts = _merge_text(inp.base, inp.left, inp.right)
    return MergeOutput(merged=merged, conflicts=conflicts, format_detected=fmt)
