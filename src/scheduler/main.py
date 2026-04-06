"""Scheduler entry point — create scan jobs from CVR data or client schedules."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from loguru import logger

from src.prospecting.logging_config import setup_logging
from src.scheduler.job_creator import JobCreator

DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_INPUT_PATH = Path(os.environ.get("INPUT_DIR", "/data/input")) / "CVR-extract.xlsx"
DEFAULT_FILTERS_PATH = Path("config/filters.json")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Heimdall scheduler — push scan jobs to Redis",
    )
    parser.add_argument(
        "--mode",
        choices=["prospect", "scheduled", "daemon"],
        required=True,
        help="prospect: one-shot from CVR data. daemon: BRPOP loop for operator commands. scheduled: not yet implemented.",
    )
    parser.add_argument(
        "--confirmed",
        action="store_true",
        help="Skip interactive confirmation prompt.",
    )
    parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip the subfinder batch enrichment phase (prospect mode only).",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Path to CVR Excel file (prospect mode only).",
    )
    parser.add_argument(
        "--filters",
        type=Path,
        default=DEFAULT_FILTERS_PATH,
        help="Path to filters JSON file.",
    )
    parser.add_argument(
        "--redis-url",
        default=DEFAULT_REDIS_URL,
        help="Redis connection URL.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the scheduler. Returns the number of jobs created (or 1 on error)."""
    setup_logging(level="INFO")

    args = _parse_args(argv)

    from src.logging.redis_sink import add_redis_sink
    add_redis_sink(args.redis_url)

    if args.mode == "daemon":
        from src.scheduler.daemon import run_daemon
        run_daemon(args.redis_url, args.input, args.filters)
        return 0

    if args.mode == "scheduled":
        logger.error("Scheduled mode is not yet implemented.")
        return 1

    # -- prospect mode --
    if not args.input.exists():
        logger.error("Input file not found: {}", args.input)
        return 1

    if not args.confirmed:
        answer = input(
            f"Create prospect jobs from {args.input}? [y/N] "
        ).strip().lower()
        if answer != "y":
            logger.info("Aborted by user.")
            return 0

    creator = JobCreator(redis_url=args.redis_url)

    # Prevent concurrent schedulers (deploy scheduler + pipeline scheduler)
    lock_acquired = creator._conn.set("scheduler:lock", "1", nx=True, ex=3600)
    if not lock_acquired:
        logger.error("Another scheduler is already running — aborting to prevent duplicate jobs")
        return 1

    try:
        # Phase 1: Extract domains
        domains = creator.extract_prospect_domains(args.input, args.filters)
        if not domains:
            logger.info("No domains extracted — nothing to do")
            return 0

        # Phase 2: Enrichment pre-scan (unless skipped)
        if not args.skip_enrichment:
            logger.info("Phase 1/2: Starting subfinder batch enrichment for {} domains", len(domains))
            enrichment_count = creator.create_enrichment_jobs(domains)
            if enrichment_count > 0:
                enrichment_ok = creator.wait_for_enrichment(timeout=3600)
                if not enrichment_ok:
                    logger.warning(
                        "Enrichment did not complete within timeout — "
                        "proceeding with scan jobs (subfinder will run per-domain for uncached domains)"
                    )
            logger.info("Phase 1/2: Enrichment phase complete")
        else:
            logger.info("Enrichment phase skipped (--skip-enrichment)")

        # Phase 3: Create per-domain scan jobs
        logger.info("Phase 2/2: Creating per-domain scan jobs for {} domains", len(domains))
        count = creator.create_scan_jobs_for_domains(domains)

    except Exception:
        logger.opt(exception=True).error("Failed to create prospect jobs")
        return 1
    finally:
        creator._conn.delete("scheduler:lock")

    logger.info("Done — {} jobs pushed to Redis", count)
    return count


if __name__ == "__main__":
    sys.exit(main())
