"""Diagnostic endpoint — surfaces operational details for debugging.

Mostly useful when "something feels off" — wrong port, stale instance,
old code, weird storage path. Cheap to render so the desktop app can
poll it from a footer panel without worrying.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .. import __version__, storage

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


class Diagnostics(BaseModel):
    version: str
    pid: int
    python: str
    platform: str
    storage_home: str
    collections_dir: str
    collection_count: int
    env: dict[str, str]


@router.get("", response_model=Diagnostics)
def diagnostics() -> Diagnostics:
    summaries = storage.list_summaries()
    # Echo just our own env vars so we don't leak unrelated user secrets.
    env = {
        k: v
        for k, v in os.environ.items()
        if k.startswith("THERIDION_") or k in {"PYTHONPATH"}
    }
    return Diagnostics(
        version=__version__,
        pid=os.getpid(),
        python=sys.version.split()[0],
        platform=f"{platform.system()} {platform.machine()}",
        storage_home=str(storage.home_dir()),
        collections_dir=str(storage.collections_dir()),
        collection_count=len(summaries),
        env=env,
    )


_: Any = None  # placeholder to keep ruff happy if this file ever shrinks
