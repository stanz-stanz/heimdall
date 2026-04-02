"""Tests for Level 1 scan functions and level-aware execution."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from src.prospecting.scanner import (
    _init_scan_type_map,
    _run_nuclei,
    _validate_approval_tokens,
    _LEVEL0_SCAN_FUNCTIONS,
    _LEVEL1_SCAN_FUNCTIONS,
    _SCAN_TYPE_FUNCTIONS,
)
from src.worker.cache import ScanCache
from src.worker.scan_job import execute_scan_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache(server: fakeredis.FakeServer | None = None) -> ScanCache:
    if server is None:
        server = fakeredis.FakeServer()
    cache = ScanCache.__new__(ScanCache)
    cache.hits = 0
    cache.misses = 0
    cache._available = True
    cache._redis = fakeredis.FakeRedis(server=server, decode_responses=True)
    return cache


_DOMAIN = "example.dk"

# Mock scan results (reused from test_worker.py pattern)
_SSL_RESULT = {"valid": True, "issuer": "LE", "expiry": "2026-09-01", "days_remaining": 158}
_HEADERS_RESULT = {"x_frame_options": True, "content_security_policy": False, "strict_transport_security": True, "x_content_type_options": True}
_META_RESULT = ("", "", [], {}, [])
_HTTPX_RESULT = {_DOMAIN: {"input": _DOMAIN, "webserver": "nginx", "tech": ["WordPress"]}}
_WEBANALYZE_RESULT = {}
_SUBFINDER_RESULT = {}
_DNSX_RESULT = {}
_CRTSH_RESULT = (_DOMAIN, [])
_GHW_RESULT: dict = {}

_NUCLEI_RESULT = {_DOMAIN: {
    "findings": [
        {"template_id": "cve-2024-1234", "severity": "high", "name": "Test CVE", "matched_at": f"https://{_DOMAIN}/", "type": "http"},
    ],
    "finding_count": 1,
}}


_CMSEEK_RESULT = {_DOMAIN: {
    "cms_id": "wp",
    "cms_name": "WordPress",
    "cms_version": "6.9.4",
    "detection_param": "header",
}}


def _patch_all_scans_with_nuclei():
    """Patches for all scan functions including Level 1 tools."""
    return [
        patch("src.worker.scan_job._check_robots_txt", return_value=True),
        patch("src.worker.scan_job._check_ssl", return_value=_SSL_RESULT),
        patch("src.worker.scan_job._get_response_headers", return_value=_HEADERS_RESULT),
        patch("src.worker.scan_job._extract_page_meta", return_value=_META_RESULT),
        patch("src.worker.scan_job._run_httpx", return_value=_HTTPX_RESULT),
        patch("src.worker.scan_job._run_webanalyze", return_value=_WEBANALYZE_RESULT),
        patch("src.worker.scan_job._run_subfinder", return_value=_SUBFINDER_RESULT),
        patch("src.worker.scan_job._run_dnsx", return_value=_DNSX_RESULT),
        patch("src.worker.scan_job._query_local_ct", return_value=_CRTSH_RESULT),
        patch("src.worker.scan_job._query_grayhatwarfare", return_value=_GHW_RESULT),
        patch("src.worker.scan_job._run_nuclei", return_value=_NUCLEI_RESULT),
        patch("src.worker.scan_job._run_cmseek", return_value=_CMSEEK_RESULT),
        patch("src.worker.twin_scan.run_twin_scan", return_value=None),
        patch("src.worker.scan_job._BUCKET_FILTER", None),
    ]


# ---------------------------------------------------------------------------
# _run_nuclei unit tests
# ---------------------------------------------------------------------------

class TestRunNuclei:
    """Unit tests for the _run_nuclei scan function."""

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/local/bin/nuclei")
    @patch("src.prospecting.scanner.subprocess.run")
    def test_parses_jsonl_output(self, mock_run, mock_which):
        """Multi-line JSONL output parsed correctly."""
        findings = [
            {
                "host": "https://example.dk/",
                "template-id": "cve-2024-1234",
                "info": {"severity": "high", "name": "SQL Injection"},
                "matched-at": "https://example.dk/login",
                "type": "http",
            },
            {
                "host": "https://example.dk/api",
                "template-id": "tech-detect-nginx",
                "info": {"severity": "info", "name": "Nginx Detected"},
                "matched-at": "https://example.dk/",
                "type": "http",
            },
        ]
        mock_run.return_value = MagicMock(
            stdout="\n".join(json.dumps(f) for f in findings),
            returncode=0,
        )

        result = _run_nuclei(["example.dk"])

        assert "example.dk" in result
        assert len(result["example.dk"]["findings"]) == 2
        assert result["example.dk"]["finding_count"] == 2
        assert result["example.dk"]["findings"][0]["severity"] == "high"
        assert result["example.dk"]["findings"][0]["template_id"] == "cve-2024-1234"

    @patch("src.prospecting.scanner.shutil.which", return_value=None)
    def test_tool_not_found(self, mock_which):
        """Returns empty dict when nuclei not in PATH."""
        result = _run_nuclei(["example.dk"])
        assert result == {}

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/local/bin/nuclei")
    @patch("src.prospecting.scanner.subprocess.run", side_effect=subprocess.TimeoutExpired("nuclei", 300))
    def test_timeout(self, mock_run, mock_which):
        """Returns empty dict on timeout."""
        result = _run_nuclei(["example.dk"])
        assert result == {}

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/local/bin/nuclei")
    @patch("src.prospecting.scanner.subprocess.run")
    def test_empty_results(self, mock_run, mock_which):
        """No findings returns empty findings list per domain."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)

        result = _run_nuclei(["example.dk"])
        # No output = no entries (domain not in results)
        assert result == {}

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/local/bin/nuclei")
    @patch("src.prospecting.scanner.subprocess.run")
    def test_host_normalization(self, mock_run, mock_which):
        """Host with protocol prefix, path, and port gets normalized."""
        finding = {
            "host": "https://example.dk:443/admin",
            "template-id": "test-template",
            "info": {"severity": "medium", "name": "Test"},
            "matched-at": "https://example.dk:443/admin",
            "type": "http",
        }
        mock_run.return_value = MagicMock(
            stdout=json.dumps(finding),
            returncode=0,
        )

        result = _run_nuclei(["example.dk"])
        assert "example.dk" in result

    @patch("src.prospecting.scanner.shutil.which", return_value="/usr/local/bin/nuclei")
    @patch("src.prospecting.scanner.subprocess.run")
    def test_multi_domain(self, mock_run, mock_which):
        """Findings routed to correct domain."""
        findings = [
            {"host": "https://a.dk/", "template-id": "t1", "info": {"severity": "low", "name": "A"}, "matched-at": "https://a.dk/", "type": "http"},
            {"host": "https://b.dk/", "template-id": "t2", "info": {"severity": "high", "name": "B"}, "matched-at": "https://b.dk/", "type": "http"},
        ]
        mock_run.return_value = MagicMock(
            stdout="\n".join(json.dumps(f) for f in findings),
            returncode=0,
        )

        result = _run_nuclei(["a.dk", "b.dk"])
        assert "a.dk" in result
        assert "b.dk" in result
        assert result["a.dk"]["findings"][0]["severity"] == "low"
        assert result["b.dk"]["findings"][0]["severity"] == "high"


