"""API catalog: registry of APIs."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/catalog", tags=["api-catalog"])

_FILE = "catalog.json"


class CatalogEntry(BaseModel):
    id: str = ""
    name: str = ""
    version: str = ""
    spec_url: str = ""
    owner: str = ""
    tags: list[str] = []
    status: str = "active"  # "active" | "deprecated"


class CatalogList(BaseModel):
    entries: list[CatalogEntry] = []


def _path() -> Path:
    return storage.home_dir() / _FILE


def _load() -> list[CatalogEntry]:
    p = _path()
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [CatalogEntry(**e) for e in data]


def _save(entries: list[CatalogEntry]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([e.model_dump() for e in entries], indent=2), encoding="utf-8")


@router.get("", response_model=CatalogList)
async def list_catalog() -> CatalogList:
    return CatalogList(entries=_load())


@router.post("", response_model=CatalogEntry)
async def create_catalog_entry(body: CatalogEntry) -> CatalogEntry:
    entries = _load()
    body.id = uuid.uuid4().hex[:12]
    entries.append(body)
    _save(entries)
    return body


@router.put("/{entry_id}", response_model=CatalogEntry)
async def update_catalog_entry(entry_id: str, body: CatalogEntry) -> CatalogEntry:
    entries = _load()
    for i, e in enumerate(entries):
        if e.id == entry_id:
            body.id = entry_id
            entries[i] = body
            _save(entries)
            return body
    raise HTTPException(status_code=404, detail="Entry not found")


@router.delete("/{entry_id}")
async def delete_catalog_entry(entry_id: str) -> dict:
    entries = _load()
    filtered = [e for e in entries if e.id != entry_id]
    if len(filtered) == len(entries):
        raise HTTPException(status_code=404, detail="Entry not found")
    _save(filtered)
    return {"status": "deleted"}
