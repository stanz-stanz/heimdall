"""Interpret command -- run Claude API interpretation on promoted prospects.

This is where API spend happens. Each prospect's brief is passed through
interpret_brief() exactly as the delivery bot does, but in batch mode.

Supports:
    --min-severity high   Only interpret prospects with high/critical findings
    --limit 10            Cap the batch size (cost control)
    --dry-run             Show what would be interpreted without API calls
    --tier watchman       Prospects get watchman-level interpretation (no fix instructions)

Resume-safe: only processes prospects with outreach_status='new'. If the batch
is interrupted, re-running picks up where it left off.
"""

from __future__ import annotations

import json

from loguru import logger

from src.db.connection import init_db, _now
from src.interpreter.cache import get_cached, store as cache_store
from src.interpreter.interpreter import interpret_brief, InterpreterError


def run_interpret(
    campaign: str,
    min_severity: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    tier: str = "watchman",
    language: str | None = None,
    db_path: str | None = None,
) -> dict:
    """Interpret briefs for prospects in a campaign.

    Queries the prospects table for rows with outreach_status='new',
    optionally filtered by minimum severity. For each matching prospect:
    loads the brief JSON, pre-filters findings, calls interpret_brief(),
    and stores the result.

    Args:
        campaign: Campaign identifier to process.
        min_severity: If "high", only interpret prospects that have at least
            one high or critical finding. If "critical", only those with
            at least one critical finding. None includes all.
        limit: Maximum number of prospects to interpret in this batch.
            None means no limit.
        dry_run: If True, show what would be interpreted but skip API calls.
        tier: Interpretation tier. Prospects default to "watchman" (plain
            language only, no fix instructions -- those are the upsell).
        language: Language override (en/da). Default: from interpreter config.
        db_path: Override path to clients.db.

    Returns:
        Summary dict with counts: total_eligible, interpreted, failed, skipped.
    """
    conn = init_db(db_path) if db_path else init_db()

    # Query eligible prospects
    prospects = _query_eligible(conn, campaign, min_severity, limit)

    if not prospects:
        logger.bind(context={
            "campaign": campaign,
            "min_severity": min_severity,
        }).info("no_eligible_prospects")
        conn.close()
        return {"total_eligible": 0, "interpreted": 0, "failed": 0, "skipped": 0}

    logger.bind(context={
        "campaign": campaign,
        "eligible": len(prospects),
        "min_severity": min_severity,
        "dry_run": dry_run,
        "tier": tier,
    }).info("interpret_batch_started")

    interpreted_count = 0
    failed_count = 0
    skipped_count = 0
    cache_hits = 0

    for prospect in prospects:
        domain = prospect["domain"]
        prospect_id = prospect["id"]

        try:
            brief = json.loads(prospect["brief_json"])
        except (json.JSONDecodeError, TypeError):
            logger.bind(context={
                "domain": domain, "prospect_id": prospect_id,
            }).warning("invalid_brief_json_in_db")
            _mark_failed(conn, prospect_id, "Invalid brief JSON in database")
            failed_count += 1
            continue

        # Pre-filter findings to high/critical (same pattern as delivery runner)
        all_findings = brief.get("findings", [])
        actionable = [
            f for f in all_findings
            if f.get("severity", "").lower() in ("critical", "high")
        ]

        if not actionable:
            logger.bind(context={
                "domain": domain,
                "total_findings": len(all_findings),
            }).info("no_actionable_findings_skipping")
            _mark_skipped(conn, prospect_id, "No high/critical findings")
            skipped_count += 1
            continue

        brief["findings"] = actionable

        if dry_run:
            cached = get_cached(actionable, tier, language or "en",
                                db_path=db_path)
            logger.bind(context={
                "domain": domain,
                "findings": len(actionable),
                "tier": tier,
                "cached": cached is not None,
            }).info("dry_run_would_interpret")
            skipped_count += 1
            continue

        # Check interpretation cache before calling Claude API
        lang = language or "en"
        cached = get_cached(actionable, tier, lang, db_path=db_path)
        if cached:
            # Cache hit — inject site-specific metadata
            cached["domain"] = brief.get("domain", "")
            cached["company_name"] = brief.get("company_name", "")
            cached["scan_date"] = brief.get("scan_date", "")
            cached["meta"] = cached.get("meta", {})
            cached["meta"]["cache_hit"] = True
            _store_interpretation(conn, prospect_id, cached)
            interpreted_count += 1
            cache_hits += 1
            logger.bind(context={
                "domain": domain,
                "findings": len(actionable),
            }).info("interpretation_cache_hit")
            continue

        # Cache miss — call the interpreter (Claude API spend happens here)
        try:
            interpreted = interpret_brief(
                brief,
                language=language,
                tier=tier,
            )
        except InterpreterError as exc:
            logger.bind(context={
                "domain": domain,
                "error": str(exc),
            }).error("interpretation_failed")
            _mark_failed(conn, prospect_id, str(exc))
            failed_count += 1
            continue

        # Store in interpretation cache for future reuse
        meta = interpreted.get("meta", {})
        cache_store(
            actionable, tier, lang, interpreted,
            model=meta.get("model", ""),
            input_tokens=meta.get("input_tokens", 0),
            output_tokens=meta.get("output_tokens", 0),
            db_path=db_path,
        )

        # Store interpretation result in prospects table
        _store_interpretation(conn, prospect_id, interpreted)
        interpreted_count += 1

        logger.bind(context={
            "domain": domain,
            "findings_in": len(actionable),
            "findings_out": len(interpreted.get("findings", [])),
            "duration_ms": meta.get("duration_ms"),
        }).info("prospect_interpreted")

    summary = {
        "total_eligible": len(prospects),
        "interpreted": interpreted_count,
        "cache_hits": cache_hits,
        "api_calls": interpreted_count - cache_hits,
        "failed": failed_count,
        "skipped": skipped_count,
    }

    logger.bind(context={"campaign": campaign, **summary}).info("interpret_batch_completed")
    conn.close()

    return summary


