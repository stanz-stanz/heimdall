"""CRUD operations for pipeline runs, scan history, and brief snapshots.

Follows the enrichment/db.py pattern: plain functions, Row dicts, _now() timestamps.
"""

from __future__ import annotations

import json
import sqlite3

from src.db.connection import _now


# ---------------------------------------------------------------------------
# Pipeline runs
# ---------------------------------------------------------------------------


def create_pipeline_run(
    conn: sqlite3.Connection,
    run_id: str,
    run_date: str,
    config_json: str | None = None,
) -> dict:
    """Create a new pipeline run record. Sets started_at.

    Args:
        conn: Database connection.
        run_id: Unique run identifier (e.g. "run-2026-04-02-abcd1234").
        run_date: ISO-8601 date string (YYYY-MM-DD).
        config_json: Optional JSON string of pipeline config snapshot.

    Returns:
        Row dict with all columns for the newly created run.
    """
    now = _now()
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, started_at, status, config_json) "
        "VALUES (?, ?, ?, 'running', ?)",
        (run_id, run_date, now, config_json),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return dict(row)


def complete_pipeline_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    domain_count: int = 0,
    success_count: int = 0,
    error_count: int = 0,
    finding_count: int = 0,
    critical_count: int = 0,
    high_count: int = 0,
    medium_count: int = 0,
    low_count: int = 0,
    info_count: int = 0,
    bucket_a_count: int = 0,
    bucket_b_count: int = 0,
    bucket_c_count: int = 0,
    bucket_d_count: int = 0,
    bucket_e_count: int = 0,
    total_duration_ms: int | None = None,
    avg_domain_ms: int | None = None,
) -> None:
    """Complete a pipeline run -- sets completed_at and all rollup fields.

    Args:
        conn: Database connection.
        run_id: Run identifier to complete.
        status: Final status (completed | failed | partial).
        domain_count: Total domains attempted.
        success_count: Domains that completed scanning.
        error_count: Domains that failed.
        finding_count: Total findings across all domains.
        critical_count: Findings with severity=critical.
        high_count: Findings with severity=high.
        medium_count: Findings with severity=medium.
        low_count: Findings with severity=low.
        info_count: Findings with severity=info.
        bucket_a_count: Domains bucketed A.
        bucket_b_count: Domains bucketed B.
        bucket_c_count: Domains bucketed C.
        bucket_d_count: Domains bucketed D.
        bucket_e_count: Domains bucketed E.
        total_duration_ms: Wall-clock milliseconds.
        avg_domain_ms: Average per-domain scan time.
    """
    conn.execute(
        "UPDATE pipeline_runs SET "
        "completed_at = ?, status = ?, "
        "domain_count = ?, success_count = ?, error_count = ?, "
        "finding_count = ?, "
        "critical_count = ?, high_count = ?, medium_count = ?, "
        "low_count = ?, info_count = ?, "
        "bucket_a_count = ?, bucket_b_count = ?, bucket_c_count = ?, "
        "bucket_d_count = ?, bucket_e_count = ?, "
        "total_duration_ms = ?, avg_domain_ms = ? "
        "WHERE run_id = ?",
        (
            _now(), status,
            domain_count, success_count, error_count,
            finding_count,
            critical_count, high_count, medium_count,
            low_count, info_count,
            bucket_a_count, bucket_b_count, bucket_c_count,
            bucket_d_count, bucket_e_count,
            total_duration_ms, avg_domain_ms,
            run_id,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Scan history
# ---------------------------------------------------------------------------


def create_scan_entry(
    conn: sqlite3.Connection,
    scan_id: str,
    domain: str,
    scan_date: str,
    run_id: str | None = None,
    cvr: str | None = None,
) -> dict:
    """Create a scan_history entry. Sets created_at.

    Args:
        conn: Database connection.
        scan_id: Unique scan identifier (e.g. "scan-2026-04-02-678249fc").
        domain: Domain being scanned.
        scan_date: ISO-8601 date string.
        run_id: Optional FK to pipeline_runs.
        cvr: Optional FK to clients.

    Returns:
        Row dict with all columns for the newly created entry.
    """
    now = _now()
    conn.execute(
        "INSERT INTO scan_history (scan_id, run_id, cvr, domain, scan_date, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (scan_id, run_id, cvr, domain, scan_date, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM scan_history WHERE scan_id = ?", (scan_id,)
    ).fetchone()
    return dict(row)


def complete_scan_entry(
    conn: sqlite3.Connection,
    scan_id: str,
    status: str = "completed",
    total_ms: int | None = None,
    timing_json: str | None = None,
    cache_hits: int = 0,
    cache_misses: int = 0,
    result_json: str | None = None,
    error_message: str | None = None,
) -> None:
    """Complete a scan entry with results.

    Args:
        conn: Database connection.
        scan_id: Scan identifier to complete.
        status: Final status (completed | failed | skipped | timeout).
        total_ms: Total scan duration in milliseconds.
        timing_json: Per-scan-type timing breakdown as JSON string.
        cache_hits: Number of cache hits during scan.
        cache_misses: Number of cache misses during scan.
        result_json: Complete raw scan result JSON.
        error_message: Error details if status is failed.
    """
    conn.execute(
        "UPDATE scan_history SET "
        "status = ?, total_ms = ?, timing_json = ?, "
        "cache_hits = ?, cache_misses = ?, "
        "result_json = ?, error_message = ? "
        "WHERE scan_id = ?",
        (status, total_ms, timing_json, cache_hits, cache_misses,
         result_json, error_message, scan_id),
    )
    conn.commit()


def get_scan_history(
    conn: sqlite3.Connection,
    domain: str,
    limit: int = 10,
) -> list[dict]:
    """Most recent scans for a domain, ordered by scan_date DESC.

    Args:
        conn: Database connection.
        domain: Domain to query.
        limit: Maximum number of rows to return.

    Returns:
        List of row dicts, newest first.
    """
    rows = conn.execute(
        "SELECT * FROM scan_history WHERE domain = ? "
        "ORDER BY scan_date DESC LIMIT ?",
        (domain, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_latest_scan(
    conn: sqlite3.Connection,
    domain: str,
) -> dict | None:
    """Get the most recent scan for a domain.

    Args:
        conn: Database connection.
        domain: Domain to query.

    Returns:
        Row dict for the latest scan, or None if no scans exist.
    """
    row = conn.execute(
        "SELECT * FROM scan_history WHERE domain = ? "
        "ORDER BY scan_date DESC LIMIT 1",
        (domain,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Brief snapshots
# ---------------------------------------------------------------------------


def _extract_severity_counts(findings: list[dict]) -> dict[str, int]:
    """Count findings by severity level."""
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "").lower()
        if sev in counts:
            counts[sev] += 1
    return counts


def save_brief_snapshot(
    conn: sqlite3.Connection,
    domain: str,
    scan_date: str,
    brief_dict: dict,
    scan_id: str | None = None,
    run_id: str | None = None,
    company_name: str | None = None,
    cvr: str | None = None,
) -> None:
    """Save a brief snapshot. Extracts indexed fields from brief_dict, stores full JSON.

    Args:
        conn: Database connection.
        domain: Domain this brief describes.
        scan_date: ISO-8601 date string.
        brief_dict: Full brief dictionary to archive and extract fields from.
        scan_id: Optional FK to scan_history.
        run_id: Optional FK to pipeline_runs.
        company_name: Optional company name for cross-referencing.
        cvr: Optional CVR number.

    Raises:
        sqlite3.IntegrityError: If a snapshot for (domain, scan_date) already exists.
    """
    tech = brief_dict.get("technology", {})
    ssl = tech.get("ssl", {})
    findings = brief_dict.get("findings", [])
    severity_counts = _extract_severity_counts(findings)

    # Twin-derived finding detection
    twin_finding_count = sum(
        1 for f in findings if f.get("provenance") == "unconfirmed"
    )
    has_twin_scan = 1 if twin_finding_count > 0 else 0

    # Agency detection fields
    meta_author = brief_dict.get("meta_author")
    footer_credit = brief_dict.get("footer_credit")

    conn.execute(
        "INSERT INTO brief_snapshots ("
        "domain, scan_date, scan_id, run_id, "
        "bucket, cms, hosting, server, "
        "finding_count, critical_count, high_count, medium_count, low_count, info_count, "
        "plugin_count, theme_count, subdomain_count, "
        "has_twin_scan, twin_finding_count, "
        "ssl_valid, ssl_issuer, ssl_days_remaining, "
        "meta_author, footer_credit, "
        "company_name, cvr, "
        "brief_json, created_at"
        ") VALUES ("
        "?, ?, ?, ?, "
        "?, ?, ?, ?, "
        "?, ?, ?, ?, ?, ?, "
        "?, ?, ?, "
        "?, ?, "
        "?, ?, ?, "
        "?, ?, "
        "?, ?, "
        "?, ?"
        ")",
        (
            domain, scan_date, scan_id, run_id,
            brief_dict.get("bucket"),
            tech.get("cms"),
            tech.get("hosting"),
            tech.get("server"),
            len(findings),
            severity_counts["critical"],
            severity_counts["high"],
            severity_counts["medium"],
            severity_counts["low"],
            severity_counts["info"],
            len(tech.get("detected_plugins", [])),
            len(tech.get("detected_themes", [])),
            brief_dict.get("subdomains", {}).get("count", 0),
            has_twin_scan,
            twin_finding_count,
            1 if ssl.get("valid") is True else (0 if ssl.get("valid") is False else None),
            ssl.get("issuer"),
            ssl.get("days_remaining"),
            meta_author,
            footer_credit,
            company_name,
            cvr,
            json.dumps(brief_dict),
            _now(),
        ),
    )
    conn.commit()


def get_latest_brief(
    conn: sqlite3.Connection,
    domain: str,
) -> dict | None:
    """Get the most recent brief snapshot for a domain.

    Args:
        conn: Database connection.
        domain: Domain to query.

    Returns:
        Row dict for the latest brief snapshot, or None if none exist.
    """
    row = conn.execute(
        "SELECT * FROM brief_snapshots WHERE domain = ? "
        "ORDER BY scan_date DESC LIMIT 1",
        (domain,),
    ).fetchone()
    return dict(row) if row else None
