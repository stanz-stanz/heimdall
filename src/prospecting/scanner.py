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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

import requests

from .config import (
    CRT_SH_API_URL,
    CRT_SH_DELAY,
    DNSX_TIMEOUT,
    GRAYHATWARFARE_API_KEY,
    REQUEST_TIMEOUT,
    SUBFINDER_TIMEOUT,
    USER_AGENT,
)
from .cvr import Company

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
    subdomains: list[str] = field(default_factory=list)
    dns_records: dict = field(default_factory=dict)
    ct_certificates: list[dict] = field(default_factory=list)
    exposed_cloud_storage: list[dict] = field(default_factory=list)


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
        wp_plugin_matches = re.findall(r'/wp-content/plugins/([\w-]+)/', html)
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


def _run_subfinder(domains: list[str]) -> dict[str, list[str]]:
    """Layer 1 / Level 0 — Subdomain enumeration via passive sources (CT logs, DNS datasets).

    Uses subfinder CLI. No direct queries to the target's infrastructure beyond DNS.
    """
    if not shutil.which("subfinder"):
        log.warning("subfinder not found in PATH — skipping subdomain enumeration")
        return {}

    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(domains))
        input_file = f.name

    try:
        result = subprocess.run(
            ["subfinder", "-dL", input_file, "-json", "-silent", "-all"],
            capture_output=True,
            text=True,
            timeout=SUBFINDER_TIMEOUT,
        )
        results: dict[str, list[str]] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                host = data.get("host", "").lower().strip()
                # Determine which parent domain this subdomain belongs to
                if host:
                    for domain in domains:
                        if host.endswith(f".{domain}") or host == domain:
                            results.setdefault(domain, []).append(host)
                            break
            except json.JSONDecodeError:
                continue

        # Deduplicate per domain
        for domain in results:
            results[domain] = list(dict.fromkeys(results[domain]))

        log.info("subfinder: found %d subdomains across %d domains",
                 sum(len(v) for v in results.values()), len(results))
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("subfinder execution failed: %s", e)
        return {}
    finally:
        os.unlink(input_file)


def _run_dnsx(domains: list[str]) -> dict[str, dict]:
    """Layer 1 / Level 0 — DNS record enrichment (A, AAAA, CNAME, MX, NS, TXT).

    Standard DNS queries to public resolvers. Public by design.
    """
    if not shutil.which("dnsx"):
        log.warning("dnsx not found in PATH — skipping DNS enrichment")
        return {}

    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("\n".join(domains))
        input_file = f.name

    try:
        result = subprocess.run(
            ["dnsx", "-l", input_file, "-json", "-a", "-aaaa", "-cname", "-mx", "-ns", "-txt", "-silent"],
            capture_output=True,
            text=True,
            timeout=DNSX_TIMEOUT,
        )
        results: dict[str, dict] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                host = data.get("host", "").lower().strip()
                if host:
                    results[host] = {
                        "a": data.get("a", []),
                        "aaaa": data.get("aaaa", []),
                        "cname": data.get("cname", []),
                        "mx": data.get("mx", []),
                        "ns": data.get("ns", []),
                        "txt": data.get("txt", []),
                    }
            except json.JSONDecodeError:
                continue

        log.info("dnsx: enriched DNS for %d domains", len(results))
        return results
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("dnsx execution failed: %s", e)
        return {}
    finally:
        os.unlink(input_file)


def _query_crt_sh(domains: list[str]) -> dict[str, list[dict]]:
    """Layer 1 / Level 0 — Certificate Transparency log query via crt.sh API.

    Queries a third-party public index. No requests to the target's infrastructure.
    """
    results: dict[str, list[dict]] = {}

    for i, domain in enumerate(domains):
        try:
            resp = requests.get(
                f"{CRT_SH_API_URL}/?q=%.{domain}&output=json",
                timeout=30,
                headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code != 200:
                log.debug("crt.sh returned %d for %s", resp.status_code, domain)
                continue

            data = resp.json()
            if not isinstance(data, list):
                continue

            # Deduplicate by common_name
            seen = set()
            certs = []
            for entry in data:
                cn = entry.get("common_name", "")
                if cn and cn not in seen:
                    seen.add(cn)
                    certs.append({
                        "common_name": cn,
                        "issuer_name": entry.get("issuer_name", ""),
                        "not_before": entry.get("not_before", ""),
                        "not_after": entry.get("not_after", ""),
                    })

            if certs:
                results[domain] = certs

        except (requests.RequestException, json.JSONDecodeError) as e:
            log.debug("crt.sh query failed for %s: %s", domain, e)

        # Rate limit
        if i < len(domains) - 1:
            time.sleep(CRT_SH_DELAY)

    log.info("crt.sh: found certificates for %d/%d domains", len(results), len(domains))
    return results


def _query_grayhatwarfare(domains: list[str]) -> dict[str, list[dict]]:
    """Layer 1 / Level 0 — Exposed cloud storage search via GrayHatWarfare public index.

    Queries a third-party public index. No requests to the target's infrastructure.
    """
    if not GRAYHATWARFARE_API_KEY:
        log.warning("GRAYHATWARFARE_API_KEY not set — skipping cloud storage search")
        return {}

    results: dict[str, list[dict]] = {}

    for domain in domains:
        try:
            resp = requests.get(
                "https://buckets.grayhatwarfare.com/api/v2/files",
                params={"keywords": domain},
                headers={"Authorization": f"Bearer {GRAYHATWARFARE_API_KEY}"},
                timeout=30,
            )
            if resp.status_code != 200:
                log.debug("GrayHatWarfare returned %d for %s", resp.status_code, domain)
                continue

            data = resp.json()
            files = data.get("files", [])
            if files:
                buckets: dict[str, int] = {}
                for f in files:
                    bucket_name = f.get("bucket", "unknown")
                    buckets[bucket_name] = buckets.get(bucket_name, 0) + 1

                results[domain] = [
                    {"bucket_name": name, "file_count": count}
                    for name, count in buckets.items()
                ]

        except (requests.RequestException, json.JSONDecodeError) as e:
            log.debug("GrayHatWarfare query failed for %s: %s", domain, e)

    log.info("GrayHatWarfare: found exposed storage for %d/%d domains", len(results), len(domains))
    return results


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
        "subdomain_enumeration_passive": _run_subfinder,
        "dns_enrichment": _run_dnsx,
        "certificate_transparency_query": _query_crt_sh,
        "cloud_storage_index_query": _query_grayhatwarfare,
    })


