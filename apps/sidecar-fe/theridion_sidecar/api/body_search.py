"""Response Body Search — text/regex, JSONPath, and XPath search within response bodies."""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/search", tags=["search"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class BodySearchInput(BaseModel):
    body: str
    query: str
    regex: bool = False
    case_sensitive: bool = False


class BodySearchMatch(BaseModel):
    start: int
    end: int
    line: int
    column: int
    context: str


class BodySearchOutput(BaseModel):
    matches: list[BodySearchMatch] = Field(default_factory=list)
    total: int = 0
    query_valid: bool = True


class JsonPathInput(BaseModel):
    body: str
    path: str


class JsonPathMatch(BaseModel):
    path: str
    value: Any
    type: str


class JsonPathOutput(BaseModel):
    matches: list[JsonPathMatch] = Field(default_factory=list)
    total: int = 0


class XPathInput(BaseModel):
    body: str
    xpath: str


class XPathMatch(BaseModel):
    path: str
    value: str


class XPathOutput(BaseModel):
    matches: list[XPathMatch] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONTEXT_CHARS = 40


def _line_col(text: str, pos: int) -> tuple[int, int]:
    """Return 1-based line and column for a character offset."""
    line = text.count("\n", 0, pos) + 1
    last_nl = text.rfind("\n", 0, pos)
    col = pos - last_nl  # 1-based (if no newline before, last_nl is -1)
    return line, col


def _context(text: str, start: int, end: int) -> str:
    """Extract context: 40 chars before + match + 40 chars after."""
    ctx_start = max(0, start - CONTEXT_CHARS)
    ctx_end = min(len(text), end + CONTEXT_CHARS)
    return text[ctx_start:ctx_end]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/body", response_model=BodySearchOutput)
async def search_body(inp: BodySearchInput) -> BodySearchOutput:
    """Search response body by plain text or regex."""
    if not inp.query:
        return BodySearchOutput(matches=[], total=0, query_valid=True)

    if inp.regex:
        flags = 0 if inp.case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(inp.query, flags)
        except re.error:
            return BodySearchOutput(matches=[], total=0, query_valid=False)

        matches: list[BodySearchMatch] = []
        for m in pattern.finditer(inp.body):
            line, col = _line_col(inp.body, m.start())
            matches.append(BodySearchMatch(
                start=m.start(),
                end=m.end(),
                line=line,
                column=col,
                context=_context(inp.body, m.start(), m.end()),
            ))
        return BodySearchOutput(matches=matches, total=len(matches), query_valid=True)

    # Plain text search
    text = inp.body
    query = inp.query
    if not inp.case_sensitive:
        text = text.lower()
        query = query.lower()

    matches = []
    start = 0
    while True:
        idx = text.find(query, start)
        if idx == -1:
            break
        end = idx + len(inp.query)
        line, col = _line_col(inp.body, idx)
        matches.append(BodySearchMatch(
            start=idx,
            end=end,
            line=line,
            column=col,
            context=_context(inp.body, idx, end),
        ))
        start = idx + 1

    return BodySearchOutput(matches=matches, total=len(matches), query_valid=True)


@router.post("/json-path", response_model=JsonPathOutput)
async def search_json_path(inp: JsonPathInput) -> JsonPathOutput:
    """Search response body using a JSONPath expression."""
    import json

    try:
        data = json.loads(inp.body)
    except (json.JSONDecodeError, ValueError):
        return JsonPathOutput(matches=[], total=0)

    try:
        from jsonpath_ng import parse as jp_parse

        expr = jp_parse(inp.path)
    except Exception:
        return JsonPathOutput(matches=[], total=0)

    results: list[JsonPathMatch] = []
    for match in expr.find(data):
        val = match.value
        results.append(JsonPathMatch(
            path=str(match.full_path),
            value=val,
            type=type(val).__name__,
        ))

    return JsonPathOutput(matches=results, total=len(results))


@router.post("/xpath", response_model=XPathOutput)
async def search_xpath(inp: XPathInput) -> XPathOutput:
    """Search XML response body using an XPath expression."""
    try:
        root = ET.fromstring(inp.body)
    except ET.ParseError:
        return XPathOutput(matches=[], total=0)

    try:
        elements = root.findall(inp.xpath)
    except (SyntaxError, KeyError):
        return XPathOutput(matches=[], total=0)

    results: list[XPathMatch] = []
    for elem in elements:
        tag = elem.tag
        text = elem.text or ""
        # Build a simple path representation
        results.append(XPathMatch(
            path=tag,
            value=text.strip() if text else ET.tostring(elem, encoding="unicode"),
        ))

    return XPathOutput(matches=results, total=len(results))
