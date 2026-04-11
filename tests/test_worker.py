"""Tests for src.worker.scan_job — single-domain scan job execution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fakeredis

from src.worker.cache import ScanCache
from src.worker.scan_job import execute_scan_job

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache(server: fakeredis.FakeServer | None = None) -> ScanCache:
    """Create a ScanCache backed by fakeredis."""
    if server is None:
        server = fakeredis.FakeServer()
    cache = ScanCache.__new__(ScanCache)
    cache.hits = 0
    cache.misses = 0
    cache._available = True
    cache._redis = fakeredis.FakeRedis(server=server, decode_responses=True)
    return cache


_DOMAIN = "example.dk"

_BASE_JOB = {
    "job_id": "test-001",
    "domain": _DOMAIN,
    "client_id": "prospect",
    "tier": "watchman",
    "layer": 1,
    "level": 0,
}

# Realistic return values for each scan function
_SSL_RESULT = {"valid": True, "issuer": "Let's Encrypt", "expiry": "2026-09-01", "days_remaining": 158}
_HEADERS_RESULT = {
    "x_frame_options": True,
    "content_security_policy": False,
    "strict_transport_security": True,
    "x_content_type_options": True,
}
_META_RESULT = ("Agency X", "Designed by Agency X", ["contact-form-7", "woocommerce"])
_HTTPX_RESULT = {_DOMAIN: {"input": _DOMAIN, "webserver": "nginx", "tech": ["WordPress", "PHP"]}}
_WEBANALYZE_RESULT = {_DOMAIN: ["WordPress", "jQuery"]}
_SUBFINDER_RESULT = {_DOMAIN: ["mail.example.dk", "www.example.dk"]}
_DNSX_RESULT = {_DOMAIN: {"a": ["1.2.3.4"], "aaaa": [], "cname": [], "mx": ["mx.example.dk"], "ns": [], "txt": []}}
_CRTSH_RESULT = (_DOMAIN, [{"common_name": "*.example.dk", "issuer_name": "LE", "not_before": "2026-01-01", "not_after": "2026-04-01"}])
_GHW_RESULT: dict = {}


def _patch_all_scans():
    """Return a stack of patches for every scan function used by scan_job."""
    return [
        patch("src.worker.scan_job.check_robots_txt", return_value=True),
        patch("src.worker.scan_job.check_ssl", return_value=_SSL_RESULT),
        patch("src.worker.scan_job.get_response_headers", return_value=_HEADERS_RESULT),
        patch("src.worker.scan_job.extract_page_meta", return_value=_META_RESULT),
        patch("src.worker.scan_job.run_httpx", return_value=_HTTPX_RESULT),
        patch("src.worker.scan_job.run_webanalyze", return_value=_WEBANALYZE_RESULT),
        patch("src.worker.scan_job.run_subfinder", return_value=_SUBFINDER_RESULT),
        patch("src.worker.scan_job.run_dnsx", return_value=_DNSX_RESULT),
        patch("src.worker.scan_job._query_local_ct", return_value=_CRTSH_RESULT),
        patch("src.worker.scan_job.query_grayhatwarfare", return_value=_GHW_RESULT),
        patch("src.worker.scan_job._BUCKET_FILTER", None),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestColdCache:
    """All cache misses — every scan function should be called."""

    def test_execute_scan_job_cold_cache(self) -> None:
        cache = _make_cache()
        patches = _patch_all_scans()
        mocks: list[MagicMock] = []
        for p in patches:
            m = p.start()
            mocks.append(m)

        try:
            result = execute_scan_job(_BASE_JOB, cache)

            assert result["status"] == "completed"
            assert result["domain"] == _DOMAIN
            # All scan functions must have been called (robots + 9 scan types)
            for m in mocks:
                if m is not None:  # attribute patches (e.g. _BUCKET_FILTER) return None
                    m.assert_called()
            # All misses, no hits (robots is not cached)
            assert result["cache_stats"]["misses"] == 9
            assert result["cache_stats"]["hits"] == 0
        finally:
            for p in patches:
                p.stop()


class TestWarmCache:
    """All cache hits — no scan functions called (except robots.txt)."""

    def test_execute_scan_job_warm_cache(self) -> None:
        cache = _make_cache()

        # Pre-populate cache for all scan types
        cache.set("ssl", _DOMAIN, _SSL_RESULT)
        cache.set("headers", _DOMAIN, _HEADERS_RESULT)
        cache.set("meta", _DOMAIN, list(_META_RESULT))
        cache.set("httpx", _DOMAIN, _HTTPX_RESULT)
        cache.set("webanalyze", _DOMAIN, _WEBANALYZE_RESULT)
        cache.set("subfinder", _DOMAIN, _SUBFINDER_RESULT)
        cache.set("dnsx", _DOMAIN, _DNSX_RESULT)
        cache.set("crtsh", _DOMAIN, list(_CRTSH_RESULT))
        cache.set("ghw", _DOMAIN, _GHW_RESULT)

        # Reset hit/miss counters after seeding
        cache.hits = 0
        cache.misses = 0

        with patch("src.worker.scan_job.check_robots_txt", return_value=True) as mock_robots, \
             patch("src.worker.scan_job.check_ssl") as mock_ssl, \
             patch("src.worker.scan_job.get_response_headers") as mock_headers, \
             patch("src.worker.scan_job.extract_page_meta") as mock_meta, \
             patch("src.worker.scan_job.run_httpx") as mock_httpx, \
             patch("src.worker.scan_job.run_webanalyze") as mock_wa, \
             patch("src.worker.scan_job.run_subfinder") as mock_sf, \
             patch("src.worker.scan_job.run_dnsx") as mock_dnsx, \
             patch("src.worker.scan_job._query_local_ct") as mock_crtsh, \
             patch("src.worker.scan_job.query_grayhatwarfare") as mock_ghw:

            result = execute_scan_job(_BASE_JOB, cache)

            assert result["status"] == "completed"
            # robots.txt is always called fresh
            mock_robots.assert_called_once()
            # Scan functions must NOT have been called — all cached
            mock_ssl.assert_not_called()
            mock_headers.assert_not_called()
            mock_meta.assert_not_called()
            mock_httpx.assert_not_called()
            mock_wa.assert_not_called()
            mock_sf.assert_not_called()
            mock_dnsx.assert_not_called()
            mock_crtsh.assert_not_called()
            mock_ghw.assert_not_called()
            # All hits
            assert result["cache_stats"]["hits"] == 9
            assert result["cache_stats"]["misses"] == 0


class TestMixedCache:
    """Some cache hits, some misses."""

    def test_execute_scan_job_mixed_cache(self) -> None:
        cache = _make_cache()

        # Only populate ssl and headers in cache
        cache.set("ssl", _DOMAIN, _SSL_RESULT)
        cache.set("headers", _DOMAIN, _HEADERS_RESULT)
        cache.hits = 0
        cache.misses = 0

        with patch("src.worker.scan_job.check_robots_txt", return_value=True), \
             patch("src.worker.scan_job.check_ssl") as mock_ssl, \
             patch("src.worker.scan_job.get_response_headers") as mock_headers, \
             patch("src.worker.scan_job.extract_page_meta", return_value=_META_RESULT), \
             patch("src.worker.scan_job.run_httpx", return_value=_HTTPX_RESULT), \
             patch("src.worker.scan_job.run_webanalyze", return_value=_WEBANALYZE_RESULT), \
             patch("src.worker.scan_job.run_subfinder", return_value=_SUBFINDER_RESULT), \
             patch("src.worker.scan_job.run_dnsx", return_value=_DNSX_RESULT), \
             patch("src.worker.scan_job._query_local_ct", return_value=_CRTSH_RESULT), \
             patch("src.worker.scan_job.query_grayhatwarfare", return_value=_GHW_RESULT):

            result = execute_scan_job(_BASE_JOB, cache)

            assert result["status"] == "completed"
            # ssl and headers should NOT be called (cached)
            mock_ssl.assert_not_called()
            mock_headers.assert_not_called()
            # 2 hits (ssl, headers), 7 misses
            assert result["cache_stats"]["hits"] == 2
            assert result["cache_stats"]["misses"] == 7


class TestRobotsTxtDenied:
    """Domain denied by robots.txt — no scans executed."""

    def test_robots_txt_denied(self) -> None:
        cache = _make_cache()

        with patch("src.worker.scan_job.check_robots_txt", return_value=False), \
             patch("src.worker.scan_job.check_ssl") as mock_ssl, \
             patch("src.worker.scan_job.get_response_headers") as mock_headers:

            result = execute_scan_job(_BASE_JOB, cache)

            assert result["status"] == "skipped"
            assert result["skip_reason"] == "robots.txt denied"
            assert result["scan_result"] is None
            # No scan functions called
            mock_ssl.assert_not_called()
            mock_headers.assert_not_called()
            assert result["cache_stats"]["hits"] == 0
            assert result["cache_stats"]["misses"] == 0


class TestResultStructure:
    """Verify returned dict has expected keys."""

    def test_result_structure(self) -> None:
        cache = _make_cache()
        patches = _patch_all_scans()
        for p in patches:
            p.start()

        try:
            result = execute_scan_job(_BASE_JOB, cache)

            # Top-level keys
            assert "domain" in result
            assert "job_id" in result
            assert "status" in result
            assert "scan_result" in result
            assert "timing" in result
            assert "cache_stats" in result

            assert result["domain"] == _DOMAIN
            assert result["job_id"] == "test-001"

            # Timing has a total
            assert "total_ms" in result["timing"]
            assert isinstance(result["timing"]["total_ms"], int)

            # Cache stats
            assert "hits" in result["cache_stats"]
            assert "misses" in result["cache_stats"]

            # scan_result is a dict (from dataclass)
            sr = result["scan_result"]
            assert isinstance(sr, dict)
            assert sr["domain"] == _DOMAIN
            assert "ssl_valid" in sr
            assert "headers" in sr
            assert "tech_stack" in sr
        finally:
            for p in patches:
                p.stop()


class TestCMSDerivation:
    """Verify WordPress detected from httpx tech stack."""

    def test_cms_derivation_wordpress(self) -> None:
        cache = _make_cache()

        httpx_with_wp = {_DOMAIN: {"input": _DOMAIN, "webserver": "nginx", "tech": ["WordPress", "PHP", "MySQL"]}}

        with patch("src.worker.scan_job.check_robots_txt", return_value=True), \
             patch("src.worker.scan_job.check_ssl", return_value=_SSL_RESULT), \
             patch("src.worker.scan_job.get_response_headers", return_value=_HEADERS_RESULT), \
             patch("src.worker.scan_job.extract_page_meta", return_value=("", "", [])), \
             patch("src.worker.scan_job.run_httpx", return_value=httpx_with_wp), \
             patch("src.worker.scan_job.run_webanalyze", return_value={}), \
             patch("src.worker.scan_job.run_subfinder", return_value={}), \
             patch("src.worker.scan_job.run_dnsx", return_value={}), \
             patch("src.worker.scan_job._query_local_ct", return_value=(_DOMAIN, [])), \
             patch("src.worker.scan_job.query_grayhatwarfare", return_value={}):

            result = execute_scan_job(_BASE_JOB, cache)

            sr = result["scan_result"]
            assert sr["cms"] == "WordPress"
            assert "WordPress" in sr["tech_stack"]

    def test_cms_derivation_no_cms(self) -> None:
        cache = _make_cache()

        httpx_no_cms = {_DOMAIN: {"input": _DOMAIN, "webserver": "nginx", "tech": ["nginx", "HTML5"]}}

        with patch("src.worker.scan_job.check_robots_txt", return_value=True), \
             patch("src.worker.scan_job.check_ssl", return_value=_SSL_RESULT), \
             patch("src.worker.scan_job.get_response_headers", return_value=_HEADERS_RESULT), \
             patch("src.worker.scan_job.extract_page_meta", return_value=("", "", [])), \
             patch("src.worker.scan_job.run_httpx", return_value=httpx_no_cms), \
             patch("src.worker.scan_job.run_webanalyze", return_value={}), \
             patch("src.worker.scan_job.run_subfinder", return_value={}), \
             patch("src.worker.scan_job.run_dnsx", return_value={}), \
             patch("src.worker.scan_job._query_local_ct", return_value=(_DOMAIN, [])), \
             patch("src.worker.scan_job.query_grayhatwarfare", return_value={}):

            result = execute_scan_job(_BASE_JOB, cache)

            sr = result["scan_result"]
            assert sr["cms"] == ""


class TestBucketFilterEarlyReturn:
    """Verify bucket filter skips expensive scans for excluded buckets."""

    def test_bucket_filter_skips_subfinder(self) -> None:
        """When _BUCKET_FILTER excludes the domain's bucket, subfinder is NOT called."""
        cache = _make_cache()

        # Nginx + HTML5 only → no CMS → bucket E
        httpx_no_cms = {_DOMAIN: {"input": _DOMAIN, "webserver": "nginx", "tech": ["nginx", "HTML5"]}}

        with patch("src.worker.scan_job.check_robots_txt", return_value=True), \
             patch("src.worker.scan_job.check_ssl", return_value=_SSL_RESULT), \
             patch("src.worker.scan_job.get_response_headers", return_value=_HEADERS_RESULT), \
             patch("src.worker.scan_job.extract_page_meta", return_value=("", "", [])), \
             patch("src.worker.scan_job.run_httpx", return_value=httpx_no_cms), \
             patch("src.worker.scan_job.run_webanalyze", return_value={}), \
             patch("src.worker.scan_job.run_subfinder") as mock_subfinder, \
             patch("src.worker.scan_job.run_dnsx", return_value={}), \
             patch("src.worker.scan_job._query_local_ct", return_value=(_DOMAIN, [])), \
             patch("src.worker.scan_job.query_grayhatwarfare", return_value={}), \
             patch("src.worker.scan_job._BUCKET_FILTER", {"A"}):

            result = execute_scan_job(_BASE_JOB, cache)

            assert result["status"] == "completed"
            assert result["filtered"] == "bucket:E"
            assert "brief" in result
            assert "timing" in result
            assert "total_ms" in result["timing"]
            mock_subfinder.assert_not_called()