def _validate_approval_tokens() -> dict | None:
    """Validate all scan types have current approval tokens with matching function hashes.

    Returns the approvals dict on success, None on failure.
    """
    from .config import PROJECT_ROOT
    approvals_path = PROJECT_ROOT / "agents" / "valdi" / "approvals.json"
    try:
        with open(approvals_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error("Cannot read approval tokens: %s", e)
        return None

    approvals = {a["scan_type_id"]: a for a in data.get("approvals", [])}

    for scan_type_id, func in _SCAN_TYPE_FUNCTIONS.items():
        approval = approvals.get(scan_type_id)
        if not approval:
            log.error("No approval token for scan type: %s", scan_type_id)
            return None

        current_hash = "sha256:" + hashlib.sha256(
            inspect.getsource(func).encode("utf-8")
        ).hexdigest()
        if current_hash != approval["function_hash"]:
            log.error(
                "Function hash mismatch for %s — approval token invalidated. "
                "Re-submit to Valdi for Gate 1 review.",
                scan_type_id,
            )
            return None

    return data


def _write_pre_scan_check(allowed: list[str], skipped: list[str]) -> Path:
    """Write pre-scan compliance check to data/compliance/."""
    from .config import PROJECT_ROOT
    check_dir = PROJECT_ROOT / "agents" / "valdi" / "compliance"
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


def scan_domains(companies: list[Company], confirmed: bool = False) -> dict[str, ScanResult]:
    """Layer 1 / Level 0 — Run passive technology fingerprinting on all non-discarded companies.

    Validates Valdi approval tokens and function hashes before execution.
    Filters domains through robots.txt before any scanning activity.
    Requires operator confirmation unless confirmed=True.
    Returns dict keyed by domain.
    """
    from .operator import (
        print_gate1_summary,
        print_pre_scan_summary,
        print_run_summary,
        prompt_confirmation,
        write_run_summary,
    )

    _init_scan_type_map()

    # Gate check: validate all approval tokens and function hashes
    approvals_data = _validate_approval_tokens()
    if approvals_data is None:
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

    # --- Operator notification ---
    print_gate1_summary(approvals_data)
    print_pre_scan_summary(
        allowed_domains, skipped_domains,
        list(_SCAN_TYPE_FUNCTIONS.keys()), approvals_data,
    )

    # --- Hard confirmation gate ---
    if not confirmed:
        if not prompt_confirmation(len(allowed_domains)):
            log.info("ABORTED — Operator declined confirmation. No scans executed.")
            return {}

    start_time = datetime.now(timezone.utc)

    # Batch scans with CLI tools — only robots.txt-allowed domains
    httpx_results = _run_httpx(allowed_domains)
    webanalyze_results = _run_webanalyze(allowed_domains)

    # New passive enrichment tools
    subfinder_results = _run_subfinder(allowed_domains)
    crt_sh_results = _query_crt_sh(allowed_domains)

    # DNS enrichment: primary domains + discovered subdomains
    all_dns_targets = set(allowed_domains)
    for subs in subfinder_results.values():
        all_dns_targets.update(subs)
    dnsx_results = _run_dnsx(list(all_dns_targets))

    ghw_results = _query_grayhatwarfare(allowed_domains)

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
        from .config import CMS_KEYWORDS
        for tech in scan.tech_stack:
            for keyword, cms_name in CMS_KEYWORDS.items():
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
        from .config import HOSTING_PROVIDERS
        combined = (scan.server + " " + " ".join(scan.tech_stack)).lower()
        for hint, provider in HOSTING_PROVIDERS.items():
            if hint in combined and provider:
                scan.hosting = provider
                break

        # Subdomains (from subfinder)
        scan.subdomains = subfinder_results.get(domain, [])

        # DNS records (from dnsx — primary domain only)
        scan.dns_records = dnsx_results.get(domain, {})

        # CT certificates (from crt.sh)
        scan.ct_certificates = crt_sh_results.get(domain, [])

        # Cloud storage exposure (from GrayHatWarfare)
        scan.exposed_cloud_storage = ghw_results.get(domain, [])

        results[domain] = scan

        if i % 25 == 0:
            log.info("Scanned %d/%d domains", i, len(allowed_domains))

    end_time = datetime.now(timezone.utc)

    # --- Post-scan notification ---
    print_run_summary(results, skipped_domains, start_time, end_time)
    summary_path = write_run_summary(
        results, skipped_domains, allowed_domains, pre_scan_path,
        "interactive" if not confirmed else "--confirmed flag",
        start_time, end_time, approvals_data,
    )

    log.info(
        "Layer 1 scanning complete: %d domains scanned, %d skipped (robots.txt)",
        len(results), len(skipped_domains),
    )
    log.info("Run summary: %s", summary_path)
    return results
