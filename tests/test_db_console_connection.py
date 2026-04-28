"""Tests for src.db.console_connection — Stage A console.db factories.

Mirrors tests/test_db_connection.py (the sibling for clients.db). Slice 1
ships only the schema + connection factories; the operator-#0 seed is
deferred to slice 2 alongside the argon2-cffi dependency, so these tests
don't exercise it.

Coverage:
- All Stage A tables present after init_db_console().
- All Stage A indexes present (including partial / functional indexes).
- WAL + foreign_keys + synchronous + cache_size pragmas applied.
- Idempotent re-init (CREATE TABLE IF NOT EXISTS).
- Fail-loud when the schema file is missing — same contract as init_db().
- get_console_conn() returns a usable read/write connection without
  re-applying the schema.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import src.db.console_connection as cc
from src.db.console_connection import (
    DEFAULT_CONSOLE_DB_PATH,
    get_console_conn,
    init_db_console,
)

# ---------------------------------------------------------------------------
# Expected objects from docs/architecture/console-db-schema.sql
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {"operators", "sessions", "audit_log"}

EXPECTED_INDEXES = {
    "idx_operators_username_lower",
    "idx_operators_active",
    "idx_sessions_token_hash_active",
    "idx_sessions_operator",
    "idx_sessions_expires",
    "idx_console_audit_log_occurred",
    "idx_console_audit_log_operator",
    "idx_console_audit_log_target",
    "idx_console_audit_log_action",
    "idx_console_audit_log_request",
}


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_init_db_console_creates_tables(tmp_path: Path) -> None:
    """All Stage A tables are created by init_db_console."""
    conn = init_db_console(tmp_path / "console.db")
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {row["name"] for row in rows}
    missing = EXPECTED_TABLES - table_names
    assert not missing, f"Missing tables: {missing}"
    conn.close()


def test_init_db_console_creates_indexes(tmp_path: Path) -> None:
    """All Stage A indexes (including partial / functional) are created."""
    conn = init_db_console(tmp_path / "console.db")
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    index_names = {row["name"] for row in rows}
    missing = EXPECTED_INDEXES - index_names
    assert not missing, f"Missing indexes: {missing}"
    conn.close()


def test_init_db_console_pragmas(tmp_path: Path) -> None:
    """WAL mode, foreign_keys=ON, synchronous=NORMAL, cache_size=-8000."""
    conn = init_db_console(tmp_path / "console.db")

    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal == "wal", f"Expected WAL, got {journal}"

    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1, f"Expected foreign_keys=ON, got {fk}"

    sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    # synchronous=NORMAL = 1
    assert sync == 1, f"Expected synchronous=NORMAL (1), got {sync}"

    cache = conn.execute("PRAGMA cache_size").fetchone()[0]
    assert cache == -8000, f"Expected cache_size=-8000, got {cache}"

    conn.close()


def test_init_db_console_idempotent(tmp_path: Path) -> None:
    """Running init_db_console twice is a no-op — CREATE IF NOT EXISTS."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    # Second call must not raise; schema row count unchanged.
    # Filter out sqlite_* tables (sqlite_sequence is auto-created by
    # AUTOINCREMENT columns and isn't part of our schema).
    conn = init_db_console(db_path)
    rows = conn.execute(
        "SELECT count(*) FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    assert rows == len(EXPECTED_TABLES)
    conn.close()


def test_init_db_console_creates_parent_dir(tmp_path: Path) -> None:
    """Parent directories are created if they don't exist."""
    nested = tmp_path / "nested" / "subdir" / "console.db"
    assert not nested.parent.exists()
    conn = init_db_console(nested)
    assert nested.parent.is_dir()
    assert nested.is_file()
    conn.close()


def test_init_db_console_fails_loud_on_missing_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing schema file raises FileNotFoundError, not a silent empty DB.

    Mirrors the contract enforced by src.db.connection.init_db: if the
    Docker image was built without ``COPY docs/architecture/console-db-schema.sql``,
    the api must fail loud at startup so the misconfigured image is
    detected immediately, not after operators try to log in.
    """
    monkeypatch.setattr(cc, "_SCHEMA_PATH", tmp_path / "nonexistent.sql")
    with pytest.raises(FileNotFoundError, match="Console schema file not found"):
        init_db_console(tmp_path / "console.db")


def test_default_db_path_is_relative() -> None:
    """The default path is relative — mirrors ``src/db/connection._DEFAULT_DB_PATH``.

    Production override via the ``CONSOLE_DB_PATH`` env var resolves to
    ``/data/console/console.db`` (the named-volume mount target); tests
    running from the project root create a local ``data/console/`` that
    sits under the gitignored ``data/`` tree.
    """
    assert DEFAULT_CONSOLE_DB_PATH == "data/console/console.db"


# ---------------------------------------------------------------------------
# get_console_conn — runtime open path
# ---------------------------------------------------------------------------


def test_get_console_conn_after_init_works(tmp_path: Path) -> None:
    """get_console_conn opens a usable RW connection on an already-initialised DB."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()

    conn = get_console_conn(db_path)
    assert conn.row_factory is sqlite3.Row
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1, f"foreign_keys must be ON for FK enforcement, got {fk}"

    # Smoke test: can insert + read back from operators.
    conn.execute("BEGIN")
    conn.execute(
        "INSERT INTO operators "
        "(username, display_name, password_hash, role_hint, created_at, updated_at) "
        "VALUES ('alice', 'Alice', 'placeholder', 'operator', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    conn.execute("COMMIT")

    row = conn.execute("SELECT username FROM operators").fetchone()
    assert row["username"] == "alice"
    conn.close()


def test_operators_table_enforces_unique_username(tmp_path: Path) -> None:
    """The natural-key UNIQUE on username + the case-insensitive functional
    index together prevent both exact-case and case-variant duplicates."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    conn = get_console_conn(db_path)

    conn.execute(
        "INSERT INTO operators "
        "(username, display_name, password_hash, created_at, updated_at) "
        "VALUES ('federico', 'Federico', 'h', '2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    conn.commit()

    # Exact-case duplicate — caught by UNIQUE constraint.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO operators "
            "(username, display_name, password_hash, created_at, updated_at) "
            "VALUES ('federico', 'F2', 'h2', '2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
        )
        conn.commit()
    conn.rollback()

    # Case-variant — caught by idx_operators_username_lower (UNIQUE on LOWER(username)).
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO operators "
            "(username, display_name, password_hash, created_at, updated_at) "
            "VALUES ('Federico', 'F3', 'h3', '2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
        )
        conn.commit()
    conn.rollback()

    conn.close()


def test_audit_log_fk_restricts_operator_delete(tmp_path: Path) -> None:
    """ON DELETE RESTRICT on audit_log.operator_id and audit_log.session_id.

    The audit log is immutable; deleting an operator while audit rows
    reference them would orphan the trail. RESTRICT raises IntegrityError
    rather than silently nulling or cascading.
    """
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    conn = get_console_conn(db_path)

    conn.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', 'h', '2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    conn.execute(
        "INSERT INTO sessions "
        "(id, token_hash, operator_id, issued_at, expires_at, absolute_expires_at, csrf_token) "
        "VALUES (1, 'h1', 1, '2026-04-28T09:00:00Z', '2026-04-28T09:15:00Z', "
        "'2026-04-28T21:00:00Z', 'csrf1')"
    )
    conn.execute(
        "INSERT INTO audit_log "
        "(occurred_at, operator_id, session_id, action) "
        "VALUES ('2026-04-28T09:01:00Z', 1, 1, 'auth.login_ok')"
    )
    conn.commit()

    # Deleting the session that an audit row references must be blocked.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM sessions WHERE id = 1")
        conn.commit()
    conn.rollback()

    # Same for the operator. (The CASCADE on sessions.operator_id would
    # try to delete sessions, but RESTRICT on audit_log.session_id blocks
    # that, so the entire DELETE is rejected.)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM operators WHERE id = 1")
        conn.commit()
    conn.rollback()

    conn.close()


def test_sessions_fk_cascades_on_operator_delete(tmp_path: Path) -> None:
    """ON DELETE CASCADE on sessions.operator_id — disaster-recovery contract.

    Operators are normally disabled (disabled_at set), not hard-deleted. This
    test verifies the cascade anyway because the spec calls it out as the
    desired FK action and it's worth a regression tripwire.
    """
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    conn = get_console_conn(db_path)

    conn.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', 'h', '2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    conn.execute(
        "INSERT INTO sessions "
        "(token_hash, operator_id, issued_at, expires_at, absolute_expires_at, csrf_token) "
        "VALUES ('h1', 1, '2026-04-28T09:00:00Z', '2026-04-28T09:15:00Z', "
        "'2026-04-28T21:00:00Z', 'csrf1')"
    )
    conn.commit()

    assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1

    conn.execute("DELETE FROM operators WHERE id = 1")
    conn.commit()

    assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    conn.close()
