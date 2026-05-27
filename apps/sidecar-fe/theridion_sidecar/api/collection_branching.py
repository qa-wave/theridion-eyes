"""Collection branching: fork and merge collections."""

from __future__ import annotations

import copy
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/collections", tags=["collection-branching"])


class ForkOutput(BaseModel):
    id: str
    name: str
    parent_id: str
    item_count: int


class MergeInput(BaseModel):
    source_id: str


class MergeOutput(BaseModel):
    id: str
    name: str
    merged_items: int


@router.post("/{collection_id}/fork", response_model=ForkOutput)
async def fork_collection(collection_id: str) -> ForkOutput:
    col = storage.load_collection(collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    new_id = uuid.uuid4().hex[:12]
    fork_data = col.model_dump()
    fork_data["id"] = new_id
    fork_data["name"] = f"{col.name} (fork)"
    fork_data["version"] = 1

    from theridion_sidecar.models import StoredCollection
    fork_col = StoredCollection(**fork_data)
    storage.save_collection(fork_col)

    count = len(fork_data.get("items", []))
    return ForkOutput(id=new_id, name=fork_col.name, parent_id=collection_id, item_count=count)


@router.post("/{collection_id}/merge", response_model=MergeOutput)
async def merge_collection(collection_id: str, body: MergeInput) -> MergeOutput:
    target = storage.load_collection(collection_id)
    source = storage.load_collection(body.source_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target collection not found")
    if source is None:
        raise HTTPException(status_code=404, detail="Source collection not found")

    existing_ids = {_get_ids(i) for i in target.items}
    added = 0
    for item in source.items:
        iid = _get_ids(item)
        if iid not in existing_ids:
            target.items.append(copy.deepcopy(item))
            added += 1

    target.version += 1
    storage.save_collection(target)
    return MergeOutput(id=collection_id, name=target.name, merged_items=added)


def _get_ids(item: object) -> str:
    d = item.model_dump() if hasattr(item, "model_dump") else item
    return d.get("id", "")
