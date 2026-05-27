"""Favorites — pin/unpin requests for quick access."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..storage import home_dir

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class Favorite(BaseModel):
    collection_id: str
    request_id: str
    name: str = ""
    method: str = "GET"
    url: str = ""


class FavoritesList(BaseModel):
    items: list[Favorite] = Field(default_factory=list)


def _path() -> Path:
    return home_dir() / "favorites.json"


def _load() -> FavoritesList:
    p = _path()
    if not p.exists():
        return FavoritesList()
    try:
        return FavoritesList(**json.loads(p.read_text()))
    except Exception:
        return FavoritesList()


def _save(fl: FavoritesList) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="favs.", suffix=".json.tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(fl.model_dump(mode="json"), f, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(Path(tmp), p)
    except Exception:
        try: Path(tmp).unlink(missing_ok=True)
        except OSError: pass
        raise


@router.get("", response_model=FavoritesList)
def list_favorites() -> FavoritesList:
    return _load()


@router.post("", response_model=FavoritesList)
def add_favorite(body: Favorite) -> FavoritesList:
    fl = _load()
    # Don't duplicate
    if not any(f.request_id == body.request_id and f.collection_id == body.collection_id for f in fl.items):
        fl.items.insert(0, body)
    _save(fl)
    return fl


@router.delete("/{collection_id}/{request_id}", response_model=FavoritesList)
def remove_favorite(collection_id: str, request_id: str) -> FavoritesList:
    fl = _load()
    fl.items = [f for f in fl.items if not (f.collection_id == collection_id and f.request_id == request_id)]
    _save(fl)
    return fl
