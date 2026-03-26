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
import logging
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

log = logging.getLogger("pipeline")


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
    log.info("=== Step 1: Reading CVR data from %s ===", input_path.name)
    companies = read_excel(input_path)
    if not companies:
        log.error("No companies found in input file")
        return

    # Step 2: Load and apply pre-scan filters
    log.info("=== Step 2: Applying pre-scan filters ===")
    filters = load_filters(filters_path)
    companies = apply_pre_scan_filters(companies, filters)

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
        scan_results = scan_domains(companies, confirmed=confirmed)
    else:
        log.info("=== Step 5: Skipping Layer 1 scan (--skip-scan) ===")

    # Step 6: Bucketing
    log.info("=== Step 6: Assigning buckets ===")
    buckets = assign_buckets(companies, scan_results)

    # Step 7: Apply post-scan filters (bucket)
    log.info("=== Step 7: Applying post-scan filters ===")
    companies = apply_post_scan_filters(companies, buckets, filters)

    # Step 8: Agency detection
    log.info("=== Step 8: Agency detection ===")
    agency_briefs = detect_agencies(companies, scan_results, buckets)

    # Step 9: Generate per-site briefs (includes evidence-based GDPR determination)
    log.info("=== Step 9: Generating briefs (with GDPR determination) ===")
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
    log.info("=== Step 10: Writing outputs ===")
    csv_path = write_csv(companies, buckets, site_briefs, scan_results, output_dir)
    brief_count = write_briefs(site_briefs, briefs_dir)
    agency_count = write_agency_briefs(agency_briefs, output_dir)

    # Summary
    pipeline_end = time.monotonic()
    total = len(companies)
    discarded = sum(1 for c in companies if c.discarded)
    active = total - discarded
    gdpr_count = sum(1 for b in site_briefs.values() if b.get("gdpr_sensitive"))
    log.info("=== Pipeline complete ===")
    log.info("Total companies: %d", total)
    log.info("Discarded: %d", discarded)
    log.info("Active prospects: %d", active)
    log.info("GDPR-sensitive (evidence-based): %d", gdpr_count)
    log.info("Site briefs generated: %d", brief_count)
    log.info("Agency briefs generated: %d", agency_count)
    log.info("CSV output: %s", csv_path)

    log.info(
        "pipeline_complete",
        extra={"context": {
            "total_companies": total,
            "discarded": discarded,
            "active": active,
            "gdpr_sensitive": gdpr_count,
            "briefs_generated": brief_count,
            "agency_briefs": agency_count,
            "duration_ms": int((pipeline_end - pipeline_start) * 1000),
        }},
    )


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
        log.error("Input file not found: %s", args.input)
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
