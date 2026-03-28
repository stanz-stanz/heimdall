"""Tests for the digital twin server templates and responses."""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.twin import templates
from tools.twin.twin_server import TwinHandler, _build_routes, _build_common_headers


@pytest.fixture
def conrads_brief():
    brief_path = Path(__file__).parents[3] / "data" / "output" / "briefs" / "conrads.dk.json"
    with open(brief_path) as f:
        return json.load(f)


@pytest.fixture
def slug_map():
    return templates.load_slug_map()


@pytest.fixture
def plugins(conrads_brief, slug_map):
    return templates.parse_tech_stack(conrads_brief, slug_map)


# --- parse_tech_stack ---

def test_parse_tech_stack_extracts_versions(conrads_brief, slug_map):
    plugins = templates.parse_tech_stack(conrads_brief, slug_map)
    assert plugins["wordpress-seo"] == "26.9"


def test_parse_tech_stack_deduplicates(conrads_brief, slug_map):
    """Brief has 'Gravityforms' twice in detected_plugins."""
    plugins = templates.parse_tech_stack(conrads_brief, slug_map)
    assert "gravityforms" in plugins
    slugs = list(plugins.keys())
    assert slugs.count("gravityforms") == 1


def test_slug_map_yoast(slug_map):
    assert slug_map["Yoast SEO"] == "wordpress-seo"


def test_slug_map_null_entries_skipped(conrads_brief, slug_map):
    """Non-plugin tech (jQuery, PHP, MySQL) should not appear in plugins."""
    plugins = templates.parse_tech_stack(conrads_brief, slug_map)
    for non_plugin in ("jquery", "php", "mysql", "cloudflare"):
        assert non_plugin not in plugins


# --- build_index_html ---

