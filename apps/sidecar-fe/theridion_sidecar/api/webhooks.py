"""Webhooks: register webhook URLs that trigger collection runs."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_FILE = "webhooks.json"


class Webhook(BaseModel):
    id: str = ""
    collection_id: str = ""
    environment_id: str | None = None
    url: str = ""
    enabled: bool = True


class WebhookList(BaseModel):
    webhooks: list[Webhook] = []


def _path() -> Path:
    return storage.home_dir() / _FILE


def _load() -> list[Webhook]:
    p = _path()
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Webhook(**w) for w in data]


def _save(webhooks: list[Webhook]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([w.model_dump() for w in webhooks], indent=2), encoding="utf-8")


@router.get("", response_model=WebhookList)
async def list_webhooks() -> WebhookList:
    return WebhookList(webhooks=_load())


@router.post("/create", response_model=Webhook)
async def create_webhook(body: Webhook) -> Webhook:
    webhooks = _load()
    body.id = uuid.uuid4().hex[:12]
    webhooks.append(body)
    _save(webhooks)
    return body


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str) -> dict:
    webhooks = _load()
    filtered = [w for w in webhooks if w.id != webhook_id]
    if len(filtered) == len(webhooks):
        raise HTTPException(status_code=404, detail="Webhook not found")
    _save(filtered)
    return {"status": "deleted"}


@router.post("/{webhook_id}/trigger")
async def trigger_webhook(webhook_id: str) -> dict:
    webhooks = _load()
    wh = next((w for w in webhooks if w.id == webhook_id), None)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "triggered", "collection_id": wh.collection_id}
