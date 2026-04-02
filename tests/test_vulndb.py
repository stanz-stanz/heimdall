"""Tests for the WordPress vulnerability database (WPVulnerability API + cache)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.vulndb.cache import (
    get_core_vulns,
    get_plugin_vulns,
    get_stale_slugs,
    init_db,
    is_slug_cached,
    store_core_vulns,
    store_plugin_vulns,
)
from src.vulndb.client import _normalize_vuln
from src.vulndb.matcher import (
    build_findings,
    extract_primary_cve,
    is_vulnerable,
    map_severity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    conn = init_db(str(tmp_path / "vulndb.sqlite3"))
    yield conn
    conn.close()


@pytest.fixture
def sample_vuln():
    """A typical normalized vulnerability dict."""
    return {
        "uuid": "abc123",
        "name": "Contact Form 7 [contact-form-7] < 5.3.2",
        "max_version": "5.3.2",
        "max_operator": "lt",
        "min_version": "",
        "min_operator": "",
        "unfixed": "0",
        "cvss_score": "9.8",
        "cvss_severity": "c",
        "cwe_ids": ["CWE-434"],
        "sources": [
            {"id": "CVE-2020-35489", "name": "CVE-2020-35489", "link": "https://cve.org/..."},
            {"id": "abc-uuid", "name": "Unrestricted File Upload", "link": "https://wpscan.com/..."},
        ],
    }


@pytest.fixture
def sample_vuln_range():
    """A vuln with both min and max version constraints."""
    return {
        "uuid": "def456",
        "name": "Plugin X >= 3.0 and < 5.0",
        "max_version": "5.0.0",
        "max_operator": "lt",
        "min_version": "3.0.0",
        "min_operator": "gte",
        "unfixed": "0",
        "cvss_score": "7.5",
        "cvss_severity": "h",
        "cwe_ids": ["CWE-79"],
        "sources": [{"id": "CVE-2023-12345", "name": "CVE-2023-12345", "link": ""}],
    }


@pytest.fixture
def sample_api_response():
    """Raw WPVulnerability API response for a plugin."""
    return {
        "error": 0,
        "data": {
            "name": "Contact Form 7",
            "plugin": "contact-form-7",
            "vulnerability": [
                {
                    "uuid": "abc123",
                    "name": "Contact Form 7 [contact-form-7] < 5.3.2",
                    "operator": {
                        "max_version": "5.3.2",
                        "max_operator": "lt",
                        "min_version": None,
                        "min_operator": None,
                        "unfixed": "0",
                    },
                    "source": [
                        {"id": "CVE-2020-35489", "name": "CVE-2020-35489",
                         "link": "https://cve.org/", "description": "File upload vuln"},
                    ],
                    "impact": {
                        "cvss": {"score": "9.8", "severity": "c"},
                        "cwe": [{"cwe": "CWE-434", "name": "Unrestricted Upload"}],
                    },
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


class TestCache:
    def test_init_creates_tables(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = {t["name"] for t in tables}
        assert "plugin_vulns" in names
        assert "core_vulns" in names
        assert "lookup_meta" in names

    def test_store_and_retrieve_plugin(self, db, sample_vuln):
        store_plugin_vulns(db, "contact-form-7", [sample_vuln])
        vulns = get_plugin_vulns(db, "contact-form-7")
        assert vulns is not None
        assert len(vulns) == 1
        assert vulns[0]["name"] == "Contact Form 7 [contact-form-7] < 5.3.2"
        assert vulns[0]["cvss_severity"] == "c"

    def test_uncached_returns_none(self, db):
        assert get_plugin_vulns(db, "nonexistent") is None

    def test_store_empty_vulns(self, db):
        store_plugin_vulns(db, "safe-plugin", [])
        vulns = get_plugin_vulns(db, "safe-plugin")
        assert vulns is not None
        assert len(vulns) == 0

    def test_is_slug_cached_fresh(self, db, sample_vuln):
        store_plugin_vulns(db, "contact-form-7", [sample_vuln])
        assert is_slug_cached(db, "contact-form-7", "plugin", max_age_days=7)

    def test_is_slug_cached_not_present(self, db):
        assert not is_slug_cached(db, "unknown", "plugin")

    def test_store_replaces_existing(self, db, sample_vuln):
        store_plugin_vulns(db, "cf7", [sample_vuln])
        sample_vuln_2 = {**sample_vuln, "uuid": "xyz789", "name": "New vuln"}
        store_plugin_vulns(db, "cf7", [sample_vuln_2])
        vulns = get_plugin_vulns(db, "cf7")
        assert len(vulns) == 1
        assert vulns[0]["name"] == "New vuln"

    def test_core_vulns(self, db, sample_vuln):
        store_core_vulns(db, "6.9.4", [sample_vuln])
        vulns = get_core_vulns(db, "6.9.4")
        assert vulns is not None
        assert len(vulns) == 1

    def test_stale_slugs(self, db, sample_vuln):
        store_plugin_vulns(db, "old-plugin", [sample_vuln])
        # Force old timestamp
        db.execute(
            "UPDATE lookup_meta SET fetched_at = '2020-01-01T00:00:00Z' WHERE slug = 'old-plugin'"
        )
        db.commit()
        stale = get_stale_slugs(db, max_age_days=7)
        assert ("old-plugin", "plugin") in stale

    def test_json_fields_roundtrip(self, db, sample_vuln):
        store_plugin_vulns(db, "cf7", [sample_vuln])
        vulns = get_plugin_vulns(db, "cf7")
        assert vulns[0]["cwe_ids"] == ["CWE-434"]
        assert isinstance(vulns[0]["sources"], list)
        assert vulns[0]["sources"][0]["id"] == "CVE-2020-35489"


# ---------------------------------------------------------------------------
# Client tests
# ---------------------------------------------------------------------------


class TestClient:
    def test_normalize_vuln(self):
        raw = {
            "uuid": "abc",
            "name": "Test Vuln",
            "operator": {"max_version": "1.0", "max_operator": "lt",
                         "min_version": None, "min_operator": None, "unfixed": "0"},
            "source": [{"id": "CVE-2024-1234", "name": "Test", "link": ""}],
            "impact": {
                "cvss": {"score": "7.5", "severity": "h"},
                "cwe": [{"cwe": "CWE-79"}],
            },
        }
        result = _normalize_vuln(raw)
        assert result["uuid"] == "abc"
        assert result["max_version"] == "1.0"
        assert result["max_operator"] == "lt"
        assert result["cvss_score"] == "7.5"
        assert result["cvss_severity"] == "h"
        assert result["cwe_ids"] == ["CWE-79"]
        assert result["sources"][0]["id"] == "CVE-2024-1234"

    def test_normalize_vuln_missing_fields(self):
        raw = {"uuid": "x", "name": "Minimal", "operator": {}, "source": [], "impact": {}}
        result = _normalize_vuln(raw)
        assert result["max_version"] == ""
        assert result["cvss_score"] == ""
        assert result["cwe_ids"] == []
        assert result["sources"] == []

    @patch("src.vulndb.client.requests.get")
    def test_fetch_plugin_success(self, mock_get, sample_api_response):
        from src.vulndb.client import fetch_plugin_vulns

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = sample_api_response
        mock_get.return_value = mock_resp

        status, vulns = fetch_plugin_vulns("contact-form-7")
        assert status == 200
        assert len(vulns) == 1
        assert vulns[0]["uuid"] == "abc123"

    @patch("src.vulndb.client.requests.get")
    def test_fetch_plugin_not_found(self, mock_get):
        from src.vulndb.client import fetch_plugin_vulns

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "error": 0, "data": {"plugin": "xyz", "vulnerability": None},
        }
        mock_get.return_value = mock_resp

        status, vulns = fetch_plugin_vulns("nonexistent-plugin")
        assert status == 200
        assert vulns == []

    @patch("src.vulndb.client.requests.get")
    def test_fetch_plugin_api_error(self, mock_get):
        from src.vulndb.client import fetch_plugin_vulns

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": 1, "message": "Invalid"}
        mock_get.return_value = mock_resp

        status, vulns = fetch_plugin_vulns("bad-request")
        assert vulns == []

    @patch("src.vulndb.client.requests.get")
    def test_fetch_network_error(self, mock_get):
        from src.vulndb.client import fetch_plugin_vulns
        import requests as req

        mock_get.side_effect = req.ConnectionError("timeout")

        status, vulns = fetch_plugin_vulns("any-plugin")
        assert status == 0
        assert vulns == []


# ---------------------------------------------------------------------------
# Version matcher tests
# ---------------------------------------------------------------------------


class TestMatcher:
    def test_vulnerable_lt(self, sample_vuln):
        assert is_vulnerable("5.3.1", sample_vuln)  # < 5.3.2 → vulnerable
        assert not is_vulnerable("5.3.2", sample_vuln)  # not < 5.3.2
        assert not is_vulnerable("6.0.0", sample_vuln)

    def test_vulnerable_lte(self):
        vuln = {"max_version": "2.0.0", "max_operator": "lte"}
        assert is_vulnerable("2.0.0", vuln)
        assert is_vulnerable("1.9.9", vuln)
        assert not is_vulnerable("2.0.1", vuln)

    def test_vulnerable_range(self, sample_vuln_range):
        assert is_vulnerable("3.0.0", sample_vuln_range)  # >= 3.0.0
        assert is_vulnerable("4.5.0", sample_vuln_range)
        assert not is_vulnerable("2.9.9", sample_vuln_range)  # < 3.0.0
        assert not is_vulnerable("5.0.0", sample_vuln_range)  # not < 5.0.0

    def test_unknown_version_is_vulnerable(self, sample_vuln):
        assert is_vulnerable("", sample_vuln)  # unknown → flag conservatively
        assert is_vulnerable(None, sample_vuln)

    def test_unfixed_vuln_all_versions(self):
        vuln = {"unfixed": "1", "max_version": "", "max_operator": ""}
        assert is_vulnerable("1.0.0", vuln)
        assert is_vulnerable("99.0.0", vuln)

    def test_unfixed_vuln_with_min_version(self):
        vuln = {"unfixed": "1", "min_version": "3.0.0", "min_operator": "gte"}
        assert is_vulnerable("3.0.0", vuln)
        assert is_vulnerable("5.0.0", vuln)
        assert not is_vulnerable("2.9.9", vuln)

    def test_invalid_version_not_vulnerable(self, sample_vuln):
        assert not is_vulnerable("not-a-version-!!!", sample_vuln)

    def test_extract_cve(self, sample_vuln):
        assert extract_primary_cve(sample_vuln) == "CVE-2020-35489"

    def test_extract_cve_none(self):
        vuln = {"sources": [{"id": "some-uuid", "name": "Test"}]}
        assert extract_primary_cve(vuln) == ""

    def test_map_severity_critical(self):
        assert map_severity({"cvss_severity": "c"}) == "critical"

    def test_map_severity_high(self):
        assert map_severity({"cvss_severity": "h"}) == "high"

    def test_map_severity_missing(self):
        assert map_severity({}) == "medium"

    def test_build_findings(self, sample_vuln):
        findings = build_findings("contact-form-7", "5.3.1", [sample_vuln])
        assert len(findings) == 1
        f = findings[0]
        assert f["severity"] == "critical"
        assert "CVE-2020-35489" in f["description"]
        assert f["provenance"] == "twin-derived"
        assert f["provenance_detail"]["twin_scan_tool"] == "wpvulnerability"
        assert f["provenance_detail"]["template_id"] == "CVE-2020-35489"

    def test_build_findings_safe_version(self, sample_vuln):
        findings = build_findings("contact-form-7", "5.3.2", [sample_vuln])
        assert len(findings) == 0  # version not affected

    def test_build_findings_no_provenance(self, sample_vuln):
        findings = build_findings("cf7", "5.3.1", [sample_vuln], provenance="")
        assert "provenance" not in findings[0]


# ---------------------------------------------------------------------------
# Lookup orchestrator tests
# ---------------------------------------------------------------------------


class TestLookup:
    @patch("src.vulndb.lookup.fetch_plugin_vulns")
    def test_cache_miss_fetches(self, mock_fetch, tmp_path, sample_vuln):
        from src.vulndb.lookup import lookup_wordpress_vulns

        mock_fetch.return_value = (200, [sample_vuln])
        db_path = str(tmp_path / "vulndb.sqlite3")

        findings = lookup_wordpress_vulns(
            plugin_slugs=["contact-form-7"],
            plugin_versions={"contact-form-7": "5.3.1"},
            db_path=db_path,
        )
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"
        mock_fetch.assert_called_once_with("contact-form-7")

    @patch("src.vulndb.lookup.fetch_plugin_vulns")
    def test_cache_hit_skips_fetch(self, mock_fetch, tmp_path, sample_vuln):
        from src.vulndb.lookup import lookup_wordpress_vulns

        db_path = str(tmp_path / "vulndb.sqlite3")
        # Pre-populate cache
        conn = init_db(db_path)
        store_plugin_vulns(conn, "contact-form-7", [sample_vuln])
        conn.close()

        findings = lookup_wordpress_vulns(
            plugin_slugs=["contact-form-7"],
            plugin_versions={"contact-form-7": "5.3.1"},
            db_path=db_path,
        )
        assert len(findings) == 1
        mock_fetch.assert_not_called()

    @patch("src.vulndb.lookup.fetch_plugin_vulns")
    def test_multiple_plugins(self, mock_fetch, tmp_path, sample_vuln):
        from src.vulndb.lookup import lookup_wordpress_vulns

        mock_fetch.return_value = (200, [sample_vuln])
        db_path = str(tmp_path / "vulndb.sqlite3")

        findings = lookup_wordpress_vulns(
            plugin_slugs=["plugin-a", "plugin-b"],
            plugin_versions={"plugin-a": "5.3.1", "plugin-b": "5.3.1"},
            db_path=db_path,
        )
        assert mock_fetch.call_count == 2

    @patch("src.vulndb.lookup.fetch_core_vulns")
    @patch("src.vulndb.lookup.fetch_plugin_vulns")
    def test_core_version_lookup(self, mock_plugin, mock_core, tmp_path, sample_vuln):
        from src.vulndb.lookup import lookup_wordpress_vulns

        mock_plugin.return_value = (200, [])
        mock_core.return_value = (200, [sample_vuln])
        db_path = str(tmp_path / "vulndb.sqlite3")

        findings = lookup_wordpress_vulns(
            plugin_slugs=["safe-plugin"],
            wp_version="5.3.1",
            db_path=db_path,
        )
        mock_core.assert_called_once_with("5.3.1")
        assert len(findings) >= 1

    @patch("src.vulndb.lookup.fetch_plugin_vulns")
    def test_api_failure_returns_empty(self, mock_fetch, tmp_path):
        from src.vulndb.lookup import lookup_wordpress_vulns

        mock_fetch.return_value = (0, [])
        db_path = str(tmp_path / "vulndb.sqlite3")

        findings = lookup_wordpress_vulns(
            plugin_slugs=["any-plugin"],
            plugin_versions={"any-plugin": "1.0"},
            db_path=db_path,
        )
        assert findings == []


class TestWPVersionCheck:
    """Tests for WordPress.org latest version lookups."""

    @patch("src.vulndb.wp_versions.requests.get")
    def test_fetches_latest_version(self, mock_get, tmp_path):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"version": "27.3", "name": "Yoast SEO"}

        from src.vulndb.wp_versions import get_latest_plugin_version
        ver = get_latest_plugin_version("wordpress-seo", db_path=str(tmp_path / "v.db"))
        assert ver == "27.3"

    @patch("src.vulndb.wp_versions.requests.get")
    def test_caches_result(self, mock_get, tmp_path):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"version": "5.0"}

        from src.vulndb.wp_versions import get_latest_plugin_version
        db = str(tmp_path / "v.db")
        get_latest_plugin_version("contact-form-7", db_path=db)
        get_latest_plugin_version("contact-form-7", db_path=db)
        # API called only once (second call hits cache)
        assert mock_get.call_count == 1

    @patch("src.vulndb.wp_versions.requests.get")
    def test_api_failure_returns_none(self, mock_get, tmp_path):
        import requests as req
        mock_get.side_effect = req.RequestException("timeout")

        from src.vulndb.wp_versions import get_latest_plugin_version
        ver = get_latest_plugin_version("bad-plugin", db_path=str(tmp_path / "v.db"))
        assert ver is None

    @patch("src.vulndb.wp_versions.requests.get")
    def test_404_returns_none(self, mock_get, tmp_path):
        mock_get.return_value.status_code = 404

        from src.vulndb.wp_versions import get_latest_plugin_version
        ver = get_latest_plugin_version("nonexistent", db_path=str(tmp_path / "v.db"))
        assert ver is None

    @patch("src.vulndb.wp_versions.get_latest_plugin_version")
    def test_outdated_detection(self, mock_latest):
        mock_latest.return_value = "27.3"

        from src.vulndb.wp_versions import check_outdated_plugins
        results = check_outdated_plugins({"wordpress-seo": "25.0"})
        assert len(results) == 1
        assert results[0]["outdated"] is True
        assert results[0]["installed"] == "25.0"
        assert results[0]["latest"] == "27.3"

    @patch("src.vulndb.wp_versions.get_latest_plugin_version")
    def test_current_version_not_outdated(self, mock_latest):
        mock_latest.return_value = "27.3"

        from src.vulndb.wp_versions import check_outdated_plugins
        results = check_outdated_plugins({"wordpress-seo": "27.3"})
        assert len(results) == 1
        assert results[0]["outdated"] is False

    @patch("src.vulndb.wp_versions.get_latest_plugin_version")
    def test_unknown_latest_skipped(self, mock_latest):
        mock_latest.return_value = None

        from src.vulndb.wp_versions import check_outdated_plugins
        results = check_outdated_plugins({"unknown-plugin": "1.0"})
        assert results == []
