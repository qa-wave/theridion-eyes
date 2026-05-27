"""Tests for cross-module events API (api/events.py)."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from multiprocessing import Pool

import pytest
from fastapi.testclient import TestClient

from theridion_sidecar.api.events import write_event, _validate_workspace


# ---------------------------------------------------------------------------
# Unit tests for write_event helper
# ---------------------------------------------------------------------------


def test_write_event_creates_json_file(tmp_path: Path) -> None:
    """write_event produces a valid JSON file in the events spool dir."""
    event = {
        "version": "1",
        "type": "test.passed",
        "source": "runner",
        "timestamp": "2026-05-26T10:00:00Z",
        "context": {"summary": "All good"},
        "actions": [],
    }
    dest = write_event(tmp_path, event)
    assert dest.exists()
    assert dest.suffix == ".json"
    assert dest.parent == tmp_path / ".theridion" / "events"
    loaded = json.loads(dest.read_text())
    assert loaded["type"] == "test.passed"
    assert loaded["context"]["summary"] == "All good"


def test_write_event_atomic_no_partial_reads(tmp_path: Path) -> None:
    """The file should appear complete — no partial JSON mid-write."""
    event = {"version": "1", "type": "run.completed", "source": "runner",
             "timestamp": "2026-05-26T10:00:00Z", "context": {}, "actions": []}
    dest = write_event(tmp_path, event)
    # If JSON is malformed we'd get an exception here.
    data = json.loads(dest.read_text())
    assert data["type"] == "run.completed"


def test_write_event_unique_filenames(tmp_path: Path) -> None:
    """Each call produces a different filename (uuid4-based)."""
    event = {"version": "1", "type": "a", "source": "s",
             "timestamp": "T", "context": {}, "actions": []}
    paths = [write_event(tmp_path, event) for _ in range(5)]
    assert len({str(p) for p in paths}) == 5


def test_write_event_creates_missing_directory(tmp_path: Path) -> None:
    """Events dir is created if it doesn't exist."""
    workspace = tmp_path / "project"
    # workspace itself doesn't need to pre-exist — only resolved path matters.
    workspace.mkdir()
    event = {"version": "1", "type": "x", "source": "s",
             "timestamp": "T", "context": {}, "actions": []}
    dest = write_event(workspace, event)
    assert (workspace / ".theridion" / "events").is_dir()
    assert dest.exists()


# ---------------------------------------------------------------------------
# Path traversal guard
# ---------------------------------------------------------------------------


def test_path_traversal_rejected_null_byte(tmp_path: Path) -> None:
    """Null bytes in path are rejected."""
    with pytest.raises(ValueError, match="null byte"):
        _validate_workspace(Path("/tmp/safe\x00evil"))


def test_validate_workspace_accepts_absolute_path(tmp_path: Path) -> None:
    """Any absolute path without null bytes passes the basic guard."""
    # Just checking it doesn't raise.
    _validate_workspace(tmp_path)


def test_write_event_rejects_non_absolute(tmp_path: Path) -> None:
    """Relative workspace paths are rejected."""
    event = {"version": "1", "type": "x", "source": "s",
             "timestamp": "T", "context": {}, "actions": []}
    with pytest.raises(ValueError, match="absolute"):
        write_event(Path("relative/path"), event)


# ---------------------------------------------------------------------------
# Concurrent writes
# ---------------------------------------------------------------------------


def _write_one(args: tuple) -> str:
    """Worker target: write one event and return the file path string."""
    workspace_str, idx = args
    event = {"version": "1", "type": "concurrent.test", "source": "test",
             "timestamp": "2026-05-26T10:00:00Z",
             "context": {"summary": f"worker {idx}"},
             "actions": []}
    dest = write_event(Path(workspace_str), event)
    return str(dest)


def test_concurrent_writes_no_collision(tmp_path: Path) -> None:
    """Multiple concurrent writes produce distinct, valid files."""
    n = 8
    with Pool(processes=4) as pool:
        results = pool.map(_write_one, [(str(tmp_path), i) for i in range(n)])

    assert len(set(results)) == n, "Expected unique file paths"
    for path_str in results:
        p = Path(path_str)
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["type"] == "concurrent.test"


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------


def test_emit_endpoint_creates_file(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    """POST /api/events/emit writes a JSON file under the given workspace."""
    import theridion_sidecar.storage as _storage
    monkeypatch.setattr(_storage, "home_dir", lambda: tmp_path)

    payload = {
        "event": {
            "version": "1",
            "type": "incident.opened",
            "source": "silk",
            "timestamp": "2026-05-26T10:00:00Z",
            "context": {"summary": "POST /api/orders returned 500"},
            "actions": [
                {"label": "Open in Silk", "command": "silk.open", "args": {}}
            ],
        }
    }
    resp = client.post("/api/events/emit", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    dest = Path(body["file"])
    assert dest.exists()
    data = json.loads(dest.read_text())
    assert data["type"] == "incident.opened"


def test_emit_endpoint_rejects_traversal(client: TestClient) -> None:
    """POST /api/events/emit rejects a workspace_path that is relative."""
    payload = {
        "event": {
            "version": "1",
            "type": "x",
            "source": "s",
            "timestamp": "T",
            "context": {},
            "actions": [],
        },
        "workspace_path": "../../etc",
    }
    resp = client.post("/api/events/emit", json=payload)
    assert resp.status_code == 400
