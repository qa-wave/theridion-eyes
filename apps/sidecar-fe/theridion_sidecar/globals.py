"""Global variables store — persistent key/value pairs that apply
to all requests regardless of environment or collection.

Stored at ``$THERIDION_HOME/globals.json``.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .storage import home_dir


class GlobalVariable(BaseModel):
    name: str
    value: str
    enabled: bool = True


class GlobalsStore(BaseModel):
    variables: list[GlobalVariable] = Field(default_factory=list)


def _path() -> Path:
    return home_dir() / "globals.json"


def load() -> GlobalsStore:
    p = _path()
    if not p.exists():
        return GlobalsStore()
    try:
        return GlobalsStore(**json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return GlobalsStore()


def save(store: GlobalsStore) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = store.model_dump(mode="json")
    fd, tmp_str = tempfile.mkstemp(prefix="globals.", suffix=".json.tmp", dir=str(p.parent))
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def as_dict() -> dict[str, str]:
    """Return enabled globals as a flat dict for variable resolution."""
    store = load()
    return {v.name: v.value for v in store.variables if v.enabled}
