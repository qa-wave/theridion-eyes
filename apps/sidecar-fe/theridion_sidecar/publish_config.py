"""Publish-config persistence — stores RunResult v2 push targets.

Storage layout::

    $THERIDION_HOME/
    └── publish-config.json

The file holds a single JSON object matching ``PublishConfig``.  Writes are
atomic (write-temp-then-rename).  Tokens are never logged.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from . import storage


class PublishConfig(BaseModel):
    """Configuration for pushing RunResult v2 payloads to Weave / Hub."""

    weave_url: str = Field(
        default="",
        description="Weave ingest URL (e.g. https://weave.example.com/api/runs/ingest).",
    )
    weave_token: str = Field(
        default="",
        description="Bearer token for Weave (never logged).",
    )
    hub_url: str = Field(
        default="",
        description="Hub ingest URL (optional).",
    )
    hub_token: str = Field(
        default="",
        description="Bearer token for Hub (never logged, optional).",
    )
    enabled: bool = Field(
        default=False,
        description="When False the publisher is a no-op even if URLs are set.",
    )


def _config_path() -> Path:
    return storage.home_dir() / "publish-config.json"


def load() -> PublishConfig:
    """Return the persisted config, or defaults if none has been saved yet."""
    p = _config_path()
    if not p.exists():
        return PublishConfig()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return PublishConfig(**data)
    except Exception:
        return PublishConfig()


def save(cfg: PublishConfig) -> None:
    """Persist *cfg* atomically.  Tokens are written but never logged here."""
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix="publish-config.", suffix=".json.tmp", dir=str(p.parent)
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(mode="json"), f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