def test_index_html_generator_meta(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert '<meta name="generator" content="WordPress 6.9.4" />' in html


def test_index_html_plugin_paths(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert "/wp-content/plugins/wordpress-seo/" in html
    assert "/wp-content/plugins/gravityforms/" in html


def test_index_html_jquery_migrate(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert '/wp-includes/js/jquery/jquery-migrate.min.js?ver=3.4.1' in html


def test_index_html_emoji_script(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert "wpemojiSettings" in html


def test_index_html_jsonld(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert 'application/ld+json' in html
    assert '"@type"' in html


def test_index_html_size(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert len(html) > 30000, f"HTML too small: {len(html)} bytes"


def test_index_html_wp_content_regex(conrads_brief, plugins):
    """Verify the exact regex from scanner.py can extract plugins."""
    html = templates.build_index_html(conrads_brief, plugins)
    found = re.findall(r'/wp-content/plugins/([\w-]+)/', html)
    found_set = set(found)
    assert "wordpress-seo" in found_set
    assert "gravityforms" in found_set


def test_index_html_wp_rocket_cache(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert "/wp-content/cache/wp-rocket/" in html


def test_index_html_theme_link(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert "/wp-content/themes/flavor/style.css" in html


def test_index_html_api_discovery(conrads_brief, plugins):
    html = templates.build_index_html(conrads_brief, plugins)
    assert 'rel="https://api.w.org/"' in html


# --- build_plugin_readme ---

def test_plugin_readme_stable_tag():
    readme = templates.build_plugin_readme("Yoast SEO", "26.9")
    assert "Stable tag: 26.9" in readme


def test_plugin_readme_tested_up_to():
    readme = templates.build_plugin_readme("Test Plugin", "1.0")
    assert "Tested up to:" in readme


# --- build_theme_style_css ---

def test_theme_style_css_header():
    css = templates.build_theme_style_css()
    assert "Theme Name: flavor" in css


# --- build_wpjson ---

def test_wpjson_root_has_namespaces(conrads_brief):
    root = templates.build_wpjson_root("conrads.dk")
    assert "namespaces" in root
    assert "wp/v2" in root["namespaces"]


def test_wpjson_users():
    users = templates.build_wpjson_users()
    assert len(users) >= 1
    assert users[0]["slug"] == "admin"


# --- build_xmlrpc_response ---

def test_xmlrpc_response():
    xml = templates.build_xmlrpc_response()
    assert "methodResponse" in xml


# --- build_wp_login_html ---

def test_wp_login_has_form():
    html = templates.build_wp_login_html("conrads.dk")
    assert "loginform" in html
    assert "WordPress" in html


# --- build_readme_html ---

def test_readme_html_version():
    html = templates.build_readme_html("6.9.4")
    assert "6.9.4" in html
    assert "WordPress" in html


# --- Response headers ---

def test_headers_omit_missing(conrads_brief):
    headers = _build_common_headers(conrads_brief)
    assert "X-Frame-Options" not in headers
    assert "Content-Security-Policy" not in headers
    assert "Strict-Transport-Security" not in headers
    assert "X-Content-Type-Options" not in headers


def test_headers_include_present():
    brief = {
        "domain": "test.dk",
        "technology": {
            "server": "nginx",
            "headers": {
                "x_frame_options": True,
                "content_security_policy": True,
                "strict_transport_security": True,
                "x_content_type_options": True,
            },
        },
        "tech_stack": ["PHP"],
    }
    headers = _build_common_headers(brief)
    assert "X-Frame-Options" in headers
    assert "Content-Security-Policy" in headers
    assert "Strict-Transport-Security" in headers
    assert "X-Content-Type-Options" in headers


def test_headers_server_matches_brief(conrads_brief):
    headers = _build_common_headers(conrads_brief)
    assert headers["Server"] == "cloudflare"


def test_headers_link_wpjson(conrads_brief):
    headers = _build_common_headers(conrads_brief)
    assert "api.w.org" in headers.get("Link", "")


def test_headers_x_pingback(conrads_brief):
    headers = _build_common_headers(conrads_brief)
    assert "xmlrpc.php" in headers.get("X-Pingback", "")


def test_headers_x_powered_by(conrads_brief):
    headers = _build_common_headers(conrads_brief)
    assert headers.get("X-Powered-By", "").startswith("PHP/")


# --- Route table ---

def test_route_table_has_core_paths(conrads_brief, slug_map):
    routes = _build_routes(conrads_brief, slug_map)
    for path in ["/", "/wp-login.php", "/wp-json/", "/xmlrpc.php",
                 "/robots.txt", "/readme.html", "/license.txt", "/healthz",
                 "/favicon.ico", "/wp-cron.php"]:
        assert path in routes, f"Missing route: {path}"


def test_route_table_has_plugin_readmes(conrads_brief, slug_map):
    routes = _build_routes(conrads_brief, slug_map)
    assert "/wp-content/plugins/wordpress-seo/readme.txt" in routes


def test_route_table_has_theme_css(conrads_brief, slug_map):
    routes = _build_routes(conrads_brief, slug_map)
    assert "/wp-content/themes/flavor/style.css" in routes


# --- Integration test ---

@pytest.mark.integration
def test_server_serves_responses(conrads_brief, slug_map):
    """Start the twin server and make real HTTP requests."""
    import urllib.request

    routes = _build_routes(conrads_brief, slug_map)
    common_headers = _build_common_headers(conrads_brief)

    TwinHandler.routes = routes
    TwinHandler.domain = "conrads.dk"
    TwinHandler.common_headers = common_headers
    TwinHandler.login_cookie = "domain=conrads.dk"
    TwinHandler.jitter = False

    server = HTTPServer(("127.0.0.1", 0), TwinHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # Homepage
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        html = resp.read().decode()
        assert resp.status == 200
        assert "WordPress 6.9.4" in html

        # Plugin regex matches
        found = re.findall(r'/wp-content/plugins/([\w-]+)/', html)
        assert "wordpress-seo" in set(found)

        # wp-json
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/wp-json/")
        data = json.loads(resp.read())
        assert "namespaces" in data

        # Plugin readme
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/wp-content/plugins/wordpress-seo/readme.txt")
        readme = resp.read().decode()
        assert "Stable tag: 26.9" in readme

        # Healthz
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz")
        assert resp.status == 200

        # 404 for unknown path
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nonexistent")
            assert False, "Should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 404

        # Check common headers
        resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
        assert resp.headers.get("Server") == "cloudflare"
        assert "api.w.org" in resp.headers.get("Link", "")
        assert "X-Frame-Options" not in resp.headers
    finally:
        server.shutdown()
