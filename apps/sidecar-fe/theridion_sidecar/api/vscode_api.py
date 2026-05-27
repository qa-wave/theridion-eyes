"""VS Code API: expose sidecar status and collections for VS Code extension."""

from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel

from theridion_sidecar import __version__, storage

router = APIRouter(prefix="/api/vscode", tags=["vscode"])

_STARTED_AT = time.monotonic()


class VscodeStatus(BaseModel):
    status: str = "ok"
    version: str = ""
    uptime_seconds: float = 0


class VscodeCollection(BaseModel):
    id: str
    name: str
    request_count: int


class VscodeCollectionList(BaseModel):
    collections: list[VscodeCollection] = []


@router.get("/status", response_model=VscodeStatus)
async def vscode_status() -> VscodeStatus:
    return VscodeStatus(
        version=__version__,
        uptime_seconds=round(time.monotonic() - _STARTED_AT, 3),
    )


@router.get("/collections", response_model=VscodeCollectionList)
async def vscode_collections() -> VscodeCollectionList:
    summaries = storage.list_collections()
    items = [
        VscodeCollection(id=s.id, name=s.name, request_count=s.request_count)
        for s in summaries
    ]
    return VscodeCollectionList(collections=items)
