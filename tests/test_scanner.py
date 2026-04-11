"""Tests for scanner.py — all Layer 1 scan functions."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, mock_open, patch

from src.prospecting.scanners.registry import (
    _SCAN_TYPE_FUNCTIONS,
    _init_scan_type_map,
    _validate_approval_tokens,
)
from src.prospecting.scanners.tls import check_ssl
from src.prospecting.scanners.headers import get_response_headers
from src.prospecting.scanners.robots import check_robots_txt
from src.prospecting.scanners.httpx_scan import run_httpx
from src.prospecting.scanners.webanalyze import run_webanalyze
from src.prospecting.scanners.subfinder import run_subfinder
from src.prospecting.scanners.dnsx import run_dnsx
from src.prospecting.scanners.ct import query_crt_sh_single
from src.prospecting.scanners.grayhat import query_grayhatwarfare
from src.prospecting.scanners.wordpress import extract_page_meta


class TestCheckSSL:
    @patch("src.prospecting.scanners.tls.socket.socket")
    @patch("src.prospecting.scanners.tls.ssl.create_default_context")
    def test_valid_cert(self, mock_ctx, mock_sock_cls):
        future = datetime.now(UTC) + timedelta(days=60)
        cert = {
            "notAfter": future.strftime("%b %d %H:%M:%S %Y GMT"),
            "issuer": ((("organizationName", "Let's Encrypt"),),),
        }
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = cert
        mock_ctx.return_value.wrap_socket.return_value.__enter__ = lambda s: mock_ssock
        mock_ctx.return_value.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)

        result = check_ssl("test.dk")
        assert result["valid"] is True
        assert result["issuer"] == "Let's Encrypt"
        assert result["days_remaining"] > 50

    @patch("src.prospecting.scanners.tls.socket.socket")
    @patch("src.prospecting.scanners.tls.ssl.create_default_context")
    def test_expired_cert(self, mock_ctx, mock_sock_cls):
        past = datetime.now(UTC) - timedelta(days=10)
        cert = {
            "notAfter": past.strftime("%b %d %H:%M:%S %Y GMT"),
            "issuer": ((("organizationName", "Let's Encrypt"),),),
        }
        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = cert
        mock_ctx.return_value.wrap_socket.return_value.__enter__ = lambda s: mock_ssock
        mock_ctx.return_value.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)

        result = check_ssl("test.dk")
        assert result["valid"] is False
        assert result["days_remaining"] < 0

    @patch("src.prospecting.scanners.tls.socket.socket")
    @patch("src.prospecting.scanners.tls.ssl.create_default_context")
    def test_connection_refused(self, mock_ctx, mock_sock_cls):
        mock_ctx.return_value.wrap_socket.return_value.__enter__ = MagicMock(
            side_effect=ConnectionRefusedError
        )
        mock_ctx.return_value.wrap_socket.return_value.__exit__ = MagicMock(return_value=False)

        result = check_ssl("test.dk")
        assert result["valid"] is False
        assert result["days_remaining"] == -1


class TestGetResponseHeaders:
    @patch("src.prospecting.scanners.headers.requests.head")
    def test_all_headers_present(self, mock_head):
        mock_head.return_value.headers = {
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'",
            "Strict-Transport-Security": "max-age=31536000",
            "X-Content-Type-Options": "nosniff",
        }
        result = get_response_headers("test.dk")
        assert result["x_frame_options"] is True
        assert result["content_security_policy"] is True
        assert result["strict_transport_security"] is True
        assert result["x_content_type_options"] is True

    @patch("src.prospecting.scanners.headers.requests.head")
    def test_all_headers_missing(self, mock_head):
        mock_head.return_value.headers = {}
        result = get_response_headers("test.dk")
        assert result["x_frame_options"] is False
        assert result["content_security_policy"] is False
        assert result["strict_transport_security"] is False
        assert result["x_content_type_options"] is False

    @patch("src.prospecting.scanners.headers.requests.head")
    def test_partial_headers(self, mock_head):
        mock_head.return_value.headers = {
            "Strict-Transport-Security": "max-age=31536000",
        }
        result = get_response_headers("test.dk")
        assert result["strict_transport_security"] is True
        assert result["x_frame_options"] is False

    @patch("src.prospecting.scanners.headers.requests.head")
    def test_connection_error(self, mock_head):
        import requests
        mock_head.side_effect = requests.RequestException("timeout")
        result = get_response_headers("test.dk")
        assert result["x_frame_options"] is False


class TestExtractPageMeta:
    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_wordpress_plugins(self, mock_get):
        mock_get.return_value.text = """
        <html>
        <link rel="stylesheet" href="/wp-content/plugins/contact-form-7/style.css">
        <script src="/wp-content/plugins/yoast-seo/js/main.js"></script>
        </html>
        """
        author, credit, plugins, versions, themes = extract_page_meta("test.dk")
        assert "contact-form-7" in plugins
        assert "yoast-seo" in plugins

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_meta_author(self, mock_get):
        mock_get.return_value.text = '<meta name="author" content="WebBureauet">'
        author, credit, plugins, versions, themes = extract_page_meta("test.dk")
        assert author == "WebBureauet"

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_footer_credit_danish(self, mock_get):
        mock_get.return_value.text = '<footer>Website lavet af SuperWeb ApS</footer>'
        author, credit, plugins, versions, themes = extract_page_meta("test.dk")
        assert "SuperWeb" in credit

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_footer_credit_powered_by(self, mock_get):
        mock_get.return_value.text = '<footer>Powered by Starter Agency</footer>'
        author, credit, plugins, versions, themes = extract_page_meta("test.dk")
        assert "Starter Agency" in credit

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_no_matches(self, mock_get):
        mock_get.return_value.text = "<html><body>Simple page</body></html>"
        author, credit, plugins, versions, themes = extract_page_meta("test.dk")
        assert author == ""
        assert credit == ""
        assert plugins == []
        assert versions == {}
        assert themes == []

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_request_exception(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("timeout")
        author, credit, plugins, versions, themes = extract_page_meta("test.dk")
        assert author == ""
        assert credit == ""
        assert plugins == []
        assert versions == {}
        assert themes == []

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_malformed_plugin_slugs_rejected(self, mock_get):
        mock_get.return_value.text = """
        <link href="/wp-content/plugins/good-plugin/style.css">
        <link href='/wp-content/plugins/*","bad/style.css'>
        """
        _, _, plugins, _, _ = extract_page_meta("test.dk")
        assert "good-plugin" in plugins
        # Malformed slug with special chars should be rejected by [\w-]+ regex
        assert not any("*" in p for p in plugins)

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_plugin_version_from_ver_param(self, mock_get):
        mock_get.return_value.text = """
        <link rel="stylesheet" href="/wp-content/plugins/wordpress-seo/css/style.css?ver=26.9">
        <script src="/wp-content/plugins/contact-form-7/js/scripts.js?ver=5.3.2"></script>
        <link href="/wp-content/plugins/no-version/style.css">
        """
        _, _, plugins, versions, _ = extract_page_meta("test.dk")
        assert "wordpress-seo" in plugins
        assert "contact-form-7" in plugins
        assert "no-version" in plugins
        assert versions["wordpress-seo"] == "26.9"
        assert versions["contact-form-7"] == "5.3.2"
        assert "no-version" not in versions

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_plugin_version_keeps_first(self, mock_get):
        mock_get.return_value.text = """
        <link href="/wp-content/plugins/elementor/css/a.css?ver=3.27.3">
        <script src="/wp-content/plugins/elementor/js/b.js?ver=3.27.3"></script>
        <script src="/wp-content/plugins/elementor/js/c.js"></script>
        """
        _, _, plugins, versions, _ = extract_page_meta("test.dk")
        assert plugins.count("elementor") == 1
        assert versions["elementor"] == "3.27.3"

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_plugin_version_html_entity(self, mock_get):
        """WordPress sometimes writes &#038; instead of & in HTML."""
        mock_get.return_value.text = """
        <script src="/wp-content/plugins/woocommerce/assets/js/frontend.js?ver=9.6.4&#038;other=1"></script>
        <link href="/wp-content/plugins/yoast/css/main.css?foo=1&amp;ver=27.3">
        """
        _, _, plugins, versions, _ = extract_page_meta("test.dk")
        assert versions.get("woocommerce") == "9.6.4"
        assert versions.get("yoast") == "27.3"

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_theme_extraction(self, mock_get):
        mock_get.return_value.text = """
        <link rel="stylesheet" href="/wp-content/themes/flavor/style.css?ver=1.0">
        <script src="/wp-content/themes/flavor/js/scripts.js"></script>
        <link href="/wp-content/themes/flavor-child/style.css">
        """
        _, _, _, _, themes = extract_page_meta("test.dk")
        assert "flavor" in themes
        assert "flavor-child" in themes

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_meta_generator_woocommerce(self, mock_get):
        mock_get.return_value.text = """
        <meta name="generator" content="WordPress 6.9.4">
        <meta name="generator" content="WooCommerce 9.6.4">
        """
        _, _, plugins, versions, _ = extract_page_meta("test.dk")
        assert "woocommerce" in plugins
        assert versions.get("woocommerce") == "9.6.4"

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_css_class_divi_detection(self, mock_get):
        mock_get.return_value.text = """
        <html><body class="et_divi_theme">
        <div class="et_pb_section et_pb_row">content</div>
        </body></html>
        """
        _, _, plugins, _, _ = extract_page_meta("test.dk")
        assert "divi-builder" in plugins

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_css_class_woocommerce_detection(self, mock_get):
        mock_get.return_value.text = """
        <html><body class="woocommerce-page woocommerce-no-js">
        <div class="woocommerce">shop</div>
        </body></html>
        """
        _, _, plugins, _, _ = extract_page_meta("test.dk")
        assert "woocommerce" in plugins

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_rest_api_namespace_detection(self, mock_get):
        """REST API namespaces reveal installed plugins."""
        homepage_resp = MagicMock()
        homepage_resp.text = """
        <link rel="https://api.w.org/" href="https://test.dk/wp-json/">
        """
        api_resp = MagicMock()
        api_resp.status_code = 200
        api_resp.json.return_value = {
            "namespaces": ["wp/v2", "wc/v3", "wc/store/v1", "gf/v2", "yoast/v1"]
        }
        mock_get.side_effect = [homepage_resp, api_resp]
        _, _, plugins, _, _ = extract_page_meta("test.dk")
        assert "woocommerce" in plugins
        assert "gravityforms" in plugins
        assert "wordpress-seo" in plugins

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_rest_api_failure_graceful(self, mock_get):
        """REST API fetch failure doesn't crash — falls back to HTML-only detection."""
        homepage_resp = MagicMock()
        homepage_resp.text = """
        <link rel="https://api.w.org/" href="https://test.dk/wp-json/">
        <link href="/wp-content/plugins/akismet/style.css">
        """
        api_resp = MagicMock()
        api_resp.status_code = 403
        mock_get.side_effect = [homepage_resp, api_resp]
        _, _, plugins, _, _ = extract_page_meta("test.dk")
        assert "akismet" in plugins  # HTML detection still works

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_no_duplicate_from_multiple_sources(self, mock_get):
        """Plugin detected via HTML path + meta generator + CSS class = only listed once."""
        homepage_resp = MagicMock()
        homepage_resp.text = """
        <meta name="generator" content="WooCommerce 9.6.4">
        <body class="woocommerce-page">
        <link href="/wp-content/plugins/woocommerce/assets/style.css?ver=9.6.4">
        </body>
        """
        mock_get.return_value = homepage_resp
        _, _, plugins, versions, _ = extract_page_meta("test.dk")
        assert plugins.count("woocommerce") == 1
        assert versions["woocommerce"] == "9.6.4"

    @patch("src.prospecting.scanners.wordpress.requests.get")
    def test_returns_five_element_tuple(self, mock_get):
        mock_get.return_value.text = "<html></html>"
        result = extract_page_meta("test.dk")
        assert len(result) == 5
        assert result[3] == {}
        assert result[4] == []


