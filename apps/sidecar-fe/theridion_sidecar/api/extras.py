"""Extra collection endpoints: request duplication + collection variables."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..models import Collection, CollectionItem, CollectionVariable

router = APIRouter(prefix="/api/collections", tags=["collections"])


# ---- Request duplication ---------------------------------------------------

def _find_item(items: list[CollectionItem], item_id: str) -> CollectionItem | None:
    """Find an item anywhere in the tree by id."""
    for it in items:
        if it.id == item_id:
            return it
        if it.is_folder:
            found = _find_item(it.items, item_id)
            if found is not None:
                return found
    return None


def _find_parent_items(
    items: list[CollectionItem], item_id: str
) -> list[CollectionItem] | None:
    """Find the parent list that contains the item with the given id."""
    for it in items:
        if it.id == item_id:
            return items
        if it.is_folder:
            found = _find_parent_items(it.items, item_id)
            if found is not None:
                return found
    return None


@router.post(
    "/{collection_id}/requests/{request_id}/duplicate",
    response_model=Collection,
)
def duplicate_request(collection_id: str, request_id: str) -> Collection:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    original = _find_item(coll.items, request_id)
    if original is None or original.is_folder:
        raise HTTPException(status_code=404, detail="request not found")

    parent_list = _find_parent_items(coll.items, request_id)
    if parent_list is None:
        raise HTTPException(status_code=404, detail="request not found")

    # Deep copy with new id
    clone_data = original.model_dump()
    clone_data["id"] = str(uuid.uuid4())
    clone_data["name"] = f"{original.name} (copy)"
    clone = CollectionItem(**clone_data)

    # Insert right after the original
    idx = next(i for i, it in enumerate(parent_list) if it.id == request_id)
    parent_list.insert(idx + 1, clone)

    storage._atomic_write(coll)
    return coll


# ---- Collection variables --------------------------------------------------

class UpdateCollectionVariablesInput(BaseModel):
    variables: list[CollectionVariable] = Field(default_factory=list)


@router.patch("/{collection_id}/variables", response_model=Collection)
def update_collection_variables(
    collection_id: str, body: UpdateCollectionVariablesInput
) -> Collection:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")

    coll.variables = list(body.variables)
    storage._atomic_write(coll)
    return coll
