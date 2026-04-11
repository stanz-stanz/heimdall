"""Tests for SQLite hardening — verify_integrity and startup protection."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest

from src.db.connection import init_db, verify_integrity


# ---------------------------------------------------------------------------
# verify_integrity tests
# ---------------------------------------------------------------------------


def test_verify_integrity_passes_on_good_db(tmp_path: object) -> None:
    """verify_integrity returns True for a freshly initialised database."""
    conn = init_db(tmp_path / "test.db")  # type: ignore[arg-type]
    assert verify_integrity(conn) is True
    conn.close()


def test_verify_integrity_detects_corruption() -> None:
    """verify_integrity returns False when conn.execute raises DatabaseError."""
    conn = MagicMock(spec=sqlite3.Connection)
    conn.execute.side_effect = sqlite3.DatabaseError("disk image is malformed")
    assert verify_integrity(conn) is False


def test_verify_integrity_returns_false_on_non_ok_result() -> None:
    """verify_integrity returns False when integrity_check returns a non-ok row."""
    conn = MagicMock(spec=sqlite3.Connection)
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("*** in page 1 of database: ...")
    conn.execute.return_value = mock_cursor
    assert verify_integrity(conn) is False


# ---------------------------------------------------------------------------
# PRAGMA smoke tests (delegated from connection.py but clarified here)
# ---------------------------------------------------------------------------


def test_init_db_uses_wal_mode(tmp_path: object) -> None:
    """PRAGMA journal_mode returns 'wal' after init_db."""
    conn = init_db(tmp_path / "test.db")  # type: ignore[arg-type]
    result = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert result == "wal", f"Expected 'wal', got {result!r}"
    conn.close()


def test_init_db_enables_foreign_keys(tmp_path: object) -> None:
    """PRAGMA foreign_keys returns 1 after init_db."""
    conn = init_db(tmp_path / "test.db")  # type: ignore[arg-type]
    result = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert result == 1, f"Expected 1 (ON), got {result!r}"
    conn.close()
