#!/usr/bin/env python3
"""Export worker scan results to prospect CSV + standalone brief files.

Reads from: data/results/{client_id}/{domain}/{date}.json (worker output)
Joins with: data/input/CVR-extract.xlsx (for contactable, industry_code)
Writes to:  data/output/prospects-list.csv + data/output/briefs/{domain}.json

Usage:
    python3 scripts/export_results.py [--results-dir DIR] [--output-dir DIR] [--cvr-file PATH]

Run after workers complete a scan batch to produce the deliverables.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_RESULTS_DIR = "data/results"
DEFAULT_OUTPUT_DIR = "data/output"
DEFAULT_CVR_FILE = "data/input/CVR-extract.xlsx"


def _load_cvr_lookup(cvr_path: str) -> dict:
    """Load CVR extract and build a domain → company lookup.

    Returns a dict keyed by derived domain with contactable, industry_code, etc.
    """
    cvr_file = Path(cvr_path)
    if not cvr_file.is_file():
        log.warning("CVR file not found: %s — contactable field will be empty", cvr_path)
        return {}

    try:
        import openpyxl
    except ImportError:
        log.warning("openpyxl not installed — contactable field will be empty")
        return {}

    try:
        from src.prospecting.cvr import read_companies
        from src.prospecting.config import FREE_WEBMAIL

        companies = read_companies(cvr_file)
        lookup = {}
        for c in companies:
            # Derive domain the same way the pipeline does
            if not c.email or "@" not in c.email:
                continue
            email_domain = c.email.split("@", 1)[1].strip().lower()
            if email_domain in FREE_WEBMAIL:
                continue
            lookup[email_domain] = {
                "cvr_number": c.cvr,
                "industry_code": c.industry_code,
                "contactable": not c.ad_protected,
                "company_name": c.name,
            }
        log.info("Loaded %d companies from CVR extract", len(lookup))
        return lookup
    except Exception as exc:
        log.warning("Failed to load CVR data: %s", exc)
        return {}


def _find_latest_result(domain_dir: Path) -> dict | None:
    """Find the most recent result JSON in a domain directory."""
    json_files = sorted(domain_dir.glob("*.json"), reverse=True)
    if not json_files:
        return None
    try:
        with open(json_files[0], "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def export(results_dir: str, output_dir: str, cvr_file: str = DEFAULT_CVR_FILE) -> dict:
    """Read all worker results and produce CSV + brief files.

    Returns a summary dict with counts.
    """
    results_path = Path(results_dir)
    output_path = Path(output_dir)
    briefs_path = output_path / "briefs"
    briefs_path.mkdir(parents=True, exist_ok=True)

    # Load CVR data for contactable/industry_code enrichment
    cvr_lookup = _load_cvr_lookup(cvr_file)

    csv_rows = []
    brief_count = 0
    skipped = 0

    if not results_path.is_dir():
        log.error("Results directory not found: %s", results_path)
        return {"domains": 0, "briefs": 0, "skipped": 0}

    for client_dir in sorted(results_path.iterdir()):
        if not client_dir.is_dir():
            continue

        for domain_dir in sorted(client_dir.iterdir()):
            if not domain_dir.is_dir():
                continue
            domain = domain_dir.name

            result = _find_latest_result(domain_dir)
            if result is None or result.get("status") != "completed":
                skipped += 1
                continue

            brief = result.get("brief")
            if not brief:
                skipped += 1
                continue

            # Write standalone brief
            brief_file = briefs_path / f"{domain}.json"
            with open(brief_file, "w", encoding="utf-8") as f:
                json.dump(brief, f, indent=2, ensure_ascii=False)
            brief_count += 1

            # Enrich with CVR data
            cvr_data = cvr_lookup.get(domain, {})

            tech = brief.get("technology", {})
            ssl = tech.get("ssl", {})
            subs = brief.get("subdomains", {})

            csv_rows.append({
                "cvr_number": cvr_data.get("cvr_number", brief.get("cvr", "")),
                "company_name": brief.get("company_name", "") or cvr_data.get("company_name", ""),
                "website": brief.get("domain", domain),
                "bucket": brief.get("bucket", ""),
                "industry_code": cvr_data.get("industry_code", ""),
                "industry_name": brief.get("industry", ""),
                "gdpr_sensitive": brief.get("gdpr_sensitive", False),
                "contactable": cvr_data.get("contactable", ""),
                "cms": tech.get("cms", ""),
                "hosting": tech.get("hosting", ""),
                "ssl_valid": ssl.get("valid", ""),
                "ssl_expiry": ssl.get("expiry", ""),
                "subdomain_count": subs.get("count", 0),
                "findings_count": len(brief.get("findings", [])),
            })

    # Write CSV
    csv_path = output_path / "prospects-list.csv"
    fieldnames = [
        "cvr_number", "company_name", "website", "bucket",
        "industry_code", "industry_name", "gdpr_sensitive", "contactable",
        "cms", "hosting", "ssl_valid", "ssl_expiry", "subdomain_count",
        "findings_count",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    summary = {
        "domains": len(csv_rows),
        "briefs": brief_count,
        "skipped": skipped,
        "csv_path": str(csv_path),
        "cvr_enriched": sum(1 for r in csv_rows if r["contactable"] != ""),
    }
    log.info("export_complete", extra={"context": summary})
    return summary


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Export worker results to CSV + briefs")
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cvr-file", default=DEFAULT_CVR_FILE)
    args = parser.parse_args()

    summary = export(args.results_dir, args.output_dir, args.cvr_file)
    print(f"\nExported {summary['domains']} domains, {summary['briefs']} briefs, {summary['skipped']} skipped")
    print(f"CVR-enriched: {summary.get('cvr_enriched', 0)}")
    print(f"CSV: {summary['csv_path']}")


if __name__ == "__main__":
    main()
