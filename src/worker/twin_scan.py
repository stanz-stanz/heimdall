"""Digital twin scan — run Layer 2 tools against a local replica.

Starts the twin server in a background thread on loopback, runs Nuclei
(and WPScan if WordPress) against it, and returns enriched findings with
``provenance: "twin-derived"`` markers.

The twin is pure stdlib Python with no dependencies — it runs in-process
within the worker container.  No Docker-in-Docker required.

Layer/Level: Layer 2 tools against Heimdall-owned infrastructure.
See SCANNING_RULES.md § "Heimdall-Owned Test Infrastructure".
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from datetime import date
from http.server import HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Slug map for plugin name normalisation
_SLUG_MAP_PATH = Path(__file__).resolve().parent.parent.parent / "tools" / "twin" / "slug_map.json"


def _load_slug_map() -> dict:
    try:
        with open(_SLUG_MAP_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        log.warning("twin_slug_map_load_failed: %s", exc)
        return {}


def _start_twin_server(brief: dict, slug_map: dict) -> tuple:
    """Start the twin HTTP server on a random loopback port.

    Returns ``(server, port, thread)``.
    """
    from tools.twin.twin_server import TwinHandler, _build_routes, _build_common_headers

    routes = _build_routes(brief, slug_map)
    common_headers = _build_common_headers(brief)
    domain = brief.get("domain", "twin.local")

    TwinHandler.routes = routes
    TwinHandler.domain = domain
    TwinHandler.common_headers = common_headers
    TwinHandler.login_cookie = f"domain={domain}"
    TwinHandler.jitter = False  # No jitter for pipeline scans

    server = HTTPServer(("127.0.0.1", 0), TwinHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port, thread


def _run_nuclei_against_twin(port: int) -> List[dict]:
    """Run Nuclei against the twin on loopback.

    Returns a list of finding dicts.
    """
    if not shutil.which("nuclei"):
        log.info("twin_nuclei_skipped: nuclei binary not found")
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
        log.warning("twin_nuclei_timeout")
        return []
    except FileNotFoundError:
        log.info("twin_nuclei_skipped: nuclei binary not found")
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
                "provenance": "twin-derived",
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


def _run_wpscan_against_twin(port: int) -> List[dict]:
    """Run WPScan against the twin on loopback.

    Returns a list of finding dicts.
    """
    if not shutil.which("wpscan"):
        log.info("twin_wpscan_skipped: wpscan binary not found")
        return []

    target = f"http://127.0.0.1:{port}"
    cmd = [
        "wpscan",
        "--url", target,
        "--format", "json",
        "--no-update",
        "--disable-tls-checks",
    ]

    # Add API token if available
    import os
    api_token = os.environ.get("WPSCAN_API_TOKEN")
    if api_token:
        cmd.extend(["--api-token", api_token])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        log.info("twin_wpscan_skipped: wpscan not available or timed out")
        return []

    findings = []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return findings

    # Extract vulnerability findings from WPScan JSON
    for vuln_source in ["main_theme", "plugins", "version"]:
        source_data = data.get(vuln_source, {})
        if isinstance(source_data, dict):
            vulns = source_data.get("vulnerabilities", [])
            if isinstance(vulns, list):
                for v in vulns:
                    cve = ""
                    refs = v.get("references", {})
                    cves = refs.get("cve", [])
                    if cves:
                        cve = f"CVE-{cves[0]}"

                    findings.append({
                        "severity": _wpscan_severity(v),
                        "description": v.get("title", "Unknown vulnerability"),
                        "risk": f"{cve + ': ' if cve else ''}{v.get('title', '')}",
                        "provenance": "twin-derived",
                        "provenance_detail": {
                            "source_layer": 1,
                            "twin_scan_tool": "wpscan",
                            "template_id": cve or v.get("wpvulndb", ""),
                            "confidence": "high-inference",
                        },
                    })

    return findings


def _wpscan_severity(vuln: dict) -> str:
    """Map WPScan vulnerability type to severity."""
    vuln_type = vuln.get("vuln_type", "").lower()
    if "rce" in vuln_type or "sql" in vuln_type:
        return "critical"
    if "xss" in vuln_type or "csrf" in vuln_type:
        return "high"
    return "medium"


def run_twin_scan(brief: dict) -> Optional[dict]:
    """Run Layer 2 tools against a digital twin built from the brief.

    Returns a dict with ``findings``, ``scan_tools``, ``duration_ms``,
    and ``twin_scan_date``, or None if the twin could not be started.
    """
    slug_map = _load_slug_map()
    t0 = time.monotonic()
    scan_tools = []

    log.info("twin_start", extra={"context": {"domain": brief.get("domain", "")}})

    try:
        server, port, thread = _start_twin_server(brief, slug_map)
    except Exception as exc:
        log.error("twin_start_failed: %s", exc)
        return None

    try:
        findings: List[dict] = []

        # Nuclei
        nuclei_findings = _run_nuclei_against_twin(port)
        if nuclei_findings:
            findings.extend(nuclei_findings)
            scan_tools.append("nuclei")

        # WPScan (WordPress only)
        cms = brief.get("technology", {}).get("cms", "")
        if cms and cms.lower() == "wordpress":
            wpscan_findings = _run_wpscan_against_twin(port)
            if wpscan_findings:
                findings.extend(wpscan_findings)
                scan_tools.append("wpscan")

        duration_ms = int((time.monotonic() - t0) * 1000)

        log.info(
            "twin_scan_complete",
            extra={"context": {
                "domain": brief.get("domain", ""),
                "findings_count": len(findings),
                "scan_tools": scan_tools,
                "duration_ms": duration_ms,
            }},
        )

        return {
            "findings": findings,
            "scan_tools": scan_tools,
            "duration_ms": duration_ms,
            "twin_scan_date": date.today().isoformat(),
        }
    finally:
        server.shutdown()
