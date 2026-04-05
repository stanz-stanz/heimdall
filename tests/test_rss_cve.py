"""Tests for RSS CVE watch (src/vulndb/rss_cve.py)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from src.vulndb.rss_cve import (
    _extract_cves,
    _init_rss_tables,
    _is_feed_fresh,
    _poll_feed,
    enrich_with_rss_cves,
    get_trending_cves,
    lookup_rss_cves,
    refresh_rss_cves,
)
from src.vulndb.cache import init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Create an in-memory-like SQLite DB with RSS tables."""
    db_path = str(tmp_path / "test_vulndb.sqlite3")
    conn = init_db(db_path)
    _init_rss_tables(conn)
    return conn, db_path


def _insert_rss_cve(conn, cve_id, source="wordfence", title="Test",
                     url="https://example.com", published_at=None):
    """Helper: insert a test RSS CVE entry."""
    if published_at is None:
        published_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """INSERT OR IGNORE INTO rss_cves
           (cve_id, source, title, url, published_at, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (cve_id, source, title, url, published_at,
         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()


def _make_feed_entry(title, summary="", link="https://example.com",
                     published="Sat, 05 Apr 2026 12:00:00 GMT"):
    """Create a mock feedparser entry."""
    entry = MagicMock()
    entry.title = title
    entry.summary = summary
    entry.link = link
    entry.published_parsed = (2026, 4, 5, 12, 0, 0, 5, 95, 0)
    return entry


# ---------------------------------------------------------------------------
# CVE regex extraction
# ---------------------------------------------------------------------------

class TestExtractCves:
    def test_single_cve_in_title(self):
        assert _extract_cves("Critical: CVE-2026-1234 in WordPress") == ["CVE-2026-1234"]

    def test_multiple_cves(self):
        result = _extract_cves("CVE-2026-1234 and CVE-2026-5678 found")
        assert sorted(result) == ["CVE-2026-1234", "CVE-2026-5678"]

    def test_no_cves(self):
        assert _extract_cves("No vulnerabilities here") == []

    def test_case_insensitive(self):
        assert _extract_cves("cve-2026-1234 found") == ["CVE-2026-1234"]

    def test_five_digit_cve(self):
        assert _extract_cves("CVE-2026-12345 critical") == ["CVE-2026-12345"]

    def test_deduplicates(self):
        result = _extract_cves("CVE-2026-1234 and CVE-2026-1234 again")
        assert result == ["CVE-2026-1234"]


# ---------------------------------------------------------------------------
# Feed freshness
# ---------------------------------------------------------------------------

class TestFeedFreshness:
    def test_no_meta_not_fresh(self, db):
        conn, _ = db
        assert _is_feed_fresh(conn, "wordfence", max_age_hours=12) is False

    def test_recent_fetch_is_fresh(self, db):
        conn, _ = db
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO rss_feed_meta (feed_key, last_fetched_at, entries_count) VALUES (?, ?, ?)",
            ("wordfence", now, 10),
        )
        conn.commit()
        assert _is_feed_fresh(conn, "wordfence", max_age_hours=12) is True

    def test_old_fetch_not_fresh(self, db):
        conn, _ = db
        old = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO rss_feed_meta (feed_key, last_fetched_at, entries_count) VALUES (?, ?, ?)",
            ("wordfence", old, 10),
        )
        conn.commit()
        assert _is_feed_fresh(conn, "wordfence", max_age_hours=12) is False


# ---------------------------------------------------------------------------
# Feed polling
# ---------------------------------------------------------------------------

class TestPollFeed:
    @patch("src.vulndb.rss_cve.feedparser")
    def test_inserts_new_cves(self, mock_fp, db):
        conn, _ = db
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            _make_feed_entry("Critical CVE-2026-1234 in WooCommerce"),
            _make_feed_entry("No CVEs here"),
        ]
        mock_fp.parse.return_value = mock_feed

        count = _poll_feed(conn, "wordfence", "https://example.com/feed")
        rows = conn.execute("SELECT * FROM rss_cves").fetchall()
        assert len(rows) == 1
        assert rows[0]["cve_id"] == "CVE-2026-1234"
        assert rows[0]["source"] == "wordfence"

    @patch("src.vulndb.rss_cve.feedparser")
    def test_deduplicates_same_source(self, mock_fp, db):
        conn, _ = db
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            _make_feed_entry("CVE-2026-1234 in plugin A"),
        ]
        mock_fp.parse.return_value = mock_feed

        _poll_feed(conn, "wordfence", "https://example.com/feed")
        _poll_feed(conn, "wordfence", "https://example.com/feed")

        rows = conn.execute("SELECT * FROM rss_cves").fetchall()
        assert len(rows) == 1

    @patch("src.vulndb.rss_cve.feedparser")
    def test_same_cve_different_sources(self, mock_fp, db):
        conn, _ = db
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            _make_feed_entry("CVE-2026-1234 discovered"),
        ]
        mock_fp.parse.return_value = mock_feed

        _poll_feed(conn, "wordfence", "https://wordfence.com/feed")
        _poll_feed(conn, "bleeping", "https://bleeping.com/feed")

        rows = conn.execute("SELECT * FROM rss_cves").fetchall()
        assert len(rows) == 2

    @patch("src.vulndb.rss_cve.feedparser")
    def test_updates_feed_meta(self, mock_fp, db):
        conn, _ = db
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [_make_feed_entry("CVE-2026-1234")]
        mock_fp.parse.return_value = mock_feed

        _poll_feed(conn, "wordfence", "https://example.com/feed")

        meta = conn.execute("SELECT * FROM rss_feed_meta WHERE feed_key = 'wordfence'").fetchone()
        assert meta is not None
        assert meta["entries_count"] == 1

    @patch("src.vulndb.rss_cve.feedparser")
    def test_extracts_from_summary(self, mock_fp, db):
        conn, _ = db
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            _make_feed_entry("Security update available",
                             summary="Fixes CVE-2026-9999 auth bypass"),
        ]
        mock_fp.parse.return_value = mock_feed

        _poll_feed(conn, "wordfence", "https://example.com/feed")
        rows = conn.execute("SELECT * FROM rss_cves").fetchall()
        assert len(rows) == 1
        assert rows[0]["cve_id"] == "CVE-2026-9999"


# ---------------------------------------------------------------------------
# Refresh (top-level)
# ---------------------------------------------------------------------------

class TestRefresh:
    @patch("src.vulndb.rss_cve.feedparser")
    def test_skips_fresh_feeds(self, mock_fp, db):
        conn, db_path = db
        # Mark all feeds as fresh
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for key in ("wordfence", "cisa", "bleeping"):
            conn.execute(
                "INSERT INTO rss_feed_meta (feed_key, last_fetched_at, entries_count) VALUES (?, ?, ?)",
                (key, now, 0),
            )
        conn.commit()
        conn.close()

        count = refresh_rss_cves(db_path=db_path, max_age_hours=12)
        assert count == 0
        mock_fp.parse.assert_not_called()


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class TestLookup:
    def test_finds_matching_cves(self, db):
        conn, _ = db
        _insert_rss_cve(conn, "CVE-2026-1234", "wordfence", "WooCommerce auth bypass")
        _insert_rss_cve(conn, "CVE-2026-5678", "bleeping", "WordPress RCE")

        result = lookup_rss_cves(conn, ["CVE-2026-1234", "CVE-2026-5678"])
        assert "CVE-2026-1234" in result
        assert "CVE-2026-5678" in result
        assert "wordfence" in result["CVE-2026-1234"]["sources"]

    def test_no_match_returns_empty(self, db):
        conn, _ = db
        result = lookup_rss_cves(conn, ["CVE-9999-00001"])
        assert result == {}

    def test_empty_input_returns_empty(self, db):
        conn, _ = db
        result = lookup_rss_cves(conn, [])
        assert result == {}

    def test_respects_window(self, db):
        conn, _ = db
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _insert_rss_cve(conn, "CVE-2026-1234", published_at=old_date)

        result = lookup_rss_cves(conn, ["CVE-2026-1234"], window_days=30)
        assert "CVE-2026-1234" not in result

    def test_multi_source_counted(self, db):
        conn, _ = db
        _insert_rss_cve(conn, "CVE-2026-1234", "wordfence")
        _insert_rss_cve(conn, "CVE-2026-1234", "bleeping")

        result = lookup_rss_cves(conn, ["CVE-2026-1234"])
        assert result["CVE-2026-1234"]["mention_count"] == 2
        assert sorted(result["CVE-2026-1234"]["sources"]) == ["bleeping", "wordfence"]


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

class TestEnrich:
    def test_appends_risk_text(self, db):
        conn, db_path = db
        _insert_rss_cve(conn, "CVE-2026-1234", "wordfence")
        conn.close()

        findings = [
            {"cve_id": "CVE-2026-1234", "severity": "high",
             "risk": "Original risk.", "description": "Test vuln"},
        ]
        result = enrich_with_rss_cves(findings, db_path=db_path)
        assert "actively discussed" in result[0]["risk"]
        assert "Original risk." in result[0]["risk"]

    def test_sets_rss_trending(self, db):
        conn, db_path = db
        _insert_rss_cve(conn, "CVE-2026-1234", "wordfence")
        conn.close()

        findings = [
            {"cve_id": "CVE-2026-1234", "severity": "high",
             "risk": "Risk.", "description": "Test"},
        ]
        enrich_with_rss_cves(findings, db_path=db_path)
        assert findings[0]["rss_trending"] is True

    def test_no_match_unchanged(self, db):
        _, db_path = db
        findings = [
            {"cve_id": "CVE-9999-00001", "severity": "medium",
             "risk": "Some risk.", "description": "Unrelated"},
        ]
        original_risk = findings[0]["risk"]
        enrich_with_rss_cves(findings, db_path=db_path)
        assert findings[0]["risk"] == original_risk
        assert "rss_trending" not in findings[0]

    def test_empty_findings(self, db):
        _, db_path = db
        result = enrich_with_rss_cves([], db_path=db_path)
        assert result == []

    def test_findings_without_cve_id(self, db):
        _, db_path = db
        findings = [
            {"severity": "low", "risk": "Missing header.", "description": "No CVE"},
        ]
        enrich_with_rss_cves(findings, db_path=db_path)
        assert "rss_trending" not in findings[0]

    def test_mutates_in_place(self, db):
        conn, db_path = db
        _insert_rss_cve(conn, "CVE-2026-1234")
        conn.close()

        findings = [{"cve_id": "CVE-2026-1234", "severity": "high",
                     "risk": "Risk.", "description": "Test"}]
        result = enrich_with_rss_cves(findings, db_path=db_path)
        assert result is findings


# ---------------------------------------------------------------------------
# Trending
# ---------------------------------------------------------------------------

class TestTrending:
    def test_multi_source_appears(self, db):
        conn, db_path = db
        _insert_rss_cve(conn, "CVE-2026-1234", "wordfence")
        _insert_rss_cve(conn, "CVE-2026-1234", "bleeping")
        conn.close()

        trending = get_trending_cves(db_path=db_path, window_days=14, min_sources=2)
        assert len(trending) == 1
        assert trending[0]["cve_id"] == "CVE-2026-1234"
        assert trending[0]["source_count"] == 2

    def test_single_source_excluded(self, db):
        conn, db_path = db
        _insert_rss_cve(conn, "CVE-2026-1234", "wordfence")
        conn.close()

        trending = get_trending_cves(db_path=db_path, window_days=14, min_sources=2)
        assert len(trending) == 0

    def test_old_entries_excluded(self, db):
        conn, db_path = db
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _insert_rss_cve(conn, "CVE-2026-1234", "wordfence", published_at=old_date)
        _insert_rss_cve(conn, "CVE-2026-1234", "bleeping", published_at=old_date)
        conn.close()

        trending = get_trending_cves(db_path=db_path, window_days=14, min_sources=2)
        assert len(trending) == 0
