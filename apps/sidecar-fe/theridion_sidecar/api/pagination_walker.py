"""Pagination walker — auto-walk paginated endpoints."""

from __future__ import annotations

import re
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/test", tags=["test"])


class PaginationRequest(BaseModel):
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    strategy: Literal["link", "offset", "cursor"] = "offset"
    limit_param: str = "limit"
    offset_param: str = "offset"
    cursor_param: str = "cursor"
    page_size: int = Field(default=20, ge=1, le=1000)
    max_pages: int = Field(default=20, ge=1, le=100)


class PageResult(BaseModel):
    page: int
    status: int
    item_count: int
    url: str


class PaginationResult(BaseModel):
    pages: list[PageResult]
    total_items: int
    total_pages: int
    consistent: bool


def _parse_link_next(link_header: str) -> str | None:
    """Parse RFC 8288 Link header for rel=next."""
    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>\s*;\s*rel\s*=\s*"?next"?', part.strip())
        if match:
            return match.group(1)
    return None


def _count_items(body: str) -> int:
    """Best-effort count of items in a JSON array response."""
    import json
    try:
        data = json.loads(body)
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            # Common patterns: data, items, results
            for key in ("data", "items", "results", "records", "entries"):
                if key in data and isinstance(data[key], list):
                    return len(data[key])
        return 0
    except (json.JSONDecodeError, TypeError):
        return 0


@router.post("/pagination", response_model=PaginationResult)
async def pagination_walker(req: PaginationRequest) -> PaginationResult:
    pages: list[PageResult] = []
    total_items = 0
    current_url = req.url
    page_sizes: list[int] = []

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for page_num in range(1, req.max_pages + 1):
                # Build URL with pagination params
                if req.strategy == "offset" and page_num > 1:
                    sep = "&" if "?" in current_url else "?"
                    offset = (page_num - 1) * req.page_size
                    current_url = f"{req.url}{sep}{req.offset_param}={offset}&{req.limit_param}={req.page_size}"
                elif req.strategy == "offset" and page_num == 1:
                    sep = "&" if "?" in current_url else "?"
                    current_url = f"{req.url}{sep}{req.limit_param}={req.page_size}"

                resp = await client.get(current_url, headers=req.headers)
                body_text = resp.text
                item_count = _count_items(body_text)
                total_items += item_count
                page_sizes.append(item_count)

                pages.append(PageResult(
                    page=page_num, status=resp.status_code,
                    item_count=item_count, url=current_url,
                ))

                if item_count == 0:
                    break

                # Determine next URL
                if req.strategy == "link":
                    link = resp.headers.get("link", "")
                    next_url = _parse_link_next(link)
                    if not next_url:
                        break
                    current_url = next_url
                elif req.strategy == "cursor":
                    import json
                    try:
                        data = json.loads(body_text)
                        cursor = None
                        if isinstance(data, dict):
                            cursor = data.get("next_cursor") or data.get("cursor") or data.get("next")
                        if not cursor:
                            break
                        sep = "&" if "?" in req.url else "?"
                        current_url = f"{req.url}{sep}{req.cursor_param}={cursor}"
                    except (json.JSONDecodeError, TypeError):
                        break
                # offset: URL is rebuilt in next iteration
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Consistent = all non-last pages have same item count
    consistent = True
    if len(page_sizes) > 1:
        full_pages = page_sizes[:-1]
        consistent = len(set(full_pages)) <= 1

    return PaginationResult(
        pages=pages,
        total_items=total_items,
        total_pages=len(pages),
        consistent=consistent,
    )
