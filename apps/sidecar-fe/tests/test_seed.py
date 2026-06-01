"""Tests for the dev-mode seed (seed.py).

All tests run with THERIDION_HOME pointing at a pytest tmp_path so they never
touch the real ~/.theridion directory.

Covers:
- maybe_seed() runs without error in a fresh tmp_path
- v1 silk runs are inserted (10 rows)
- v2 marker is written after seed_all()
- 3 environments are created with correct variable counts
- globals.json is created with variables
- history.jsonl is created with 8 entries
- Screenshot PNGs are written for 3 runs
- Silk runs have screenshot_paths back-filled after seeding
- Baseline PNGs and .approved.json metadata are written (4 each)
- Idempotency: running maybe_seed() twice does not duplicate data
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def seeded_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a tmp_path that has been fully seeded via maybe_seed()."""
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    # Re-import after env override so storage.home_dir() picks up tmp_path.
    import importlib
    import theridion_sidecar.storage as _s
    import theridion_sidecar.seed as _seed

    importlib.reload(_s)
    importlib.reload(_seed)

    _seed.maybe_seed()
    return tmp_path


# ---------------------------------------------------------------------------
# Silk run history (v1 seed)
# ---------------------------------------------------------------------------

def test_silk_runs_seeded(seeded_home: Path) -> None:
    db = seeded_home / "silk" / "history.db"
    assert db.exists(), "silk/history.db must exist after seeding"
    with sqlite3.connect(str(db)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM silk_runs").fetchone()[0]
    assert count == 10, f"expected 10 silk runs, got {count}"


def test_v1_marker_written(seeded_home: Path) -> None:
    assert (seeded_home / "silk" / ".silk_seed_v1").exists()


# ---------------------------------------------------------------------------
# v2 marker
# ---------------------------------------------------------------------------

def test_v2_marker_written(seeded_home: Path) -> None:
    assert (seeded_home / ".seed_v2").exists()


# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

def test_three_environments_seeded(seeded_home: Path) -> None:
    env_files = list((seeded_home / "environments").glob("*.json"))
    assert len(env_files) == 3, f"expected 3 environment files, got {len(env_files)}"


def test_environment_variable_counts(seeded_home: Path) -> None:
    env_dir = seeded_home / "environments"
    all_envs = []
    for p in env_dir.glob("*.json"):
        data = json.loads(p.read_text())
        all_envs.append((data["name"], len(data["variables"])))
    names_vars = dict(all_envs)
    assert names_vars.get("Production") == 5
    assert names_vars.get("Staging") == 6
    assert names_vars.get("Local-dev") == 6


# ---------------------------------------------------------------------------
# Global variables
# ---------------------------------------------------------------------------

def test_globals_json_exists(seeded_home: Path) -> None:
    g = seeded_home / "globals.json"
    assert g.exists(), "globals.json must be created by seed"
    data = json.loads(g.read_text())
    assert "variables" in data
    assert len(data["variables"]) == 4


# ---------------------------------------------------------------------------
# Request history
# ---------------------------------------------------------------------------

def test_history_jsonl_exists(seeded_home: Path) -> None:
    h = seeded_home / "history.jsonl"
    assert h.exists(), "history.jsonl must be created by seed"


def test_history_entry_count(seeded_home: Path) -> None:
    h = seeded_home / "history.jsonl"
    entries = [json.loads(line) for line in h.read_text().strip().splitlines()]
    assert len(entries) == 8, f"expected 8 history entries, got {len(entries)}"


def test_history_entries_have_required_fields(seeded_home: Path) -> None:
    h = seeded_home / "history.jsonl"
    for line in h.read_text().strip().splitlines():
        entry = json.loads(line)
        for field in ("id", "method", "url", "status", "elapsed_ms", "timestamp"):
            assert field in entry, f"history entry missing field: {field}"


def test_history_methods_variety(seeded_home: Path) -> None:
    h = seeded_home / "history.jsonl"
    methods = {
        json.loads(line)["method"]
        for line in h.read_text().strip().splitlines()
    }
    assert "GET" in methods
    assert "POST" in methods
    assert "DELETE" in methods


# ---------------------------------------------------------------------------
# Screenshot PNGs
# ---------------------------------------------------------------------------

def test_screenshot_pngs_exist(seeded_home: Path) -> None:
    screenshots_found = 0
    for run_dir in (seeded_home / "silk" / "runs").iterdir():
        ss_dir = run_dir / "screenshots"
        if ss_dir.is_dir():
            screenshots_found += len(list(ss_dir.glob("*.png")))
    assert screenshots_found == 3, f"expected 3 screenshot PNGs, got {screenshots_found}"


def test_screenshot_pngs_are_valid_png(seeded_home: Path) -> None:
    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
    for run_dir in (seeded_home / "silk" / "runs").iterdir():
        ss_dir = run_dir / "screenshots"
        if ss_dir.is_dir():
            for png in ss_dir.glob("*.png"):
                header = png.read_bytes()[:8]
                assert header == PNG_MAGIC, f"{png.name} is not a valid PNG"


def test_silk_runs_screenshot_paths_backfilled(seeded_home: Path) -> None:
    db = seeded_home / "silk" / "history.db"
    with sqlite3.connect(str(db)) as conn:
        rows = conn.execute(
            "SELECT screenshot_paths FROM silk_runs WHERE screenshot_paths != '[]'"
        ).fetchall()
    assert len(rows) == 3, f"expected 3 runs with screenshot_paths, got {len(rows)}"
    for (paths_json,) in rows:
        paths = json.loads(paths_json)
        assert len(paths) == 1
        assert paths[0].endswith(".png")


# ---------------------------------------------------------------------------
# Visual regression baselines
# ---------------------------------------------------------------------------

def test_baseline_pngs_exist(seeded_home: Path) -> None:
    baselines_dir = seeded_home / "silk" / "baselines"
    assert baselines_dir.is_dir()
    pngs = list(baselines_dir.glob("*.png"))
    assert len(pngs) == 4, f"expected 4 baseline PNGs, got {len(pngs)}"


def test_baseline_metadata_exists(seeded_home: Path) -> None:
    baselines_dir = seeded_home / "silk" / "baselines"
    metas = list(baselines_dir.glob("*.approved.json"))
    assert len(metas) == 4, f"expected 4 .approved.json files, got {len(metas)}"


def test_baseline_metadata_content(seeded_home: Path) -> None:
    baselines_dir = seeded_home / "silk" / "baselines"
    for meta_path in baselines_dir.glob("*.approved.json"):
        meta = json.loads(meta_path.read_text())
        assert meta["approved"] is True
        assert "test_id" in meta
        assert "approved_by" in meta
        assert "approved_at" in meta


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_maybe_seed_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))
    import importlib
    import theridion_sidecar.storage as _s
    import theridion_sidecar.seed as _seed
    importlib.reload(_s)
    importlib.reload(_seed)

    _seed.maybe_seed()
    _seed.maybe_seed()  # second call must not duplicate

    db = tmp_path / "silk" / "history.db"
    with sqlite3.connect(str(db)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM silk_runs").fetchone()[0]
    assert count == 10, f"idempotency broken: expected 10 runs after 2×seed, got {count}"

    env_files = list((tmp_path / "environments").glob("*.json"))
    assert len(env_files) == 3, f"idempotency broken: expected 3 envs, got {len(env_files)}"

    h_lines = (tmp_path / "history.jsonl").read_text().strip().splitlines()
    assert len(h_lines) == 8, f"idempotency broken: expected 8 history entries, got {len(h_lines)}"

    baselines = list((tmp_path / "silk" / "baselines").glob("*.png"))
    assert len(baselines) == 4, f"idempotency broken: expected 4 baselines, got {len(baselines)}"


# ---------------------------------------------------------------------------
# Collections (v1 — ensure not broken)
# ---------------------------------------------------------------------------

def test_one_collection_seeded(seeded_home: Path) -> None:
    coll_files = list((seeded_home / "collections").glob("*.json"))
    assert len(coll_files) == 1, f"expected 1 collection, got {len(coll_files)}"
    data = json.loads(coll_files[0].read_text())
    assert data["name"] == "Example App — E2E Tests"
    assert len(data["items"]) == 6  # one entry per spec file
