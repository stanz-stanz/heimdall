"""Tests for the WPScan sidecar queue consumer."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

from src.wpscan_sidecar.main import _run_wpscan, _process_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis():
    return fakeredis.FakeRedis(decode_responses=True)


_WPSCAN_JSON = json.dumps({
    "version": {
        "number": "6.9.4",
        "status": "outdated",
        "vulnerabilities": [
            {"title": "WP < 6.9.5 - XSS", "fixed_in": "6.9.5", "references": {}},
        ],
    },
    "plugins": {
        "gravityforms": {
            "version": {"number": "2.8.1"},
            "outdated": True,
            "vulnerabilities": [
                {"title": "GF Auth Bypass", "fixed_in": "2.8.2"},
            ],
        },
    },
    "main_theme": {
        "vulnerabilities": [],
    },
    "themes": {},
})


# ---------------------------------------------------------------------------
# _run_wpscan unit tests
# ---------------------------------------------------------------------------

class TestRunWPScan:

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_command_includes_force_flag(self, mock_run):
        mock_run.return_value = MagicMock(stdout=_WPSCAN_JSON, returncode=0)
        _run_wpscan("example.dk")
        cmd = mock_run.call_args[0][0]
        assert "--force" in cmd, "WPScan command must include --force for twin compatibility"

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_command_includes_disable_tls_checks(self, mock_run):
        mock_run.return_value = MagicMock(stdout=_WPSCAN_JSON, returncode=0)
        _run_wpscan("example.dk")
        cmd = mock_run.call_args[0][0]
        assert "--disable-tls-checks" in cmd, "WPScan command must include --disable-tls-checks"

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_http_url_preserved(self, mock_run):
        """When domain starts with http://, sidecar must NOT prepend https://."""
        mock_run.return_value = MagicMock(stdout=_WPSCAN_JSON, returncode=0)
        _run_wpscan("http://worker-abc:45000")
        cmd = mock_run.call_args[0][0]
        url_arg = cmd[cmd.index("--url") + 1]
        assert url_arg.startswith("http://"), f"Expected http:// URL, got: {url_arg}"

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_api_token_passed_when_set(self, mock_run):
        mock_run.return_value = MagicMock(stdout=_WPSCAN_JSON, returncode=0)
        with patch.dict("os.environ", {"WPSCAN_API_TOKEN": "test-token-123"}):
            _run_wpscan("example.dk")
        cmd = mock_run.call_args[0][0]
        assert "--api-token" in cmd
        assert "test-token-123" in cmd

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_parses_valid_json(self, mock_run):
        mock_run.return_value = MagicMock(stdout=_WPSCAN_JSON, returncode=0)
        result = _run_wpscan("example.dk")

        assert result["status"] == "completed"
        assert result["domain"] == "example.dk"
        assert result["wpscan"]["wordpress"]["version"] == "6.9.4"
        assert len(result["wpscan"]["vulnerabilities"]) == 2
        assert len(result["wpscan"]["plugins"]) == 1

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_exit_code_4_not_wordpress(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=4, stderr="not WP")
        result = _run_wpscan("example.dk")

        assert result["status"] == "not_wordpress"
        assert result["exit_code"] == 4

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_exit_code_5_vulns_found(self, mock_run):
        mock_run.return_value = MagicMock(stdout=_WPSCAN_JSON, returncode=5)
        result = _run_wpscan("example.dk")

        assert result["status"] == "completed"
        assert len(result["wpscan"]["vulnerabilities"]) == 2

    @patch("src.wpscan_sidecar.main.subprocess.run", side_effect=subprocess.TimeoutExpired("wpscan", 120))
    def test_timeout(self, mock_run):
        result = _run_wpscan("example.dk")
        assert result["status"] == "timeout"

    @patch("src.wpscan_sidecar.main.subprocess.run", side_effect=FileNotFoundError)
    def test_binary_not_found(self, mock_run):
        result = _run_wpscan("example.dk")
        assert result["status"] == "error"

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_malformed_json_output(self, mock_run):
        mock_run.return_value = MagicMock(stdout="{truncated", returncode=0)
        result = _run_wpscan("example.dk")
        assert result["status"] == "error"
        assert "invalid JSON" in result.get("error", "")

    @patch("src.wpscan_sidecar.main.subprocess.run")
    def test_error_exit_code(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=1, stderr="fatal error")
        result = _run_wpscan("example.dk")
        assert result["status"] == "error"
        assert result["exit_code"] == 1


# ---------------------------------------------------------------------------
# _process_job tests
# ---------------------------------------------------------------------------

class TestProcessJob:

    @patch("src.wpscan_sidecar.main._run_wpscan")
    def test_result_written_to_response_key(self, mock_scan):
        mock_scan.return_value = {
            "status": "completed",
            "domain": "example.dk",
            "wpscan": {"vulnerabilities": [], "wordpress": {}, "plugins": []},
            "exit_code": 0,
            "duration_ms": 1000,
        }
        conn = _make_redis()
        job = {"job_id": "wpscan-test-001", "domain": "example.dk"}

        _process_job(job, conn)

        raw = conn.rpop("wpscan:result:wpscan-test-001")
        assert raw is not None
        result = json.loads(raw)
        assert result["domain"] == "example.dk"
        assert result["status"] == "completed"

    @patch("src.wpscan_sidecar.main._run_wpscan")
    def test_result_cached(self, mock_scan):
        mock_scan.return_value = {
            "status": "completed",
            "domain": "example.dk",
            "wpscan": {"vulnerabilities": []},
            "exit_code": 0,
            "duration_ms": 500,
        }
        conn = _make_redis()
        job = {"job_id": "wpscan-test-002", "domain": "example.dk"}

        _process_job(job, conn)

        cached = conn.get("cache:wpscan:example.dk")
        assert cached is not None
        data = json.loads(cached)
        assert data["status"] == "completed"

    @patch("src.wpscan_sidecar.main._run_wpscan")
    def test_cache_hit_skips_scan(self, mock_scan):
        conn = _make_redis()
        # Pre-populate cache
        conn.setex("cache:wpscan:example.dk", 86400, json.dumps({
            "status": "completed",
            "wpscan": {"vulnerabilities": [], "wordpress": {}, "plugins": []},
        }))

        job = {"job_id": "wpscan-test-003", "domain": "example.dk"}
        _process_job(job, conn)

        # Scan should NOT have been called
        mock_scan.assert_not_called()

        # But response key should still be populated
        raw = conn.rpop("wpscan:result:wpscan-test-003")
        assert raw is not None
        result = json.loads(raw)
        assert result["cached"] is True

    def test_missing_domain_skipped(self):
        conn = _make_redis()
        job = {"job_id": "wpscan-test-004"}
        # Should not raise
        _process_job(job, conn)
