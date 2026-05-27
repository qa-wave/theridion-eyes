"""Import collections from Postman v2.1 and Insomnia v4 formats."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage
from ..models import AuthConfig, Collection, CollectionItem

router = APIRouter(prefix="/api/import", tags=["import"])


class ImportInput(BaseModel):
    content: str = Field(..., min_length=1)
    format: str = "auto"  # auto, postman, insomnia


class ImportOutput(BaseModel):
    collection_id: str
    collection_name: str
    request_count: int


@router.post("", response_model=ImportOutput)
def import_collection(body: ImportInput) -> ImportOutput:
    try:
        data = json.loads(body.content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

    fmt = body.format
    if fmt == "auto":
        fmt = _detect_format(data)

    if fmt == "postman":
        coll = _import_postman(data)
    elif fmt == "insomnia":
        coll = _import_insomnia(data)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")

    storage._atomic_write(coll)
    count = _count_requests(coll.items)
    return ImportOutput(
        collection_id=coll.id,
        collection_name=coll.name,
        request_count=count,
    )


def _detect_format(data: Any) -> str:
    if isinstance(data, dict):
        if "info" in data and "item" in data:
            return "postman"
        if "_type" in data and data.get("_type") == "export":
            return "insomnia"
        if "resources" in data:
            return "insomnia"
    return "postman"


def _import_postman(data: dict[str, Any]) -> Collection:
    info = data.get("info", {})
    name = info.get("name", "Imported Collection")
    items = _convert_postman_items(data.get("item", []))
    return Collection(
        id=str(uuid.uuid4()),
        name=name,
        version=1,
        items=items,
    )


def _convert_postman_items(items: list[dict[str, Any]]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for item in items:
        if "item" in item:
            # Folder
            folder = CollectionItem(
                id=str(uuid.uuid4()),
                name=item.get("name", "Folder"),
                is_folder=True,
                items=_convert_postman_items(item["item"]),
            )
            out.append(folder)
        elif "request" in item:
            req_data = item["request"]
            if isinstance(req_data, str):
                # Simple URL string
                out.append(CollectionItem(
                    id=str(uuid.uuid4()),
                    name=item.get("name", req_data),
                    method="GET",
                    url=req_data,
                ))
                continue

            # URL
            url_data = req_data.get("url", "")
            if isinstance(url_data, dict):
                raw = url_data.get("raw", "")
            else:
                raw = str(url_data)

            # Method
            method = req_data.get("method", "GET").upper()

            # Headers
            headers: dict[str, str] = {}
            for h in req_data.get("header", []):
                if isinstance(h, dict) and not h.get("disabled", False):
                    headers[h.get("key", "")] = h.get("value", "")

            # Body
            body_data = req_data.get("body", {})
            body: str | None = None
            if isinstance(body_data, dict):
                mode = body_data.get("mode", "")
                if mode == "raw":
                    body = body_data.get("raw", "")

            # Auth
            auth = _convert_postman_auth(req_data.get("auth"))

            out.append(CollectionItem(
                id=str(uuid.uuid4()),
                name=item.get("name", raw[:40] or "Untitled"),
                method=method if method in ("GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS") else "GET",
                url=raw,
                headers=headers,
                body=body,
                auth=auth,
            ))
    return out


def _convert_postman_auth(auth: dict[str, Any] | None) -> AuthConfig | None:
    if not auth:
        return None
    auth_type = auth.get("type", "")
    if auth_type == "bearer":
        token_list = auth.get("bearer", [])
        token = ""
        for t in token_list:
            if isinstance(t, dict) and t.get("key") == "token":
                token = t.get("value", "")
        return AuthConfig(type="bearer", token=token) if token else None
    elif auth_type == "basic":
        basic_list = auth.get("basic", [])
        username = password = ""
        for b in basic_list:
            if isinstance(b, dict):
                if b.get("key") == "username":
                    username = b.get("value", "")
                elif b.get("key") == "password":
                    password = b.get("value", "")
        return AuthConfig(type="basic", username=username, password=password)
    return None


def _import_insomnia(data: dict[str, Any]) -> Collection:
    resources = data.get("resources", [])
    name = "Imported (Insomnia)"

    # Find workspace name
    for r in resources:
        if r.get("_type") == "workspace":
            name = r.get("name", name)
            break

    # Build tree from parent references
    items_by_parent: dict[str, list[CollectionItem]] = {}
    for r in resources:
        rtype = r.get("_type", "")
        parent = r.get("parentId", "")

        if rtype == "request":
            item = CollectionItem(
                id=str(uuid.uuid4()),
                name=r.get("name", "Untitled"),
                method=r.get("method", "GET"),
                url=r.get("url", ""),
                headers={h["name"]: h["value"] for h in r.get("headers", []) if isinstance(h, dict) and not h.get("disabled")},
                body=_extract_insomnia_body(r.get("body", {})),
            )
            items_by_parent.setdefault(parent, []).append(item)
        elif rtype == "request_group":
            folder = CollectionItem(
                id=r.get("_id", str(uuid.uuid4())),
                name=r.get("name", "Folder"),
                is_folder=True,
                items=[],
            )
            items_by_parent.setdefault(parent, []).append(folder)

    # Resolve tree
    def resolve(parent_id: str) -> list[CollectionItem]:
        items = items_by_parent.get(parent_id, [])
        for it in items:
            if it.is_folder:
                it.items = resolve(it.id)
        return items

    # Find root workspace id
    root_id = ""
    for r in resources:
        if r.get("_type") == "workspace":
            root_id = r.get("_id", "")
            break

    all_items = resolve(root_id) if root_id else []
    # Fallback: grab all ungrouped
    if not all_items:
        for items in items_by_parent.values():
            all_items.extend(items)

    return Collection(id=str(uuid.uuid4()), name=name, version=1, items=all_items)


def _extract_insomnia_body(body: dict[str, Any] | None) -> str | None:
    if not body:
        return None
    if body.get("mimeType") == "application/json":
        return body.get("text", "")
    return body.get("text")


def _count_requests(items: list[CollectionItem]) -> int:
    count = 0
    for it in items:
        if it.is_folder:
            count += _count_requests(it.items)
        else:
            count += 1
    return count