def _query_eligible(
    conn,
    campaign: str,
    min_severity: str | None,
    limit: int | None,
) -> list[dict]:
    """Query prospects eligible for interpretation.

    Returns prospects with outreach_status='new' in the given campaign,
    optionally filtered by minimum finding severity.
    """
    # Base query: new prospects in this campaign
    sql = (
        "SELECT id, domain, brief_json, finding_count, critical_count, high_count "
        "FROM prospects "
        "WHERE campaign = ? AND outreach_status = 'new'"
    )
    params: list = [campaign]

    # Severity filter uses the pre-computed counts from promote
    if min_severity == "critical":
        sql += " AND critical_count > 0"
    elif min_severity == "high":
        sql += " AND (critical_count > 0 OR high_count > 0)"

    # Order by severity (most critical first) for cost-limited batches
    sql += " ORDER BY critical_count DESC, high_count DESC, finding_count DESC"

    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _store_interpretation(conn, prospect_id: int, interpreted: dict) -> None:
    """Store the interpretation result and update status to 'interpreted'."""
    now = _now()
    conn.execute(
        "UPDATE prospects SET "
        "  interpreted_json = ?, interpreted_at = ?, "
        "  outreach_status = 'interpreted', updated_at = ? "
        "WHERE id = ?",
        (
            json.dumps(interpreted, ensure_ascii=False),
            now,
            now,
            prospect_id,
        ),
    )
    conn.commit()


def _mark_failed(conn, prospect_id: int, error: str) -> None:
    """Mark a prospect as failed with an error message."""
    now = _now()
    conn.execute(
        "UPDATE prospects SET "
        "  outreach_status = 'failed', error_message = ?, updated_at = ? "
        "WHERE id = ?",
        (error, now, prospect_id),
    )
    conn.commit()


def _mark_skipped(conn, prospect_id: int, reason: str) -> None:
    """Mark a prospect as skipped with a reason."""
    now = _now()
    conn.execute(
        "UPDATE prospects SET "
        "  outreach_status = 'skipped', error_message = ?, updated_at = ? "
        "WHERE id = ?",
        (reason, now, prospect_id),
    )
    conn.commit()
