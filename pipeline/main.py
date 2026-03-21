"""Heimdall Lead Generation Pipeline — CLI entrypoint.

Usage:
    python -m pipeline.main                          # defaults: CVR sample file, data/prospects/ output
    python -m pipeline.main --input path/to/file.xlsx
    python -m pipeline.main --output path/to/output/
    python -m pipeline.main --skip-scrape            # skip CVR website scraping for missing emails
    python -m pipeline.main --skip-scan              # skip Layer 1 scanning (useful for testing ingestion only)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pipeline.config import BRIEFS_DIR, DATA_DIR, DEFAULT_INPUT
from pipeline.cvr import Company, derive_domains, read_excel, scrape_missing_emails
from pipeline.resolver import resolve_domains
from pipeline.scanner import ScanResult, scan_domains
from pipeline.bucketer import assign_buckets
from pipeline.gdpr_filter import flag_gdpr_sensitive
from pipeline.agency_detector import detect_agencies
from pipeline.brief_generator import generate_brief
from pipeline.output import write_agency_briefs, write_briefs, write_csv

log = logging.getLogger("pipeline")


def run(
    input_path: Path,
    output_dir: Path,
    briefs_dir: Path,
    skip_scrape: bool = False,
    skip_scan: bool = False,
) -> None:
    """Execute the full lead generation pipeline."""

    # Step 1: Read CVR data
    log.info("=== Step 1: Reading CVR data from %s ===", input_path.name)
    companies = read_excel(input_path)
    if not companies:
        log.error("No companies found in input file")
        return

    # Step 2: Scrape missing emails from datacvr.virk.dk
    if not skip_scrape:
        log.info("=== Step 2: Scraping missing emails ===")
        companies = scrape_missing_emails(companies)
    else:
        log.info("=== Step 2: Skipping CVR scrape (--skip-scrape) ===")

    # Step 3: Derive website domains from email addresses
    log.info("=== Step 3: Deriving website domains ===")
    companies = derive_domains(companies)

    # Step 4: Resolve domains (check website exists + robots.txt)
    log.info("=== Step 4: Resolving domains ===")
    companies = resolve_domains(companies)

    # Step 5: Layer 1 scanning
    scan_results: dict[str, ScanResult] = {}
    if not skip_scan:
        log.info("=== Step 5: Layer 1 scanning ===")
        scan_results = scan_domains(companies)
    else:
        log.info("=== Step 5: Skipping Layer 1 scan (--skip-scan) ===")

    # Step 6: Bucketing
    log.info("=== Step 6: Assigning buckets ===")
    buckets = assign_buckets(companies, scan_results)

    # Step 7: GDPR filter
    log.info("=== Step 7: GDPR sensitivity filter ===")
    gdpr_flags = flag_gdpr_sensitive(companies)

    # Step 8: Agency detection
    log.info("=== Step 8: Agency detection ===")
    agency_briefs = detect_agencies(companies, scan_results, buckets)

    # Step 9: Generate per-site briefs
    log.info("=== Step 9: Generating briefs ===")
    site_briefs: dict[str, dict] = {}
    for company in companies:
        if company.discarded or not company.website_domain:
            continue
        scan = scan_results.get(company.website_domain)
        if not scan:
            continue
        gdpr_sensitive, _ = gdpr_flags.get(company.cvr, (False, ""))
        bucket = buckets.get(company.cvr, "D")
        brief = generate_brief(company, scan, bucket, gdpr_sensitive)
        site_briefs[company.website_domain] = brief

    # Step 10: Write outputs
    log.info("=== Step 10: Writing outputs ===")
    csv_path = write_csv(companies, buckets, gdpr_flags, scan_results, output_dir)
    brief_count = write_briefs(site_briefs, briefs_dir)
    agency_count = write_agency_briefs(agency_briefs, output_dir)

    # Summary
    total = len(companies)
    discarded = sum(1 for c in companies if c.discarded)
    active = total - discarded
    log.info("=== Pipeline complete ===")
    log.info("Total companies: %d", total)
    log.info("Discarded: %d", discarded)
    log.info("Active prospects: %d", active)
    log.info("Site briefs generated: %d", brief_count)
    log.info("Agency briefs generated: %d", agency_count)
    log.info("CSV output: %s", csv_path)


def main():
    parser = argparse.ArgumentParser(description="Heimdall Lead Generation Pipeline")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to CVR Excel export")
    parser.add_argument("--output", type=Path, default=DATA_DIR, help="Output directory for CSV and agency briefs")
    parser.add_argument("--briefs", type=Path, default=BRIEFS_DIR, help="Output directory for per-site JSON briefs")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip scraping datacvr.virk.dk for missing emails")
    parser.add_argument("--skip-scan", action="store_true", help="Skip Layer 1 scanning (test ingestion only)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.input.exists():
        log.error("Input file not found: %s", args.input)
        sys.exit(1)

    run(
        input_path=args.input,
        output_dir=args.output,
        briefs_dir=args.briefs,
        skip_scrape=args.skip_scrape,
        skip_scan=args.skip_scan,
    )


if __name__ == "__main__":
    main()
