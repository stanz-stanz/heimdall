"""Tests for src.db.connection — connection factory and schema initialization."""

from __future__ import annotations

import re
import sqlite3

import pytest

from src.db.connection import _now, init_db, open_readonly

# ---------------------------------------------------------------------------
# Expected objects from docs/architecture/client-db-schema.sql
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "industries",
    "clients",
    "client_domains",
    "consent_records",
    "pipeline_runs",
    "scan_history",
    "finding_definitions",
    "finding_occurrences",
    "finding_status_log",
    "brief_snapshots",
    "delivery_log",
}

EXPECTED_VIEWS = {
    "v_latest_run",
    "v_current_briefs",
    "v_bucket_distribution",
    "v_severity_breakdown",
    "v_plugin_exposure",
    "v_top_prospects",
    "v_cve_domains",
    "v_finding_trend",
    "v_findings",
}


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


def test_init_db_creates_tables(tmp_path: object) -> None:
    """All expected tables are created by init_db."""
    conn = init_db(tmp_path / "test.db")  # type: ignore[arg-type]
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {row["name"] for row in rows}
    missing = EXPECTED_TABLES - table_names
    assert not missing, f"Missing tables: {missing}"
    conn.close()


def test_init_db_creates_views(tmp_path: object) -> None:
    """All expected views are created by init_db."""
    conn = init_db(tmp_path / "test.db")  # type: ignore[arg-type]
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
    ).fetchall()
    view_names = {row["name"] for row in rows}
    missing = EXPECTED_VIEWS - view_names
    assert not missing, f"Missing views: {missing}"
    conn.close()


def test_init_db_pragmas(tmp_path: object) -> None:
    """WAL mode, synchronous=NORMAL, foreign_keys=ON, cache_size=-8000."""
    conn = init_db(tmp_path / "test.db")  # type: ignore[arg-type]

    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert journal == "wal", f"Expected WAL, got {journal}"

    sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    assert sync == 1, f"Expected synchronous=1 (NORMAL), got {sync}"

    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1, f"Expected foreign_keys=1, got {fk}"

    cache = conn.execute("PRAGMA cache_size").fetchone()[0]
    assert cache == -8000, f"Expected cache_size=-8000, got {cache}"

    conn.close()


def test_init_db_idempotent(tmp_path: object) -> None:
    """Calling init_db twice on the same path does not raise."""
    db_path = tmp_path / "test.db"  # type: ignore[operator]
    conn1 = init_db(db_path)
    conn1.close()

    conn2 = init_db(db_path)
    rows = conn2.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= table_names
    conn2.close()


def test_open_readonly_rejects_writes(tmp_path: object) -> None:
    """A read-only connection must reject INSERT statements."""
    db_path = tmp_path / "test.db"  # type: ignore[operator]
    conn = init_db(db_path)
    conn.close()

    ro_conn = open_readonly(db_path)
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute(
            "INSERT INTO industries (code, name_en) VALUES ('999999', 'Test')"
        )
    ro_conn.close()


def test_foreign_key_enforcement(tmp_path: object) -> None:
    """PRAGMA foreign_keys=ON is active and enforces REFERENCES constraints.

    The client-db-schema.sql uses comment-level FK annotations (not SQL
    REFERENCES clauses), so we create a temporary child table with an
    explicit REFERENCES to clients.cvr and verify the pragma rejects
    inserts with nonexistent parent keys.
    """
    conn = init_db(tmp_path / "test.db")  # type: ignore[arg-type]

    # Confirm the pragma is enabled
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1

    # Create a temp table with a real FK constraint
    conn.execute(
        "CREATE TABLE _fk_test ("
        "  id INTEGER PRIMARY KEY,"
        "  cvr TEXT NOT NULL REFERENCES clients(cvr)"
        ")"
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO _fk_test (cvr) VALUES ('00000000')"
        )

    conn.execute("DROP TABLE _fk_test")
    conn.close()


def test_now_format() -> None:
    """_now() returns a string matching ISO-8601 UTC format."""
    result = _now()
    # Pattern: YYYY-MM-DDTHH:MM:SSZ
    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
    assert re.match(pattern, result), f"_now() returned {result!r}, expected ISO-8601 UTC format"
