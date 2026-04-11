"""Tests for the delivery_retry table in the client DB schema."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from src.db.connection import _load_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the full schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    schema_sql = _load_schema()
    conn.executescript(schema_sql)
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_retry_table_created():
    """delivery_retry table exists after schema is applied to a fresh DB."""
    conn = _make_conn()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='delivery_retry'"
    ).fetchall()
    assert len(rows) == 1, "delivery_retry table was not created by schema"
    conn.close()


def test_retry_insert_and_query():
    """Insert a pending retry entry; query for pending rows due now returns it."""
    conn = _make_conn()

    now = _now_utc()
    # next_retry_at is set to one minute in the past so it is overdue
    past = (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn.execute(
        """
        INSERT INTO delivery_retry
            (domain, brief_path, attempt, next_retry_at, last_error, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("example.dk", "/data/output/briefs/example.dk.json", 0, past, None, "pending", now),
    )
    conn.commit()

    rows = conn.execute(
        """
        SELECT * FROM delivery_retry
        WHERE status = 'pending'
          AND next_retry_at <= ?
        """,
        (now,),
    ).fetchall()

    assert len(rows) == 1
    assert rows[0]["domain"] == "example.dk"
    assert rows[0]["brief_path"] == "/data/output/briefs/example.dk.json"
    assert rows[0]["attempt"] == 0
    assert rows[0]["status"] == "pending"
    conn.close()


def test_retry_escalation_after_max_attempts():
    """A row with attempt=3 is NOT returned by a query filtering attempt < 3."""
    conn = _make_conn()

    now = _now_utc()
    past = (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn.execute(
        """
        INSERT INTO delivery_retry
            (domain, brief_path, attempt, next_retry_at, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("example.dk", "/data/output/briefs/example.dk.json", 3, past, "pending", now),
    )
    conn.commit()

    rows = conn.execute(
        """
        SELECT * FROM delivery_retry
        WHERE status = 'pending'
          AND next_retry_at <= ?
          AND attempt < 3
        """,
        (now,),
    ).fetchall()

    assert len(rows) == 0, (
        "Row with attempt=3 should not be returned when filtering attempt < 3"
    )
    conn.close()
