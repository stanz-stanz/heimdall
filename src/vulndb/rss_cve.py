"""RSS CVE watch — lightweight threat intelligence from public feeds.

Polls 3 high-signal RSS feeds (Wordfence, CISA, Bleeping Computer),
regex-extracts CVE IDs, and stores them in the existing vulndb SQLite
cache. No LLM, no Obsidian, no new container.

Enrichment function follows the same pattern as kev.py: mutate findings
in place, append risk text, set a boolean flag.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone

import feedparser
from loguru import logger

from .cache import init_db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = os.environ.get("VULNDB_PATH", "/data/cache/vulndb.sqlite3")

FEEDS: dict[str, str] = {
    "wordfence": "https://www.wordfence.com/blog/feed/",
    "cisa": "https://www.cisa.gov/cybersecurity-advisories/all.xml",
    "bleeping": "https://www.bleepingcomputer.com/feed/",
}

USER_AGENT = "Heimdall/1.0 (EASM; +https://heimdall.dk)"

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Schema (added to existing vulndb.sqlite3 alongside cache.py tables)
# ---------------------------------------------------------------------------

_RSS_SCHEMA = """
CREATE TABLE IF NOT EXISTS rss_cves (
    id INTEGER PRIMARY KEY,
    cve_id TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE(cve_id, source)
);
CREATE INDEX IF NOT EXISTS idx_rss_cve_id ON rss_cves(cve_id);
CREATE INDEX IF NOT EXISTS idx_rss_published ON rss_cves(published_at);

