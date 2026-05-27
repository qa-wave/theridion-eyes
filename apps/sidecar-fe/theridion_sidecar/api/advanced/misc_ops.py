"""Request examples and HAR import/export endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ... import storage
from ...models import (
    AuthConfig,
    Collection,
    CollectionItem,
    HttpMethod,
    RequestExample,
)

router = APIRouter()

HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


# ---- Request examples -----------------------------------------------------


class RequestExampleInput(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    method: HttpMethod = "GET"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    auth: AuthConfig | None = None
    notes: str | None = None


class UpdateExamplesInput(BaseModel):
    examples: list[RequestExampleInput] = Field(default_factory=list)


def _find_item(items: list[CollectionItem], item_id: str) -> CollectionItem | None:
    for item in items:
        if item.id == item_id:
            return item
        if item.is_folder:
            found = _find_item(item.items, item_id)
            if found is not None:
                return found
    return None


def _flatten_requests(items: list[CollectionItem]) -> list[CollectionItem]:
    out: list[CollectionItem] = []
    for item in items:
        if item.is_folder:
            out.extend(_flatten_requests(item.items))
        else:
            out.append(item)
    return out


@router.patch(
    "/collections/{collection_id}/requests/{request_id}/examples",
    response_model=Collection,
)
def update_request_examples(
    collection_id: str, request_id: str, body: UpdateExamplesInput
) -> Collection:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    item = _find_item(coll.items, request_id)
    if item is None or item.is_folder:
        raise HTTPException(status_code=404, detail="request not found")
    item.examples = [
        RequestExample(id=example.id or str(uuid.uuid4()), **example.model_dump(exclude={"id"}))
        for example in body.examples
    ]
    storage._atomic_write(coll)
    return coll


# ---- HAR import / export --------------------------------------------------


def _parse_json_payload(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc


class HarImportInput(BaseModel):
    content: str = Field(..., min_length=1)
    collection_name: str = "HAR import"


class HarImportOutput(BaseModel):
    collection_id: str
    request_count: int


@router.post("/har/import", response_model=HarImportOutput)
def import_har(body: HarImportInput) -> HarImportOutput:
    har = _parse_json_payload(body.content)
    entries = har.get("log", {}).get("entries", []) if isinstance(har, dict) else []
    if not isinstance(entries, list):
        raise HTTPException(status_code=400, detail="HAR log.entries must be an array")
    items: list[CollectionItem] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("request"), dict):
            continue
        request_data = entry["request"]
        headers = {
            str(h.get("name")): str(h.get("value", ""))
            for h in request_data.get("headers", [])
            if isinstance(h, dict) and h.get("name")
        }
        post_data = request_data.get("postData")
        body_text = post_data.get("text") if isinstance(post_data, dict) else None
        method = str(request_data.get("method", "GET")).upper()
        if method not in HTTP_METHODS:
            method = "GET"
        items.append(
            CollectionItem(
                id=str(uuid.uuid4()),
                name=f"{method} {urlsplit(str(request_data.get('url', ''))).path or '/'}",
                method=method,  # type: ignore[arg-type]
                url=str(request_data.get("url", "")),
                headers=headers,
                body=body_text,
            )
        )
    coll = Collection(id=str(uuid.uuid4()), name=body.collection_name, version=1, items=items)
    storage._atomic_write(coll)
    return HarImportOutput(collection_id=coll.id, request_count=len(items))


@router.get("/har/export/{collection_id}")
def export_har(collection_id: str) -> dict[str, Any]:
    coll = storage.get(collection_id)
    if coll is None:
        raise HTTPException(status_code=404, detail="collection not found")
    entries = []
    for req in _flatten_requests(coll.items):
        entries.append(
            {
                "startedDateTime": datetime.now(tz=UTC).isoformat(),
                "time": 0,
                "request": {
                    "method": req.method or "GET",
                    "url": req.url or "",
                    "httpVersion": "HTTP/1.1",
                    "headers": [
                        {"name": key, "value": value}
                        for key, value in (req.headers or {}).items()
                    ],
                    "queryString": [
                        {"name": key, "value": value}
                        for key, value in parse_qsl(urlsplit(req.url or "").query)
                    ],
                    "postData": {"mimeType": "text/plain", "text": req.body or ""},
                    "headersSize": -1,
                    "bodySize": len((req.body or "").encode("utf-8")),
                },
                "response": {
                    "status": 0,
                    "statusText": "",
                    "httpVersion": "HTTP/1.1",
                    "headers": [],
                    "content": {"size": 0, "mimeType": "text/plain", "text": ""},
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": 0,
                },
                "cache": {},
                "timings": {"send": 0, "wait": 0, "receive": 0},
            }
        )
    return {
        "log": {
            "version": "1.2",
            "creator": {"name": "Theridion", "version": "0.0.1"},
            "entries": entries,
        }
    }
