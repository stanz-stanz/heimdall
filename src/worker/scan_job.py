"""Execute a single-domain scan job using cached + fresh scan results.

Orchestrates all Layer 1 scan types for one domain, checking the Redis cache
before each scan and storing fresh results back.  Returns a result dict with
scan data, timing breakdown, and cache statistics.
"""

from __future__ import annotations

import functools
import json
import os
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

import redis
from loguru import logger

from src.prospecting.brief_generator import generate_brief, _determine_gdpr_sensitivity
from src.prospecting.bucketer import classify
from src.prospecting.config import CMS_KEYWORDS, HOSTING_PROVIDERS, DEFAULT_FILTERS
from src.prospecting.cvr import Company
from src.prospecting.filters import load_filters
from src.prospecting.scanner import (
    ScanResult,
    _check_robots_txt,
    _check_ssl,
    _extract_page_meta,
    _get_response_headers,
    _query_grayhatwarfare,
    _run_dnsx,
    _run_httpx,
    _run_cmseek,
    _run_nuclei,
    _run_subfinder,
    _run_webanalyze,
)
from src.ct_collector.db import open_readonly, query_certificates

from .cache import ScanCache

# Load bucket filter once at import time
_filters = load_filters(DEFAULT_FILTERS)
_BUCKET_FILTER = None
_bucket_raw = _filters.get("bucket")
if _bucket_raw:
    _BUCKET_FILTER = {b.upper() for b in _bucket_raw}

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
        logger.bind(context={"path": _CT_DB_PATH}).debug("ct_db_not_found")
        return domain, []

    try:
        conn = open_readonly(_CT_DB_PATH)
        try:
            certs = query_certificates(conn, domain, include_expired=False)
            return domain, certs
        finally:
            conn.close()
    except Exception as exc:
        logger.bind(context={"domain": domain, "error": str(exc)}).debug("ct_db_query_failed")
        return domain, []


def _timed(fn: Any, *args: Any, **kwargs: Any) -> Tuple[Any, float]:
    """Call *fn* and return ``(result, elapsed_seconds)``."""
    t0 = time.monotonic()
    result = fn(*args, **kwargs)
    return result, time.monotonic() - t0


def _extract_wp_version(tech_stack: list) -> Optional[str]:
    """Extract WordPress core version from tech_stack entries like 'WordPress:6.9.4'."""
    for tech in tech_stack:
        if isinstance(tech, str) and tech.lower().startswith("wordpress:"):
            return tech.split(":", 1)[1]
    return None


@functools.lru_cache(maxsize=1)
def _get_slug_map() -> dict:
    """Load plugin display-name → slug mapping (cached for process lifetime)."""
    try:
        from tools.twin.templates import load_slug_map
        return load_slug_map()
    except Exception:
        return {}


def _merge_tech_stack_plugins(scan: ScanResult) -> None:
    """Merge WordPress plugins detected in tech_stack into detected_plugins + plugin_versions.

    Tech tools (httpx, webanalyze) detect plugins like "Yoast SEO:26.9" in tech_stack.
    This function uses slug_map.json to identify WP plugins and merge them with
    HTML-detected plugins from _extract_page_meta.
    """
    slug_map = _get_slug_map()

    existing_slugs = set(scan.detected_plugins)
    for tech_entry in scan.tech_stack:
        if ":" in tech_entry:
            name, version = tech_entry.split(":", 1)
        else:
            name, version = tech_entry, ""
        name = name.strip()
        slug = slug_map.get(name)
        if slug is None:
            continue  # null in slug_map = not a WP plugin
        if slug not in existing_slugs:
            existing_slugs.add(slug)
            scan.detected_plugins.append(slug)
        if version.strip() and slug not in scan.plugin_versions:
            scan.plugin_versions[slug] = version.strip()


