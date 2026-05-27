"""CRUD endpoints for collections, folders, and the requests inside."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..models import (
    Collection,
    CollectionItem,
    CollectionSummary,
    CreateCollectionInput,
    CreateFolderInput,
    SaveRequestInput,
)

router = APIRouter(prefix="/api/collections", tags=["collections"])


@router.get("", response_model=list[CollectionSummary])
def list_collections() -> list[CollectionSummary]:
    return storage.list_summaries()


@router.post("", response_model=Collection, status_code=201)
def create_collection(body: CreateCollectionInput) -> Collection:
    return storage.create(name=body.name)


@router.get("/{collection_id}", response_model=Collection)
def get_collection(collection_id: str) -> Collection:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return coll


@router.delete("/{collection_id}", status_code=204)
def delete_collection(collection_id: str) -> None:
    if not storage.delete_collection(collection_id):
        raise HTTPException(status_code=404, detail="collection not found")


@router.post("/{collection_id}/folders", response_model=Collection, status_code=201)
def create_folder(collection_id: str, body: CreateFolderInput) -> Collection:
    folder = CollectionItem(
        id=str(uuid.uuid4()),
        name=body.name,
        is_folder=True,
        items=[],
    )
    try:
        return storage.add_folder(collection_id, folder, body.parent_folder_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete(
    "/{collection_id}/folders/{folder_id}", response_model=Collection
)
def delete_folder(collection_id: str, folder_id: str) -> Collection:
    try:
        return storage.delete_folder(collection_id, folder_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{collection_id}/requests", response_model=Collection)
def save_request(collection_id: str, body: SaveRequestInput) -> Collection:
    req = CollectionItem(
        id=body.id or str(uuid.uuid4()),
        name=body.name,
        is_folder=False,
        method=body.method,
        url=body.url,
        headers=body.headers,
        body=body.body,
        auth=body.auth,
        assertions=body.assertions,
        pre_request_script=body.pre_request_script,
        examples=body.examples,
        captures=body.captures,
    )
    try:
        return storage.add_request(collection_id, req, body.parent_folder_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class RenameInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class MoveInput(BaseModel):
    target_folder_id: str | None = None


class ReorderInput(BaseModel):
    parent_folder_id: str | None = None
    item_ids: list[str]


@router.patch("/{collection_id}", response_model=Collection)
def rename_collection(collection_id: str, body: RenameInput) -> Collection:
    try:
        return storage.rename_collection(collection_id, body.name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{collection_id}/items/{item_id}/rename", response_model=Collection)
def rename_item(collection_id: str, item_id: str, body: RenameInput) -> Collection:
    try:
        return storage.rename_item(collection_id, item_id, body.name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{collection_id}/items/{item_id}/move", response_model=Collection)
def move_item(collection_id: str, item_id: str, body: MoveInput) -> Collection:
    try:
        return storage.move_item(collection_id, item_id, body.target_folder_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{collection_id}/reorder", response_model=Collection)
def reorder_items(collection_id: str, body: ReorderInput) -> Collection:
    try:
        return storage.reorder_items(
            collection_id, body.parent_folder_id, body.item_ids,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{collection_id}/export-curl")
def export_curl(collection_id: str) -> dict:
    """Generate cURL commands for every request in a collection."""
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    def _flat_requests(items: list[CollectionItem]) -> list[CollectionItem]:
        out: list[CollectionItem] = []
        for it in items:
            if it.is_folder:
                out.extend(_flat_requests(it.items))
            else:
                out.append(it)
        return out

    requests = _flat_requests(coll.items)
    curls: list[str] = []
    for req in requests:
        parts = ["curl", "-X", req.method or "GET"]
        for k, v in (req.headers or {}).items():
            parts.append(f"-H '{k}: {v}'")
        if req.body:
            parts.append(f"-d '{req.body}'")
        parts.append(f"'{req.url or ''}'")
        curls.append(" ".join(parts))
    return {"commands": curls, "count": len(curls)}


@router.delete(
    "/{collection_id}/requests/{request_id}", response_model=Collection
)
def delete_request(collection_id: str, request_id: str) -> Collection:
    try:
        return storage.delete_request(collection_id, request_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
