"""WPVulnerability.net REST API client with retry.

Free, no auth required. Aggregates CVE/NVD, WPScan, Wordfence, Patchstack data.
"""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://www.wpvulnerability.net"
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
RETRY_DELAY = 1.0
USER_AGENT = "Heimdall-EASM/1.0 (vuln-lookup)"


def fetch_plugin_vulns(slug: str) -> tuple[int, list[dict]]:
    """Fetch vulnerabilities for a WordPress plugin by slug.

    Returns (http_status, parsed_vulns). Returns (0, []) on network error.
    """
    return _fetch_vulns(f"{BASE_URL}/plugin/{slug}/", slug, "plugin")


def fetch_core_vulns(version: str) -> tuple[int, list[dict]]:
    """Fetch vulnerabilities for a WordPress core version.

    Returns (http_status, parsed_vulns).
    """
    return _fetch_vulns(f"{BASE_URL}/core/{version}/", version, "core")


def fetch_theme_vulns(slug: str) -> tuple[int, list[dict]]:
    """Fetch vulnerabilities for a WordPress theme by slug.

    Returns (http_status, parsed_vulns).
    """
    return _fetch_vulns(f"{BASE_URL}/theme/{slug}/", slug, "theme")


def _fetch_vulns(url: str, identifier: str, asset_type: str) -> tuple[int, list[dict]]:
    """Generic fetch with retry. Returns (status_code, parsed_vulns)."""
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

            if resp.status_code >= 500:
                if attempt < MAX_RETRIES:
                    log.warning("wpvuln_server_error", extra={"context": {
                        "url": url, "status": resp.status_code,
                        "attempt": attempt + 1,
                    }})
                    time.sleep(RETRY_DELAY)
                    continue
                return resp.status_code, []

            data = resp.json()

            if data.get("error") == 1:
                log.debug("wpvuln_api_error", extra={"context": {
                    "identifier": identifier, "message": data.get("message"),
                }})
                return resp.status_code, []

            raw_vulns = (data.get("data") or {}).get("vulnerability")
            if not raw_vulns:
                return resp.status_code, []

            vulns = [_normalize_vuln(v) for v in raw_vulns]

            log.info("wpvuln_fetch_ok", extra={"context": {
                "asset_type": asset_type,
                "identifier": identifier,
                "vuln_count": len(vulns),
            }})
            return resp.status_code, vulns

        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                log.warning("wpvuln_request_error", extra={"context": {
                    "url": url, "error": str(exc), "attempt": attempt + 1,
                }})
                time.sleep(RETRY_DELAY)
            else:
                log.error("wpvuln_request_failed", extra={"context": {
                    "url": url, "error": str(exc),
                }})
                return 0, []

    return 0, []


def _normalize_vuln(raw: dict) -> dict:
    """Normalize a WPVulnerability API vuln entry to our cache format."""
    operator = raw.get("operator", {})
    impact_raw = raw.get("impact", {})
    # API returns impact as either a dict or a list of dicts
    if isinstance(impact_raw, list):
        impact = impact_raw[0] if impact_raw else {}
    else:
        impact = impact_raw
    cvss = impact.get("cvss", {})
    cwe_list = impact.get("cwe", [])

    # Extract CVE IDs from sources
    sources = raw.get("source", [])
    source_list = [
        {
            "id": s.get("id", ""),
            "name": s.get("name", ""),
            "link": s.get("link", ""),
        }
        for s in sources
    ]

    cwe_ids = [c.get("cwe", "") for c in cwe_list if c.get("cwe")]

    return {
        "uuid": raw.get("uuid", ""),
        "name": raw.get("name", ""),
        "max_version": operator.get("max_version") or "",
        "max_operator": operator.get("max_operator") or "",
        "min_version": operator.get("min_version") or "",
        "min_operator": operator.get("min_operator") or "",
        "unfixed": operator.get("unfixed", "0"),
        "cvss_score": cvss.get("score", ""),
        "cvss_severity": cvss.get("severity", ""),
        "cwe_ids": cwe_ids,
        "sources": source_list,
    }