# ---------------------------------------------------------------------------
# Registry split tests
# ---------------------------------------------------------------------------

class TestRegistrySplit:
    """Verify registry is correctly split by level."""

    def test_level0_functions_populated(self):
        _init_scan_type_map()
        assert len(_LEVEL0_SCAN_FUNCTIONS) == 9
        assert "ssl_certificate_check" in _LEVEL0_SCAN_FUNCTIONS
        assert "nuclei_vulnerability_scan" not in _LEVEL0_SCAN_FUNCTIONS

    def test_level1_functions_populated(self):
        _init_scan_type_map()
        assert "nuclei_vulnerability_scan" in _LEVEL1_SCAN_FUNCTIONS
        assert "cmseek_cms_deep_scan" in _LEVEL1_SCAN_FUNCTIONS
        assert "ssl_certificate_check" not in _LEVEL1_SCAN_FUNCTIONS

    def test_combined_map_has_all(self):
        _init_scan_type_map()
        assert len(_SCAN_TYPE_FUNCTIONS) == 11
        assert "ssl_certificate_check" in _SCAN_TYPE_FUNCTIONS
        assert "nuclei_vulnerability_scan" in _SCAN_TYPE_FUNCTIONS


# ---------------------------------------------------------------------------
# Level-gated validation tests
# ---------------------------------------------------------------------------

