"""Layer 1 scanner: passive technology fingerprinting via httpx and webanalyze."""

from __future__ import annotations

import json
import logging
import re
import shutil
import ssl
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone

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
    admin_panel_exposed: bool = False
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


def _check_admin_panels(domain: str) -> bool:
    """Check for exposed admin panels at common paths."""
    admin_paths = ["/wp-admin/", "/wp-login.php", "/administrator/", "/admin/", "/user/login"]
    for path in admin_paths:
        try:
            resp = requests.get(
                f"https://{domain}{path}",
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                allow_redirects=False,
            )
            # A 200 or 302 to a login page means it's exposed
            if resp.status_code in (200, 301, 302):
                return True
        except requests.RequestException:
            continue
    return False


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


def scan_domains(companies: list[Company]) -> dict[str, ScanResult]:
    """Run Layer 1 scanning on all non-discarded companies. Returns dict keyed by domain."""
    active = [c for c in companies if not c.discarded and c.website_domain]
    domains = list(set(c.website_domain for c in active))
    log.info("Scanning %d unique domains (Layer 1 passive only)", len(domains))

    # Batch scans with CLI tools
    httpx_results = _run_httpx(domains)
    webanalyze_results = _run_webanalyze(domains)

    results: dict[str, ScanResult] = {}

    for i, domain in enumerate(domains, 1):
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

        # Admin panel check
        scan.admin_panel_exposed = _check_admin_panels(domain)

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
            log.info("Scanned %d/%d domains", i, len(domains))

    log.info("Layer 1 scanning complete: %d domains scanned", len(results))
    return results
