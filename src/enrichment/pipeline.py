"""Enrichment pipeline orchestrator — steps 1-7 in sequence."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from loguru import logger

from .db import (
    init_db,
    log_enrichment,
    populate_domains,
    update_domain,
    update_enrichments,
    upsert_companies,
)
from .domain_deriver import (
    extract_domain_from_email,
    validate_domain_name_match,
)
from .excel_reader import read_cvr_excel
from .normalizers import (
    check_gdpr_industry,
    is_free_webmail,
    load_company_forms,
    load_free_webmail,
    load_gdpr_industry_codes,
    load_industry_codes,
    lookup_industry_name,
    normalize_company_form,
)
from .search_fallback import SearchError, search_company_domain

def run_pipeline(
    input_path: Path,
    db_path: Path,
    skip_search: bool = False,
    force: bool = False,
    search_delay: float = 0.5,
) -> dict:
    """Run the full enrichment pipeline. Returns a summary stats dict."""
    stats = {
        "total_ingested": 0,
        "email_derived": 0,
        "search_derived": 0,
        "domain_verified": 0,
        "gdpr_flagged": 0,
        "contactable": 0,
        "ready_for_scan": 0,
        "no_domain": 0,
        "search_skipped": 0,
        "search_errors": 0,
    }

    conn = init_db(db_path)

    # Step 1: Excel ingestion
    logger.info("Step 1/7: Reading CVR Excel")
    rows = read_cvr_excel(input_path)
    stats["total_ingested"] = upsert_companies(conn, rows)
    logger.info("Ingested {} companies", stats["total_ingested"])

    # Step 2: Static enrichments
    logger.info("Step 2/7: Static enrichments")
    _apply_static_enrichments(conn, stats)

    # Step 3: Email domain extraction
    logger.info("Step 3/7: Email domain extraction")
    _extract_email_domains(conn, stats)

    # Step 4: Domain name-match validation
    logger.info("Step 4/7: Domain name-match validation")
    _validate_domain_names(conn, stats)

    # Step 5: Search-based domain discovery
    if skip_search:
        logger.info("Step 5/7: Search-based discovery SKIPPED (--skip-search)")
    else:
        logger.info("Step 5/7: Search-based domain discovery")
        _search_missing_domains(conn, stats, search_delay, force)

    # Step 6: Domain deduplication
    logger.info("Step 6/7: Domain deduplication")
    domain_count = populate_domains(conn)
    logger.info("Populated {} unique domains", domain_count)

    # Step 7: Summary
    stats["ready_for_scan"] = len(
        conn.execute("SELECT 1 FROM domains WHERE ready_for_scan = 1").fetchall()
    )
    stats["no_domain"] = len(
        conn.execute("SELECT 1 FROM companies WHERE domain = '' AND discard_reason = ''").fetchall()
    )

    # Integrity check: warn if stale filter flags exist
    filtered_count = conn.execute(
        "SELECT COUNT(*) as c FROM companies WHERE discard_reason LIKE 'filtered:%'"
    ).fetchone()["c"]
    if filtered_count > 0:
        logger.warning(
            "DB contains {} companies with stale filter flags (discard_reason='filtered:...'). "
            "These were set by the removed filter step. The domains table may have incorrect "
            "ready_for_scan values. Run: UPDATE companies SET discard_reason = '' "
            "WHERE discard_reason LIKE 'filtered:%' then re-run populate_domains().",
            filtered_count,
        )

    # Checkpoint WAL so the .db file is self-contained (safe for git commit)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return stats


def _apply_static_enrichments(conn: sqlite3.Connection, stats: dict) -> None:
    """Step 2: company form, industry lookup, GDPR flag, contactable, free webmail."""
    form_map = load_company_forms()
    industry_map = load_industry_codes()
    gdpr_codes = load_gdpr_industry_codes()
    webmail_set = load_free_webmail()

    rows = conn.execute(
        "SELECT cvr, company_form, industry_code, ad_protected, email FROM companies"
    ).fetchall()

    updates = []
    for row in rows:
        update: dict = {"cvr": row["cvr"]}

        # Company form normalization
        update["company_form_short"] = normalize_company_form(
            row["company_form"], form_map
        )

        # Industry English name
        update["industry_name_en"] = lookup_industry_name(
            row["industry_code"], industry_map
        )

        # Contactable
        update["contactable"] = 0 if row["ad_protected"] else 1

        # GDPR industry flag
        is_gdpr, reason = check_gdpr_industry(row["industry_code"], gdpr_codes)
        update["gdpr_industry_flag"] = int(is_gdpr)
        update["gdpr_industry_reason"] = reason
        if is_gdpr:
            stats["gdpr_flagged"] += 1

        if not row["ad_protected"]:
            stats["contactable"] += 1

        # Email domain + free webmail
        email = row["email"] or ""
        if email and "@" in email:
            email_domain = email.rsplit("@", 1)[1].strip().lower()
            update["email_domain"] = email_domain
            update["is_free_webmail"] = int(is_free_webmail(email_domain, webmail_set))
        else:
            update["email_domain"] = ""
            update["is_free_webmail"] = 0

        updates.append(update)

    updated = update_enrichments(conn, updates)
    logger.info("Enriched {} companies with static data", updated)


def _extract_email_domains(conn: sqlite3.Connection, stats: dict) -> None:
    """Step 3: set domain from email for non-webmail companies."""
    rows = conn.execute(
        "SELECT cvr, email, email_domain, is_free_webmail FROM companies "
        "WHERE email != '' AND is_free_webmail = 0 AND email_domain != ''"
    ).fetchall()

    for row in rows:
        domain = row["email_domain"]
        update_domain(conn, row["cvr"], domain, "email", 0)
        log_enrichment(conn, row["cvr"], "email_extract", row["email"], domain, True)
        stats["email_derived"] += 1


def _validate_domain_names(conn: sqlite3.Connection, stats: dict) -> None:
    """Step 4: compare domain to company name, set domain_verified."""
    rows = conn.execute(
        "SELECT cvr, domain, name FROM companies "
        "WHERE domain != '' AND domain_source = 'email'"
    ).fetchall()

    for row in rows:
        is_match, ratio = validate_domain_name_match(row["domain"], row["name"])
        conn.execute(
            "UPDATE companies SET domain_verified = ? WHERE cvr = ?",
            (int(is_match), row["cvr"]),
        )
        log_enrichment(
            conn, row["cvr"], "name_match",
            f"{row['domain']} vs {row['name']}",
            f"ratio={ratio:.3f}",
            is_match,
            f"verified={is_match}, ratio={ratio:.3f}",
        )
        if is_match:
            stats["domain_verified"] += 1

    conn.commit()


def _search_missing_domains(
    conn: sqlite3.Connection, stats: dict,
    delay: float, force: bool,
) -> None:
    """Step 5: use Claude API web search for companies without verified domains."""
    # Find candidates: no domain, or domain not verified
    rows = conn.execute(
        "SELECT cvr, name, city FROM companies "
        "WHERE (domain = '' OR domain_verified = 0) AND discard_reason = ''"
    ).fetchall()

    if not rows:
        logger.info("No companies need search-based domain discovery")
        return

    # Check which have already been searched (skip on re-run unless --force)
    already_searched = set()
    if not force:
        searched_rows = conn.execute(
            "SELECT DISTINCT cvr FROM enrichment_log WHERE step = 'web_search' AND success = 1"
        ).fetchall()
        already_searched = {r["cvr"] for r in searched_rows}

    candidates = [r for r in rows if r["cvr"] not in already_searched]
    skipped = len(rows) - len(candidates)
    stats["search_skipped"] = skipped

    if skipped:
        logger.info("Skipping {} already-searched companies (use --force to retry)", skipped)

    if not candidates:
        logger.info("No candidates for search-based discovery")
        return

    logger.info("Searching for domains for {} companies", len(candidates))

    for i, row in enumerate(candidates):
        try:
            domain, detail = search_company_domain(
                row["name"], row["city"], delay=delay,
            )
            success = bool(domain)
            log_enrichment(
                conn, row["cvr"], "web_search",
                f"{row['name']} in {row['city']}",
                domain,
                success,
                detail[:2000],  # truncate long responses
            )

            if domain:
                update_domain(conn, row["cvr"], domain, "search", 1)
                stats["search_derived"] += 1
                logger.info(
                    "Found domain via search: {} → {} ({}/{})",
                    row["name"], domain, i + 1, len(candidates),
                )
            else:
                logger.info(
                    "No domain found for: {} ({}/{})",
                    row["name"], i + 1, len(candidates),
                )

        except SearchError as exc:
            stats["search_errors"] += 1
            logger.warning("Search failed for {}: {}", row["name"], exc)
            log_enrichment(
                conn, row["cvr"], "web_search",
                f"{row['name']} in {row['city']}",
                "",
                False,
                str(exc),
            )


