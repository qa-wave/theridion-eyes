"""Keybindings: custom keyboard shortcut management."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/settings", tags=["keybindings"])

_FILE = "keybindings.json"

_DEFAULTS: dict[str, str] = {
    "send_request": "Ctrl+Enter",
    "save_request": "Ctrl+S",
    "new_request": "Ctrl+N",
    "toggle_sidebar": "Ctrl+B",
    "switch_environment": "Ctrl+E",
    "focus_url": "Ctrl+L",
    "close_tab": "Ctrl+W",
    "duplicate_request": "Ctrl+D",
}


class KeybindingsData(BaseModel):
    bindings: dict[str, str] = {}


def _path() -> Path:
    return storage.home_dir() / _FILE


@router.get("/keybindings", response_model=KeybindingsData)
async def get_keybindings() -> KeybindingsData:
    p = _path()
    if not p.exists():
        return KeybindingsData(bindings=_DEFAULTS.copy())
    data = json.loads(p.read_text(encoding="utf-8"))
    merged = {**_DEFAULTS, **data}
    return KeybindingsData(bindings=merged)


@router.put("/keybindings", response_model=KeybindingsData)
async def put_keybindings(body: KeybindingsData) -> KeybindingsData:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(body.bindings, indent=2), encoding="utf-8")
    return body