class TestLevelGatedValidation:
    """Verify _validate_approval_tokens respects max_level."""

    def test_level0_ignores_missing_level1_tokens(self):
        """A Level 0 worker should pass validation even without nuclei approval."""
        _init_scan_type_map()
        # This validates against the real approvals.json, which currently has
        # only Level 0 tokens. max_level=0 should pass.
        result = _validate_approval_tokens(max_level=0)
        assert result is not None

    def test_level1_requires_all_tokens(self):
        """Level 1 validation fails if nuclei approval token is missing."""
        _init_scan_type_map()
        # Before we add nuclei to approvals.json, Level 1 validation should fail
        # We test by patching the approvals file to exclude nuclei
        import io
        fake_approvals = json.dumps({"approvals": [
            {"scan_type_id": "ssl_certificate_check", "function_hash": "sha256:fake", "token": "t1"},
        ]})
        with patch("builtins.open", return_value=io.StringIO(fake_approvals)):
            result = _validate_approval_tokens(max_level=1)
        assert result is None  # Should fail — missing nuclei token


# ---------------------------------------------------------------------------
# Level-aware scan_job execution
# ---------------------------------------------------------------------------

class TestLevel1Execution:
    """Verify Level 1 jobs run nuclei, Level 0 jobs skip it."""

    def test_level1_job_runs_nuclei(self):
        """Level 1 job executes nuclei and includes level1_scan_result."""
        cache = _make_cache()
        job = {
            "job_id": "test-l1-001",
            "domain": _DOMAIN,
            "client_id": "client-001",
            "level": 1,
        }
        patches = _patch_all_scans_with_nuclei()
        for p in patches:
            p.start()
        try:
            result = execute_scan_job(job, cache)
            assert result["status"] == "completed"
            assert "level1_scan_result" in result
            assert "nuclei" in result["level1_scan_result"]
            nuclei = result["level1_scan_result"]["nuclei"]
            assert len(nuclei["findings"]) == 1
            assert nuclei["findings"][0]["severity"] == "high"
        finally:
            for p in patches:
                p.stop()

    def test_level0_job_skips_nuclei(self):
        """Level 0 job does NOT run nuclei or include level1_scan_result."""
        cache = _make_cache()
        job = {
            "job_id": "test-l0-001",
            "domain": _DOMAIN,
            "client_id": "prospect",
            "level": 0,
        }
        patches = _patch_all_scans_with_nuclei()
        mocks = []
        for p in patches:
            mocks.append(p.start())
        try:
            result = execute_scan_job(job, cache)
            assert result["status"] == "completed"
            assert "level1_scan_result" not in result
            # nuclei mock is second-to-last (last is run_twin_scan)
            nuclei_mock = mocks[-3]
            nuclei_mock.assert_not_called()
        finally:
            for p in patches:
                p.stop()

    def test_level1_result_structure(self):
        """Level 1 result has correct structure."""
        cache = _make_cache()
        job = {
            "job_id": "test-l1-002",
            "domain": _DOMAIN,
            "client_id": "client-001",
            "level": 1,
        }
        patches = _patch_all_scans_with_nuclei()
        for p in patches:
            p.start()
        try:
            result = execute_scan_job(job, cache)
            # Should have both scan_result (Level 0) and level1_scan_result
            assert "scan_result" in result
            assert "level1_scan_result" in result
            # Standard cache stats still present
            assert "cache_stats" in result
            # Level 1 has 10 misses (9 L0 + 1 nuclei)
            # Level 1 has 11 misses (9 L0 + nuclei + cmseek)
            assert result["cache_stats"]["misses"] == 11
        finally:
            for p in patches:
                p.stop()


# ---------------------------------------------------------------------------
# WPVulnerability lookup tests (replaced WPScan sidecar)
# ---------------------------------------------------------------------------

