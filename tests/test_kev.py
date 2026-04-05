"""Tests for CISA KEV enrichment (src/vulndb/kev.py)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from src.vulndb.kev import (
    _is_fresh,
    enrich_with_kev,
    refresh_kev,
)
from src.vulndb.cache import init_db


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_vulndb.sqlite3")
    conn = init_db(db_path)
    return conn, db_path


def _make_kev_response(cve_ids: list[str]) -> dict:
    return {
        "title": "CISA KEV Catalog",
        "catalogVersion": "2026.04.05",
        "vulnerabilities": [
            {"cveID": cve, "vendorProject": "Test", "product": "Test",
             "vulnerabilityName": f"Test vuln {cve}"}
            for cve in cve_ids
        ],
    }


def _seed_kev(conn, cve_ids: list[str]) -> None:
    for cve in cve_ids:
        conn.execute("INSERT OR IGNORE INTO kev_entries (cve_id) VALUES (?)", (cve,))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT OR REPLACE INTO kev_meta (key, last_fetched_at, entry_count) "
        "VALUES ('catalog', ?, ?)", (now, len(cve_ids)),
    )
    conn.commit()


class TestIsFresh:
    def test_fresh_within_ttl(self, db):
        conn, _ = db
        _seed_kev(conn, ["CVE-2024-1234"])
        assert _is_fresh(conn, max_age_hours=24) is True

    def test_stale_beyond_ttl(self, db):
        conn, _ = db
        old = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT OR REPLACE INTO kev_meta (key, last_fetched_at, entry_count) "
            "VALUES ('catalog', ?, 1)", (old,),
        )
        conn.commit()
        assert _is_fresh(conn, max_age_hours=24) is False

    def test_empty_db(self, db):
        conn, _ = db
        assert _is_fresh(conn, max_age_hours=24) is False


class TestRefreshKev:
    @patch("src.vulndb.kev.requests.get")
    def test_stores_entries(self, mock_get, db):
        _, db_path = db
        mock_resp = MagicMock()
        mock_resp.json.return_value = _make_kev_response(
            ["CVE-2024-1234", "CVE-2025-5678"]
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        count = refresh_kev(db_path=db_path)
        assert count == 2

        conn = init_db(db_path)
        rows = conn.execute("SELECT cve_id FROM kev_entries").fetchall()
        assert {r["cve_id"] for r in rows} == {"CVE-2024-1234", "CVE-2025-5678"}

    @patch("src.vulndb.kev.requests.get")
    def test_skips_when_fresh(self, mock_get, db):
        conn, db_path = db
        _seed_kev(conn, ["CVE-2024-1234"])
        conn.close()

        count = refresh_kev(db_path=db_path, max_age_hours=24)
        assert count == 0
        mock_get.assert_not_called()

    @patch("src.vulndb.kev.requests.get")
    def test_handles_fetch_failure(self, mock_get, db):
        _, db_path = db
        mock_get.side_effect = Exception("network error")
        count = refresh_kev(db_path=db_path)
        assert count == 0


class TestEnrichWithKev:
    def test_flags_matching_findings(self, db):
        conn, db_path = db
        _seed_kev(conn, ["CVE-2024-1234", "CVE-2025-5678"])
        conn.close()

        findings = [
            {"severity": "high", "description": "Test", "cve_id": "CVE-2024-1234", "risk": "Bad"},
            {"severity": "medium", "description": "Other", "cve_id": "CVE-9999-0000", "risk": "Ok"},
        ]
        enrich_with_kev(findings, db_path=db_path)

        assert findings[0]["known_exploited"] is True
        assert "CISA" in findings[0]["risk"]
        assert findings[1].get("known_exploited") is None

    def test_leaves_findings_without_cve_id(self, db):
        conn, db_path = db
        _seed_kev(conn, ["CVE-2024-1234"])
        conn.close()

        findings = [
            {"severity": "low", "description": "Missing header", "risk": "Minor"},
        ]
        enrich_with_kev(findings, db_path=db_path)
        assert findings[0].get("known_exploited") is None

    def test_empty_findings(self, db):
        _, db_path = db
        result = enrich_with_kev([], db_path=db_path)
        assert result == []

    def test_no_kev_matches(self, db):
        conn, db_path = db
        _seed_kev(conn, ["CVE-2024-1234"])
        conn.close()

        findings = [
            {"severity": "high", "description": "Test", "cve_id": "CVE-9999-0000", "risk": "X"},
        ]
        enrich_with_kev(findings, db_path=db_path)
        assert findings[0].get("known_exploited") is None
