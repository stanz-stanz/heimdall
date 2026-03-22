"""Layer 1 scanner: passive technology fingerprinting via httpx and webanalyze."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import shutil
import ssl
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

import requests

from pipeline.config import REQUEST_TIMEOUT, USER_AGENT
from pipeline.cvr import Company

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    domain: str = ""
    cms: str = ""
    server: str = ""
    hosting: str = ""
    ssl_valid: bool = False
    ssl_issuer: str = ""
    ssl_expiry: str = ""
    ssl_days_remaining: int = -1
    detected_plugins: list[str] = field(default_factory=list)
    headers: dict = field(default_factory=dict)
    tech_stack: list[str] = field(default_factory=list)
    meta_author: str = ""
    footer_credit: str = ""
    raw_httpx: dict = field(default_factory=dict)


def _check_ssl(domain: str) -> dict:
    """Check SSL certificate details for a domain."""
    result = {"valid": False, "issuer": "", "expiry": "", "days_remaining": -1}
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=domain) as sock:
            sock.settimeout(REQUEST_TIMEOUT)
            sock.connect((domain, 443))
            cert = sock.getpeercert()

        not_after = cert.get("notAfter", "")
        if not_after:
            expiry_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            result["expiry"] = expiry_dt.strftime("%Y-%m-%d")
            result["days_remaining"] = (expiry_dt - datetime.now(timezone.utc)).days
            result["valid"] = result["days_remaining"] > 0

        issuer = dict(x[0] for x in cert.get("issuer", []))
        result["issuer"] = issuer.get("organizationName", issuer.get("commonName", ""))

    except Exception as e:
        log.debug("SSL check failed for %s: %s", domain, e)

    return result



def _extract_page_meta(domain: str) -> tuple[str, str, list[str]]:
    """Fetch the homepage and extract meta author, footer credits, and plugin hints."""
    meta_author = ""
    footer_credit = ""
    plugins = []

    try:
        resp = requests.get(
            f"https://{domain}",
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        html = resp.text

        # Meta author
        match = re.search(r'<meta\s+name=["\']author["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if match:
            meta_author = match.group(1).strip()

        # Footer credits — look for common patterns in last portion of HTML
        footer_section = html[-5000:] if len(html) > 5000 else html
        credit_patterns = [
            r'(?:website|webdesign|design|lavet|udviklet|skabt)\s+(?:by|af|:)\s*["\']?([^"\'<\n,]{3,50})',
            r'(?:powered\s+by)\s+([^"\'<\n,]{3,50})',
        ]
        for pattern in credit_patterns:
            match = re.search(pattern, footer_section, re.IGNORECASE)
            if match:
                footer_credit = match.group(1).strip()
                break

        # WordPress plugin detection from HTML source
        wp_plugin_matches = re.findall(r'/wp-content/plugins/([^/]+)/', html)
        if wp_plugin_matches:
            plugins = list(set(wp_plugin_matches))

    except requests.RequestException as e:
        log.debug("Page meta extraction failed for %s: %s", domain, e)

    return meta_author, footer_credit, plugins


def _run_httpx(domains: list[str]) -> dict[str, dict]:
    """Run httpx CLI tool against a list of domains. Returns dict keyed by domain."""
    if not shutil.which("httpx"):
        log.warning("httpx not found in PATH — skipping httpx scan")
        return {}

    # Write domains to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(domains))
        input_file = f.name

    try:
        result = subprocess.run(
            [
                "httpx",
                "-l", input_file,
                "-json",
                "-tech-detect",
                "-server",
                "-status-code",
                "-title",
                "-follow-redirects",
                "-silent",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        results = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                host = data.get("input", data.get("host", "")).lower()
                if host:
                    results[host] = data
            except json.JSONDecodeError:
                continue
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("httpx execution failed: %s", e)
        return {}
    finally:
        import os
        os.unlink(input_file)


def _run_webanalyze(domains: list[str]) -> dict[str, list[str]]:
    """Run webanalyze CLI tool against a list of domains. Returns tech stack per domain."""
    if not shutil.which("webanalyze"):
        log.warning("webanalyze not found in PATH — skipping webanalyze scan")
        return {}

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for d in domains:
            f.write(f"https://{d}\n")
        input_file = f.name

    try:
        result = subprocess.run(
            ["webanalyze", "-hosts", input_file, "-output", "json", "-silent", "-crawl", "0"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        results = {}
        try:
            data = json.loads(result.stdout)
            if isinstance(data, list):
                for entry in data:
                    host = entry.get("hostname", "").replace("https://", "").replace("http://", "").strip("/").lower()
                    techs = [m.get("app_name", "") or m.get("app", "") for m in entry.get("matches", []) if m]
                    if host and techs:
                        results[host] = [t for t in techs if t]
        except json.JSONDecodeError:
            # webanalyze may output line-by-line JSON
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    host = entry.get("hostname", "").replace("https://", "").replace("http://", "").strip("/").lower()
                    techs = [m.get("app_name", "") or m.get("app", "") for m in entry.get("matches", []) if m]
                    if host and techs:
                        results[host] = results.get(host, []) + [t for t in techs if t]
                except json.JSONDecodeError:
                    continue
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("webanalyze execution failed: %s", e)
        return {}
    finally:
        import os
        os.unlink(input_file)


def _get_response_headers(domain: str) -> dict:
    """Fetch security-relevant response headers."""
    headers = {
        "x_frame_options": False,
        "content_security_policy": False,
        "strict_transport_security": False,
        "x_content_type_options": False,
    }
    try:
        resp = requests.head(
            f"https://{domain}",
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        h = {k.lower(): v for k, v in resp.headers.items()}
        headers["x_frame_options"] = "x-frame-options" in h
        headers["content_security_policy"] = "content-security-policy" in h
        headers["strict_transport_security"] = "strict-transport-security" in h
        headers["x_content_type_options"] = "x-content-type-options" in h
    except requests.RequestException:
        pass
    return headers


def _check_robots_txt(domain: str) -> bool:
    """Layer 1 / Level 0 — Check if robots.txt allows automated access.

    Returns True if access is allowed, False if denied.
    Fetching robots.txt is permitted at all Layers — it is an explicitly published file.
    """
    try:
        resp = requests.get(
            f"https://{domain}/robots.txt",
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return True  # No robots.txt — no restriction expressed
        rp = RobotFileParser()
        rp.parse(resp.text.splitlines())
        return rp.can_fetch("*", "/")
    except requests.RequestException:
        return True  # Cannot fetch robots.txt — no restriction determinable


# Map scan type IDs to their implementing functions (populated after all functions are defined)
_SCAN_TYPE_FUNCTIONS: dict[str, callable] = {}


def _init_scan_type_map() -> None:
    """Populate the scan type function map. Called once at module load."""
    _SCAN_TYPE_FUNCTIONS.update({
        "ssl_certificate_check": _check_ssl,
        "homepage_meta_extraction": _extract_page_meta,
        "httpx_tech_fingerprint": _run_httpx,
        "webanalyze_cms_detection": _run_webanalyze,
        "response_header_check": _get_response_headers,
    })


def _validate_approval_tokens() -> bool:
    """Validate that all scan types have current approval tokens with matching function hashes."""
    approvals_path = Path(__file__).resolve().parent.parent / "data" / "valdi" / "active_approvals.json"
    try:
        with open(approvals_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error("Cannot read approval tokens: %s", e)
        return False

    approvals = {a["scan_type_id"]: a for a in data.get("approvals", [])}

    for scan_type_id, func in _SCAN_TYPE_FUNCTIONS.items():
        approval = approvals.get(scan_type_id)
        if not approval:
            log.error("No approval token for scan type: %s", scan_type_id)
            return False

        current_hash = "sha256:" + hashlib.sha256(
            inspect.getsource(func).encode("utf-8")
        ).hexdigest()
        if current_hash != approval["function_hash"]:
            log.error(
                "Function hash mismatch for %s — approval token invalidated. "
                "Re-submit to Valdi for Gate 1 review.",
                scan_type_id,
            )
            return False

    return True


def _write_pre_scan_check(allowed: list[str], skipped: list[str]) -> Path:
    """Write pre-scan compliance check to data/compliance/."""
    check_dir = Path(__file__).resolve().parent.parent / "data" / "compliance"
    check_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    check = {
        "scan_request_id": f"req-{now.strftime('%Y%m%d-%H%M%S')}",
        "batch_type": "prospect-scan-level0",
        "scan_types": list(_SCAN_TYPE_FUNCTIONS.keys()),
        "scan_layer": 1,
        "target_level": 0,
        "checks": {
            "all_approval_tokens_valid": True,
            "all_function_hashes_match": True,
            "robots_txt_filtered": True,
        },
        "domains_allowed": len(allowed),
        "domains_skipped_robots_txt": len(skipped),
        "skipped_domains": skipped,
        "checked_at": now.isoformat() + "Z",
    }

    filepath = check_dir / f"pre-scan-check-{now.strftime('%Y-%m-%d_%H-%M-%S')}.json"
    with open(filepath, "w") as f:
        json.dump(check, f, indent=2)
    log.info("Pre-scan check written to %s", filepath)
    return filepath


def scan_domains(companies: list[Company]) -> dict[str, ScanResult]:
    """Layer 1 / Level 0 — Run passive technology fingerprinting on all non-discarded companies.

    Validates Valdi approval tokens and function hashes before execution.
    Filters domains through robots.txt before any scanning activity.
    Returns dict keyed by domain.
    """
    _init_scan_type_map()

    # Gate check: validate all approval tokens and function hashes
    if not _validate_approval_tokens():
        log.error("BLOCKED — Valdi approval token validation failed. No scans will execute.")
        return {}

    active = [c for c in companies if not c.discarded and c.website_domain]
    domains = list(set(c.website_domain for c in active))
    log.info("Scanning %d unique domains (Layer 1 passive only)", len(domains))

    # robots.txt pre-filter — BEFORE any scanning activity
    allowed_domains = []
    skipped_domains = []
    for domain in domains:
        if _check_robots_txt(domain):
            allowed_domains.append(domain)
        else:
            skipped_domains.append(domain)
            log.info("SKIPPED %s — robots.txt denies automated access", domain)

    if skipped_domains:
        log.info(
            "robots.txt filter: %d allowed, %d skipped",
            len(allowed_domains), len(skipped_domains),
        )

    if not allowed_domains:
        log.warning("No domains passed robots.txt filter — nothing to scan")
        return {}

    # Write pre-scan compliance check (Gate 2 batch check)
    pre_scan_path = _write_pre_scan_check(allowed_domains, skipped_domains)
    log.info("Pre-scan check: %s", pre_scan_path)

    # Batch scans with CLI tools — only robots.txt-allowed domains
    httpx_results = _run_httpx(allowed_domains)
    webanalyze_results = _run_webanalyze(allowed_domains)

    results: dict[str, ScanResult] = {}

    for i, domain in enumerate(allowed_domains, 1):
        scan = ScanResult(domain=domain)

        # SSL check
        ssl_info = _check_ssl(domain)
        scan.ssl_valid = ssl_info["valid"]
        scan.ssl_issuer = ssl_info["issuer"]
        scan.ssl_expiry = ssl_info["expiry"]
        scan.ssl_days_remaining = ssl_info["days_remaining"]

        # Response headers
        scan.headers = _get_response_headers(domain)

        # httpx results
        httpx_data = httpx_results.get(domain, {})
        if httpx_data:
            scan.raw_httpx = httpx_data
            scan.server = httpx_data.get("webserver", "")
            tech = httpx_data.get("tech", [])
            if tech:
                scan.tech_stack.extend(tech)

        # webanalyze results
        wa_techs = webanalyze_results.get(domain, [])
        if wa_techs:
            scan.tech_stack.extend(wa_techs)

        # Deduplicate tech stack
        scan.tech_stack = list(dict.fromkeys(scan.tech_stack))

        # Derive CMS from tech stack
        cms_keywords = {
            "wordpress": "WordPress", "joomla": "Joomla", "drupal": "Drupal",
            "prestashop": "PrestaShop", "magento": "Magento", "shopify": "Shopify",
            "squarespace": "Squarespace", "wix": "Wix", "weebly": "Weebly",
            "webflow": "Webflow", "typo3": "TYPO3", "craft cms": "Craft CMS",
            "umbraco": "Umbraco", "sitecore": "Sitecore", "woocommerce": "WordPress",
        }
        for tech in scan.tech_stack:
            for keyword, cms_name in cms_keywords.items():
                if keyword in tech.lower():
                    scan.cms = cms_name
                    break
            if scan.cms:
                break

        # Page meta extraction (author, footer credit, plugins)
        meta_author, footer_credit, plugins = _extract_page_meta(domain)
        scan.meta_author = meta_author
        scan.footer_credit = footer_credit
        if plugins:
            scan.detected_plugins = plugins

        # Derive hosting from server header and tech stack
        hosting_hints = {
            "one.com": "one.com", "simply.com": "simply.com", "gigahost": "Gigahost",
            "unoeuro": "UnoEuro/Simply", "amazonaws": "AWS", "cloudflare": "Cloudflare",
            "nginx": "", "apache": "", "litespeed": "LiteSpeed",
        }
        combined = (scan.server + " " + " ".join(scan.tech_stack)).lower()
        for hint, provider in hosting_hints.items():
            if hint in combined and provider:
                scan.hosting = provider
                break

        results[domain] = scan

        if i % 25 == 0:
            log.info("Scanned %d/%d domains", i, len(allowed_domains))

    log.info(
        "Layer 1 scanning complete: %d domains scanned, %d skipped (robots.txt)",
        len(results), len(skipped_domains),
    )
    return results
