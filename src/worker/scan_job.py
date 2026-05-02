"""Execute a single-domain scan job using cached + fresh scan results.

Orchestrates all Layer 1 scan types for one domain, checking the Redis cache
before each scan and storing fresh results back.  Returns a result dict with
scan data, timing breakdown, and cache statistics.
"""

from __future__ import annotations

import functools
import os
import time
from dataclasses import asdict
from typing import Any

import redis
from loguru import logger

from src.prospecting.brief_generator import generate_brief
from src.prospecting.bucketer import classify
from src.core.config import CMS_KEYWORDS, DEFAULT_FILTERS, HOSTING_PROVIDERS
from src.prospecting.cvr import Company
from src.prospecting.filters import load_filters
from src.prospecting.scanners.models import ScanResult
from src.prospecting.scanners.robots import check_robots_txt
from src.prospecting.scanners.nmap import nmap_ports_to_findings
from src.valdi import run_gated_scan

from .cache import ScanCache

# Load bucket filter once at import time
_filters = load_filters(DEFAULT_FILTERS)
_BUCKET_FILTER = None
_bucket_raw = _filters.get("bucket")
if _bucket_raw:
    _BUCKET_FILTER = {b.upper() for b in _bucket_raw}

SSL_SCAN = "ssl_certificate_check"
META_SCAN = "homepage_meta_extraction"
HTTPX_SCAN = "httpx_tech_fingerprint"
WEBANALYZE_SCAN = "webanalyze_cms_detection"
HEADERS_SCAN = "response_header_check"
SUBFINDER_SCAN = "subdomain_enumeration_passive"
DNS_SCAN = "dns_enrichment"
CT_SCAN = "certificate_transparency_query"
CLOUD_SCAN = "cloud_storage_index_query"
NUCLEI_SCAN = "nuclei_vulnerability_scan"
CMSEEK_SCAN = "cmseek_cms_deep_scan"
NMAP_SCAN = "nmap_port_scan"


