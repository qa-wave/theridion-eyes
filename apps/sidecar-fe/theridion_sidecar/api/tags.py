"""Tag management endpoints for request organization and filtering."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..models import CollectionItem

router = APIRouter(prefix="/api/tags", tags=["tags"])

BUILT_IN_SUGGESTIONS = [
    "auth", "smoke", "regression", "critical", "slow", "deprecated", "wip",
]


class TagCount(BaseModel):
    tag: str
    count: int


class TagListResponse(BaseModel):
    tags: list[TagCount]
    suggestions: list[str] = Field(default_factory=lambda: list(BUILT_IN_SUGGESTIONS))


class AssignTagsInput(BaseModel):
    collection_id: str
    request_id: str
    tags: list[str]


class RemoveTagInput(BaseModel):
    collection_id: str
    request_id: str
    tag: str


class BulkAssignInput(BaseModel):
    collection_id: str
    request_ids: list[str]
    tags: list[str]


class TagSearchResult(BaseModel):
    collection_id: str
    request_id: str
    name: str
    method: str | None = None
    url: str | None = None
    tags: list[str]


class TagSearchResponse(BaseModel):
    results: list[TagSearchResult]


def _walk_items(items: list[CollectionItem]):
    """Yield all items depth-first."""
    for item in items:
        yield item
        if item.is_folder:
            yield from _walk_items(item.items)


def _find_item(items: list[CollectionItem], item_id: str) -> CollectionItem | None:
    """Find an item by id in the tree."""
    for item in _walk_items(items):
        if item.id == item_id:
            return item
    return None


@router.get("", response_model=TagListResponse)
async def list_tags() -> TagListResponse:
    """List all unique tags across all collections with usage counts."""
    counter: Counter[str] = Counter()
    for summary in storage.list_summaries():
        coll = storage.get(summary.id)
        if coll is None:
            continue
        for item in _walk_items(coll.items):
            if not item.is_folder:
                for tag in item.tags:
                    counter[tag] += 1
    tags = [TagCount(tag=t, count=c) for t, c in counter.most_common()]
    return TagListResponse(tags=tags)


@router.post("/assign", response_model=list[str])
async def assign_tags(body: AssignTagsInput) -> list[str]:
    """Assign tags to a request (replaces existing tags)."""
    coll = storage.get(body.collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    item = _find_item(coll.items, body.request_id)
    if item is None or item.is_folder:
        raise HTTPException(status_code=404, detail="request not found")
    item.tags = list(dict.fromkeys(body.tags))  # dedupe preserving order
    storage._atomic_write(coll)
    return item.tags


@router.post("/remove", response_model=list[str])
async def remove_tag(body: RemoveTagInput) -> list[str]:
    """Remove a single tag from a request."""
    coll = storage.get(body.collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    item = _find_item(coll.items, body.request_id)
    if item is None or item.is_folder:
        raise HTTPException(status_code=404, detail="request not found")
    item.tags = [t for t in item.tags if t != body.tag]
    storage._atomic_write(coll)
    return item.tags


@router.get("/search", response_model=TagSearchResponse)
async def search_by_tags(tags: str, mode: str = "any") -> TagSearchResponse:
    """Search requests by tag(s). Query: ?tags=auth,critical&mode=any|all"""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if not tag_list:
        raise HTTPException(status_code=400, detail="tags parameter required")
    if mode not in ("any", "all"):
        raise HTTPException(status_code=400, detail="mode must be 'any' or 'all'")

    results: list[TagSearchResult] = []
    for summary in storage.list_summaries():
        coll = storage.get(summary.id)
        if coll is None:
            continue
        for item in _walk_items(coll.items):
            if item.is_folder or not item.tags:
                continue
            if mode == "any":
                match = any(t in item.tags for t in tag_list)
            else:
                match = all(t in item.tags for t in tag_list)
            if match:
                results.append(TagSearchResult(
                    collection_id=summary.id,
                    request_id=item.id,
                    name=item.name,
                    method=item.method,
                    url=item.url,
                    tags=item.tags,
                ))
    return TagSearchResponse(results=results)


@router.post("/bulk", response_model=dict)
async def bulk_assign(body: BulkAssignInput) -> dict:
    """Assign tags to multiple requests at once."""
    coll = storage.get(body.collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    updated = 0
    for item in _walk_items(coll.items):
        if item.id in body.request_ids and not item.is_folder:
            merged = list(dict.fromkeys(item.tags + body.tags))
            item.tags = merged
            updated += 1
    storage._atomic_write(coll)
    return {"updated": updated}