def execute_scan_job(
    job: dict,
    cache: ScanCache,
    redis_conn: Optional[redis.Redis] = None,
) -> dict:
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
        logger.bind(context={"domain": domain, "reason": "robots.txt denied"}).info("domain_skipped")
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
            logger.bind(context={"domain": domain, "scan_type": scan_type}).debug("cache_hit")
            return cached
        job_misses += 1
        result, dt = _timed(fn, *args)
        timing[scan_type] = round(dt, 4)
        # Normalise result to a JSON-serialisable dict/list for caching
        serialisable = result
        if isinstance(result, tuple):
            serialisable = list(result)
        cache.set(scan_type, domain, serialisable)
        logger.bind(context={"domain": domain, "scan_type": scan_type, "duration_ms": int(dt * 1000)}).info("scan_type_complete")
        return result

    # --- individual per-domain scans ---
    ssl_info = _cached_or_run("ssl", _check_ssl, domain)
    headers = _cached_or_run("headers", _get_response_headers, domain)
    meta_raw = _cached_or_run("meta", _extract_page_meta, domain)

    # meta comes back as tuple/list:
    # New: (meta_author, footer_credit, plugins, plugin_versions, themes)
    # Old cached: (meta_author, footer_credit, plugins)
    html_plugin_versions: dict = {}
    themes: list = []
    if isinstance(meta_raw, (list, tuple)):
        if len(meta_raw) >= 5:
            meta_author, footer_credit, plugins = meta_raw[0], meta_raw[1], meta_raw[2]
            html_plugin_versions = meta_raw[3] if isinstance(meta_raw[3], dict) else {}
            themes = meta_raw[4] if isinstance(meta_raw[4], list) else []
        elif len(meta_raw) == 3:
            meta_author, footer_credit, plugins = meta_raw
        else:
            meta_author, footer_credit, plugins = "", "", []
    else:
        meta_author, footer_credit, plugins = "", "", []

    # --- batch-style tools for tech detection (cheap) ---
    httpx_results = _cached_or_run("httpx", _run_httpx, [domain])
    webanalyze_results = _cached_or_run("webanalyze", _run_webanalyze, [domain])

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
    scan.plugin_versions = html_plugin_versions
    scan.detected_themes = themes

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

    # Merge tech_stack-detected WordPress plugins into detected_plugins
    _merge_tech_stack_plugins(scan)

    # ------------------------------------------------------------------
    # 3b. Derive CMS and hosting (early — needed for bucket filter)
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
    # 3c. Bucket filter — skip expensive scans for unwanted buckets
    # ------------------------------------------------------------------
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

    if _BUCKET_FILTER and bucket not in _BUCKET_FILTER:
        total_ms = int((time.monotonic() - job_t0) * 1000)
        logger.bind(context={
            "domain": domain, "bucket": bucket,
            "allowed_buckets": sorted(_BUCKET_FILTER),
            "duration_ms": total_ms,
        }).info("domain_filtered")
        brief = generate_brief(company, scan, bucket)
        timing_ms = {k: int(v * 1000) if isinstance(v, float) else v for k, v in timing.items()}
        timing_ms["total_ms"] = total_ms
        return {
            "domain": domain,
            "job_id": job_id,
            "status": "completed",
            "scan_result": asdict(scan),
            "brief": brief,
            "timing": timing_ms,
            "cache_stats": {"hits": job_hits, "misses": job_misses},
            "filtered": f"bucket:{bucket}",
        }

    # ------------------------------------------------------------------
    # 4. Expensive scans — only for domains that pass bucket filter
    # ------------------------------------------------------------------
    subfinder_results = _cached_or_run("subfinder", _run_subfinder, [domain])
    dnsx_results = _cached_or_run("dnsx", _run_dnsx, [domain])
    crtsh_raw = _cached_or_run("crtsh", _query_local_ct, domain)
    ghw_results = _cached_or_run("ghw", _query_grayhatwarfare, [domain])

    # Subdomains
    if isinstance(subfinder_results, dict):
        scan.subdomains = subfinder_results.get(domain, [])

    # DNS
    if isinstance(dnsx_results, dict):
        scan.dns_records = dnsx_results.get(domain, {})

    # crt.sh — returns (domain, certs_list) or cached list
    if isinstance(crtsh_raw, (list, tuple)):
        if len(crtsh_raw) == 2 and isinstance(crtsh_raw[0], str):
            scan.ct_certificates = crtsh_raw[1] if isinstance(crtsh_raw[1], list) else []
        else:
            scan.ct_certificates = list(crtsh_raw)
    elif isinstance(crtsh_raw, dict):
        scan.ct_certificates = []

    # GrayHatWarfare
    if isinstance(ghw_results, dict):
        scan.exposed_cloud_storage = ghw_results.get(domain, [])

    # ------------------------------------------------------------------
    # 4b. Level 1 scans (active probing — only when job.level >= 1)
    # ------------------------------------------------------------------
    level1_scan_result: Optional[dict] = None
    job_level = job.get("level", 0)

    if isinstance(job_level, int) and not isinstance(job_level, bool) and job_level >= 1:
        nuclei_results = _cached_or_run("nuclei", _run_nuclei, [domain])

        nuclei_data: dict = {}
        if isinstance(nuclei_results, dict):
            nuclei_data = nuclei_results.get(domain, {"findings": [], "finding_count": 0})

        cmseek_results = _cached_or_run("cmseek", _run_cmseek, [domain])

        cmseek_data: dict = {}
        if isinstance(cmseek_results, dict):
            cmseek_data = cmseek_results.get(domain, {})

        level1_scan_result = {
            "nuclei": nuclei_data,
            "cmseek": cmseek_data,
        }

        logger.bind(context={
            "domain": domain,
            "job_id": job_id,
            "nuclei_findings": len(nuclei_data.get("findings", [])),
        }).info("level1_nuclei_complete")

    # ------------------------------------------------------------------
    # 4c. WPVulnerability lookup — WordPress domains only
    # ------------------------------------------------------------------
    if level1_scan_result is not None and scan.cms == "WordPress":
        try:
            from src.vulndb.lookup import lookup_wordpress_vulns

            vulndb_path = os.environ.get("VULNDB_PATH", "/data/cache/vulndb.sqlite3")
            wp_version = _extract_wp_version(scan.tech_stack)

            vuln_findings = lookup_wordpress_vulns(
                plugin_slugs=scan.detected_plugins,
                plugin_versions=scan.plugin_versions,
                wp_version=wp_version,
                provenance="",
                db_path=vulndb_path,
            )
            level1_scan_result["wpvulnerability"] = {
                "findings": vuln_findings,
                "finding_count": len(vuln_findings),
            }
        except Exception:
            logger.opt(exception=True).error("vulndb_lookup_failed for {}", domain)

    # ------------------------------------------------------------------
    # 4d. Outdated plugin check — WordPress domains with known versions
    # ------------------------------------------------------------------
    outdated_plugins: list[dict] = []
    if scan.cms == "WordPress" and scan.plugin_versions:
        try:
            from src.vulndb.wp_versions import check_outdated_plugins
            outdated_plugins = check_outdated_plugins(
                scan.plugin_versions,
                db_path=os.environ.get("VULNDB_PATH", "/data/cache/vulndb.sqlite3"),
            )
        except Exception:
            logger.opt(exception=True).error("outdated_plugin_check_failed for {}", domain)

    # ------------------------------------------------------------------
    # 5. Generate findings + GDPR determination
    # ------------------------------------------------------------------
    brief = generate_brief(company, scan, bucket, outdated_plugins=outdated_plugins)

    # ------------------------------------------------------------------
    # 5b. Twin scan — Layer 2 tools against a digital twin (WordPress only)
    # ------------------------------------------------------------------
    if scan.cms == "WordPress" and brief.get("tech_stack"):
        try:
            from .twin_scan import run_twin_scan
            twin_result = run_twin_scan(brief)
            if twin_result and twin_result.get("findings"):
                for finding in twin_result["findings"]:
                    finding["provenance"] = "unconfirmed"
                brief["findings"].extend(twin_result["findings"])
                brief["twin_scan"] = {
                    "twin_scan_date": twin_result["twin_scan_date"],
                    "scan_tools": twin_result["scan_tools"],
                    "duration_ms": twin_result["duration_ms"],
                    "note": "Findings derived from passive fingerprinting, not confirmed against live target",
                }
                logger.bind(context={
                    "domain": domain,
                    "twin_findings": len(twin_result["findings"]),
                    "twin_tools": twin_result["scan_tools"],
                    "twin_duration_ms": twin_result["duration_ms"],
                }).info("twin_scan_enriched")
        except Exception:
            logger.opt(exception=True).error("twin_scan_failed for {}", domain)

    # ------------------------------------------------------------------
    # 6. Build return dict
    # ------------------------------------------------------------------
    total_ms = int((time.monotonic() - job_t0) * 1000)
    # Convert all timing values to ms (int)
    timing_ms = {k: int(v * 1000) if isinstance(v, float) else v for k, v in timing.items()}
    timing_ms["total_ms"] = total_ms

    logger.bind(context={
        "domain": domain,
        "job_id": job_id,
        "duration_ms": total_ms,
        "cache_hits": job_hits,
        "cache_misses": job_misses,
        "findings_count": len(brief.get("findings", [])),
    }).info("domain_scan_complete")

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
