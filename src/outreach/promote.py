"""Promote command -- load briefs from disk, filter, insert into prospects table.

No Claude API calls. No Telegram. Pure data loading and filtering.
Idempotent: domains already in the campaign are skipped (UNIQUE constraint).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from loguru import logger

from src.db.connection import _now, init_db


def run_promote(
    campaign: str,
    buckets: list[str] | None = None,
    industry_prefixes: list[str] | None = None,
    briefs_dir: str = "data/output/briefs",
    db_path: str | None = None,
) -> dict:
    """Load brief JSON files, apply filters, and INSERT into prospects table.

    Args:
        campaign: Campaign identifier (e.g. "0426-restaurants").
        buckets: Optional list of bucket letters to include (e.g. ["A", "B"]).
        industry_prefixes: Optional list of industry code prefixes to include
            (e.g. ["56", "86"]). A brief matches if its industry_code starts
            with any of these prefixes.
        briefs_dir: Path to the directory containing {domain}.json brief files.
        db_path: Override path to clients.db.

    Returns:
        Summary dict with counts: loaded, filtered, inserted, skipped.
    """
    briefs_path = Path(briefs_dir)
    if not briefs_path.is_dir():
        raise FileNotFoundError(f"Briefs directory not found: {briefs_path}")

    conn = init_db(db_path) if db_path else init_db()

    # Ensure the prospects table exists (idempotent DDL)
    _ensure_prospects_table(conn)

    brief_files = sorted(briefs_path.glob("*.json"))
    if not brief_files:
        logger.warning("no_brief_files_found dir={}", briefs_dir)
        return {"loaded": 0, "filtered": 0, "inserted": 0, "skipped": 0}

    logger.bind(context={
        "campaign": campaign,
        "briefs_dir": str(briefs_dir),
        "total_files": len(brief_files),
        "bucket_filter": buckets,
        "industry_filter": industry_prefixes,
    }).info("promote_started")

    loaded = 0
    filtered = 0
    inserted = 0
    skipped = 0
    errors = 0

    for brief_file in brief_files:
        try:
            brief = _load_brief(brief_file)
        except (json.JSONDecodeError, OSError) as exc:
            logger.bind(context={
                "file": str(brief_file), "error": str(exc),
            }).warning("brief_load_error")
            errors += 1
            continue

        loaded += 1

        # Apply filters
        if not _matches_filters(brief, buckets, industry_prefixes):
            filtered += 1
            continue

        # Attempt insert (skip on UNIQUE violation = already promoted)
        try:
            insert_prospect(conn, campaign, brief)
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

    summary = {
        "loaded": loaded,
        "filtered": filtered,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }

    logger.bind(context={"campaign": campaign, **summary}).info("promote_completed")
    conn.close()

    return summary


def _load_brief(path: Path) -> dict:
    """Load and validate a brief JSON file.

    Raises:
        json.JSONDecodeError: If the file is not valid JSON.
        ValueError: If the brief is missing the required 'domain' key.
    """
    with open(path, encoding="utf-8") as f:
        brief = json.load(f)

    if not isinstance(brief, dict):
        raise ValueError(f"Expected dict, got {type(brief).__name__}")
    if not brief.get("domain"):
        raise ValueError(f"Brief missing 'domain' key: {path}")

    return brief


def _matches_filters(
    brief: dict,
    buckets: list[str] | None,
    industry_prefixes: list[str] | None,
) -> bool:
    """Check whether a brief passes the configured filters.

    Returns True if the brief should be included, False to skip.
    """
    # Bucket filter
    if buckets:
        brief_bucket = brief.get("bucket", "")
        if brief_bucket not in buckets:
            return False

    # Industry code prefix filter
    if industry_prefixes:
        # Industry code may be stored at brief top level or nested
        industry_code = brief.get("industry_code", "")
        if not industry_code:
            return False
        if not any(industry_code.startswith(prefix) for prefix in industry_prefixes):
            return False

    return True


def _count_by_severity(findings: list[dict], severity: str) -> int:
    """Count findings matching a given severity level."""
    return sum(
        1 for f in findings
        if f.get("severity", "").lower() == severity
    )


def insert_prospect(
    conn: sqlite3.Connection,
    campaign: str,
    brief: dict,
) -> None:
    """Insert a single prospect row from a brief dict.

    Raises:
        sqlite3.IntegrityError: If (domain, campaign) already exists.
    """
    now = _now()
    findings = brief.get("findings", [])

    conn.execute(
        "INSERT INTO prospects ("
        "  domain, cvr, company_name, campaign, bucket,"
        "  industry_code, industry_name, brief_json,"
        "  finding_count, critical_count, high_count,"
        "  outreach_status, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)",
        (
            brief.get("domain", ""),
            brief.get("cvr", ""),
            brief.get("company_name", ""),
            campaign,
            brief.get("bucket", ""),
            brief.get("industry_code", ""),
            brief.get("industry", ""),
            json.dumps(brief, ensure_ascii=False),
            len(findings),
            _count_by_severity(findings, "critical"),
            _count_by_severity(findings, "high"),
            now,
            now,
        ),
    )
    conn.commit()


def _ensure_prospects_table(conn: sqlite3.Connection) -> None:
    """Create the prospects table if it does not exist.

    This is a safety net so promote works even before the schema migration
    is applied to clients.db. The schema matches the DDL in
    docs/architecture/client-db-schema.sql.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prospects (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            domain              TEXT NOT NULL,
            cvr                 TEXT,
            company_name        TEXT,
            campaign            TEXT NOT NULL,
            bucket              TEXT,
            industry_code       TEXT,
            industry_name       TEXT,
            brief_json          TEXT NOT NULL,
            finding_count       INTEGER NOT NULL DEFAULT 0,
            critical_count      INTEGER NOT NULL DEFAULT 0,
            high_count          INTEGER NOT NULL DEFAULT 0,
            interpreted_json    TEXT,
            interpreted_at      TEXT,
            outreach_status     TEXT NOT NULL DEFAULT 'new',
            outreach_sent_at    TEXT,
            delivery_id         INTEGER,
            error_message       TEXT,
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            UNIQUE(domain, campaign)
        );

        CREATE INDEX IF NOT EXISTS idx_prospects_campaign_status
            ON prospects(campaign, outreach_status);

        CREATE INDEX IF NOT EXISTS idx_prospects_campaign_bucket
            ON prospects(campaign, bucket);

        CREATE INDEX IF NOT EXISTS idx_prospects_domain
            ON prospects(domain);
    """)
