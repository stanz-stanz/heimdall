"""Execute a single-domain scan job using cached + fresh scan results.

Orchestrates all Layer 1 scan types for one domain, checking the Redis cache
before each scan and storing fresh results back.  Returns a result dict with
scan data, timing breakdown, and cache statistics.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from src.prospecting.brief_generator import generate_brief, _determine_gdpr_sensitivity
from src.prospecting.bucketer import classify
from src.prospecting.config import CMS_KEYWORDS, HOSTING_PROVIDERS
from src.prospecting.cvr import Company
from src.prospecting.scanner import (
    ScanResult,
    _check_robots_txt,
    _check_ssl,
    _extract_page_meta,
    _get_response_headers,
    _query_grayhatwarfare,
    _run_dnsx,
    _run_httpx,
    _run_nuclei,
    _run_subfinder,
    _run_webanalyze,
    _run_wpscan,
)
from src.ct_collector.db import open_readonly, query_certificates

from .cache import ScanCache

log = logging.getLogger(__name__)

# Path to the local CT database (set via CT_DB_PATH env var or --ct-db arg)
_CT_DB_PATH: str = os.environ.get("CT_DB_PATH", "/data/ct/certificates.db")


def _query_local_ct(domain: str) -> tuple:
    """Query the local CT SQLite database for certificates matching *domain*.

    Returns ``(domain, certs_list)`` in the same format as
    ``_query_crt_sh_single`` for backward compatibility with cache unpacking
    on lines 191-199.

    Degrades gracefully: if the database is missing or unreadable, returns
    ``(domain, [])``.
    """
    if not os.path.isfile(_CT_DB_PATH):
        log.debug("ct_db_not_found", extra={"context": {"path": _CT_DB_PATH}})
        return domain, []

    try:
        conn = open_readonly(_CT_DB_PATH)
        try:
            certs = query_certificates(conn, domain, include_expired=False)
            return domain, certs
        finally:
            conn.close()
    except Exception as exc:
        log.debug("ct_db_query_failed", extra={"context": {"domain": domain, "error": str(exc)}})
        return domain, []


def _timed(fn: Any, *args: Any, **kwargs: Any) -> Tuple[Any, float]:
    """Call *fn* and return ``(result, elapsed_seconds)``."""
    t0 = time.monotonic()
    result = fn(*args, **kwargs)
    return result, time.monotonic() - t0


def execute_scan_job(job: dict, cache: ScanCache) -> dict:
    """Execute all Layer 1 scan types for a single domain.

    Parameters
    ----------
    job:
        Scan job dict with at least ``domain``.  May also contain
        ``client_id``, ``tier``, ``layer``, ``level``, ``job_id``.
    cache:
        :class:`ScanCache` instance for checking / storing cached results.

    Returns
    -------
    dict
        Keys: ``domain``, ``status``, ``scan_result`` (dict), ``timing``
        (per-scan-type seconds), ``cache_stats`` (hits / misses for this job).
    """
    domain: str = job.get("domain", "")
    job_id: str = job.get("job_id", "")

    job_t0 = time.monotonic()
    timing: Dict[str, float] = {}
    job_hits = 0
    job_misses = 0

    # ------------------------------------------------------------------
    # 1. robots.txt — always checked fresh, never cached
    # ------------------------------------------------------------------
    robots_allowed, robots_dt = _timed(_check_robots_txt, domain)
    timing["robots_txt"] = round(robots_dt, 4)

    if not robots_allowed:
        log.info(
            "domain_skipped",
            extra={"context": {"domain": domain, "reason": "robots.txt denied"}},
        )
        return {
            "domain": domain,
            "job_id": job_id,
            "status": "skipped",
            "skip_reason": "robots.txt denied",
            "scan_result": None,
            "timing": timing,
            "cache_stats": {"hits": 0, "misses": 0},
        }

    # ------------------------------------------------------------------
    # 2. Per-scan-type: check cache, run if miss, store result
    # ------------------------------------------------------------------

    def _cached_or_run(
        scan_type: str, fn: Any, *args: Any
    ) -> Any:
        nonlocal job_hits, job_misses
        cached = cache.get(scan_type, domain)
        if cached is not None:
            job_hits += 1
            log.debug("cache_hit", extra={"context": {"domain": domain, "scan_type": scan_type}})
            return cached
        job_misses += 1
        result, dt = _timed(fn, *args)
        timing[scan_type] = round(dt, 4)
        # Normalise result to a JSON-serialisable dict/list for caching
        serialisable = result
        if isinstance(result, tuple):
            serialisable = list(result)
        cache.set(scan_type, domain, serialisable)
        log.info(
            "scan_type_complete",
            extra={"context": {"domain": domain, "scan_type": scan_type, "duration_ms": int(dt * 1000)}},
        )
        return result

    # --- individual per-domain scans ---
    ssl_info = _cached_or_run("ssl", _check_ssl, domain)
    headers = _cached_or_run("headers", _get_response_headers, domain)
    meta_raw = _cached_or_run("meta", _extract_page_meta, domain)

    # meta comes back as tuple/list (meta_author, footer_credit, plugins)
    if isinstance(meta_raw, (list, tuple)) and len(meta_raw) == 3:
        meta_author, footer_credit, plugins = meta_raw
    else:
        meta_author, footer_credit, plugins = "", "", []

    # --- batch-style tools called with single-domain list ---
    httpx_results = _cached_or_run("httpx", _run_httpx, [domain])
    webanalyze_results = _cached_or_run("webanalyze", _run_webanalyze, [domain])
    subfinder_results = _cached_or_run("subfinder", _run_subfinder, [domain])
    dnsx_results = _cached_or_run("dnsx", _run_dnsx, [domain])

    # --- API queries ---
    crtsh_raw = _cached_or_run("crtsh", _query_local_ct, domain)
    ghw_results = _cached_or_run("ghw", _query_grayhatwarfare, [domain])

    # ------------------------------------------------------------------
    # 3. Assemble ScanResult
    # ------------------------------------------------------------------
    scan = ScanResult(domain=domain)

    # SSL
    if isinstance(ssl_info, dict):
        scan.ssl_valid = ssl_info.get("valid", False)
        scan.ssl_issuer = ssl_info.get("issuer", "")
        scan.ssl_expiry = ssl_info.get("expiry", "")
        scan.ssl_days_remaining = ssl_info.get("days_remaining", -1)

    # Headers
    if isinstance(headers, dict):
        scan.headers = headers

    # Page meta
    scan.meta_author = meta_author if isinstance(meta_author, str) else ""
    scan.footer_credit = footer_credit if isinstance(footer_credit, str) else ""
    if isinstance(plugins, list):
        scan.detected_plugins = plugins

    # httpx
    httpx_data: dict = {}
    if isinstance(httpx_results, dict):
        httpx_data = httpx_results.get(domain, {})
    if httpx_data:
        scan.raw_httpx = httpx_data
        scan.server = httpx_data.get("webserver", "")
        tech = httpx_data.get("tech", [])
        if tech:
            scan.tech_stack.extend(tech)

    # webanalyze
    wa_techs: List[str] = []
    if isinstance(webanalyze_results, dict):
        wa_techs = webanalyze_results.get(domain, [])
    if wa_techs:
        scan.tech_stack.extend(wa_techs)

    # Deduplicate tech stack
    scan.tech_stack = list(dict.fromkeys(scan.tech_stack))

    # Subdomains
    if isinstance(subfinder_results, dict):
        scan.subdomains = subfinder_results.get(domain, [])

    # DNS
    if isinstance(dnsx_results, dict):
        scan.dns_records = dnsx_results.get(domain, {})

    # crt.sh — returns (domain, certs_list) or cached list
    if isinstance(crtsh_raw, (list, tuple)):
        if len(crtsh_raw) == 2 and isinstance(crtsh_raw[0], str):
            # Fresh call: (domain, certs)
            scan.ct_certificates = crtsh_raw[1] if isinstance(crtsh_raw[1], list) else []
        else:
            # Cached: already the list (was serialised as list from tuple)
            scan.ct_certificates = list(crtsh_raw)
    elif isinstance(crtsh_raw, dict):
        scan.ct_certificates = []

    # GrayHatWarfare
    if isinstance(ghw_results, dict):
        scan.exposed_cloud_storage = ghw_results.get(domain, [])

    # ------------------------------------------------------------------
    # 3b. Level 1 scans (active probing — only when job.level >= 1)
    # ------------------------------------------------------------------
    level1_scan_result: Optional[dict] = None
    job_level = job.get("level", 0)

    if isinstance(job_level, int) and not isinstance(job_level, bool) and job_level >= 1:
        nuclei_results = _cached_or_run("nuclei", _run_nuclei, [domain])
        wpscan_results = _cached_or_run("wpscan", _run_wpscan, [domain])

        nuclei_data: dict = {}
        if isinstance(nuclei_results, dict):
            nuclei_data = nuclei_results.get(domain, {"findings": [], "finding_count": 0})

        wpscan_data: dict = {}
        if isinstance(wpscan_results, dict):
            wpscan_data = wpscan_results.get(domain, {"vulnerabilities": [], "wordpress": {}, "plugins": [], "themes": []})

        level1_scan_result = {
            "nuclei": nuclei_data,
            "wpscan": wpscan_data,
        }

        log.info(
            "level1_scans_complete",
            extra={"context": {
                "domain": domain,
                "job_id": job_id,
                "nuclei_findings": len(nuclei_data.get("findings", [])),
                "wpscan_vulns": len(wpscan_data.get("vulnerabilities", [])),
                "wpscan_plugins": len(wpscan_data.get("plugins", [])),
            }},
        )

    # ------------------------------------------------------------------
    # 4. Derive CMS and hosting (same logic as scanner.py)
    # ------------------------------------------------------------------
    for tech in scan.tech_stack:
        for keyword, cms_name in CMS_KEYWORDS.items():
            if keyword in tech.lower():
                scan.cms = cms_name
                break
        if scan.cms:
            break

    combined = (scan.server + " " + " ".join(scan.tech_stack)).lower()
    for hint, provider in HOSTING_PROVIDERS.items():
        if hint in combined and provider:
            scan.hosting = provider
            break

    # ------------------------------------------------------------------
    # 5. Generate findings + GDPR determination
    # ------------------------------------------------------------------
    # Build a minimal Company for brief generation
    company = Company(
        cvr=job.get("client_id", "prospect"),
        name=job.get("company_name", domain),
        address="", postcode="", city="",
        company_form="", industry_code=job.get("industry_code", ""),
        industry_name=job.get("industry_name", ""),
        phone="", email="",
        ad_protected=False,
        website_domain=domain,
        discard_reason="",
    )
    bucket = classify(company, scan)
    brief = generate_brief(company, scan, bucket)

    # ------------------------------------------------------------------
    # 6. Build return dict
    # ------------------------------------------------------------------
    total_ms = int((time.monotonic() - job_t0) * 1000)
    # Convert all timing values to ms (int)
    timing_ms = {k: int(v * 1000) if isinstance(v, float) else v for k, v in timing.items()}
    timing_ms["total_ms"] = total_ms

    log.info(
        "domain_scan_complete",
        extra={
            "context": {
                "domain": domain,
                "job_id": job_id,
                "duration_ms": total_ms,
                "cache_hits": job_hits,
                "cache_misses": job_misses,
                "findings_count": len(brief.get("findings", [])),
            },
        },
    )

    result = {
        "domain": domain,
        "job_id": job_id,
        "status": "completed",
        "scan_result": asdict(scan),
        "brief": brief,
        "timing": timing_ms,
        "cache_stats": {"hits": job_hits, "misses": job_misses},
    }
    if level1_scan_result is not None:
        result["level1_scan_result"] = level1_scan_result
    return result