class TestCheckRobotsTxt:
    @patch("src.prospecting.scanners.robots.requests.get")
    def test_allows_all(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "User-agent: *\nAllow: /"
        assert check_robots_txt("test.dk") is True

    @patch("src.prospecting.scanners.robots.requests.get")
    def test_disallows_all(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "User-agent: *\nDisallow: /"
        assert check_robots_txt("test.dk") is False

    @patch("src.prospecting.scanners.robots.requests.get")
    def test_no_robots_txt(self, mock_get):
        mock_get.return_value.status_code = 404
        assert check_robots_txt("test.dk") is True

    @patch("src.prospecting.scanners.robots.requests.get")
    def test_connection_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("timeout")
        assert check_robots_txt("test.dk") is True


class TestRunHttpx:
    @patch("src.prospecting.scanners.httpx_scan.shutil.which", return_value="/usr/bin/httpx")
    @patch("src.prospecting.scanners.httpx_scan.subprocess.run")
    def test_parses_json_output(self, mock_run, mock_which):
        mock_run.return_value.stdout = '{"input":"test.dk","host":"test.dk","webserver":"Apache","tech":["WordPress","PHP"]}\n'
        mock_run.return_value.returncode = 0
        result = run_httpx(["test.dk"])
        assert "test.dk" in result
        assert result["test.dk"]["webserver"] == "Apache"

    @patch("src.prospecting.scanners.httpx_scan.shutil.which", return_value=None)
    def test_tool_not_found(self, mock_which):
        result = run_httpx(["test.dk"])
        assert result == {}

    @patch("src.prospecting.scanners.httpx_scan.shutil.which", return_value="/usr/bin/httpx")
    @patch("src.prospecting.scanners.httpx_scan.subprocess.run")
    def test_timeout(self, mock_run, mock_which):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="httpx", timeout=300)
        result = run_httpx(["test.dk"])
        assert result == {}

    @patch("src.prospecting.scanners.httpx_scan.shutil.which", return_value="/usr/bin/httpx")
    @patch("src.prospecting.scanners.httpx_scan.subprocess.run")
    def test_invalid_json_skipped(self, mock_run, mock_which):
        mock_run.return_value.stdout = 'not json\n{"input":"valid.dk","host":"valid.dk","webserver":"nginx"}\n'
        result = run_httpx(["valid.dk"])
        assert "valid.dk" in result


class TestRunWebanalyze:
    @patch("src.prospecting.scanners.webanalyze.shutil.which", return_value="/usr/bin/webanalyze")
    @patch("src.prospecting.scanners.webanalyze.subprocess.run")
    def test_json_array_output(self, mock_run, mock_which):
        mock_run.return_value.stdout = json.dumps([
            {"hostname": "https://test.dk", "matches": [{"app_name": "WordPress"}, {"app_name": "jQuery"}]}
        ])
        result = run_webanalyze(["test.dk"])
        assert "test.dk" in result
        assert "WordPress" in result["test.dk"]

    @patch("src.prospecting.scanners.webanalyze.shutil.which", return_value="/usr/bin/webanalyze")
    @patch("src.prospecting.scanners.webanalyze.subprocess.run")
    def test_json_lines_fallback(self, mock_run, mock_which):
        # Two lines of JSON (not a JSON array) — triggers line-by-line fallback
        mock_run.return_value.stdout = '{"hostname":"https://test.dk","matches":[{"app_name":"WordPress"}]}\n{"hostname":"https://other.dk","matches":[{"app_name":"Joomla"}]}'
        result = run_webanalyze(["test.dk", "other.dk"])
        assert "test.dk" in result
        assert "other.dk" in result

    @patch("src.prospecting.scanners.webanalyze.shutil.which", return_value=None)
    def test_tool_not_found(self, mock_which):
        result = run_webanalyze(["test.dk"])
        assert result == {}


class TestRunSubfinder:
    @patch("src.prospecting.scanners.subfinder.shutil.which", return_value="/usr/bin/subfinder")
    @patch("src.prospecting.scanners.subfinder.subprocess.run")
    def test_groups_by_parent(self, mock_run, mock_which):
        lines = [
            '{"host":"www.test.dk","source":"crtsh"}',
            '{"host":"mail.test.dk","source":"dns"}',
            '{"host":"api.other.dk","source":"crtsh"}',
        ]
        mock_run.return_value.stdout = "\n".join(lines)
        result = run_subfinder(["test.dk", "other.dk"])
        assert "www.test.dk" in result.get("test.dk", [])
        assert "mail.test.dk" in result.get("test.dk", [])
        assert "api.other.dk" in result.get("other.dk", [])

    @patch("src.prospecting.scanners.subfinder.shutil.which", return_value=None)
    def test_tool_not_found(self, mock_which):
        result = run_subfinder(["test.dk"])
        assert result == {}

    @patch("src.prospecting.scanners.subfinder.shutil.which", return_value="/usr/bin/subfinder")
    @patch("src.prospecting.scanners.subfinder.subprocess.run")
    def test_timeout(self, mock_run, mock_which):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="subfinder", timeout=600)
        result = run_subfinder(["test.dk"])
        assert result == {}