CREATE TABLE IF NOT EXISTS rss_feed_meta (
    feed_key TEXT PRIMARY KEY,
    last_fetched_at TEXT NOT NULL,
    entries_count INTEGER DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _init_rss_tables(conn: sqlite3.Connection) -> None:
    """Ensure RSS tables exist (idempotent)."""
    conn.executescript(_RSS_SCHEMA)
    conn.commit()


def _get_conn(db_path: str | None = None) -> sqlite3.Connection:
    """Get a connection with RSS tables initialized."""
    path = db_path or DEFAULT_DB_PATH
    conn = init_db(path)
    _init_rss_tables(conn)
    return conn


# ---------------------------------------------------------------------------
# Feed polling
# ---------------------------------------------------------------------------

def _is_feed_fresh(conn: sqlite3.Connection, feed_key: str,
                   max_age_hours: int) -> bool:
    """Check if a feed was fetched recently enough to skip."""
    row = conn.execute(
        "SELECT last_fetched_at FROM rss_feed_meta WHERE feed_key = ?",
        (feed_key,),
    ).fetchone()
    if row is None:
        return False
    fetched = datetime.fromisoformat(row["last_fetched_at"].replace("Z", "+00:00"))
    age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
    return age_hours < max_age_hours


def _extract_cves(text: str) -> list[str]:
    """Extract unique CVE IDs from a text string."""
    return list(set(_CVE_RE.findall(text.upper())))


def _parse_published(entry) -> str:
    """Extract published date from a feedparser entry as ISO 8601."""
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            pass
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            pass
    return _now()


def _poll_feed(conn: sqlite3.Connection, feed_key: str, feed_url: str) -> int:
    """Poll a single RSS feed and insert new CVE entries. Returns new count."""
    now = _now()
    new_count = 0

    try:
        feed = feedparser.parse(feed_url, agent=USER_AGENT)
    except Exception as exc:
        logger.warning("RSS fetch failed for {feed_key}: {exc}",
                       feed_key=feed_key, exc=exc)
        return 0

    if feed.bozo and not feed.entries:
        logger.warning("RSS parse error for {feed_key}: {exc}",
                       feed_key=feed_key, exc=feed.bozo_exception)
        return 0

    for entry in feed.entries:
        title = getattr(entry, "title", "")
        summary = getattr(entry, "summary", "")
        link = getattr(entry, "link", "")

        cve_ids = _extract_cves(f"{title} {summary}")
        if not cve_ids:
            continue

        published = _parse_published(entry)

        for cve_id in cve_ids:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO rss_cves
                       (cve_id, source, title, url, published_at, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (cve_id, feed_key, title[:500], link[:1000], published, now),
                )
                if conn.total_changes:
                    new_count += 1
            except sqlite3.Error:
                pass  # UNIQUE constraint — already have this cve_id+source

    conn.execute(
        """INSERT OR REPLACE INTO rss_feed_meta
           (feed_key, last_fetched_at, entries_count)
           VALUES (?, ?, ?)""",
        (feed_key, now, len(feed.entries)),
    )
    conn.commit()

    logger.info("rss_feed_polled: {feed_key} — {new} new CVEs from {total} entries",
                feed_key=feed_key, new=new_count, total=len(feed.entries))
    return new_count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def refresh_rss_cves(db_path: str | None = None,
                     max_age_hours: int = 12) -> int:
    """Poll all RSS feeds and store new CVE mentions.

    Skips feeds polled within ``max_age_hours``. Returns total new entries.
    """
    conn = _get_conn(db_path)
    total_new = 0

    for feed_key, feed_url in FEEDS.items():
        if _is_feed_fresh(conn, feed_key, max_age_hours):
            logger.debug("rss_feed_fresh: {feed_key} — skipping",
                         feed_key=feed_key)
            continue
        total_new += _poll_feed(conn, feed_key, feed_url)

    conn.close()
    return total_new


def lookup_rss_cves(conn: sqlite3.Connection, cve_ids: list[str],
                    window_days: int = 30) -> dict[str, dict]:
    """Look up which CVE IDs appear in recent RSS feeds.

    Returns a dict mapping cve_id → {sources, title, first_seen,
    last_seen, mention_count}.
    """
    if not cve_ids:
        return {}

    placeholders = ",".join("?" for _ in cve_ids)
    rows = conn.execute(
        f"""SELECT cve_id, source, title, published_at
            FROM rss_cves
            WHERE cve_id IN ({placeholders})
              AND published_at > datetime('now', '-{window_days} days')
            ORDER BY published_at DESC""",
        cve_ids,
    ).fetchall()

    result: dict[str, dict] = {}
    for row in rows:
        cve = row["cve_id"]
        if cve not in result:
            result[cve] = {
                "sources": [],
                "title": row["title"],
                "first_seen": row["published_at"],
                "last_seen": row["published_at"],
                "mention_count": 0,
            }
        entry = result[cve]
        if row["source"] not in entry["sources"]:
            entry["sources"].append(row["source"])
        entry["mention_count"] += 1
        if row["published_at"] < entry["first_seen"]:
            entry["first_seen"] = row["published_at"]
        if row["published_at"] > entry["last_seen"]:
            entry["last_seen"] = row["published_at"]

    return result


def enrich_with_rss_cves(findings: list[dict],
                         db_path: str | None = None) -> list[dict]:
    """Enrich findings by flagging CVEs trending in RSS feeds.

    Mutates each matching finding in place:
    - Appends RSS context to the ``risk`` field
    - Sets ``rss_trending: True``

    Follows the same pattern as enrich_with_kev() in kev.py.
    """
    if not findings:
        return findings

    cve_ids = [f["cve_id"] for f in findings if f.get("cve_id")]
    if not cve_ids:
        return findings

    conn = _get_conn(db_path)
    matches = lookup_rss_cves(conn, cve_ids)
    conn.close()

    if not matches:
        return findings

    flagged = 0
    for finding in findings:
        cve_id = finding.get("cve_id")
        if not cve_id or cve_id not in matches:
            continue

        match = matches[cve_id]
        source_names = ", ".join(match["sources"])
        count = match["mention_count"]

        rss_suffix = (
            f" This vulnerability is being actively discussed in the security"
            f" community ({count} mention{'s' if count != 1 else ''}"
            f" across {source_names} in the last 30 days)."
        )

        existing_risk = finding.get("risk", "")
        finding["risk"] = existing_risk + rss_suffix
        finding["rss_trending"] = True
        flagged += 1

        logger.info("RSS CVE match: {cve_id} — {count} mentions across {sources}",
                     cve_id=cve_id, count=count, sources=source_names)

    if flagged:
        logger.bind(context={"rss_matches": flagged, "total_findings": len(findings)}).info(
            "rss_cve_enrichment_complete"
        )

    return findings


def get_trending_cves(db_path: str | None = None,
                      window_days: int = 14,
                      min_sources: int = 2) -> list[dict]:
    """Return CVEs mentioned by multiple sources in the last N days.

    Useful for operator digests and future intelligence queries.
    """
    conn = _get_conn(db_path)

    rows = conn.execute(
        f"""SELECT cve_id, COUNT(DISTINCT source) as source_count,
                   COUNT(*) as mention_count,
                   MIN(published_at) as first_seen,
                   MAX(published_at) as last_seen,
                   GROUP_CONCAT(DISTINCT source) as sources
            FROM rss_cves
            WHERE published_at > datetime('now', '-{window_days} days')
            GROUP BY cve_id
            HAVING source_count >= ?
            ORDER BY source_count DESC, mention_count DESC""",
        (min_sources,),
    ).fetchall()

    conn.close()

    return [
        {
            "cve_id": row["cve_id"],
            "source_count": row["source_count"],
            "mention_count": row["mention_count"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "sources": row["sources"].split(","),
        }
        for row in rows
    ]
