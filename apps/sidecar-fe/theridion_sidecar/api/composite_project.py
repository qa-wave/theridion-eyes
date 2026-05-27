"""Composite project: explode/implode collections to/from directory structures."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from theridion_sidecar import storage

router = APIRouter(prefix="/api/format", tags=["composite-project"])


class ExplodeOutput(BaseModel):
    files_created: int = 0
    directory: str = ""


class ImplodeInput(BaseModel):
    directory: str


class ImplodeOutput(BaseModel):
    collection_id: str = ""
    items_loaded: int = 0


@router.post("/explode/{collection_id}", response_model=ExplodeOutput)
async def explode_collection(collection_id: str) -> ExplodeOutput:
    col = storage.load_collection(collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    out_dir = storage.home_dir() / "exploded" / collection_id
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in col.items:
        d = item.model_dump()
        name = d.get("name", f"item_{count}")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        fp = out_dir / f"{safe_name}.json"
        fp.write_text(json.dumps(d, indent=2), encoding="utf-8")
        count += 1

    # Write collection metadata
    meta = {"id": col.id, "name": col.name, "version": col.version}
    (out_dir / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return ExplodeOutput(files_created=count, directory=str(out_dir))


@router.post("/implode", response_model=ImplodeOutput)
async def implode_collection(body: ImplodeInput) -> ImplodeOutput:
    dir_path = Path(body.directory)
    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail="Directory not found")

    meta_path = dir_path / "_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        meta = {"id": dir_path.name, "name": dir_path.name, "version": 1}

    items: list[dict] = []
    for fp in sorted(dir_path.glob("*.json")):
        if fp.name.startswith("_"):
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        items.append(data)

    from theridion_sidecar.models import StoredCollection, CollectionItem
    col_items = [CollectionItem(**i) for i in items]
    col = StoredCollection(
        id=meta.get("id", dir_path.name),
        name=meta.get("name", dir_path.name),
        version=meta.get("version", 1),
        items=col_items,
    )
    storage.save_collection(col)

    return ImplodeOutput(collection_id=col.id, items_loaded=len(items))
