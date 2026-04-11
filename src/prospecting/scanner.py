"""Layer 1 scanner: passive technology fingerprinting via httpx and webanalyze.

Uses ThreadPoolExecutor for concurrent I/O. Designed to scale to thousands of domains.

Individual scan-tool functions have been extracted to ``src.prospecting.scanners.*``
and are re-exported here under their original underscore-prefixed names so that
existing consumers (tests, worker, benchmark) continue to work unchanged.
"""

from __future__ import annotations

import json  # noqa: F401 — re-export for test patches
import os  # noqa: F401 — re-export for test patches
import re  # noqa: F401 — re-export for test patches
import shutil  # noqa: F401 — re-export for test patches
import socket  # noqa: F401 — re-export for test patches
import ssl  # noqa: F401 — re-export for test patches
import subprocess  # noqa: F401 — re-export for test patches
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import requests  # noqa: F401 — re-export for test patches
from loguru import logger

# Concurrency settings — tune based on network capacity and target politeness
MAX_WORKERS_HTTP = 20    # for SSL, headers, meta, robots.txt
MAX_WORKERS_API = 5      # for rate-limited APIs (crt.sh, GrayHatWarfare)

from .config import REQUEST_TIMEOUT, USER_AGENT
from .cvr import Company
from .scanners.compliance import _write_pre_scan_check
from .scanners.models import ScanResult
from .scanners.registry import (
    _LEVEL0_SCAN_FUNCTIONS,
    _LEVEL1_SCAN_FUNCTIONS,
    _SCAN_TYPE_FUNCTIONS,
    _init_scan_type_map,
    _validate_approval_tokens,
)

# ---------------------------------------------------------------------------
# Re-exports from extracted scanner modules (preserve underscore-prefixed API)
# ---------------------------------------------------------------------------
from .scanners.tls import check_ssl as _check_ssl  # noqa: F401
from .scanners.headers import get_response_headers as _get_response_headers  # noqa: F401
from .scanners.robots import check_robots_txt as _check_robots_txt  # noqa: F401
from .scanners.httpx_scan import run_httpx as _run_httpx  # noqa: F401
from .scanners.webanalyze import run_webanalyze as _run_webanalyze  # noqa: F401
from .scanners.subfinder import run_subfinder as _run_subfinder  # noqa: F401
from .scanners.dnsx import run_dnsx as _run_dnsx  # noqa: F401
from .scanners.ct import (  # noqa: F401
    query_crt_sh_single as _query_crt_sh_single,
    query_crt_sh as _query_crt_sh,
)
from .scanners.grayhat import query_grayhatwarfare as _query_grayhatwarfare  # noqa: F401
from .scanners.nuclei import run_nuclei as _run_nuclei  # noqa: F401
from .scanners.cmseek import run_cmseek as _run_cmseek  # noqa: F401
from .scanners.nmap import (  # noqa: F401
    parse_nmap_xml as _parse_nmap_xml,
    nmap_ports_to_findings as _nmap_ports_to_findings,
    run_nmap as _run_nmap,
)
from .scanners.wordpress import (  # noqa: F401
    extract_page_meta as _extract_page_meta,
    extract_rest_api_plugins as _extract_rest_api_plugins,
)