def _timed(fn: Any, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    """Call *fn* and return ``(result, elapsed_seconds)``."""
    t0 = time.monotonic()
    result = fn(*args, **kwargs)
    return result, time.monotonic() - t0


def _extract_wp_version(tech_stack: list) -> str | None:
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
        logger.warning("slug_map_load_failed — plugin name normalization disabled",
                       exc_info=True)
        return {}


def _merge_tech_stack_plugins(scan: ScanResult) -> None:
    """Merge WordPress plugins detected in tech_stack into detected_plugins + plugin_versions.

    Tech tools (httpx, webanalyze) detect plugins like "Yoast SEO:26.9" in tech_stack.
    This function uses slug_map.json to identify WP plugins and merge them with
    HTML-detected plugins from extract_page_meta.
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
    redis_conn: redis.Redis | None = None,
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
    timing: dict[str, float] = {}
    job_hits = 0
    job_misses = 0

    if "robots_allowed" in job:
        robots_allowed = bool(job.get("robots_allowed"))
        timing["robots_txt"] = 0.0
    else:
        robots_allowed, robots_dt = _timed(check_robots_txt, domain)
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

    def _cached_or_run(cache_key: str, scan_type: str, *args: Any) -> Any:
        nonlocal job_hits, job_misses
        cached = cache.get(cache_key, domain)
        if cached is not None:
            job_hits += 1
            logger.bind(context={"domain": domain, "scan_type": scan_type}).debug("cache_hit")
            return cached
        job_misses += 1
        result, dt = _timed(run_gated_scan, scan_type, *args)
        timing[scan_type] = round(dt, 4)
        # Normalise result to a JSON-serialisable dict/list for caching
        serialisable = result
        if isinstance(result, tuple):
            serialisable = list(result)
        cache.set(cache_key, domain, serialisable)
        logger.bind(context={"domain": domain, "scan_type": scan_type, "duration_ms": int(dt * 1000)}).info("scan_type_complete")
        return result

    # --- individual per-domain scans ---
    ssl_info = _cached_or_run("ssl", SSL_SCAN, domain)
    headers = _cached_or_run("headers", HEADERS_SCAN, domain)
    meta_raw = _cached_or_run("meta", META_SCAN, domain)

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
    httpx_results = _cached_or_run("httpx", HTTPX_SCAN, [domain])
    webanalyze_results = _cached_or_run("webanalyze", WEBANALYZE_SCAN, [domain])

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
        scan.tls_version = ssl_info.get("tls_version", "")
        scan.tls_cipher = ssl_info.get("tls_cipher", "")
        scan.tls_bits = ssl_info.get("tls_bits", 0)

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
    wa_techs: list[str] = []
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
    subfinder_results = _cached_or_run("subfinder", SUBFINDER_SCAN, [domain])
    dnsx_results = _cached_or_run("dnsx", DNS_SCAN, [domain])
    # CT now routes through the registered batch function (`query_crt_sh`)
    # rather than the un-registered single-domain helper. Pass `[domain]`.
    crtsh_raw = _cached_or_run("crtsh", CT_SCAN, [domain])
    ghw_results = _cached_or_run("ghw", CLOUD_SCAN, [domain])

    # Subdomains
    if isinstance(subfinder_results, dict):
        scan.subdomains = subfinder_results.get(domain, [])

    # DNS
    if isinstance(dnsx_results, dict):
        scan.dns_records = dnsx_results.get(domain, {})

    if isinstance(crtsh_raw, dict):
        scan.ct_certificates = crtsh_raw.get(domain, [])
    elif (
        isinstance(crtsh_raw, list)
        and len(crtsh_raw) == 2
        and crtsh_raw[0] == domain
        and isinstance(crtsh_raw[1], list)
    ):
        # Legacy cache shape from the un-registered `query_crt_sh_single`
        # helper (pre-Valdí runtime hardening). JSON-serialised as
        # `[domain, certs]`. Eligible for removal once the Redis cache TTL
        # has cycled all old entries through the new dict format.
        scan.ct_certificates = crtsh_raw[1]

    # GrayHatWarfare
    if isinstance(ghw_results, dict):
        scan.exposed_cloud_storage = ghw_results.get(domain, [])

    # ------------------------------------------------------------------
    # 4b. Level 1 scans (active probing — only when job.level >= 1)
    # ------------------------------------------------------------------
    level1_scan_result: dict | None = None
    job_level = job.get("level", 0)

    if isinstance(job_level, int) and not isinstance(job_level, bool) and job_level >= 1:
        nuclei_results = _cached_or_run("nuclei", NUCLEI_SCAN, [domain])

        nuclei_data: dict = {}
        if isinstance(nuclei_results, dict):
            nuclei_data = nuclei_results.get(domain, {"findings": [], "finding_count": 0})

        cmseek_results = _cached_or_run("cmseek", CMSEEK_SCAN, [domain])

        cmseek_data: dict = {}
        if isinstance(cmseek_results, dict):
            cmseek_data = cmseek_results.get(domain, {})

        nmap_results = _cached_or_run("nmap", NMAP_SCAN, [domain])

        nmap_data: dict = {}
        if isinstance(nmap_results, dict):
            nmap_data = nmap_results.get(domain, {"open_ports": [], "port_count": 0})

        if nmap_data.get("open_ports"):
            nmap_data["findings"] = nmap_ports_to_findings(nmap_data["open_ports"])

        level1_scan_result = {
            "nuclei": nuclei_data,
            "cmseek": cmseek_data,
            "nmap": nmap_data,
        }

        logger.bind(context={
            "domain": domain,
            "job_id": job_id,
            "nuclei_findings": len(nuclei_data.get("findings", [])),
            "nmap_open_ports": nmap_data.get("port_count", 0),
        }).info("level1_scans_complete")

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
    # 5a. RSS CVE enrichment — flag CVEs trending in security feeds
    # ------------------------------------------------------------------
    if brief.get("findings"):
        try:
            from src.vulndb.rss_cve import enrich_with_rss_cves, refresh_rss_cves
            refresh_rss_cves()  # no-op if feeds are fresh (< 12 hours)
            enrich_with_rss_cves(brief["findings"])
        except Exception:
            logger.opt(exception=True).warning("rss_cve_enrichment_failed for {}", domain)

    # ------------------------------------------------------------------
    # 5a2. KEV enrichment — flag known exploited vulnerabilities
    # ------------------------------------------------------------------
    if brief.get("findings"):
        try:
            from src.vulndb.kev import enrich_with_kev, refresh_kev
            refresh_kev()  # no-op if catalog is fresh (< 24 hours)
            enrich_with_kev(brief["findings"])
        except Exception:
            logger.opt(exception=True).warning("kev_enrichment_failed for {}", domain)

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
