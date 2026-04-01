"""CLI entrypoint: python -m src.enrichment"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .pipeline import run_pipeline


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Heimdall CVR enrichment — preprocess CVR data into SQLite",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/input/CVR-extract.xlsx"),
        help="Path to CVR Excel file.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/enriched/companies.db"),
        help="Path to output SQLite database.",
    )
    parser.add_argument(
        "--filters",
        type=Path,
        default=Path("config/filters.json"),
        help="Path to filters JSON file.",
    )
    parser.add_argument(
        "--skip-search",
        action="store_true",
        help="Skip Claude API web search (email-only domain derivation).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-enrich all companies, ignoring previous enrichment.",
    )
    parser.add_argument(
        "--search-delay",
        type=float,
        default=0.5,
        help="Seconds between search API calls (default: 0.5).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if not args.input.exists():
        logging.error("Input file not found: %s", args.input)
        return 1

    stats = run_pipeline(
        input_path=args.input,
        db_path=args.db,
        filters_path=args.filters,
        skip_search=args.skip_search,
        force=args.force,
        search_delay=args.search_delay,
    )

    # Summary report
    print(f"\n{'=' * 60}")
    print(f"  ENRICHMENT SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total ingested:      {stats['total_ingested']:>6d}")
    print(f"  Email-derived:       {stats['email_derived']:>6d}")
    print(f"  Search-derived:      {stats['search_derived']:>6d}")
    print(f"  Domain verified:     {stats['domain_verified']:>6d}")
    print(f"  GDPR industry flag:  {stats['gdpr_flagged']:>6d}")
    print(f"  Contactable:         {stats['contactable']:>6d}")
    print(f"  Ready for scan:      {stats['ready_for_scan']:>6d}")
    print(f"  No domain found:     {stats['no_domain']:>6d}")
    if not args.skip_search:
        print(f"  Search skipped:      {stats['search_skipped']:>6d}")
        print(f"  Search errors:       {stats['search_errors']:>6d}")
    print(f"{'=' * 60}")
    print(f"  Database: {args.db}")
    print(f"{'=' * 60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
