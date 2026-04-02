"""WordPress.org Plugin API client for latest version lookups.

Public API, no auth required. Results cached in vulndb SQLite.
Used to check if installed plugins are outdated.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import requests

from .cache import init_db

log = logging.getLogger(__name__)

WP_API_URL = "https://api.wordpress.org/plugins/info/1.0/{slug}.json"
REQUEST_TIMEOUT = 10
API_DELAY = 0.5  # seconds between API calls to avoid rate limiting
DEFAULT_DB_PATH = os.environ.get("VULNDB_PATH", "/data/cache/vulndb.sqlite3")

_last_api_call: float = 0.0


def get_latest_plugin_version(
    slug: str,
    db_path: str | None = None,
    max_age_hours: int = 24,
) -> str | None:
    """Get the latest version of a WordPress plugin.

    Checks SQLite cache first; fetches from wordpress.org API on miss.
    Returns version string or None if plugin not found.
    """
    db_path = db_path or DEFAULT_DB_PATH
    conn = init_db(db_path)

    try:
        # Check cache
        row = conn.execute(
            "SELECT latest_version, fetched_at FROM wp_latest_versions "
            "WHERE slug = ? AND asset_type = 'plugin'",
            (slug,),
        ).fetchone()

        if row:
            fetched = datetime.fromisoformat(row["fetched_at"].replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
            if age_hours < max_age_hours:
                return row["latest_version"]

        # Fetch from API
        version = _fetch_latest_from_api(slug)
        if version:
            _store_latest(conn, slug, "plugin", version)
        return version

    finally:
        conn.close()


def _fetch_latest_from_api(slug: str) -> str | None:
    """Fetch latest version from wordpress.org plugin info API."""
    global _last_api_call
    elapsed = time.monotonic() - _last_api_call
    if elapsed < API_DELAY:
        time.sleep(API_DELAY - elapsed)
    _last_api_call = time.monotonic()

    url = WP_API_URL.format(slug=slug)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if isinstance(data, dict) and "version" in data:
            return data["version"]
        return None
    except (requests.RequestException, ValueError):
        return None


def _store_latest(conn, slug: str, asset_type: str, version: str) -> None:
    """Cache a latest version entry."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT OR REPLACE INTO wp_latest_versions (slug, asset_type, latest_version, fetched_at) "
        "VALUES (?, ?, ?, ?)",
        (slug, asset_type, version, now),
    )
    conn.commit()


def check_outdated_plugins(
    plugin_versions: dict[str, str],
    db_path: str | None = None,
) -> list[dict]:
    """Check installed plugin versions against latest from wordpress.org.

    Returns list of {slug, installed, latest, outdated} dicts.
    Only includes plugins where both installed and latest versions are known.
    """
    from packaging.version import InvalidVersion, Version

    results = []
    for slug, installed_ver in plugin_versions.items():
        if not installed_ver:
            continue
        latest = get_latest_plugin_version(slug, db_path)
        if not latest:
            continue
        try:
            outdated = Version(installed_ver) < Version(latest)
        except InvalidVersion:
            outdated = False
        results.append({
            "slug": slug,
            "installed": installed_ver,
            "latest": latest,
            "outdated": outdated,
        })
    return results
