"""Heimdall Lead Generation Pipeline — CLI entrypoint.

Usage:
    python -m pipeline.main                          # defaults: data/prospects/CVR-extract.xlsx
    python -m pipeline.main --input path/to/file.xlsx
    python -m pipeline.main --output path/to/output/
    python -m pipeline.main --filters path/to/filters.json
    python -m pipeline.main --skip-scan              # skip Layer 1 scanning (useful for testing ingestion only)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import BRIEFS_DIR, DATA_DIR, DEFAULT_FILTERS, DEFAULT_INPUT
from .cvr import Company, derive_domains, read_excel
from .filters import apply_post_scan_filters, apply_pre_scan_filters, load_filters
from .resolver import resolve_domains
from .scanner import ScanResult, scan_domains
from .bucketer import assign_buckets
from .agency_detector import detect_agencies
from .brief_generator import generate_brief
from .logging_config import setup_logging
from .output import write_agency_briefs, write_briefs, write_csv
from loguru import logger


def run(
    input_path: Path,
    output_dir: Path,
    briefs_dir: Path,
    filters_path: Path,
    skip_scan: bool = False,
    confirmed: bool = False,
) -> None:
    """Execute the full lead generation pipeline."""
    pipeline_start = time.monotonic()

    # Step 1: Read CVR data
    logger.info("=== Step 1: Reading CVR data from %s ===", input_path.name)
    companies = read_excel(input_path)
    if not companies:
        logger.error("No companies found in input file")
        return

    # Step 2: Load and apply pre-scan filters
    logger.info("=== Step 2: Applying pre-scan filters ===")
    filters = load_filters(filters_path)
    companies = apply_pre_scan_filters(companies, filters)

    # Step 3: Derive website domains from email addresses
    logger.info("=== Step 3: Deriving website domains ===")
    companies = derive_domains(companies)

    # Step 4: Resolve domains (check website exists + robots.txt)
    logger.info("=== Step 4: Resolving domains ===")
    companies = resolve_domains(companies)

    # Step 5: Layer 1 scanning
    scan_results: dict[str, ScanResult] = {}
    if not skip_scan:
        logger.info("=== Step 5: Layer 1 scanning ===")
        scan_results = scan_domains(companies, confirmed=confirmed)
    else:
        logger.info("=== Step 5: Skipping Layer 1 scan (--skip-scan) ===")

    # Step 6: Bucketing
    logger.info("=== Step 6: Assigning buckets ===")
    buckets = assign_buckets(companies, scan_results)

    # Step 7: Apply post-scan filters (bucket)
    logger.info("=== Step 7: Applying post-scan filters ===")
    companies = apply_post_scan_filters(companies, buckets, filters)

    # Step 8: Agency detection
    logger.info("=== Step 8: Agency detection ===")
    agency_briefs = detect_agencies(companies, scan_results, buckets)

    # Step 9: Generate per-site briefs (includes evidence-based GDPR determination)
    logger.info("=== Step 9: Generating briefs (with GDPR determination) ===")
    site_briefs: dict[str, dict] = {}
    for company in companies:
        if company.discarded or not company.website_domain:
            continue
        scan = scan_results.get(company.website_domain)
        if not scan:
            continue
        bucket = buckets.get(company.cvr, "D")
        brief = generate_brief(company, scan, bucket)
        site_briefs[company.website_domain] = brief

    # Step 10: Write outputs
    logger.info("=== Step 10: Writing outputs ===")
    csv_path = write_csv(companies, buckets, site_briefs, scan_results, output_dir)
    brief_count = write_briefs(site_briefs, briefs_dir)
    agency_count = write_agency_briefs(agency_briefs, output_dir)

    # Summary
    pipeline_end = time.monotonic()
    total = len(companies)
    discarded = sum(1 for c in companies if c.discarded)
    active = total - discarded
    gdpr_count = sum(1 for b in site_briefs.values() if b.get("gdpr_sensitive"))
    logger.info("=== Pipeline complete ===")
    logger.info("Total companies: %d", total)
    logger.info("Discarded: %d", discarded)
    logger.info("Active prospects: %d", active)
    logger.info("GDPR-sensitive (evidence-based): %d", gdpr_count)
    logger.info("Site briefs generated: %d", brief_count)
    logger.info("Agency briefs generated: %d", agency_count)
    logger.info("CSV output: %s", csv_path)

    logger.bind(context={
        "total_companies": total,
        "discarded": discarded,
        "active": active,
        "gdpr_sensitive": gdpr_count,
        "briefs_generated": brief_count,
        "agency_briefs": agency_count,
        "duration_ms": int((pipeline_end - pipeline_start) * 1000),
    }).info("pipeline_complete")


def main():
    parser = argparse.ArgumentParser(description="Heimdall Lead Generation Pipeline")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to CVR Excel export")
    parser.add_argument("--output", type=Path, default=DATA_DIR, help="Output directory for CSV and agency briefs")
    parser.add_argument("--briefs", type=Path, default=BRIEFS_DIR, help="Output directory for per-site JSON briefs")
    parser.add_argument("--filters", type=Path, default=DEFAULT_FILTERS, help="Path to filters JSON file")
    parser.add_argument("--skip-scan", action="store_true", help="Skip Layer 1 scanning (test ingestion only)")
    parser.add_argument("--confirmed", action="store_true", help="Skip interactive confirmation (operator has pre-reviewed)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--log-format", choices=["text", "json"], default="text", help="Log output format")
    args = parser.parse_args()

    setup_logging(
        level="DEBUG" if args.verbose else "INFO",
        fmt=args.log_format,
    )

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
        sys.exit(1)

    run(
        input_path=args.input,
        output_dir=args.output,
        briefs_dir=args.briefs,
        filters_path=args.filters,
        skip_scan=args.skip_scan,
        confirmed=args.confirmed,
    )


if __name__ == "__main__":
    main()
