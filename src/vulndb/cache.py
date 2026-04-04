"""SQLite cache layer for WordPress vulnerability data.

Follows the ct_collector/db.py pattern: WAL mode, Row factory, batch ops.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plugin_vulns (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL,
    vuln_uuid TEXT NOT NULL,
    name TEXT NOT NULL,
    max_version TEXT,
    max_operator TEXT,
    min_version TEXT,
    min_operator TEXT,
    unfixed TEXT DEFAULT '0',
    cvss_score TEXT,
    cvss_severity TEXT,
    cwe_ids TEXT,
    sources TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(slug, vuln_uuid)
);
CREATE INDEX IF NOT EXISTS idx_plugin_slug ON plugin_vulns(slug);

CREATE TABLE IF NOT EXISTS core_vulns (
    id INTEGER PRIMARY KEY,
    version TEXT NOT NULL,
    vuln_uuid TEXT NOT NULL,
    name TEXT NOT NULL,
    max_version TEXT,
    max_operator TEXT,
    min_version TEXT,
    min_operator TEXT,
    unfixed TEXT DEFAULT '0',
    cvss_score TEXT,
    cvss_severity TEXT,
    cwe_ids TEXT,
    sources TEXT,
    fetched_at TEXT NOT NULL,
    UNIQUE(version, vuln_uuid)
);
CREATE INDEX IF NOT EXISTS idx_core_version ON core_vulns(version);

CREATE TABLE IF NOT EXISTS lookup_meta (
    slug TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    vuln_count INTEGER DEFAULT 0,
    PRIMARY KEY (slug, asset_type)
);

CREATE TABLE IF NOT EXISTS wp_latest_versions (
    slug TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    latest_version TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (slug, asset_type)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_db(db_path: str) -> sqlite3.Connection:
    """Create schema and configure WAL mode. Returns read-write connection."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-4000")  # 4 MB
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def is_slug_cached(conn: sqlite3.Connection, slug: str, asset_type: str,
                   max_age_days: int = 7) -> bool:
    """Check if a slug was fetched recently enough."""
    row = conn.execute(
        "SELECT fetched_at FROM lookup_meta WHERE slug = ? AND asset_type = ?",
        (slug, asset_type),
    ).fetchone()
    if row is None:
        return False
    fetched = datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - fetched).days
    return age_days < max_age_days


def get_plugin_vulns(conn: sqlite3.Connection, slug: str) -> list[dict] | None:
    """Return cached vulns for a plugin slug, or None if not cached."""
    if not conn.execute(
        "SELECT 1 FROM lookup_meta WHERE slug = ? AND asset_type = 'plugin'",
        (slug,),
    ).fetchone():
        return None

    rows = conn.execute(
        "SELECT * FROM plugin_vulns WHERE slug = ?", (slug,)
    ).fetchall()
    return [_row_to_vuln(r) for r in rows]


def get_core_vulns(conn: sqlite3.Connection, version: str) -> list[dict] | None:
    """Return cached vulns for a WordPress core version, or None if not cached."""
    if not conn.execute(
        "SELECT 1 FROM lookup_meta WHERE slug = ? AND asset_type = 'core'",
        (version,),
    ).fetchone():
        return None

    rows = conn.execute(
        "SELECT * FROM core_vulns WHERE version = ?", (version,)
    ).fetchall()
    return [_row_to_vuln(r) for r in rows]


def store_plugin_vulns(conn: sqlite3.Connection, slug: str, vulns: list[dict]) -> None:
    """Store vulnerability data for a plugin slug. Replaces existing entries."""
    now = _now()
    conn.execute("DELETE FROM plugin_vulns WHERE slug = ?", (slug,))
    for v in vulns:
        conn.execute(
            "INSERT INTO plugin_vulns "
            "(slug, vuln_uuid, name, max_version, max_operator, min_version, min_operator, "
            "unfixed, cvss_score, cvss_severity, cwe_ids, sources, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                slug,
                v.get("uuid", ""),
                v.get("name", ""),
                v.get("max_version", ""),
                v.get("max_operator", ""),
                v.get("min_version", ""),
                v.get("min_operator", ""),
                v.get("unfixed", "0"),
                v.get("cvss_score", ""),
                v.get("cvss_severity", ""),
                json.dumps(v.get("cwe_ids", [])),
                json.dumps(v.get("sources", [])),
                now,
            ),
        )
    conn.execute(
        "INSERT OR REPLACE INTO lookup_meta (slug, asset_type, fetched_at, vuln_count) "
        "VALUES (?, 'plugin', ?, ?)",
        (slug, now, len(vulns)),
    )
    conn.commit()


def store_core_vulns(conn: sqlite3.Connection, version: str, vulns: list[dict]) -> None:
    """Store vulnerability data for a WordPress core version."""
    now = _now()
    conn.execute("DELETE FROM core_vulns WHERE version = ?", (version,))
    for v in vulns:
        conn.execute(
            "INSERT INTO core_vulns "
            "(version, vuln_uuid, name, max_version, max_operator, min_version, min_operator, "
            "unfixed, cvss_score, cvss_severity, cwe_ids, sources, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version,
                v.get("uuid", ""),
                v.get("name", ""),
                v.get("max_version", ""),
                v.get("max_operator", ""),
                v.get("min_version", ""),
                v.get("min_operator", ""),
                v.get("unfixed", "0"),
                v.get("cvss_score", ""),
                v.get("cvss_severity", ""),
                json.dumps(v.get("cwe_ids", [])),
                json.dumps(v.get("sources", [])),
                now,
            ),
        )
    conn.execute(
        "INSERT OR REPLACE INTO lookup_meta (slug, asset_type, fetched_at, vuln_count) "
        "VALUES (?, 'core', ?, ?)",
        (version, now, len(vulns)),
    )
    conn.commit()


def get_stale_slugs(conn: sqlite3.Connection, max_age_days: int = 7) -> list[tuple[str, str]]:
    """Return (slug, asset_type) pairs older than max_age_days."""
    rows = conn.execute(
        "SELECT slug, asset_type, fetched_at FROM lookup_meta"
    ).fetchall()
    stale = []
    now = datetime.now(timezone.utc)
    for row in rows:
        fetched = datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))
        if (now - fetched).days >= max_age_days:
            stale.append((row["slug"], row["asset_type"]))
    return stale


def _row_to_vuln(row: sqlite3.Row) -> dict:
    """Convert a SQLite row to a vulnerability dict."""
    d = dict(row)
    # Parse JSON fields
    for field in ("cwe_ids", "sources"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
    return d
