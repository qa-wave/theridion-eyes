"""Application settings — persisted at ~/.theridion/settings.json."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .storage import home_dir


class AISettings(BaseModel):
    provider: Literal["ollama", "openai", "anthropic"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"


class AppSettings(BaseModel):
    ai: AISettings = Field(default_factory=AISettings)


def _path() -> Path:
    return home_dir() / "settings.json"


def load() -> AppSettings:
    p = _path()
    if not p.exists():
        return AppSettings()
    try:
        return AppSettings(**json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return AppSettings()


def save(settings: AppSettings) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump(mode="json")
    fd, tmp_str = tempfile.mkstemp(prefix="settings.", suffix=".json.tmp", dir=str(p.parent))
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
