"""Export command -- export interpreted prospects as CSV for email mail merge.

Joins the prospects table (from clients.db) with the enriched companies DB
(companies.db) to produce a CSV with:
    - domain, company_name, cvr, email, industry_name, bucket
    - top confirmed finding (for Email 1 lead)
    - finding count, critical count, high count
    - GDPR sensitivity flag
    - interpreted text snippet (for manual email personalization)

Usage:
    python -m src.outreach export --campaign 0426-vejle-gdpr
    python -m src.outreach export --campaign 0426-vejle-gdpr --output outreach.csv
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from loguru import logger

from src.db.connection import init_db

_ENRICHED_DB_PATH = "data/enriched/companies.db"


def run_export(
    campaign: str,
    output: str | None = None,
    status: str = "interpreted",
    db_path: str | None = None,
    enriched_db_path: str | None = None,
) -> dict:
    """Export interpreted prospects to CSV for email mail merge.

    Queries prospects with the given outreach_status, enriches with
    contact email from the companies DB, and writes a CSV.

    Args:
        campaign: Campaign identifier to export.
        output: Output CSV path. Defaults to data/output/campaign-{campaign}.csv.
        status: Outreach status to export (default: 'interpreted').
        db_path: Override path to clients.db.
        enriched_db_path: Override path to companies.db.

    Returns:
        Summary dict with counts.
    """
    conn = init_db(db_path) if db_path else init_db()

    enriched_path = enriched_db_path or _ENRICHED_DB_PATH
    email_lookup = _load_email_lookup(enriched_path)

    prospects = _query_prospects(conn, campaign, status)
    conn.close()

    if not prospects:
        logger.bind(context={"campaign": campaign, "status": status}).info(
            "no_prospects_to_export"
        )
        return {"total": 0, "exported": 0, "missing_email": 0}

    output_path = output or f"data/output/campaign-{campaign}.csv"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    rows = []
    missing_email = 0

    for prospect in prospects:
        domain = prospect["domain"]
        cvr = prospect["cvr"] or ""

        # Look up contact email from enriched DB
        email = email_lookup.get(cvr, "")
        if not email:
            missing_email += 1

        # Extract top confirmed finding from brief
        top_finding = _extract_top_confirmed_finding(prospect["brief_json"])

        # Extract a short interpretation snippet
        snippet = _extract_snippet(prospect["interpreted_json"])

        # Check GDPR sensitivity from brief
        gdpr_sensitive = _check_gdpr(prospect["brief_json"])

        rows.append({
            "domain": domain,
            "company_name": prospect["company_name"] or "",
            "cvr": cvr,
            "email": email,
            "industry_name": prospect["industry_name"] or "",
            "bucket": prospect["bucket"] or "",
            "finding_count": prospect["finding_count"],
            "critical_count": prospect["critical_count"],
            "high_count": prospect["high_count"],
            "gdpr_sensitive": gdpr_sensitive,
            "top_confirmed_finding": top_finding,
            "interpretation_snippet": snippet,
        })

    # Sort by severity (critical desc, high desc) for batch prioritization
    rows.sort(key=lambda r: (-r["critical_count"], -r["high_count"]))

    fieldnames = [
        "domain", "company_name", "cvr", "email", "industry_name", "bucket",
        "finding_count", "critical_count", "high_count", "gdpr_sensitive",
        "top_confirmed_finding", "interpretation_snippet",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "total": len(prospects),
        "exported": len(rows),
        "missing_email": missing_email,
        "output_path": output_path,
    }
    logger.bind(context=summary).info("export_completed")

    print(f"\nExported {len(rows)} prospects to {output_path}")
    print(f"  With email: {len(rows) - missing_email}")
    print(f"  Missing email: {missing_email}")

    return summary


def _load_email_lookup(enriched_db_path: str) -> dict[str, str]:
    """Load CVR -> email mapping from the enriched companies DB."""
    path = Path(enriched_db_path)
    if not path.exists():
        logger.warning("enriched_db_not_found: {}", enriched_db_path)
        return {}

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT cvr, email FROM companies WHERE email != '' AND contactable = 1"
    ).fetchall()
    conn.close()

    return {row["cvr"]: row["email"] for row in rows}


def _query_prospects(conn: sqlite3.Connection, campaign: str, status: str) -> list[dict]:
    """Query prospects with given status from the campaign."""
    rows = conn.execute(
        "SELECT domain, cvr, company_name, industry_name, bucket, "
        "  brief_json, interpreted_json, finding_count, critical_count, high_count "
        "FROM prospects "
        "WHERE campaign = ? AND outreach_status = ? "
        "ORDER BY critical_count DESC, high_count DESC",
        (campaign, status),
    ).fetchall()
    return [dict(r) for r in rows]


def _extract_top_confirmed_finding(brief_json: str | None) -> str:
    """Extract the most impactful confirmed (Layer 1) finding from a brief.

    Prioritizes: exposed PHP version > missing security headers > SSL issues > server exposure.
    These are directly observed Layer 1 facts usable in email outreach.
    """
    if not brief_json:
        return ""

    try:
        brief = json.loads(brief_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    headers = brief.get("headers", {})
    ssl = brief.get("ssl", {})

    # Priority 1: Exposed PHP version (most specific, best analogy)
    php_version = headers.get("x_powered_by", "")
    if php_version and "php" in php_version.lower():
        return f"Server afslorer PHP-version: {php_version}"

    # Priority 2: Missing security protections (broad impact)
    missing = []
    if not headers.get("content_security_policy"):
        missing.append("Content-Security-Policy")
    if not headers.get("strict_transport_security"):
        missing.append("HSTS")
    if not headers.get("x_frame_options"):
        missing.append("X-Frame-Options")
    if missing:
        count = len(missing)
        return f"Mangler {count} grundlaeggende sikkerhedsbeskyttelse(r)"

    # Priority 3: SSL issues
    days = ssl.get("days_remaining")
    if days is not None and days < 30:
        return f"SSL-certifikat udlober om {days} dage"

    # Priority 4: Server software exposure
    server = headers.get("server", "")
    if server and server.lower() not in ("", "cloudflare", "nginx", "apache"):
        return f"Server afslorer software: {server}"

    return "Flere sikkerhedsobservationer fundet"


def _extract_snippet(interpreted_json: str | None) -> str:
    """Extract a short snippet from the LLM interpretation for the CSV."""
    if not interpreted_json:
        return ""

    try:
        interpreted = json.loads(interpreted_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    # The interpreter returns a list of findings
    if isinstance(interpreted, list) and interpreted:
        first = interpreted[0]
        title = first.get("title", "")
        explanation = first.get("explanation", "")
        # Truncate for CSV readability
        if explanation and len(explanation) > 200:
            explanation = explanation[:197] + "..."
        return f"{title}: {explanation}" if title else explanation

    if isinstance(interpreted, dict):
        summary = interpreted.get("summary", "")
        if summary:
            return summary[:200] + "..." if len(summary) > 200 else summary

    return ""


def _check_gdpr(brief_json: str | None) -> str:
    """Check if the prospect handles customer data (GDPR-sensitive)."""
    if not brief_json:
        return "unknown"

    try:
        brief = json.loads(brief_json)
    except (json.JSONDecodeError, TypeError):
        return "unknown"

    gdpr = brief.get("gdpr", {})
    if isinstance(gdpr, dict):
        reasons = gdpr.get("reasons", [])
        if reasons:
            return "yes"
        sensitive = gdpr.get("sensitive", gdpr.get("is_sensitive", False))
        return "yes" if sensitive else "no"

    return "unknown"