# Re-export constants that were previously module-level here, so that
# consumers patching e.g. ``scanner.NUCLEI_TIMEOUT`` still work.
from .scanners.nuclei import NUCLEI_RATE_LIMIT, NUCLEI_CONCURRENCY, NUCLEI_TIMEOUT  # noqa: F401
from .scanners.cmseek import CMSEEK_TIMEOUT, CMSEEK_PATH  # noqa: F401
from .scanners.nmap import (  # noqa: F401
    NMAP_TIMEOUT,
    NMAP_TOP_PORTS,
    NMAP_SUPPLEMENT_PORTS,
    _NMAP_PORT_SEVERITY,
    _NMAP_PORT_LABELS,
)
from .scanners.cmseek import _DOMAIN_RE  # noqa: F401
from .scanners.wordpress import (  # noqa: F401
    _NAMESPACE_TO_SLUG,
    _GENERATOR_TO_SLUG,
    _CSS_CLASS_SIGNATURES,
)


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
        logger.error("BLOCKED — Valdi approval token validation failed. No scans will execute.")
        return {}

    active = [c for c in companies if not c.discarded and c.website_domain]
    domains = list(set(c.website_domain for c in active))
    logger.info("Scanning {} unique domains (Layer 1 passive only)", len(domains))

    # robots.txt pre-filter — BEFORE any scanning activity (concurrent)
    allowed_domains = []
    skipped_domains = []
    logger.info("Checking robots.txt for {} domains (concurrent, {} workers)", len(domains), MAX_WORKERS_HTTP)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_HTTP) as executor:
        futures = {executor.submit(_check_robots_txt, d): d for d in domains}
        for future in as_completed(futures):
            domain = futures[future]
            try:
                if future.result():
                    allowed_domains.append(domain)
                else:
                    skipped_domains.append(domain)
                    logger.info("SKIPPED {} — robots.txt denies automated access", domain)
            except Exception as e:
                allowed_domains.append(domain)  # fail-open: can't check = no restriction
                logger.debug("robots.txt check error for {}: {}", domain, e)

    if skipped_domains:
        logger.info(
            "robots.txt filter: {} allowed, {} skipped",
            len(allowed_domains), len(skipped_domains),
        )

    if not allowed_domains:
        logger.warning("No domains passed robots.txt filter — nothing to scan")
        return {}

    # Write pre-scan compliance check (Gate 2 batch check)
    pre_scan_path = _write_pre_scan_check(allowed_domains, skipped_domains)
    logger.info("Pre-scan check: {}", pre_scan_path)

    # --- Operator notification ---
    print_gate1_summary(approvals_data)
    print_pre_scan_summary(
        allowed_domains, skipped_domains,
        list(_SCAN_TYPE_FUNCTIONS.keys()), approvals_data,
    )

    # --- Hard confirmation gate ---
    if not confirmed:
        if not prompt_confirmation(len(allowed_domains)):
            logger.info("ABORTED — Operator declined confirmation. No scans executed.")
            return {}

    start_time = datetime.now(UTC)

    # Batch scans with CLI tools — only robots.txt-allowed domains
    httpx_results = _run_httpx(allowed_domains)
    webanalyze_results = _run_webanalyze(allowed_domains)

    # --- Concurrent enrichment tools (run in parallel with CLI batch scans) ---
    # subfinder and dnsx are CLI batch tools — run sequentially but fast
    subfinder_results = _run_subfinder(allowed_domains)

    # crt.sh and GrayHatWarfare are API queries — run concurrently with rate limiting
    logger.info("Querying APIs concurrently (crt.sh, GrayHatWarfare) for {} domains", len(allowed_domains))
    crt_sh_results = _query_crt_sh(allowed_domains)
    ghw_results = _query_grayhatwarfare(allowed_domains)

    # DNS enrichment: primary domains + discovered subdomains
    all_dns_targets = set(allowed_domains)
    for subs in subfinder_results.values():
        all_dns_targets.update(subs)
    dnsx_results = _run_dnsx(list(all_dns_targets))

    # --- Concurrent per-domain scanning (SSL, headers, meta) ---
    from .config import CMS_KEYWORDS, HOSTING_PROVIDERS

    def _scan_single_domain(domain: str) -> ScanResult:
        """Scan a single domain — designed to run in a thread pool."""
        domain_t0 = time.monotonic()
        scan = ScanResult(domain=domain)

        # SSL check
        t0 = time.monotonic()
        ssl_info = _check_ssl(domain)
        logger.bind(context={"domain": domain, "scan_type": "ssl", "duration_ms": int((time.monotonic() - t0) * 1000)}).info("scan_type_complete")
        scan.ssl_valid = ssl_info["valid"]
        scan.ssl_issuer = ssl_info["issuer"]
        scan.ssl_expiry = ssl_info["expiry"]
        scan.ssl_days_remaining = ssl_info["days_remaining"]
        scan.tls_version = ssl_info.get("tls_version", "")
        scan.tls_cipher = ssl_info.get("tls_cipher", "")
        scan.tls_bits = ssl_info.get("tls_bits", 0)

        # Response headers
        t0 = time.monotonic()
        scan.headers = _get_response_headers(domain)
        logger.bind(context={"domain": domain, "scan_type": "headers", "duration_ms": int((time.monotonic() - t0) * 1000)}).info("scan_type_complete")

        # Page meta extraction (author, footer credit, plugins)
        t0 = time.monotonic()
        meta_author, footer_credit, plugins = _extract_page_meta(domain)
        logger.bind(context={"domain": domain, "scan_type": "page_meta", "duration_ms": int((time.monotonic() - t0) * 1000)}).info("scan_type_complete")
        scan.meta_author = meta_author
        scan.footer_credit = footer_credit
        if plugins:
            scan.detected_plugins = plugins

        # httpx results (from batch)
        httpx_data = httpx_results.get(domain, {})
        if httpx_data:
            scan.raw_httpx = httpx_data
            scan.server = httpx_data.get("webserver", "")
            tech = httpx_data.get("tech", [])
            if tech:
                scan.tech_stack.extend(tech)

        # webanalyze results (from batch)
        wa_techs = webanalyze_results.get(domain, [])
        if wa_techs:
            scan.tech_stack.extend(wa_techs)

        # Deduplicate tech stack
        scan.tech_stack = list(dict.fromkeys(scan.tech_stack))

        # Derive CMS from tech stack
        for tech in scan.tech_stack:
            for keyword, cms_name in CMS_KEYWORDS.items():
                if keyword in tech.lower():
                    scan.cms = cms_name
                    break
            if scan.cms:
                break

        # Derive hosting from server header and tech stack
        combined = (scan.server + " " + " ".join(scan.tech_stack)).lower()
        for hint, provider in HOSTING_PROVIDERS.items():
            if hint in combined and provider:
                scan.hosting = provider
                break

        # Enrichment data (from batch results)
        scan.subdomains = subfinder_results.get(domain, [])
        scan.dns_records = dnsx_results.get(domain, {})
        scan.ct_certificates = crt_sh_results.get(domain, [])
        scan.exposed_cloud_storage = ghw_results.get(domain, [])

        total_ms = int((time.monotonic() - domain_t0) * 1000)
        findings_count = len(scan.tech_stack) + len(scan.subdomains) + len(scan.ct_certificates) + len(scan.exposed_cloud_storage)
        logger.bind(context={"domain": domain, "duration_ms": total_ms, "findings_count": findings_count}).info("domain_scan_complete")

        return scan

    results: dict[str, ScanResult] = {}
    logger.info("Scanning {} domains concurrently ({} workers)", len(allowed_domains), MAX_WORKERS_HTTP)
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_HTTP) as executor:
        futures = {executor.submit(_scan_single_domain, d): d for d in allowed_domains}
        for future in as_completed(futures):
            domain = futures[future]
            try:
                results[domain] = future.result()
            except Exception as e:
                logger.warning("Scan failed for {}: {}", domain, e)
            completed += 1
            if completed % 50 == 0:
                logger.info("Scanned {}/{} domains", completed, len(allowed_domains))

    end_time = datetime.now(UTC)

    # --- Post-scan notification ---
    print_run_summary(results, skipped_domains, start_time, end_time)
    summary_path = write_run_summary(
        results, skipped_domains, allowed_domains, pre_scan_path,
        "interactive" if not confirmed else "--confirmed flag",
        start_time, end_time, approvals_data,
    )

    logger.info(
        "Layer 1 scanning complete: {} domains scanned, {} skipped (robots.txt)",
        len(results), len(skipped_domains),
    )
    logger.info("Run summary: {}", summary_path)
    return results
