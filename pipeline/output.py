"""Output writer: produce bucketed CSV and per-site JSON briefs."""

from __future__ import annotations

import csv
import json
import logging
from datetime import date
from pathlib import Path

from pipeline.config import BRIEFS_DIR, DATA_DIR, INDUSTRY_CODES_PATH
from pipeline.cvr import Company
from pipeline.scanner import ScanResult

log = logging.getLogger(__name__)


def _load_industry_codes() -> dict[str, str]:
    """Load industry code-to-English-name mapping from JSON."""
    if not INDUSTRY_CODES_PATH.exists():
        log.warning("Industry codes file not found: %s", INDUSTRY_CODES_PATH)
        return {}
    with open(INDUSTRY_CODES_PATH, encoding="utf-8") as f:
        return json.load(f)


def write_csv(
    companies: list[Company],
    buckets: dict[str, str],
    gdpr_flags: dict[str, tuple[bool, str]],
    scan_results: dict[str, ScanResult],
    output_dir: Path | None = None,
) -> Path:
    """Write the bucketed prospect list CSV."""
    output_dir = output_dir or DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    industry_codes = _load_industry_codes()

    filename = "prospects-list.csv"
    filepath = output_dir / filename

    fieldnames = [
        "cvr_number", "company_name", "website", "bucket", "industry_code",
        "industry_name", "gdpr_sensitive", "contactable", "cms", "hosting",
        "ssl_valid", "ssl_expiry", "subdomain_count", "risk_summary",
    ]

    rows = []
    for company in companies:
        if company.discarded or not company.website_domain:
            continue

        bucket = buckets.get(company.cvr, "D")
        gdpr_sensitive, _ = gdpr_flags.get(company.cvr, (False, ""))
        scan = scan_results.get(company.website_domain)

        row = {
            "cvr_number": company.cvr,
            "company_name": company.name,
            "website": company.website_domain,
            "bucket": bucket,
            "industry_code": company.industry_code,
            "industry_name": industry_codes.get(company.industry_code, company.industry_name),
            "gdpr_sensitive": gdpr_sensitive,
            "contactable": not company.ad_protected,
            "cms": scan.cms if scan else "",
            "hosting": scan.hosting if scan else "",
            "ssl_valid": scan.ssl_valid if scan else "",
            "ssl_expiry": scan.ssl_expiry if scan else "",
            "subdomain_count": len(scan.subdomains) if scan else 0,
            "risk_summary": "",
        }
        rows.append(row)

    # Sort: bucket A first, then B, E, C, D. Within each bucket, GDPR-sensitive first.
    bucket_order = {"A": 0, "B": 1, "E": 2, "C": 3, "D": 4}
    rows.sort(key=lambda r: (bucket_order.get(r["bucket"], 5), not r["gdpr_sensitive"], r["company_name"]))

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    log.info("Wrote %d rows to %s", len(rows), filepath)
    return filepath


def write_briefs(briefs: dict[str, dict], output_dir: Path | None = None) -> int:
    """Write per-site JSON briefs to individual files."""
    output_dir = output_dir or BRIEFS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for domain, brief in briefs.items():
        filepath = output_dir / f"{domain}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(brief, f, indent=2, ensure_ascii=False)
        count += 1

    log.info("Wrote %d site briefs to %s", count, output_dir)
    return count


def write_agency_briefs(agency_briefs: list[dict], output_dir: Path | None = None) -> int:
    """Write agency briefs to a single JSON file."""
    if not agency_briefs:
        return 0

    output_dir = output_dir or DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    filepath = output_dir / f"agency-briefs-{date.today().isoformat()}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(agency_briefs, f, indent=2, ensure_ascii=False)

    log.info("Wrote %d agency briefs to %s", len(agency_briefs), filepath)
    return len(agency_briefs)
