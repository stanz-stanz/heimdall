"""High-level vulnerability lookup: cache-first, API-on-miss."""

from __future__ import annotations

import logging
import os

from .cache import (
    get_core_vulns,
    get_plugin_vulns,
    init_db,
    is_slug_cached,
    store_core_vulns,
    store_plugin_vulns,
)
from .client import fetch_core_vulns, fetch_plugin_vulns
from .matcher import build_findings

log = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.environ.get("VULNDB_PATH", "/data/cache/vulndb.sqlite3")


def lookup_wordpress_vulns(
    plugin_slugs: list[str],
    plugin_versions: dict[str, str] | None = None,
    wp_version: str | None = None,
    provenance: str = "twin-derived",
    max_cache_age_days: int = 7,
    db_path: str | None = None,
) -> list[dict]:
    """Look up vulnerabilities for detected WordPress plugins and core.

    For each slug:
    1. Check SQLite cache
    2. On cache miss: fetch from WPVulnerability API, store in cache
    3. Run version matcher
    4. Generate findings

    Returns a list of finding dicts ready to append to brief["findings"].
    """
    db_path = db_path or DEFAULT_DB_PATH
    plugin_versions = plugin_versions or {}
    all_findings: list[dict] = []

    conn = init_db(db_path)

    try:
        # Plugin vulnerabilities
        for slug in plugin_slugs:
            vulns = _get_or_fetch_plugin(conn, slug, max_cache_age_days)
            if not vulns:
                continue

            version = plugin_versions.get(slug)
            findings = build_findings(slug, version, vulns, provenance)
            all_findings.extend(findings)

        # WordPress core vulnerabilities
        if wp_version:
            vulns = _get_or_fetch_core(conn, wp_version, max_cache_age_days)
            if vulns:
                findings = build_findings("wordpress-core", wp_version, vulns, provenance)
                all_findings.extend(findings)

    finally:
        conn.close()

    if all_findings:
        log.info("vulndb_findings", extra={"context": {
            "plugin_count": len(plugin_slugs),
            "finding_count": len(all_findings),
        }})

    return all_findings


def _get_or_fetch_plugin(conn, slug: str, max_age_days: int) -> list[dict]:
    """Get from cache or fetch from API for a plugin slug."""
    if is_slug_cached(conn, slug, "plugin", max_age_days):
        vulns = get_plugin_vulns(conn, slug)
        if vulns is not None:
            return vulns

    status, vulns = fetch_plugin_vulns(slug)
    if status == 200:
        store_plugin_vulns(conn, slug, vulns)
    return vulns


def _get_or_fetch_core(conn, version: str, max_age_days: int) -> list[dict]:
    """Get from cache or fetch from API for WordPress core."""
    if is_slug_cached(conn, version, "core", max_age_days):
        vulns = get_core_vulns(conn, version)
        if vulns is not None:
            return vulns

    status, vulns = fetch_core_vulns(version)
    if status == 200:
        store_core_vulns(conn, version, vulns)
    return vulns


def refresh_stale_cache(db_path: str | None = None, max_age_days: int = 7) -> int:
    """Re-fetch vulns for slugs older than max_age_days.

    Returns the number of slugs refreshed.
    """
    from .cache import get_stale_slugs

    db_path = db_path or DEFAULT_DB_PATH
    conn = init_db(db_path)
    stale = get_stale_slugs(conn, max_age_days)

    refreshed = 0
    for slug, asset_type in stale:
        if asset_type == "plugin":
            status, vulns = fetch_plugin_vulns(slug)
            store_plugin_vulns(conn, slug, vulns)
        elif asset_type == "core":
            status, vulns = fetch_core_vulns(slug)
            store_core_vulns(conn, slug, vulns)
        refreshed += 1

    conn.close()
    log.info("vulndb_refresh", extra={"context": {
        "stale_count": len(stale), "refreshed": refreshed,
    }})
    return refreshed
