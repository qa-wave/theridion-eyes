"""OpenAPI sync: compare collection with OpenAPI spec for drift."""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/sync", tags=["openapi-sync"])


class OpenApiSyncInput(BaseModel):
    collection_id: str
    spec_url: str


class OpenApiSyncOutput(BaseModel):
    in_sync: bool = True
    missing_in_collection: list[str] = []
    extra_in_collection: list[str] = []
    drifted: list[str] = []


def _collect_urls(items: list) -> set[str]:
    urls: set[str] = set()
    for item in items:
        d = item.model_dump() if hasattr(item, "model_dump") else item
        if d.get("is_folder") and d.get("items"):
            urls.update(_collect_urls(d["items"]))
        elif d.get("url"):
            method = d.get("method", "GET")
            urls.add(f"{method} {d['url']}")
    return urls


@router.post("/openapi", response_model=OpenApiSyncOutput)
async def sync_openapi(body: OpenApiSyncInput) -> OpenApiSyncOutput:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(body.spec_url)
    try:
        spec = json.loads(resp.text)
    except json.JSONDecodeError:
        return OpenApiSyncOutput(in_sync=False, drifted=["Could not parse spec"])

    spec_endpoints: set[str] = set()
    for path, methods in spec.get("paths", {}).items():
        if isinstance(methods, dict):
            for m in ("get", "post", "put", "delete", "patch", "head", "options"):
                if m in methods:
                    spec_endpoints.add(f"{m.upper()} {path}")

    col = storage.load_collection(body.collection_id)
    collection_endpoints: set[str] = set()
    if col:
        collection_endpoints = _collect_urls(col.items)

    missing = sorted(spec_endpoints - collection_endpoints)
    extra = sorted(collection_endpoints - spec_endpoints)

    return OpenApiSyncOutput(
        in_sync=len(missing) == 0 and len(extra) == 0,
        missing_in_collection=missing,
        extra_in_collection=extra,
    )
