"""Workspace export/import — ZIP bundle of collections, envs, globals, settings."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import environments, storage
from ..globals import load as load_globals
from ..settings import load as load_settings
from ..storage import home_dir

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("/export")
async def export_workspace() -> StreamingResponse:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Collections
        coll_dir = home_dir() / "collections"
        if coll_dir.exists():
            for f in coll_dir.glob("*.json"):
                zf.writestr(f"collections/{f.name}", f.read_text())

        # Environments
        env_dir = home_dir() / "environments"
        if env_dir.exists():
            for f in env_dir.glob("*.json"):
                zf.writestr(f"environments/{f.name}", f.read_text())

        # Globals
        gp = home_dir() / "globals.json"
        if gp.exists():
            zf.writestr("globals.json", gp.read_text())

        # Settings
        sp = home_dir() / "settings.json"
        if sp.exists():
            zf.writestr("settings.json", sp.read_text())

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=theridion-workspace.zip"},
    )


class ImportResult(BaseModel):
    collections: int = 0
    environments: int = 0
    globals_imported: bool = False
    settings_imported: bool = False


@router.post("/import", response_model=ImportResult)
async def import_workspace(file: UploadFile) -> ImportResult:
    content = await file.read()
    result = ImportResult()
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                data = zf.read(name).decode("utf-8")
                if name.startswith("collections/") and name.endswith(".json"):
                    dest = home_dir() / "collections" / Path(name).name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(data)
                    result.collections += 1
                elif name.startswith("environments/") and name.endswith(".json"):
                    dest = home_dir() / "environments" / Path(name).name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(data)
                    result.environments += 1
                elif name == "globals.json":
                    (home_dir() / "globals.json").write_text(data)
                    result.globals_imported = True
                elif name == "settings.json":
                    (home_dir() / "settings.json").write_text(data)
                    result.settings_imported = True
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid ZIP: {e}") from e
    return result
