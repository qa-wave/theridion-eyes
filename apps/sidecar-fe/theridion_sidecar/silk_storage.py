"""Silk run history — SQLite-backed persistence.

Schema
------
silk_runs(
    id TEXT PRIMARY KEY,
    spec_path TEXT NOT NULL,
    status TEXT NOT NULL,          -- "passed" | "failed" | "error"
    duration_ms INTEGER NOT NULL,
    started_at TEXT NOT NULL,      -- ISO-8601
    browsers TEXT NOT NULL,        -- JSON array e.g. '["chromium"]'
    trace_path TEXT,
    screenshot_paths TEXT,         -- JSON array
    a11y_violations_count INTEGER NOT NULL DEFAULT 0,
    stderr_tail TEXT NOT NULL DEFAULT '',
    json_report TEXT               -- full Playwright JSON as text
)

All writes are immediate (journal_mode=WAL for concurrent access).
The DB lives at $THERIDION_HOME/silk/history.db.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    d = storage.home_dir() / "silk"
    d.mkdir(parents=True, exist_ok=True)
    return d / "history.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS silk_runs (
            id TEXT PRIMARY KEY,
            spec_path TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            browsers TEXT NOT NULL DEFAULT '["chromium"]',
            trace_path TEXT,
            screenshot_paths TEXT,
            a11y_violations_count INTEGER NOT NULL DEFAULT 0,
            stderr_tail TEXT NOT NULL DEFAULT '',
            json_report TEXT
        )
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def save_run(
    *,
    run_id: str,
    spec_path: str,
    exit_code: int,
    duration_ms: int,
    browsers: list[str] | None = None,
    trace_path: str | None = None,
    screenshot_paths: list[str] | None = None,
    a11y_violations_count: int = 0,
    stderr_tail: str = "",
    json_report: dict[str, Any] | None = None,
) -> None:
    """Persist one Silk run to the history DB."""
    if exit_code == 0:
        status = "passed"
    elif exit_code == 1:
        status = "failed"
    else:
        status = "error"

    started_at = datetime.now(tz=timezone.utc).isoformat()
    browsers_json = json.dumps(browsers or ["chromium"])
    screenshots_json = json.dumps(screenshot_paths or [])
    report_json = json.dumps(json_report) if json_report else None

    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO silk_runs
              (id, spec_path, status, duration_ms, started_at, browsers,
               trace_path, screenshot_paths, a11y_violations_count,
               stderr_tail, json_report)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, spec_path, status, duration_ms, started_at,
                browsers_json, trace_path, screenshots_json,
                a11y_violations_count, stderr_tail, report_json,
            ),
        )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["browsers"] = json.loads(d.get("browsers") or '["chromium"]')
    d["screenshot_paths"] = json.loads(d.get("screenshot_paths") or "[]")
    if d.get("json_report"):
        try:
            d["json_report"] = json.loads(d["json_report"])
        except json.JSONDecodeError:
            d["json_report"] = None
    return d


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Return runs ordered by started_at DESC."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, spec_path, status, duration_ms, started_at, browsers,
                   trace_path, screenshot_paths, a11y_violations_count,
                   stderr_tail
            FROM silk_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_run(run_id: str) -> dict[str, Any] | None:
    """Return a single run (with json_report) or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM silk_runs WHERE id = ?", (run_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None
