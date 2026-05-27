"""JDBC query: execute SQL queries — SQLite and PostgreSQL supported."""

from __future__ import annotations

import sqlite3
from typing import Any
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/jdbc", tags=["jdbc"])


class JdbcInput(BaseModel):
    connection_string: str
    query: str
    params: list[Any] = []
    max_rows: int = 1000


class JdbcOutput(BaseModel):
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    error: str | None = None


# ── helpers ──────────────────────────────────────────────────────────────────


def _run_sqlite(connection_string: str, query: str, params: list[Any], max_rows: int) -> JdbcOutput:
    db_path = (
        connection_string.replace("sqlite:///", "").replace("sqlite://", "") or ":memory:"
    )
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute(query, params)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = [list(r) for r in cur.fetchmany(max_rows)]
        conn.close()
        return JdbcOutput(columns=columns, rows=rows, row_count=len(rows))
    except Exception as exc:
        return JdbcOutput(error=str(exc))


def _parse_pg_url(connection_string: str) -> dict[str, Any]:
    """Parse jdbc:postgresql://host:port/db or postgresql://host:port/db."""
    cs = connection_string
    # Strip JDBC prefix if present
    for prefix in ("jdbc:postgresql://", "jdbc:postgres://"):
        if cs.startswith(prefix):
            cs = "postgresql://" + cs[len(prefix):]
            break
    parsed = urlparse(cs)
    params: dict[str, Any] = {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 5432,
        "dbname": (parsed.path or "/").lstrip("/") or "postgres",
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "connect_timeout": 10,
        "options": "-c statement_timeout=10000",
    }
    return params


def _run_postgres(
    connection_string: str, query: str, params: list[Any], max_rows: int
) -> JdbcOutput:
    try:
        conn_params = _parse_pg_url(connection_string)
        conn = psycopg2.connect(**conn_params)
        conn.autocommit = True
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(query, params if params else None)
        columns: list[str] = []
        rows: list[list[Any]] = []
        if cur.description:
            columns = [d.name for d in cur.description]
            fetched = cur.fetchmany(max_rows)
            rows = [list(r.values()) for r in fetched]
        cur.close()
        conn.close()
        return JdbcOutput(columns=columns, rows=rows, row_count=len(rows))
    except Exception as exc:
        return JdbcOutput(error=str(exc))


# ── endpoint ─────────────────────────────────────────────────────────────────


@router.post("/query", response_model=JdbcOutput)
async def jdbc_query(body: JdbcInput) -> JdbcOutput:
    cs = body.connection_string.lower()
    if "sqlite" in cs or cs.endswith(".db") or cs.endswith(".sqlite"):
        return _run_sqlite(body.connection_string, body.query, body.params, body.max_rows)

    if "postgresql" in cs or "postgres" in cs:
        return _run_postgres(body.connection_string, body.query, body.params, body.max_rows)

    return JdbcOutput(
        error=(
            "Unsupported database type. Supported connection string prefixes: "
            "sqlite:///, jdbc:postgresql://, postgresql://"
        )
    )
