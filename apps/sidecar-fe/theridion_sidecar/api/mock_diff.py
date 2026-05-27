"""Mock diff — compare actual response against mock/expected response."""

from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class MockDiffRequest(BaseModel):
    actual_body: str = ""
    mock_body: str = ""
    actual_headers: dict[str, str] = Field(default_factory=dict)
    mock_headers: dict[str, str] = Field(default_factory=dict)


class DiffEntry(BaseModel):
    path: str
    expected: str | None = None
    actual: str | None = None


class MockDiffResult(BaseModel):
    body_diffs: list[DiffEntry]
    header_diffs: list[DiffEntry]
    match: bool


def _diff_json(expected: object, actual: object, path: str, diffs: list[DiffEntry]) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        all_keys = set(expected.keys()) | set(actual.keys())
        for key in sorted(all_keys):
            child = f"{path}.{key}" if path else key
            if key not in actual:
                diffs.append(DiffEntry(path=child, expected=str(expected[key]), actual=None))
            elif key not in expected:
                diffs.append(DiffEntry(path=child, expected=None, actual=str(actual[key])))
            else:
                _diff_json(expected[key], actual[key], child, diffs)
    elif isinstance(expected, list) and isinstance(actual, list):
        for i in range(max(len(expected), len(actual))):
            child = f"{path}[{i}]"
            if i >= len(actual):
                diffs.append(DiffEntry(path=child, expected=str(expected[i]), actual=None))
            elif i >= len(expected):
                diffs.append(DiffEntry(path=child, expected=None, actual=str(actual[i])))
            else:
                _diff_json(expected[i], actual[i], child, diffs)
    else:
        if expected != actual:
            diffs.append(DiffEntry(path=path, expected=str(expected), actual=str(actual)))


@router.post("/mock-diff", response_model=MockDiffResult)
async def mock_diff(req: MockDiffRequest) -> MockDiffResult:
    body_diffs: list[DiffEntry] = []

    try:
        expected_body = json.loads(req.mock_body) if req.mock_body else None
        actual_body = json.loads(req.actual_body) if req.actual_body else None
        if expected_body is not None and actual_body is not None:
            _diff_json(expected_body, actual_body, "$", body_diffs)
        elif expected_body != actual_body:
            body_diffs.append(DiffEntry(path="$", expected=req.mock_body, actual=req.actual_body))
    except json.JSONDecodeError:
        if req.mock_body != req.actual_body:
            body_diffs.append(DiffEntry(path="$", expected=req.mock_body, actual=req.actual_body))

    header_diffs: list[DiffEntry] = []
    all_hdrs = set(req.mock_headers.keys()) | set(req.actual_headers.keys())
    for name in sorted(all_hdrs):
        exp = req.mock_headers.get(name)
        act = req.actual_headers.get(name)
        if exp != act:
            header_diffs.append(DiffEntry(path=name, expected=exp, actual=act))

    return MockDiffResult(
        body_diffs=body_diffs,
        header_diffs=header_diffs,
        match=len(body_diffs) == 0 and len(header_diffs) == 0,
    )
