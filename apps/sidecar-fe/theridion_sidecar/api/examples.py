"""Request examples CRUD — manage multiple body variants per request."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..models import Collection, CollectionItem, RequestExample

router = APIRouter(prefix="/api/collections", tags=["examples"])


class AddExampleInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    notes: str | None = None


def _find_request(items: list[CollectionItem], rid: str) -> CollectionItem | None:
    for it in items:
        if not it.is_folder and it.id == rid:
            return it
        if it.is_folder:
            found = _find_request(it.items, rid)
            if found:
                return found
    return None


@router.post("/{collection_id}/requests/{request_id}/examples", response_model=Collection)
def add_example(collection_id: str, request_id: str, body: AddExampleInput) -> Collection:
    coll = storage.get(collection_id)
    if not coll:
        raise HTTPException(status_code=404, detail="collection not found")
    req = _find_request(coll.items, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")
    example = RequestExample(
        id=str(uuid.uuid4()),
        name=body.name,
        method=body.method,
        url=body.url,
        headers=body.headers,
        body=body.body,
        notes=body.notes,
    )
    req.examples.append(example)
    storage._atomic_write(coll)
    return coll


@router.delete("/{collection_id}/requests/{request_id}/examples/{example_id}", response_model=Collection)
def delete_example(collection_id: str, request_id: str, example_id: str) -> Collection:
    coll = storage.get(collection_id)
    if not coll:
        raise HTTPException(status_code=404, detail="collection not found")
    req = _find_request(coll.items, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")
    req.examples = [e for e in req.examples if e.id != example_id]
    storage._atomic_write(coll)
    return coll


@router.get("/{collection_id}/requests/{request_id}/examples")
def list_examples(collection_id: str, request_id: str) -> list[RequestExample]:
    coll = storage.get(collection_id)
    if not coll:
        raise HTTPException(status_code=404, detail="collection not found")
    req = _find_request(coll.items, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")
    return req.examples
