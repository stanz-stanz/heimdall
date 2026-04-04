"""Digital twin HTTP/HTTPS server.

Reads a prospect brief JSON and serves WordPress-like responses that
are detectable by the Heimdall scanning pipeline (httpx, webanalyze,
WPScan, Nuclei).

Usage:
    python -m tools.twin.twin_server --brief data/output/briefs/conrads.dk.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import signal
import ssl
import sys
import time
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread

from loguru import logger

from src.prospecting.logging_config import setup_logging

from . import templates

# WordPress "W" favicon — 16x16 ICO, base64-encoded
_WP_FAVICON_B64 = (
    "AAABAAEAEBAAAAEAIABoBAAAFgAAACgAAAAQAAAAIAAAAAEAIAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAjRp7/I0ae/yNGnv8jRp7/I0ae/yNGnv8jRp7/I0ae/yNGnv8jRp7/I0ae/yNG"
    "nv8AAAAAAAAAAAAAAAAAAAAAI0ae/yNGnv8jRp7/I0ae/yNGnv8jRp7/I0ae/yNGnv8j"
    "Rp7/I0ae/yNGnv8jRp7/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
)
_WP_FAVICON = base64.b64decode(_WP_FAVICON_B64)

_GPL_TEXT = "GNU GENERAL PUBLIC LICENSE\nVersion 2, June 1991\nhttps://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html\n"


class TwinHandler(BaseHTTPRequestHandler):
    """Request handler that serves pre-built responses from a route table."""

    # Set by the server at startup
    routes: dict = {}
    domain: str = "localhost"
    common_headers: dict = {}
    login_cookie: str = ""
    jitter: bool = True

    # Use HTTP/1.1 — WPScan uses libcurl which expects 1.1
    protocol_version = "HTTP/1.1"

    # Suppress BaseHTTPRequestHandler's default Server header
    server_version = ""
    sys_version = ""

    def version_string(self):
        return self.common_headers.get("Server", "")

    def log_message(self, format, *args):
        """Override default stderr logging with structured JSON."""
        pass  # We log in do_GET/do_HEAD instead

    def _send_response(self, path: str, include_body: bool = True):
        start = time.monotonic()

        if self.jitter:
            time.sleep(random.uniform(0.05, 0.2))

        route = self.routes.get(path)

        # Slash-agnostic fallback: /wp-json → /wp-json/ and vice versa
        if route is None:
            alt = path.rstrip("/") + "/" if not path.endswith("/") else path.rstrip("/")
            route = self.routes.get(alt)

        # Try prefix matching for dynamic paths
        if route is None:
            for prefix in ("/wp-content/plugins/", "/wp-content/cache/", "/wp-includes/"):
                if path.startswith(prefix):
                    # Check for known plugin readme
                    parts = path.split("/")
                    if (
                        prefix == "/wp-content/plugins/"
                        and len(parts) >= 5
                        and parts[3] in self.routes.get("_plugin_slugs", set())
                    ):
                        if path.endswith("/readme.txt"):
                            route = self.routes.get(f"/wp-content/plugins/{parts[3]}/readme.txt")
                            break
                    # Generic stub for known prefix paths
                    route = ("", "text/plain", 200)
                    break

        if route is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            for k, v in self.common_headers.items():
                if k == "Server":
                    continue
                self.send_header(k, v)
            self.end_headers()
            if include_body:
                self.wfile.write(b"<html><body><h1>Not Found</h1></body></html>")
            duration = (time.monotonic() - start) * 1000
            logger.info(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "path": path, "method": self.command, "status": 404, "ms": round(duration, 1)}))
            return

        if isinstance(route, tuple) and len(route) >= 3:
            body, content_type, status = route[0], route[1], route[2]
        else:
            body, content_type, status = route, "text/html; charset=utf-8", 200

        self.send_response(status)
        self.send_header("Content-Type", content_type)

        for k, v in self.common_headers.items():
            # Server header is already emitted by send_response() via version_string()
            if k == "Server":
                continue
            self.send_header(k, v)

        # Login page cookie
        if path == "/wp-login.php":
            self.send_header("Set-Cookie", f"wordpress_test_cookie=WP+Cookie+check; path=/; {self.login_cookie}")

        # Redirect
        if status == 302:
            self.send_header("Location", body)
            self.end_headers()
            duration = (time.monotonic() - start) * 1000
            logger.info(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "path": path, "method": self.command, "status": 302, "ms": round(duration, 1)}))
            return

        if isinstance(body, bytes):
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if include_body:
                self.wfile.write(body)
        else:
            encoded = body.encode("utf-8") if isinstance(body, str) else body
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            if include_body:
                self.wfile.write(encoded)

        duration = (time.monotonic() - start) * 1000
        logger.info(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "path": path, "method": self.command, "status": status, "ms": round(duration, 1)}))

    def do_GET(self):
        self._send_response(self.path.split("?")[0])

    def do_HEAD(self):
        self._send_response(self.path.split("?")[0], include_body=False)

    def do_POST(self):
        # Nuclei sends POST to /xmlrpc.php
        self._send_response(self.path.split("?")[0])


def _build_routes(brief: dict, slug_map: dict) -> dict:
    """Build the full route table from a brief."""
    domain = brief.get("domain", "localhost")
    plugins = templates.parse_tech_stack(brief, slug_map)
    wp_version = templates._extract_wp_version(brief)

    routes = {}

    # Core pages
    routes["/"] = (templates.build_index_html(brief, plugins), "text/html; charset=utf-8", 200)
    routes["/wp-login.php"] = (templates.build_wp_login_html(domain), "text/html; charset=utf-8", 200)
    routes["/wp-admin/"] = ("/wp-login.php", "text/html", 302)
    routes["/wp-json/"] = (json.dumps(templates.build_wpjson_root(domain)), "application/json; charset=utf-8", 200)
    routes["/wp-json/wp/v2/users/"] = (json.dumps(templates.build_wpjson_users()), "application/json; charset=utf-8", 200)
    routes["/xmlrpc.php"] = (templates.build_xmlrpc_response(), "text/xml; charset=utf-8", 200)
    routes["/robots.txt"] = ("User-agent: *\nAllow: /\n", "text/plain; charset=utf-8", 200)
    routes["/readme.html"] = (templates.build_readme_html(wp_version), "text/html; charset=utf-8", 200)
    routes["/license.txt"] = (_GPL_TEXT, "text/plain; charset=utf-8", 200)
    routes["/wp-cron.php"] = ("", "text/html; charset=utf-8", 200)
    routes["/favicon.ico"] = (_WP_FAVICON, "image/x-icon", 200)
    routes["/healthz"] = (json.dumps({"status": "ok"}), "application/json", 200)

    # RSS feed — WPScan checks /feed/ for version detection
    routes["/feed/"] = (
        templates.build_rss_feed(domain, wp_version), "application/rss+xml; charset=utf-8", 200
    )

    # Theme
    routes["/wp-content/themes/flavor/style.css"] = (
        templates.build_theme_style_css(), "text/css; charset=utf-8", 200
    )

    # Plugin readmes
    plugin_slugs = set()
    for slug, ver in plugins.items():
        display_name = slug.replace("-", " ").title()
        routes[f"/wp-content/plugins/{slug}/readme.txt"] = (
            templates.build_plugin_readme(display_name, ver or "1.0"),
            "text/plain; charset=utf-8",
            200,
        )
        plugin_slugs.add(slug)

    # Store plugin slugs for prefix matching
    routes["_plugin_slugs"] = plugin_slugs

    return routes


def _build_common_headers(brief: dict) -> dict:
    """Build headers sent with every response."""
    domain = brief.get("domain", "localhost")
    headers = {}

    # Server
    server = brief.get("technology", {}).get("server", "")
    if server:
        headers["Server"] = server

    # PHP
    php_ver = templates._extract_php_version(brief)
    if php_ver:
        headers["X-Powered-By"] = f"PHP/{php_ver}"

    # WordPress API discovery
    headers["Link"] = f'<https://{domain}/wp-json/>; rel="https://api.w.org/"'
    headers["X-Pingback"] = f"https://{domain}/xmlrpc.php"

    # Security headers — only include where brief says true
    header_map = {
        "x_frame_options": ("X-Frame-Options", "SAMEORIGIN"),
        "content_security_policy": ("Content-Security-Policy", "default-src 'self'"),
        "strict_transport_security": ("Strict-Transport-Security", "max-age=31536000; includeSubDomains"),
        "x_content_type_options": ("X-Content-Type-Options", "nosniff"),
    }
    brief_headers = brief.get("technology", {}).get("headers", {})
    for key, (header_name, header_value) in header_map.items():
        if brief_headers.get(key, False):
            headers[header_name] = header_value

    return headers


def _run_http_redirect(http_port: int, https_port: int, host: str, jitter: bool):
    """Run a simple HTTP server that redirects to HTTPS."""

    class RedirectHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/healthz":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
                return
            self.send_response(301)
            self.send_header("Location", f"https://localhost:{https_port}{self.path}")
            self.end_headers()

        def do_HEAD(self):
            self.do_GET()

    server = HTTPServer((host, http_port), RedirectHandler)
    logger.info(f"HTTP redirect server on {host}:{http_port} -> https://localhost:{https_port}")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Heimdall digital twin server")
    parser.add_argument("--brief", default=os.environ.get("BRIEF_FILE", "/config/brief.json"),
                        help="Path to prospect brief JSON")
    parser.add_argument("--port", type=int, default=int(os.environ.get("TWIN_PORT", "9443")),
                        help="HTTPS port (default: 9443)")
    parser.add_argument("--http-port", type=int, default=int(os.environ.get("TWIN_HTTP_PORT", "9080")),
                        help="HTTP port (default: 9080)")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--no-jitter", action="store_true", help="Disable response jitter")
    parser.add_argument("--no-tls", action="store_true", help="Skip TLS (serve HTTP only on --port)")
    args = parser.parse_args()

    # Logging
    setup_logging(level="INFO")

    # Load brief
    brief_path = Path(args.brief)
    if not brief_path.exists():
        logger.error(f"Brief not found: {brief_path}")
        sys.exit(1)

    with open(brief_path) as f:
        brief = json.load(f)

    domain = brief.get("domain", "localhost")
    logger.info(f"Loading twin for {domain} from {brief_path}")

    # Load slug map
    slug_map = templates.load_slug_map()

    # Build routes and headers
    routes = _build_routes(brief, slug_map)
    common_headers = _build_common_headers(brief)

    logger.info(f"Routes: {len(routes) - 1} paths, {len(routes.get('_plugin_slugs', set()))} plugins")

    # Configure handler
    TwinHandler.routes = routes
    TwinHandler.domain = domain
    TwinHandler.common_headers = common_headers
    TwinHandler.login_cookie = f"domain={domain}"
    TwinHandler.jitter = not args.no_jitter

    # Track stats for shutdown summary
    start_time = time.monotonic()

    # Start HTTP redirect server in background thread
    if not args.no_tls:
        http_thread = Thread(
            target=_run_http_redirect,
            args=(args.http_port, args.port, args.host, not args.no_jitter),
            daemon=True,
        )
        http_thread.start()

    # HTTPS server
    server = HTTPServer((args.host, args.port), TwinHandler)

    if not args.no_tls:
        cert_dir = Path(os.environ.get("CERT_DIR", "/home/heimdall/.certs"))
        cert_file = cert_dir / "cert.pem"
        key_file = cert_dir / "key.pem"

        if not cert_file.exists():
            logger.warning(f"Cert not found at {cert_file}, serving HTTP only on port {args.port}")
        else:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(cert_file), str(key_file))
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            logger.info(f"HTTPS server on {args.host}:{args.port}")

    else:
        logger.info(f"HTTP server on {args.host}:{args.port} (TLS disabled)")

    # Graceful shutdown
    def _shutdown(signum, frame):
        uptime = time.monotonic() - start_time
        logger.info(json.dumps({
            "event": "shutdown",
            "uptime_seconds": round(uptime, 1),
            "domain": domain,
        }))
        server.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    server.serve_forever()


if __name__ == "__main__":
    main()
