"""Spin database state verification — snapshot before test, compare after."""

from __future__ import annotations

from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────────────

def _connect_sqlite(connection_string: str):  # type: ignore[return]
    import sqlite3

    db_path = (
        connection_string.replace("sqlite:///", "")
        .replace("sqlite://", "")
        or ":memory:"
    )
    return sqlite3.connect(db_path)


def _connect_postgres(connection_string: str):  # type: ignore[return]
    from ..api.jdbc_query import _parse_pg_url
    import psycopg2

    params = _parse_pg_url(connection_string)
    conn = psycopg2.connect(**params)
    conn.autocommit = True
    return conn


def _get_connection(connection_string: str):  # type: ignore[return]
    cs = connection_string.lower()
    if "sqlite" in cs or cs.endswith(".db") or cs.endswith(".sqlite"):
        return _connect_sqlite(connection_string)
    if "postgresql" in cs or "postgres" in cs:
        return _connect_postgres(connection_string)
    raise ValueError(
        f"Unsupported DB. Use sqlite:// or postgresql:// prefix. Got: {connection_string!r}"
    )


# ── Public functions ─────────────────────────────────────────────────────────

def count_rows(connection_string: str, table: str) -> int:
    """Return the current row count for a given table."""
    conn = _get_connection(connection_string)
    try:
        cur = conn.cursor()
        # Use parameterized table name via format (table names can't be parameterized in SQL)
        # We sanitize: only allow word characters and dots
        import re
        if not re.match(r"^[\w.]+$", table):
            raise ValueError(f"Invalid table name: {table!r}")
        cur.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row = cur.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def query_rows(
    connection_string: str,
    query: str,
    params: list[Any] | None = None,
    max_rows: int = 1000,
) -> list[dict[str, Any]]:
    """Execute arbitrary SELECT and return list of dicts."""
    from ..api.jdbc_query import _run_sqlite, _run_postgres

    cs_lower = connection_string.lower()
    if "sqlite" in cs_lower or cs_lower.endswith(".db"):
        result = _run_sqlite(connection_string, query, params or [], max_rows)
    else:
        result = _run_postgres(connection_string, query, params or [], max_rows)

    if result.error:
        raise RuntimeError(result.error)
    return [dict(zip(result.columns, row)) for row in result.rows]


def take_snapshot(connection_string: str, table: str) -> dict[str, Any]:
    """Capture the current state of a table (row count + first 5 rows for audit)."""
    row_count = count_rows(connection_string, table)
    import re
    if not re.match(r"^[\w.]+$", table):
        raise ValueError(f"Invalid table name: {table!r}")
    try:
        sample_rows = query_rows(
            connection_string,
            f"SELECT * FROM {table} ORDER BY 1 DESC LIMIT 5",  # noqa: S608
        )
    except Exception:
        sample_rows = []
    return {
        "table": table,
        "row_count": row_count,
        "sample_rows": sample_rows,
    }


def compare_snapshot(
    connection_string: str,
    table: str,
    snapshot_before: dict[str, Any] | None,
    expected_delta: int,
) -> tuple[bool, int]:
    """Compare current row count against snapshot and assert expected delta.

    Returns (ok, actual_delta).
    """
    current_count = count_rows(connection_string, table)
    before_count = snapshot_before["row_count"] if snapshot_before else 0
    actual_delta = current_count - before_count
    return actual_delta == expected_delta, actual_delta


def assert_row_exists(
    connection_string: str,
    table: str,
    conditions: dict[str, Any],
) -> bool:
    """Assert that at least one row matching all conditions exists in the table."""
    import re
    if not re.match(r"^[\w.]+$", table):
        raise ValueError(f"Invalid table name: {table!r}")

    # Build WHERE clause with parameterized values
    where_parts = [f"{col} = %s" if "postgres" in connection_string.lower() else f"{col} = ?" for col in conditions]
    values = list(conditions.values())
    where_sql = " AND ".join(where_parts)
    query = f"SELECT COUNT(*) FROM {table} WHERE {where_sql}"  # noqa: S608

    try:
        rows = query_rows(connection_string, query, values)
        count = rows[0].get("count", rows[0].get("COUNT(*)", 0)) if rows else 0
        return int(count) > 0
    except Exception:
        return False


def diff_snapshots(
    snapshot_before: dict[str, Any],
    snapshot_after: dict[str, Any],
) -> dict[str, Any]:
    """Produce a human-readable diff between two snapshots."""
    before_count = snapshot_before.get("row_count", 0)
    after_count = snapshot_after.get("row_count", 0)
    delta = after_count - before_count
    return {
        "table": snapshot_before.get("table", "unknown"),
        "rows_before": before_count,
        "rows_after": after_count,
        "delta": delta,
        "delta_str": f"+{delta}" if delta > 0 else str(delta),
    }
