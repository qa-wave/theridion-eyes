"""Tests for Spin database state verification — snapshot/compare with SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from theridion_sidecar.spin.database import (
    assert_row_exists,
    compare_snapshot,
    count_rows,
    diff_snapshots,
    query_rows,
    take_snapshot,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sqlite_db(tmp_path: Path) -> str:
    """Create a temporary SQLite database with an orders table."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()
    return f"sqlite:///{db_path}"


def _insert_order(db_path: str, user_id: int = 1, status: str = "pending") -> None:
    clean_path = db_path.replace("sqlite:///", "").replace("sqlite://", "")
    conn = sqlite3.connect(clean_path)
    conn.execute("INSERT INTO orders (user_id, status) VALUES (?, ?)", (user_id, status))
    conn.commit()
    conn.close()


# ── count_rows ────────────────────────────────────────────────────────────────

def test_count_rows_empty_table(sqlite_db: str):
    assert count_rows(sqlite_db, "orders") == 0


def test_count_rows_with_data(sqlite_db: str):
    _insert_order(sqlite_db)
    _insert_order(sqlite_db)
    assert count_rows(sqlite_db, "orders") == 2


# ── take_snapshot ─────────────────────────────────────────────────────────────

def test_take_snapshot_empty(sqlite_db: str):
    snap = take_snapshot(sqlite_db, "orders")
    assert snap["table"] == "orders"
    assert snap["row_count"] == 0
    assert snap["sample_rows"] == []


def test_take_snapshot_with_rows(sqlite_db: str):
    _insert_order(sqlite_db, user_id=42)
    snap = take_snapshot(sqlite_db, "orders")
    assert snap["row_count"] == 1
    assert len(snap["sample_rows"]) == 1
    assert snap["sample_rows"][0]["user_id"] == 42


# ── compare_snapshot ──────────────────────────────────────────────────────────

def test_compare_snapshot_delta_plus_one(sqlite_db: str):
    snap_before = take_snapshot(sqlite_db, "orders")
    _insert_order(sqlite_db)
    ok, delta = compare_snapshot(sqlite_db, "orders", snap_before, expected_delta=1)
    assert ok is True
    assert delta == 1


def test_compare_snapshot_delta_mismatch(sqlite_db: str):
    snap_before = take_snapshot(sqlite_db, "orders")
    _insert_order(sqlite_db)
    _insert_order(sqlite_db)
    ok, delta = compare_snapshot(sqlite_db, "orders", snap_before, expected_delta=1)
    assert ok is False
    assert delta == 2


def test_compare_snapshot_no_change(sqlite_db: str):
    snap_before = take_snapshot(sqlite_db, "orders")
    ok, delta = compare_snapshot(sqlite_db, "orders", snap_before, expected_delta=0)
    assert ok is True
    assert delta == 0


def test_compare_snapshot_none_before(sqlite_db: str):
    _insert_order(sqlite_db)
    ok, delta = compare_snapshot(sqlite_db, "orders", None, expected_delta=1)
    assert ok is True
    assert delta == 1


# ── query_rows ────────────────────────────────────────────────────────────────

def test_query_rows_select_all(sqlite_db: str):
    _insert_order(sqlite_db, user_id=10, status="paid")
    rows = query_rows(sqlite_db, "SELECT * FROM orders")
    assert len(rows) == 1
    assert rows[0]["user_id"] == 10
    assert rows[0]["status"] == "paid"


def test_query_rows_with_params(sqlite_db: str):
    _insert_order(sqlite_db, user_id=1, status="pending")
    _insert_order(sqlite_db, user_id=2, status="paid")
    rows = query_rows(sqlite_db, "SELECT * FROM orders WHERE status = ?", ["paid"])
    assert len(rows) == 1
    assert rows[0]["user_id"] == 2


# ── diff_snapshots ────────────────────────────────────────────────────────────

def test_diff_snapshots_positive_delta():
    before = {"table": "orders", "row_count": 5, "sample_rows": []}
    after = {"table": "orders", "row_count": 8, "sample_rows": []}
    diff = diff_snapshots(before, after)
    assert diff["delta"] == 3
    assert diff["delta_str"] == "+3"


def test_diff_snapshots_negative_delta():
    before = {"table": "orders", "row_count": 10, "sample_rows": []}
    after = {"table": "orders", "row_count": 7, "sample_rows": []}
    diff = diff_snapshots(before, after)
    assert diff["delta"] == -3
    assert diff["delta_str"] == "-3"


def test_diff_snapshots_no_change():
    before = {"table": "orders", "row_count": 5, "sample_rows": []}
    diff = diff_snapshots(before, before)
    assert diff["delta"] == 0
