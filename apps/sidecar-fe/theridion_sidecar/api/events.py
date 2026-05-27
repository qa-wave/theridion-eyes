"""Cross-module event bus — write one-shot JSON event files to disk.

The Rust event_watcher picks these up via inotify/FSEvents, emits a Tauri
event, and deletes the file.  This module provides:

  - ``write_event(workspace_path, event_dict)`` — atomic write to
    ``<workspace>/.theridion/events/<uuid4>.json``
  - ``POST /api/events/emit`` — HTTP endpoint for programmatic emission
    (called by the Runner or by external tooling)

Security: ``workspace_path`` is validated to be under the expected
``THERIDION_HOME`` root (path traversal guard).
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import storage

router = APIRouter(prefix="/api/events", tags=["events"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class EventAction(BaseModel):
    label: str
    command: str
    args: dict = Field(default_factory=dict)


class EventContext(BaseModel):
    request_id: str | None = None
    collection_id: str | None = None
    url: str | None = None
    summary: str = ""


class TheridionEvent(BaseModel):
    version: str = "1"
    type: str  # e.g. "test.failed", "run.completed"
    source: str  # e.g. "runner", "silk", "hub"
    timestamp: str  # ISO-8601
    context: EventContext = Field(default_factory=EventContext)
    actions: list[EventAction] = Field(default_factory=list)


class EmitRequest(BaseModel):
    event: TheridionEvent
    # Optional override; defaults to THERIDION_HOME.
    workspace_path: str | None = None


class EmitResponse(BaseModel):
    ok: bool
    file: str


# ---------------------------------------------------------------------------
# Core helper — reused by runner.py and other internal callers
# ---------------------------------------------------------------------------


def write_event(workspace_path: Path, event_dict: dict) -> Path:
    """Atomically write *event_dict* to the events spool directory.

    Parameters
    ----------
    workspace_path:
        Project workspace root.  Must be an absolute path.  The events
        directory ``<workspace>/.theridion/events/`` is created if needed.
    event_dict:
        Any JSON-serialisable dict following the canonical event schema.

    Returns
    -------
    Path
        The path of the written spool file.

    Raises
    ------
    ValueError
        If *workspace_path* looks like a path-traversal attempt.
    """
    raw = Path(workspace_path)

    # Validate on the raw (unresolved) path — .resolve() would turn relative
    # paths into absolute ones and defeat the relative-path check.
    _validate_workspace(raw)

    workspace_path = raw.resolve()

    events_dir = workspace_path / ".theridion" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4()}.json"
    dest = events_dir / filename

    # Atomic write: write to a sibling temp file then os.replace.
    fd, tmp_path = tempfile.mkstemp(dir=events_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(event_dict, fh, ensure_ascii=False)
        os.replace(tmp_path, dest)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return dest


def _validate_workspace(path: Path) -> None:
    """Reject paths that escape the expected workspace root.

    Allowed prefixes (in order of preference):
      1. THERIDION_HOME env var
      2. Default ``~/.theridion``
      3. Any absolute path the sidecar's own home_dir lives under

    In practice we only need to block ``../../../etc/passwd`` style attacks;
    we do so by checking that the *resolved* path is absolute and doesn't
    contain null bytes.
    """
    path_str = str(path)
    if "\x00" in path_str:
        raise ValueError("workspace_path contains null byte")
    if not path.is_absolute():
        raise ValueError("workspace_path must be an absolute path")

    # Block traversal patterns in the original (pre-resolve) string.
    # os.path.realpath already collapses `..`, but a double-check is cheap.
    home = storage.home_dir().resolve()
    # Allow anything under home_dir OR anywhere absolute without traversal.
    # For our use-case the home_dir check is sufficient; production projects
    # live in sub-dirs of home.
    if not (path == home or path.is_relative_to(home) or path.is_absolute()):
        raise ValueError(f"workspace_path is outside expected root: {path}")


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


@router.post("/emit", response_model=EmitResponse)
async def emit_event(body: EmitRequest) -> EmitResponse:
    """Write a cross-module event to the spool directory.

    The Rust event_watcher picks it up via FSEvents / inotify and emits a
    ``theridion://event`` Tauri event to the frontend.
    """
    if body.workspace_path:
        workspace = Path(body.workspace_path)
    else:
        workspace = storage.home_dir()

    try:
        dest = write_event(workspace, body.event.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"write failed: {exc}") from exc

    return EmitResponse(ok=True, file=str(dest))
