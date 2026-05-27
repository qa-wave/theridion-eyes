"""Monitors: CRUD for scheduled collection runs."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/monitors", tags=["monitors"])

_FILE = "monitors.json"


class Monitor(BaseModel):
    id: str = ""
    collection_id: str = ""
    environment_id: str | None = None
    cron: str = "*/30 * * * *"
    enabled: bool = True
    last_run: str | None = None
    last_status: str | None = None


class MonitorList(BaseModel):
    monitors: list[Monitor] = []


def _path() -> Path:
    return storage.home_dir() / _FILE


def _load() -> list[Monitor]:
    p = _path()
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Monitor(**m) for m in data]


def _save(monitors: list[Monitor]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([m.model_dump() for m in monitors], indent=2), encoding="utf-8")


@router.get("", response_model=MonitorList)
async def list_monitors() -> MonitorList:
    return MonitorList(monitors=_load())


@router.post("/create", response_model=Monitor)
async def create_monitor(body: Monitor) -> Monitor:
    monitors = _load()
    body.id = uuid.uuid4().hex[:12]
    monitors.append(body)
    _save(monitors)
    return body


@router.delete("/{monitor_id}")
async def delete_monitor(monitor_id: str) -> dict:
    monitors = _load()
    filtered = [m for m in monitors if m.id != monitor_id]
    if len(filtered) == len(monitors):
        raise HTTPException(status_code=404, detail="Monitor not found")
    _save(filtered)
    return {"status": "deleted"}
