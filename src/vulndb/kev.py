"""CISA KEV (Known Exploited Vulnerabilities) enrichment.

Fetches the CISA KEV catalog (~1,100 CVE IDs), caches in SQLite,
and flags matching findings with ``known_exploited: True`` so the
interpreter can add the [ACTIVELY EXPLOITED] marker.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime

import requests
from loguru import logger

from .cache import init_db

_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
_DEFAULT_DB_PATH = os.environ.get("VULNDB_PATH", "/data/cache/vulndb.sqlite3")
_USER_AGENT = "Heimdall/1.0 (EASM; +https://heimdall.dk)"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_conn(db_path: str | None = None) -> sqlite3.Connection:
    return init_db(db_path or _DEFAULT_DB_PATH)


def _is_fresh(conn: sqlite3.Connection, max_age_hours: int) -> bool:
    row = conn.execute(
        "SELECT last_fetched_at FROM kev_meta WHERE key = 'catalog'"
    ).fetchone()
    if row is None:
        return False
    fetched = datetime.fromisoformat(row["last_fetched_at"].replace("Z", "+00:00"))
    age_hours = (datetime.now(UTC) - fetched).total_seconds() / 3600
    return age_hours < max_age_hours


def refresh_kev(db_path: str | None = None, max_age_hours: int = 24) -> int:
    """Fetch CISA KEV catalog if stale. Returns entry count."""
    conn = _get_conn(db_path)
    if _is_fresh(conn, max_age_hours):
        conn.close()
        return 0

    try:
        resp = requests.get(_KEV_URL, timeout=15,
                            headers={"User-Agent": _USER_AGENT})
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("KEV fetch failed: {}", exc)
        conn.close()
        return 0

    vulns = data.get("vulnerabilities", [])
    cve_ids = [v["cveID"] for v in vulns if v.get("cveID")]

    conn.execute("DELETE FROM kev_entries")
    conn.executemany(
        "INSERT OR IGNORE INTO kev_entries (cve_id) VALUES (?)",
        [(cve,) for cve in cve_ids],
    )
    conn.execute(
        "INSERT OR REPLACE INTO kev_meta (key, last_fetched_at, entry_count) "
        "VALUES ('catalog', ?, ?)",
        (_now(), len(cve_ids)),
    )
    conn.commit()
    conn.close()

    logger.info("kev_catalog_refreshed: {} entries", len(cve_ids))
    return len(cve_ids)


def enrich_with_kev(findings: list[dict],
                    db_path: str | None = None) -> list[dict]:
    """Flag findings whose cve_id is in the CISA KEV catalog.

    Mutates each matching finding in place:
    - Sets ``known_exploited: True``
    - Appends KEV context to the ``risk`` field
    """
    cve_ids = [f["cve_id"] for f in findings if f.get("cve_id")]
    if not cve_ids:
        return findings

    conn = _get_conn(db_path)
    placeholders = ",".join("?" for _ in cve_ids)
    rows = conn.execute(
        f"SELECT cve_id FROM kev_entries WHERE cve_id IN ({placeholders})",
        cve_ids,
    ).fetchall()
    conn.close()

    kev_set = {row["cve_id"] for row in rows}
    if not kev_set:
        return findings

    flagged = 0
    for finding in findings:
        cve_id = finding.get("cve_id")
        if cve_id and cve_id in kev_set:
            finding["known_exploited"] = True
            finding["risk"] = (
                finding.get("risk", "")
                + " This vulnerability is on the CISA Known Exploited"
                " Vulnerabilities catalog, indicating confirmed active"
                " exploitation in the wild."
            )
            flagged += 1

    if flagged:
        logger.info("kev_enrichment: {} findings flagged as actively exploited",
                     flagged)

    return findings
