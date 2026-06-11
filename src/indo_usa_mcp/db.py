"""Thin PostgreSQL access layer using psycopg3.

A single module-level connection is lazily opened. Rows come back as dicts.
"""

from __future__ import annotations

import pathlib
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import settings

_conn: psycopg.Connection | None = None

# SQL migrations ship inside the package so they're present in any install (wheel/Docker).
SQL_DIR = pathlib.Path(__file__).resolve().parent / "sql"


def get_conn() -> psycopg.Connection:
    """Return a live connection, opening one on first use."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(
            settings.effective_database_url, row_factory=dict_row, autocommit=True
        )
    return _conn


def query(sql: str, params: Any = None) -> list[dict[str, Any]]:
    with get_conn().cursor() as cur:
        cur.execute(sql, params)
        if cur.description is None:
            return []
        return cur.fetchall()


def query_one(sql: str, params: Any = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Any = None) -> None:
    with get_conn().cursor() as cur:
        cur.execute(sql, params)


def init_db() -> None:
    """Apply every sql/*.sql migration in filename order (idempotent)."""
    conn = get_conn()
    for path in sorted(SQL_DIR.glob("*.sql")):
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))


def wait_for_schema(table: str = "agent_runs", timeout_s: int = 90) -> None:
    """Block until `table` exists (and the DB is reachable).

    Lets a worker process start independently of whichever process runs migrations,
    avoiding a startup race without doing concurrent DDL itself.
    """
    import time

    deadline = time.monotonic() + timeout_s
    while True:
        try:
            row = query_one("SELECT to_regclass(%s) AS t", (table,))
            if row and row["t"] is not None:
                return
        except psycopg.OperationalError:
            pass  # DB not accepting connections yet
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Schema table '{table}' not present after {timeout_s}s")
        time.sleep(2)
