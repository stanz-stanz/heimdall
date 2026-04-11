"""Digital twin scan — run Layer 2 tools against a local replica.

Starts the twin server in a background thread on loopback, runs Nuclei
(and WPVulnerability lookup if WordPress) against it, and returns enriched
findings with ``provenance: "unconfirmed"`` markers.

The twin is pure stdlib Python with no dependencies — it runs in-process
within the worker container.  No Docker-in-Docker required.

Layer/Level: Layer 2 tools against Heimdall-owned infrastructure.
See SCANNING_RULES.md § "Heimdall-Owned Test Infrastructure".
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import date
from http.server import HTTPServer
from pathlib import Path

from loguru import logger


def _get_container_ip() -> str:
    """Get this container's IP on the Docker bridge network.

    Falls back to the hostname if IP detection fails (e.g., local dev).
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("redis", 6379))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return socket.gethostname()


# Slug map for plugin name normalisation
_SLUG_MAP_PATH = Path(__file__).resolve().parent.parent.parent / "tools" / "twin" / "slug_map.json"


def _load_slug_map() -> dict:
    try:
        with open(_SLUG_MAP_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("twin_slug_map_load_failed: {}", exc)
        return {}


def _start_twin_server(brief: dict, slug_map: dict) -> tuple:
    """Start the twin HTTP server on a random loopback port.

    Returns ``(server, port, thread)``.
    """
    from tools.twin.twin_server import TwinHandler, _build_common_headers, _build_routes

    routes = _build_routes(brief, slug_map)
    common_headers = _build_common_headers(brief)
    domain = brief.get("domain", "twin.local")

    TwinHandler.routes = routes
    TwinHandler.domain = domain
    TwinHandler.common_headers = common_headers
    TwinHandler.login_cookie = f"domain={domain}"
    TwinHandler.jitter = False  # No jitter for pipeline scans

    # Bind to 0.0.0.0 so Nuclei (in the same container) can reach the twin
    server = HTTPServer(("0.0.0.0", 0), TwinHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, thread


def _run_nuclei_against_twin(port: int) -> list[dict]:
    """Run Nuclei against the twin on loopback.

    Returns a list of finding dicts.
    """
    if not shutil.which("nuclei"):
        logger.info("twin_nuclei_skipped: nuclei binary not found")
        return []

    target = f"http://127.0.0.1:{port}"
    cmd = [
        "nuclei",
        "-u", target,
        "-jsonl",
        "-silent",
        "-no-color",
        "-severity", "critical,high,medium,low",
        "-rate-limit", "50",
        "-concurrency", "5",
        "-timeout", "10",
        "-no-update-check",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.warning("twin_nuclei_timeout")
        return []
    except FileNotFoundError:
        logger.info("twin_nuclei_skipped: nuclei binary not found")
        return []

    findings = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            severity = entry.get("info", {}).get("severity", "info").lower()
            findings.append({
                "severity": severity,
                "description": entry.get("info", {}).get("name", "Unknown finding"),
                "risk": entry.get("info", {}).get("description", ""),
                "provenance": "unconfirmed",
                "provenance_detail": {
                    "source_layer": 1,
                    "twin_scan_tool": "nuclei",
                    "template_id": entry.get("template-id", ""),
                    "confidence": "high-inference",
                },
            })
        except json.JSONDecodeError:
            continue

    return findings


def run_twin_scan(brief: dict) -> dict | None:
    """Run Layer 2 tools against a digital twin built from the brief.

    Parameters
    ----------
    brief : dict
        The scan brief (from brief_generator).

    Returns a dict with ``findings``, ``scan_tools``, ``duration_ms``,
    and ``twin_scan_date``, or None if the twin could not be started.

    Note: not safe for concurrent use — TwinHandler uses class-level
    attributes that would be overwritten by a parallel call.
    """
    slug_map = _load_slug_map()
    t0 = time.monotonic()
    scan_tools = []

    logger.bind(context={"domain": brief.get("domain", "")}).info("twin_start")

    try:
        server, port, thread = _start_twin_server(brief, slug_map)
    except Exception as exc:
        logger.error("twin_start_failed: {}", exc)
        return None

    try:
        findings: list[dict] = []

        # Nuclei
        nuclei_findings = _run_nuclei_against_twin(port)
        if nuclei_findings:
            findings.extend(nuclei_findings)
            scan_tools.append("nuclei")

        # WPVulnerability lookup (WordPress only)
        cms = brief.get("technology", {}).get("cms", "")
        if cms and cms.lower() == "wordpress":
            try:
                from src.vulndb.lookup import lookup_wordpress_vulns

                vulndb_path = os.environ.get("VULNDB_PATH", "/data/cache/vulndb.sqlite3")
                plugin_slugs = brief.get("technology", {}).get("detected_plugins", [])
                # Resolve display names to slugs where possible
                resolved = []
                for name in plugin_slugs:
                    slug = slug_map.get(name, name.lower().replace(" ", "-"))
                    resolved.append(slug)

                # Extract plugin versions from brief
                brief_plugin_versions = dict(brief.get("plugin_versions", {}))

                # Extract WP core version from tech_stack
                wp_version = None
                for entry in brief.get("tech_stack", []):
                    if isinstance(entry, str) and entry.lower().startswith("wordpress:"):
                        wp_version = entry.split(":", 1)[1]
                        break

                vuln_findings = lookup_wordpress_vulns(
                    plugin_slugs=resolved,
                    plugin_versions=brief_plugin_versions,
                    wp_version=wp_version,
                    provenance="unconfirmed",
                    db_path=vulndb_path,
                )
                if vuln_findings:
                    findings.extend(vuln_findings)
                    scan_tools.append("wpvulnerability")
            except Exception:
                logger.opt(exception=True).error("twin_vulndb_lookup_failed")

        duration_ms = int((time.monotonic() - t0) * 1000)

        logger.bind(context={
            "domain": brief.get("domain", ""),
            "findings_count": len(findings),
            "scan_tools": scan_tools,
            "duration_ms": duration_ms,
        }).info("twin_scan_complete")

        return {
            "findings": findings,
            "scan_tools": scan_tools,
            "duration_ms": duration_ms,
            "twin_scan_date": date.today().isoformat(),
        }
    finally:
        server.shutdown()
