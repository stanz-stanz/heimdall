"""Scan orchestrator: batch scanning of domains with concurrent enrichment.

Moved from ``src.prospecting.scanner`` (P2-4).  The top-level
``scan_domains()`` function validates Valdi approval tokens, filters
domains through robots.txt, runs batch CLI tools, then fans out per-domain
scanning (SSL, headers, page-meta) across a thread pool.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from loguru import logger

from src.prospecting.config import CMS_KEYWORDS, HOSTING_PROVIDERS
from src.prospecting.cvr import Company
from src.valdi import GateDeniedError, ScanRequest, gate_or_raise, gated_execution, get_gate_execution_context
from src.valdi.envelope import validate_and_persist_envelope

from .compliance import _write_pre_scan_check
from .models import ScanResult
from .registry import (
    _SCAN_TYPE_FUNCTIONS,
    _init_scan_type_map,
)

from .robots import check_robots_txt
from .ct import query_crt_sh
from .dnsx import run_dnsx
from .grayhat import query_grayhatwarfare
from .headers import get_response_headers
from .httpx_scan import run_httpx
from .subfinder import run_subfinder
from .tls import check_ssl
from .webanalyze import run_webanalyze
from .wordpress import extract_page_meta

SSL_SCAN = "ssl_certificate_check"
META_SCAN = "homepage_meta_extraction"
HTTPX_SCAN = "httpx_tech_fingerprint"
WEBANALYZE_SCAN = "webanalyze_cms_detection"
HEADERS_SCAN = "response_header_check"
SUBFINDER_SCAN = "subdomain_enumeration_passive"
DNS_SCAN = "dns_enrichment"
CT_SCAN = "certificate_transparency_query"
CLOUD_SCAN = "cloud_storage_index_query"


def _run_scan_impl(scan_type: str, *args):
    ctx = get_gate_execution_context()
    if ctx is None:
        raise RuntimeError(f"Registered scan {scan_type} executed without Valdi gate context")
    if scan_type not in ctx.decision.allowed_scan_types:
        raise RuntimeError(f"Registered scan {scan_type} not authorised by current Valdi decision")
    dispatch = {
        SSL_SCAN: check_ssl,
        META_SCAN: extract_page_meta,
        HTTPX_SCAN: run_httpx,
        WEBANALYZE_SCAN: run_webanalyze,
        HEADERS_SCAN: get_response_headers,
        SUBFINDER_SCAN: run_subfinder,
        DNS_SCAN: run_dnsx,
        CT_SCAN: query_crt_sh,
        CLOUD_SCAN: query_grayhatwarfare,
    }
    return dispatch[scan_type](*args)

# Concurrency settings — tune based on network capacity and target politeness
MAX_WORKERS_HTTP = 20  # for SSL, headers, meta, robots.txt


def _scan_single_domain(
    domain: str,
    *,
    httpx_results: dict,
    webanalyze_results: dict,
    subfinder_results: dict,
    dnsx_results: dict,
    crt_sh_results: dict,
    ghw_results: dict,
) -> ScanResult:
    """Scan a single domain — designed to run in a thread pool.

    Formerly an inner closure of ``scan_domains``; extracted as a regular
    function that receives batch results via keyword arguments.
    """
    domain_t0 = time.monotonic()
    scan = ScanResult(domain=domain)

    # SSL check
    t0 = time.monotonic()
    ssl_info = _run_scan_impl(SSL_SCAN, domain)
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
    scan.headers = _run_scan_impl(HEADERS_SCAN, domain)
    logger.bind(context={"domain": domain, "scan_type": "headers", "duration_ms": int((time.monotonic() - t0) * 1000)}).info("scan_type_complete")

    # Page meta extraction (author, footer credit, plugins, plugin_versions, themes)
    t0 = time.monotonic()
    meta_author, footer_credit, plugins, plugin_versions, themes = _run_scan_impl(META_SCAN, domain)
    logger.bind(context={"domain": domain, "scan_type": "page_meta", "duration_ms": int((time.monotonic() - t0) * 1000)}).info("scan_type_complete")
    scan.meta_author = meta_author
    scan.footer_credit = footer_credit
    if plugins:
        scan.detected_plugins = plugins
    if plugin_versions:
        scan.plugin_versions = plugin_versions
    if themes:
        scan.detected_themes = themes

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

    # Merge SAN hostnames from CT certs into subdomains (free enrichment)
    domain_lower = domain.lower()
    suffix = "." + domain_lower
    existing_subs = {s.lower() for s in scan.subdomains}
    san_additions: list[str] = []
    for cert in scan.ct_certificates:
        for san in cert.get("sans", []) or []:
            host = san.lstrip("*.").lower()
            if not host or host in existing_subs:
                continue
            if host == domain_lower or host.endswith(suffix):
                existing_subs.add(host)
                san_additions.append(host)
    if san_additions:
        scan.subdomains.extend(san_additions)

    total_ms = int((time.monotonic() - domain_t0) * 1000)
    findings_count = len(scan.tech_stack) + len(scan.subdomains) + len(scan.ct_certificates) + len(scan.exposed_cloud_storage)
    logger.bind(context={"domain": domain, "duration_ms": total_ms, "findings_count": findings_count}).info("domain_scan_complete")

    return scan


def scan_domains(companies: list[Company], confirmed: bool = False) -> dict[str, ScanResult]:
    """Layer 1 / Level 0 — Run passive technology fingerprinting on all non-discarded companies.

    Validates Valdi approval tokens and function hashes before execution.
    Filters domains through robots.txt before any scanning activity.
    Requires operator confirmation unless confirmed=True.
    Returns dict keyed by domain.
    """
    from src.prospecting.operator import (
        print_gate1_summary,
        print_pre_scan_summary,
        print_run_summary,
        prompt_confirmation,
        write_run_summary,
    )

    _init_scan_type_map()

    envelope = validate_and_persist_envelope(0, surface="runner")
    approvals_data = {"approvals": [{"scan_type_id": sid, "token": info.approval_token} for sid, info in envelope.scan_types.items()]}

    active = [c for c in companies if not c.discarded and c.website_domain]
    domains = list(set(c.website_domain for c in active))
    logger.info("Scanning {} unique domains (Layer 1 passive only)", len(domains))

    # robots.txt pre-filter — BEFORE any scanning activity (concurrent)
    allowed_domains = []
    skipped_domains = []
    logger.info("Checking robots.txt for {} domains (concurrent, {} workers)", len(domains), MAX_WORKERS_HTTP)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_HTTP) as executor:
        futures = {executor.submit(check_robots_txt, d): d for d in domains}
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

    try:
        decision = gate_or_raise(
            ScanRequest(
                surface="runner",
                scan_type="passive_domain_scan_orchestrator",
                requested_level=0,
                domains=tuple(sorted(allowed_domains)),
                confirmed=True,
                envelope=envelope,
            )
        )
    except GateDeniedError as exc:
        logger.error("BLOCKED — Valdi gate denied runner execution: {}", exc)
        return {}

    start_time = datetime.now(UTC)

    with gated_execution(decision):
        # Batch scans with CLI tools — only robots.txt-allowed domains
        httpx_results = _run_scan_impl(HTTPX_SCAN, allowed_domains)
        webanalyze_results = _run_scan_impl(WEBANALYZE_SCAN, allowed_domains)

        # --- Concurrent enrichment tools (run in parallel with CLI batch scans) ---
        # subfinder and dnsx are CLI batch tools — run sequentially but fast
        subfinder_results = _run_scan_impl(SUBFINDER_SCAN, allowed_domains)

        # crt.sh and GrayHatWarfare are API queries — run concurrently with rate limiting
        logger.info("Querying APIs concurrently (crt.sh, GrayHatWarfare) for {} domains", len(allowed_domains))
        crt_sh_results = _run_scan_impl(CT_SCAN, allowed_domains)
        ghw_results = _run_scan_impl(CLOUD_SCAN, allowed_domains)

        # DNS enrichment: primary domains + discovered subdomains
        all_dns_targets = set(allowed_domains)
        for subs in subfinder_results.values():
            all_dns_targets.update(subs)
        dnsx_results = _run_scan_impl(DNS_SCAN, list(all_dns_targets))

        # --- Concurrent per-domain scanning (SSL, headers, meta) ---
        results: dict[str, ScanResult] = {}
        logger.info("Scanning {} domains concurrently ({} workers)", len(allowed_domains), MAX_WORKERS_HTTP)
        completed = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS_HTTP) as executor:
            futures = {
                executor.submit(
                    _scan_single_domain,
                    d,
                    httpx_results=httpx_results,
                    webanalyze_results=webanalyze_results,
                    subfinder_results=subfinder_results,
                    dnsx_results=dnsx_results,
                    crt_sh_results=crt_sh_results,
                    ghw_results=ghw_results,
                ): d
                for d in allowed_domains
            }
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    results[domain] = future.result()
                except Exception as e:
                    logger.opt(exception=True).warning("Scan failed for {}: {}", domain, e)
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
