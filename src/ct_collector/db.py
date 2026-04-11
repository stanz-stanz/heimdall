"""SQLite database layer for Certificate Transparency log storage.

Provides functions for initialising, querying, and maintaining a local CT
certificate database.  Designed for high-throughput inserts from CertStream
and low-latency reads from the scan worker.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

from loguru import logger

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS certificates (
    id INTEGER PRIMARY KEY,
    common_name TEXT NOT NULL,
    issuer_name TEXT,
    not_before TEXT,
    not_after TEXT,
    san_domains TEXT,
    seen_at TEXT NOT NULL,
    UNIQUE(common_name, not_before)
);
CREATE INDEX IF NOT EXISTS idx_cn ON certificates(common_name);
CREATE INDEX IF NOT EXISTS idx_san ON certificates(san_domains);
CREATE INDEX IF NOT EXISTS idx_seen_at ON certificates(seen_at);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Create the database schema and configure WAL mode.

    Parameters
    ----------
    db_path:
        Filesystem path for the SQLite database file.

    Returns
    -------
    sqlite3.Connection
        Read-write connection with WAL mode and performance PRAGMAs set.
    """
    # Ensure parent directory exists
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")  # 8 MB — safe for 256 MB container budget

    conn.executescript(_SCHEMA_SQL)
    conn.commit()

    logger.bind(context={"db_path": db_path}).info("ct_db_initialised")
    return conn


def open_readonly(db_path: str) -> sqlite3.Connection:
    """Open the database in read-only mode.

    Parameters
    ----------
    db_path:
        Filesystem path for the SQLite database file.

    Returns
    -------
    sqlite3.Connection
        Read-only connection.

    Raises
    ------
    sqlite3.OperationalError
        If the database file does not exist.
    """
    uri = f"file:{db_path}?immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def insert_certificate(
    conn: sqlite3.Connection,
    common_name: str,
    issuer_name: str,
    not_before: str,
    not_after: str,
    san_domains: list[str],
    seen_at: str,
) -> bool:
    """Insert a single certificate record, ignoring duplicates.

    Returns True if the row was inserted, False if it already existed.
    """
    san_json = json.dumps(san_domains, ensure_ascii=False)
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO certificates "
            "(common_name, issuer_name, not_before, not_after, san_domains, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (common_name, issuer_name, not_before, not_after, san_json, seen_at),
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as exc:
        logger.bind(context={"error": str(exc)}).warning("insert_certificate_failed")
        return False


def insert_certificates_batch(conn: sqlite3.Connection, certs: list[dict[str, Any]]) -> int:
    """Insert multiple certificates in a single transaction.

    Each dict in *certs* must have keys: common_name, issuer_name,
    not_before, not_after, san_domains (list[str]), seen_at.

    Returns the number of rows actually inserted (duplicates are ignored).
    """
    rows = [
        (
            c["common_name"],
            c["issuer_name"],
            c["not_before"],
            c["not_after"],
            json.dumps(c.get("san_domains", []), ensure_ascii=False),
            c["seen_at"],
        )
        for c in certs
    ]

    try:
        cursor = conn.executemany(
            "INSERT OR IGNORE INTO certificates "
            "(common_name, issuer_name, not_before, not_after, san_domains, seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        return cursor.rowcount
    except sqlite3.Error as exc:
        logger.bind(context={"error": str(exc)}).warning("insert_batch_failed")
        conn.rollback()
        return 0


def query_certificates(
    conn: sqlite3.Connection,
    domain: str,
    include_expired: bool = False,
) -> list[dict[str, str]]:
    """Query certificates matching a domain by CN exact, CN wildcard, or SAN.

    Parameters
    ----------
    domain:
        The domain to search for (e.g. ``example.dk``).
    include_expired:
        If False (default), exclude certificates whose ``not_after`` is in
        the past.

    Returns
    -------
    list[dict]
        Each dict has keys: common_name, issuer_name, not_before, not_after.
    """
    wildcard = f"*.{domain}"
    # SAN search uses JSON contains — the domain appears in the JSON array string
    san_pattern = f"%{domain}%"

    if include_expired:
        sql = (
            "SELECT DISTINCT common_name, issuer_name, not_before, not_after "
            "FROM certificates "
            "WHERE common_name = ? OR common_name = ? OR san_domains LIKE ? "
            "ORDER BY not_before DESC"
        )
        params: tuple = (domain, wildcard, san_pattern)
    else:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        sql = (
            "SELECT DISTINCT common_name, issuer_name, not_before, not_after "
            "FROM certificates "
            "WHERE (common_name = ? OR common_name = ? OR san_domains LIKE ?) "
            "AND not_after >= ? "
            "ORDER BY not_before DESC"
        )
        params = (domain, wildcard, san_pattern, now)

    try:
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "common_name": row["common_name"],
                "issuer_name": row["issuer_name"],
                "not_before": row["not_before"],
                "not_after": row["not_after"],
            }
            for row in rows
        ]
    except sqlite3.Error as exc:
        logger.bind(context={"domain": domain, "error": str(exc)}).warning("query_certificates_failed")
        return []


def cleanup_old_entries(conn: sqlite3.Connection, days: int = 90) -> int:
    """Delete certificates older than *days* and run incremental vacuum.

    Returns the number of rows deleted.
    """
    from datetime import timedelta

    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    try:
        cursor = conn.execute(
            "DELETE FROM certificates WHERE seen_at < ?",
            (cutoff,),
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.execute("PRAGMA incremental_vacuum")
        logger.bind(context={"deleted": deleted, "cutoff": cutoff}).info("cleanup_complete")
        return deleted
    except sqlite3.Error as exc:
        logger.bind(context={"error": str(exc)}).warning("cleanup_failed")
        conn.rollback()
        return 0


def get_db_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return summary statistics about the certificate database.

    Returns
    -------
    dict
        Keys: total_rows, oldest_entry, newest_entry, db_size_bytes.
    """
    stats: dict[str, Any] = {
        "total_rows": 0,
        "oldest_entry": None,
        "newest_entry": None,
        "db_size_bytes": 0,
    }

    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM certificates").fetchone()
        stats["total_rows"] = row["cnt"] if row else 0

        row = conn.execute("SELECT MIN(seen_at) as oldest FROM certificates").fetchone()
        stats["oldest_entry"] = row["oldest"] if row else None

        row = conn.execute("SELECT MAX(seen_at) as newest FROM certificates").fetchone()
        stats["newest_entry"] = row["newest"] if row else None

        # page_count * page_size gives total db size
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        stats["db_size_bytes"] = page_count * page_size

    except sqlite3.Error as exc:
        logger.bind(context={"error": str(exc)}).warning("get_db_stats_failed")

    return stats
