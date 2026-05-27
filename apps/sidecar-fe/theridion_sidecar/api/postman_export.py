"""Export a Theridion collection as Postman Collection v2.1 format."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage
from theridion_sidecar.models import CollectionItem

router = APIRouter(prefix="/api/export", tags=["export"])


class PostmanExportOutput(BaseModel):
    postman_json: str


def _auth_to_postman(item: CollectionItem) -> dict | None:
    if not item.auth or item.auth.type == "none":
        return None
    if item.auth.type == "bearer":
        return {
            "type": "bearer",
            "bearer": [{"key": "token", "value": item.auth.token or "", "type": "string"}],
        }
    if item.auth.type == "basic":
        return {
            "type": "basic",
            "basic": [
                {"key": "username", "value": item.auth.username or "", "type": "string"},
                {"key": "password", "value": item.auth.password or "", "type": "string"},
            ],
        }
    if item.auth.type == "apikey":
        return {
            "type": "apikey",
            "apikey": [
                {"key": "key", "value": item.auth.key or "", "type": "string"},
                {"key": "value", "value": item.auth.value or "", "type": "string"},
                {"key": "in", "value": item.auth.add_to or "header", "type": "string"},
            ],
        }
    return None


def _item_to_postman(item: CollectionItem) -> dict:
    if item.is_folder:
        return {
            "name": item.name,
            "item": [_item_to_postman(child) for child in item.items],
        }

    headers = [{"key": k, "value": v} for k, v in item.headers.items()]

    request: dict = {
        "method": item.method or "GET",
        "header": headers,
        "url": {"raw": item.url or "", "protocol": "", "host": [], "path": []},
    }

    if item.body:
        request["body"] = {
            "mode": "raw",
            "raw": item.body,
            "options": {"raw": {"language": "json"}},
        }

    auth = _auth_to_postman(item)
    if auth:
        request["auth"] = auth

    result: dict = {"name": item.name, "request": request, "response": []}
    return result


@router.post("/postman/{collection_id}", response_model=PostmanExportOutput)
async def export_postman(collection_id: str) -> PostmanExportOutput:
    col = storage.get_collection(collection_id)
    if not col:
        raise HTTPException(status_code=404, detail="collection not found")

    postman = {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": col.name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [_item_to_postman(item) for item in col.items],
        "variable": [
            {"key": v.name, "value": v.value}
            for v in col.variables
            if v.enabled
        ],
    }

    return PostmanExportOutput(postman_json=json.dumps(postman, indent=2))
