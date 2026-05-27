"""Team workspaces: local workspace management."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

_FILE = "workspaces.json"


class Workspace(BaseModel):
    id: str = ""
    name: str = ""
    collections: list[str] = []
    environments: list[str] = []
    members: list[str] = []


class WorkspaceList(BaseModel):
    workspaces: list[Workspace] = []


def _path() -> Path:
    return storage.home_dir() / _FILE


def _load() -> list[Workspace]:
    p = _path()
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Workspace(**w) for w in data]


def _save(workspaces: list[Workspace]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([w.model_dump() for w in workspaces], indent=2), encoding="utf-8")


@router.get("", response_model=WorkspaceList)
async def list_workspaces() -> WorkspaceList:
    return WorkspaceList(workspaces=_load())


@router.post("", response_model=Workspace)
async def create_workspace(body: Workspace) -> Workspace:
    workspaces = _load()
    body.id = uuid.uuid4().hex[:12]
    workspaces.append(body)
    _save(workspaces)
    return body


@router.put("/{workspace_id}", response_model=Workspace)
async def update_workspace(workspace_id: str, body: Workspace) -> Workspace:
    workspaces = _load()
    for i, w in enumerate(workspaces):
        if w.id == workspace_id:
            body.id = workspace_id
            workspaces[i] = body
            _save(workspaces)
            return body
    raise HTTPException(status_code=404, detail="Workspace not found")


@router.delete("/{workspace_id}")
async def delete_workspace(workspace_id: str) -> dict:
    workspaces = _load()
    filtered = [w for w in workspaces if w.id != workspace_id]
    if len(filtered) == len(workspaces):
        raise HTTPException(status_code=404, detail="Workspace not found")
    _save(filtered)
    return {"status": "deleted"}
