"""Regression tests for the digital twin pipeline.

These tests verify that:
1. The twin server correctly replicates a WordPress site from a brief
2. The twin scan module can start/stop the server and collect findings
3. Scanner regex patterns match against twin-generated HTML
4. Provenance markers are correctly set on twin-derived findings
"""

from __future__ import annotations

import json
import re
import threading
from http.server import HTTPServer
from pathlib import Path

import pytest

from tools.twin import templates
from tools.twin.twin_server import TwinHandler, _build_routes, _build_common_headers


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "briefs"


@pytest.fixture
def wordpress_brief():
    with open(FIXTURES_DIR / "wordpress-full.json") as f:
        return json.load(f)


@pytest.fixture
def slug_map():
    return templates.load_slug_map()


@pytest.fixture
def twin_server(wordpress_brief, slug_map):
    """Start a twin server and yield (port, brief). Shuts down after test."""
    routes = _build_routes(wordpress_brief, slug_map)
    common_headers = _build_common_headers(wordpress_brief)

    TwinHandler.routes = routes
    TwinHandler.domain = wordpress_brief["domain"]
    TwinHandler.common_headers = common_headers
    TwinHandler.login_cookie = f"domain={wordpress_brief['domain']}"
    TwinHandler.jitter = False

    server = HTTPServer(("127.0.0.1", 0), TwinHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield port, wordpress_brief

    server.shutdown()


# --- Golden snapshot: HTML structure ---


class TestTwinHTMLStructure:
    """Verify twin HTML matches patterns that scanners rely on."""

    def test_wordpress_meta_generator(self, wordpress_brief, slug_map):
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        assert '<meta name="generator" content="WordPress 6.9.4" />' in html

    def test_plugin_paths_match_scanner_regex(self, wordpress_brief, slug_map):
        """The regex from scanner.py must find plugins in twin HTML."""
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        found = set(re.findall(r'/wp-content/plugins/([\w-]+)/', html))
        assert "wordpress-seo" in found
        assert "gravityforms" in found

    def test_jquery_migrate_version_present(self, wordpress_brief, slug_map):
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        assert "jquery-migrate.min.js?ver=3.4.1" in html

    def test_html_exceeds_minimum_size(self, wordpress_brief, slug_map):
        """Twin must produce realistically sized HTML (>30KB)."""
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        assert len(html) > 30000

    def test_jsonld_structured_data(self, wordpress_brief, slug_map):
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        assert "application/ld+json" in html

    def test_wp_rocket_cache_path(self, wordpress_brief, slug_map):
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        assert "/wp-content/cache/wp-rocket/" in html


# --- Golden snapshot: Response headers ---


class TestTwinResponseHeaders:
    """Verify twin response headers match the brief's declared state."""

    def test_missing_headers_omitted(self, wordpress_brief):
        """Headers declared false in the brief must NOT appear in twin responses."""
        headers = _build_common_headers(wordpress_brief)
        assert "X-Frame-Options" not in headers
        assert "Content-Security-Policy" not in headers
        assert "Strict-Transport-Security" not in headers

    def test_server_header_matches_brief(self, wordpress_brief):
        headers = _build_common_headers(wordpress_brief)
        assert headers["Server"] == "cloudflare"

    def test_wp_api_link_header(self, wordpress_brief):
        headers = _build_common_headers(wordpress_brief)
        assert "api.w.org" in headers.get("Link", "")

    def test_x_powered_by_php(self, wordpress_brief):
        headers = _build_common_headers(wordpress_brief)
        assert headers.get("X-Powered-By", "").startswith("PHP/")


# --- Golden snapshot: Route table completeness ---


class TestTwinRouteTable:
    """Verify all expected routes exist for scanner tools to hit."""

    EXPECTED_ROUTES = [
        "/",
        "/wp-login.php",
        "/wp-json/",
        "/xmlrpc.php",
        "/robots.txt",
        "/readme.html",
        "/license.txt",
        "/healthz",
        "/favicon.ico",
        "/wp-cron.php",
    ]

    def test_all_core_routes_present(self, wordpress_brief, slug_map):
        routes = _build_routes(wordpress_brief, slug_map)
        for path in self.EXPECTED_ROUTES:
            assert path in routes, f"Missing route: {path}"

    def test_plugin_readme_routes(self, wordpress_brief, slug_map):
        routes = _build_routes(wordpress_brief, slug_map)
        assert "/wp-content/plugins/wordpress-seo/readme.txt" in routes


# --- Integration: live HTTP ---


@pytest.mark.integration
class TestTwinLiveHTTP:
    """Start the twin and make real HTTP requests."""

    def test_homepage_returns_wordpress(self, twin_server):
        import urllib.request
        port, brief = twin_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        html = resp.read().decode()
        assert resp.status == 200
        assert "WordPress 6.9.4" in html

    def test_healthz_returns_200(self, twin_server):
        import urllib.request
        port, _ = twin_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz")
        assert resp.status == 200

    def test_unknown_path_returns_404(self, twin_server):
        import urllib.request
        import urllib.error
        port, _ = twin_server
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nonexistent-path")
        assert exc_info.value.code == 404

    def test_wp_json_has_namespaces(self, twin_server):
        import urllib.request
        port, _ = twin_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/wp-json/")
        data = json.loads(resp.read())
        assert "namespaces" in data
        assert "wp/v2" in data["namespaces"]


# --- WPScan detection signals ---


class TestWPScanDetectionSignals:
    """Verify the twin serves all signals WPScan uses for WordPress detection.

    WPScan checks the homepage for these patterns (any one is sufficient):
    1. <link>/<script> URIs matching /wp-content/(themes|plugins|uploads)/ or /wp-includes/
    2. <link> URIs matching /wp-json/oembed/
    3. <meta name="generator"> with "wordpress" (case-insensitive)
    4. HTML comments containing "wordpress"
    5. Inline scripts referencing /wp-admin/admin-ajax.php
    """

    def test_wp_content_in_link_tags(self, wordpress_brief, slug_map):
        """WPScan Check 1: <link> tags with wp-content paths."""
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        wp_pattern = re.compile(r'/(?:wp-content/(?:themes|plugins|uploads)|wp-includes)/')
        links = re.findall(r'<link[^>]+href="([^"]*)"', html)
        matching = [u for u in links if wp_pattern.search(u)]
        assert len(matching) >= 2, f"Expected >=2 wp-content/wp-includes links, got: {matching}"

    def test_wp_includes_in_script_tags(self, wordpress_brief, slug_map):
        """WPScan Check 1: <script> tags with wp-includes paths."""
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        scripts = re.findall(r'<script[^>]+src="([^"]*)"', html)
        wp_includes = [s for s in scripts if "/wp-includes/" in s]
        assert len(wp_includes) >= 1, f"Expected wp-includes scripts, got: {scripts}"

    def test_oembed_link_tag(self, wordpress_brief, slug_map):
        """WPScan Check 2: oEmbed discovery link."""
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        assert "/wp-json/oembed/" in html

    def test_meta_generator_wordpress(self, wordpress_brief, slug_map):
        """WPScan Check 3: meta generator tag."""
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        gen = re.search(r'<meta[^>]+name="generator"[^>]+content="([^"]*)"', html)
        assert gen is not None
        assert "wordpress" in gen.group(1).lower()

    def test_html_comment_wordpress(self, wordpress_brief, slug_map):
        """WPScan Check 4: HTML comments containing 'wordpress'."""
        plugins = templates.parse_tech_stack(wordpress_brief, slug_map)
        html = templates.build_index_html(wordpress_brief, plugins)
        comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
        wp_comments = [c for c in comments if "wordpress" in c.lower()]
        assert len(wp_comments) >= 1, "Expected at least one HTML comment with 'wordpress'"

    def test_rss_feed_has_generator(self, wordpress_brief):
        """WPScan version detection: RSS feed generator tag."""
        wp_version = templates._extract_wp_version(wordpress_brief)
        feed = templates.build_rss_feed(wordpress_brief["domain"], wp_version)
        assert f"?v={wp_version}" in feed
        assert "wordpress.org" in feed


@pytest.mark.integration
class TestWPScanDetectionLiveHTTP:
    """Live HTTP tests for WPScan detection — verify slash-agnostic routing."""

    def test_wp_json_without_trailing_slash(self, twin_server):
        """WPScan may request /wp-json without trailing slash."""
        import urllib.request
        port, _ = twin_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/wp-json")
        data = json.loads(resp.read())
        assert "namespaces" in data

    def test_feed_returns_rss(self, twin_server):
        """WPScan checks /feed/ for version detection."""
        import urllib.request
        port, _ = twin_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/feed/")
        body = resp.read().decode()
        assert "wordpress.org" in body
        assert "<generator>" in body

    def test_homepage_no_duplicate_server_header(self, twin_server):
        """Server header should appear exactly once."""
        import urllib.request
        port, _ = twin_server
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        server_headers = resp.headers.get_all("Server")
        assert len(server_headers) == 1, f"Expected 1 Server header, got {len(server_headers)}: {server_headers}"

    def test_homepage_is_http11(self, twin_server):
        """Twin should respond with HTTP/1.1."""
        import http.client
        port, _ = twin_server
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request("GET", "/")
        resp = conn.getresponse()
        assert resp.version == 11, f"Expected HTTP/1.1 (11), got {resp.version}"
        conn.close()


# --- Twin scan module ---


class TestTwinScanModule:
    """Test the twin_scan orchestration module."""

    def test_run_twin_scan_returns_result(self, wordpress_brief):
        """Twin scan should return a dict even when tools aren't installed."""
        from src.worker.twin_scan import run_twin_scan
        result = run_twin_scan(wordpress_brief)
        assert result is not None
        assert "findings" in result
        assert "scan_tools" in result
        assert "duration_ms" in result
        assert "twin_scan_date" in result
        assert isinstance(result["findings"], list)

    def test_wpscan_response_parsing(self):
        """Verify _request_twin_wpscan parses the sidecar's restructured format."""
        from src.worker.twin_scan import _request_twin_wpscan, _wpscan_severity
        from unittest.mock import MagicMock

        # Simulate sidecar response in its actual format
        sidecar_response = json.dumps({
            "job_id": "twin-wpscan-test123",
            "domain": "http://container:9080",
            "status": "completed",
            "wpscan": {
                "vulnerabilities": [
                    {"title": "WordPress < 6.9.5 - XSS", "type": "wordpress_core", "fixed_in": "6.9.5"},
                    {"title": "CF7 < 5.8 - RCE", "type": "plugin", "plugin": "contact-form-7", "fixed_in": "5.8"},
                ],
                "wordpress": {"version": "6.9.4", "status": "insecure"},
                "plugins": [
                    {"name": "contact-form-7", "version": "5.7", "outdated": True, "vuln_count": 1},
                    {"name": "elementor", "version": "3.18", "outdated": False, "vuln_count": 0},
                ],
            },
            "exit_code": 5,
            "duration_ms": 6000,
        })

        mock_redis = MagicMock()
        mock_redis.rpush.return_value = 1
        mock_redis.brpop.return_value = ("wpscan:result:twin-wpscan-test123", sidecar_response)

        findings = _request_twin_wpscan(mock_redis, "container", 9080)

        # Should find 2 vulns + 1 outdated plugin = 3 findings
        assert len(findings) == 3
        assert any("XSS" in f["description"] for f in findings)
        assert any("RCE" in f["description"] for f in findings)
        assert any("Outdated" in f["description"] for f in findings)
        assert all(f["provenance"] == "twin-derived" for f in findings)

    def test_wpscan_not_wordpress_response(self):
        """Exit code 4 (not WordPress) should produce 0 findings."""
        from src.worker.twin_scan import _request_twin_wpscan
        from unittest.mock import MagicMock

        sidecar_response = json.dumps({
            "job_id": "twin-wpscan-test456",
            "domain": "http://container:9080",
            "status": "not_wordpress",
            "wpscan": {},
            "exit_code": 4,
        })

        mock_redis = MagicMock()
        mock_redis.rpush.return_value = 1
        mock_redis.brpop.return_value = ("key", sidecar_response)

        findings = _request_twin_wpscan(mock_redis, "container", 9080)
        assert findings == []

    def test_twin_scan_findings_have_provenance(self, wordpress_brief):
        """Any findings from twin scan must have provenance markers."""
        from src.worker.twin_scan import run_twin_scan
        result = run_twin_scan(wordpress_brief)
        for finding in result.get("findings", []):
            assert finding.get("provenance") == "twin-derived"
            assert "provenance_detail" in finding