class TestRunDnsx:
    @patch("src.prospecting.scanners.dnsx.shutil.which", return_value="/usr/bin/dnsx")
    @patch("src.prospecting.scanners.dnsx.subprocess.run")
    def test_parses_records(self, mock_run, mock_which):
        mock_run.return_value.stdout = '{"host":"test.dk","a":["1.2.3.4"],"mx":["mx.test.dk"],"txt":["v=spf1"]}\n'
        result = run_dnsx(["test.dk"])
        assert "test.dk" in result
        assert result["test.dk"]["a"] == ["1.2.3.4"]
        assert result["test.dk"]["mx"] == ["mx.test.dk"]

    @patch("src.prospecting.scanners.dnsx.shutil.which", return_value=None)
    def test_tool_not_found(self, mock_which):
        result = run_dnsx(["test.dk"])
        assert result == {}


class TestQueryCrtShSingle:
    @patch("src.prospecting.scanners.ct.requests.get")
    @patch("src.prospecting.scanners.ct.time.sleep")
    def test_parses_and_deduplicates(self, mock_sleep, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [
            {"common_name": "test.dk", "issuer_name": "LE", "not_before": "2026-01-01", "not_after": "2026-04-01"},
            {"common_name": "test.dk", "issuer_name": "LE", "not_before": "2026-01-01", "not_after": "2026-04-01"},
            {"common_name": "www.test.dk", "issuer_name": "LE", "not_before": "2026-01-01", "not_after": "2026-04-01"},
        ]
        domain, certs = query_crt_sh_single("test.dk")
        assert domain == "test.dk"
        assert len(certs) == 2  # deduplicated

    @patch("src.prospecting.scanners.ct.requests.get")
    @patch("src.prospecting.scanners.ct.time.sleep")
    def test_rate_limited_429(self, mock_sleep, mock_get):
        mock_get.return_value.status_code = 429
        domain, certs = query_crt_sh_single("test.dk")
        assert certs == []

    @patch("src.prospecting.scanners.ct.requests.get")
    @patch("src.prospecting.scanners.ct.time.sleep")
    def test_timeout(self, mock_sleep, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("timeout")
        domain, certs = query_crt_sh_single("test.dk")
        assert certs == []


class TestQueryGrayHatWarfare:
    @patch("src.prospecting.scanners.grayhat.GRAYHATWARFARE_API_KEY", "test-key")
    @patch("src.prospecting.scanners.grayhat.requests.get")
    def test_aggregates_buckets(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "files": [
                {"bucket": "test-bucket", "filename": "file1.txt"},
                {"bucket": "test-bucket", "filename": "file2.txt"},
                {"bucket": "other-bucket", "filename": "file3.txt"},
            ]
        }
        result = query_grayhatwarfare(["test.dk"])
        assert "test.dk" in result
        buckets = {b["bucket_name"]: b["file_count"] for b in result["test.dk"]}
        assert buckets["test-bucket"] == 2
        assert buckets["other-bucket"] == 1

    @patch("src.prospecting.scanners.grayhat.GRAYHATWARFARE_API_KEY", "")
    def test_no_api_key_skips(self):
        result = query_grayhatwarfare(["test.dk"])
        assert result == {}

    @patch("src.prospecting.scanners.grayhat.GRAYHATWARFARE_API_KEY", "test-key")
    @patch("src.prospecting.scanners.grayhat.requests.get")
    def test_api_error(self, mock_get):
        mock_get.return_value.status_code = 500
        result = query_grayhatwarfare(["test.dk"])
        assert result.get("test.dk") is None


class TestValidateApprovalTokens:
    @patch("builtins.open", mock_open(read_data='{"approvals": []}'))
    def test_missing_scan_type_returns_none(self):
        _init_scan_type_map()
        result = _validate_approval_tokens()
        assert result is None

    @patch("builtins.open")
    def test_file_not_found_returns_none(self, mock_file):
        mock_file.side_effect = FileNotFoundError
        _init_scan_type_map()
        result = _validate_approval_tokens()
        assert result is None


class TestInitScanTypeMap:
    def test_registers_all_scan_types(self):
        _init_scan_type_map()
        expected = {
            "ssl_certificate_check",
            "homepage_meta_extraction",
            "httpx_tech_fingerprint",
            "webanalyze_cms_detection",
            "response_header_check",
            "subdomain_enumeration_passive",
            "dns_enrichment",
            "certificate_transparency_query",
            "cloud_storage_index_query",
            "nuclei_vulnerability_scan",
            "cmseek_cms_deep_scan",
            "nmap_port_scan",
        }
        assert set(_SCAN_TYPE_FUNCTIONS.keys()) == expected

    def test_all_are_callable(self):
        _init_scan_type_map()
        for name, func in _SCAN_TYPE_FUNCTIONS.items():
            assert callable(func), f"{name} is not callable"