class TestVulnDBLookup:
    """Verify WPVulnerability lookup for WordPress domains."""

    def test_wordpress_domain_triggers_vulndb(self):
        """Level 1 WordPress job triggers WPVulnerability lookup."""
        cache = _make_cache()
        redis_conn = fakeredis.FakeRedis(decode_responses=True)

        mock_findings = [{"severity": "critical", "description": "Test Vuln (CVE-2024-1234)"}]

        job = {
            "job_id": "test-wp-001",
            "domain": _DOMAIN,
            "client_id": "client-001",
            "level": 1,
        }
        wp_httpx = {_DOMAIN: {"input": _DOMAIN, "webserver": "nginx", "tech": ["WordPress"]}}
        patches = [
            patch("src.worker.scan_job._check_robots_txt", return_value=True),
            patch("src.worker.scan_job._check_ssl", return_value=_SSL_RESULT),
            patch("src.worker.scan_job._get_response_headers", return_value=_HEADERS_RESULT),
            patch("src.worker.scan_job._extract_page_meta", return_value=_META_RESULT),
            patch("src.worker.scan_job._run_httpx", return_value=wp_httpx),
            patch("src.worker.scan_job._run_webanalyze", return_value={}),
            patch("src.worker.scan_job._run_subfinder", return_value=_SUBFINDER_RESULT),
            patch("src.worker.scan_job._run_dnsx", return_value=_DNSX_RESULT),
            patch("src.worker.scan_job._query_local_ct", return_value=_CRTSH_RESULT),
            patch("src.worker.scan_job._query_grayhatwarfare", return_value=_GHW_RESULT),
            patch("src.worker.scan_job._run_nuclei", return_value=_NUCLEI_RESULT),
            patch("src.worker.scan_job._run_cmseek", return_value=_CMSEEK_RESULT),
            patch("src.worker.twin_scan.run_twin_scan", return_value=None),
            patch("src.vulndb.lookup.lookup_wordpress_vulns", return_value=mock_findings),
        ]
        for p in patches:
            p.start()
        try:
            result = execute_scan_job(job, cache, redis_conn=redis_conn)
            assert "level1_scan_result" in result
            assert "wpvulnerability" in result["level1_scan_result"]
            assert result["level1_scan_result"]["wpvulnerability"]["finding_count"] == 1
        finally:
            for p in patches:
                p.stop()

    def test_non_wordpress_skips_vulndb(self):
        """Level 1 non-WordPress job does not trigger vulndb lookup."""
        cache = _make_cache()
        redis_conn = fakeredis.FakeRedis(decode_responses=True)

        job = {
            "job_id": "test-nowp-001",
            "domain": _DOMAIN,
            "client_id": "client-001",
            "level": 1,
        }
        no_wp_httpx = {_DOMAIN: {"input": _DOMAIN, "webserver": "nginx", "tech": ["Nginx", "HTML5"]}}
        patches = [
            patch("src.worker.scan_job._check_robots_txt", return_value=True),
            patch("src.worker.scan_job._check_ssl", return_value=_SSL_RESULT),
            patch("src.worker.scan_job._get_response_headers", return_value=_HEADERS_RESULT),
            patch("src.worker.scan_job._extract_page_meta", return_value=_META_RESULT),
            patch("src.worker.scan_job._run_httpx", return_value=no_wp_httpx),
            patch("src.worker.scan_job._run_webanalyze", return_value={}),
            patch("src.worker.scan_job._run_subfinder", return_value=_SUBFINDER_RESULT),
            patch("src.worker.scan_job._run_dnsx", return_value=_DNSX_RESULT),
            patch("src.worker.scan_job._query_local_ct", return_value=_CRTSH_RESULT),
            patch("src.worker.scan_job._query_grayhatwarfare", return_value=_GHW_RESULT),
            patch("src.worker.scan_job._run_nuclei", return_value=_NUCLEI_RESULT),
            patch("src.worker.scan_job._run_cmseek", return_value=_CMSEEK_RESULT),
            patch("src.worker.twin_scan.run_twin_scan", return_value=None),
            patch("src.worker.scan_job._BUCKET_FILTER", None),
        ]
        for p in patches:
            p.start()
        try:
            result = execute_scan_job(job, cache, redis_conn=redis_conn)
            assert "level1_scan_result" in result
            assert "wpvulnerability" not in result["level1_scan_result"]
        finally:
            for p in patches:
                p.stop()

    def test_level0_skips_vulndb(self):
        """Level 0 job never triggers vulndb regardless of CMS."""
        cache = _make_cache()
        redis_conn = fakeredis.FakeRedis(decode_responses=True)

        job = {
            "job_id": "test-l0-wp-001",
            "domain": _DOMAIN,
            "client_id": "prospect",
            "level": 0,
        }
        patches = _patch_all_scans_with_nuclei()
        for p in patches:
            p.start()
        try:
            result = execute_scan_job(job, cache, redis_conn=redis_conn)
            assert "level1_scan_result" not in result
        finally:
            for p in patches:
                p.stop()
