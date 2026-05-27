"""Cookie manager: full CRUD for cookies across environments."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/cookies", tags=["cookie-manager"])

_FILE = "cookies.json"


class CookieEntry(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    env_id: str | None = None


class CookieList(BaseModel):
    cookies: list[CookieEntry] = []


def _path() -> Path:
    return storage.home_dir() / _FILE


def _load() -> list[CookieEntry]:
    p = _path()
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [CookieEntry(**c) for c in data]


def _save(cookies: list[CookieEntry]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([c.model_dump() for c in cookies], indent=2), encoding="utf-8")


@router.get("/all", response_model=CookieList)
async def get_all_cookies() -> CookieList:
    return CookieList(cookies=_load())


@router.delete("/domain/{domain}")
async def delete_cookies_by_domain(domain: str) -> dict:
    cookies = _load()
    filtered = [c for c in cookies if c.domain != domain]
    _save(filtered)
    return {"status": "deleted", "removed": len(cookies) - len(filtered)}


@router.put("/edit", response_model=CookieList)
async def edit_cookies(body: CookieList) -> CookieList:
    _save(body.cookies)
    return body
