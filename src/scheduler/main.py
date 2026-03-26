"""Scheduler entry point — create scan jobs from CVR data or client schedules."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from src.scheduler.job_creator import JobCreator

log = logging.getLogger(__name__)

DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
DEFAULT_INPUT_PATH = Path("data/prospects/CVR-extract.xlsx")
DEFAULT_FILTERS_PATH = Path("config/filters.json")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Heimdall scheduler — push scan jobs to Redis",
    )
    parser.add_argument(
        "--mode",
        choices=["prospect", "scheduled"],
        required=True,
        help="prospect: one-shot from CVR data. scheduled: APScheduler loop (not yet implemented).",
    )
    parser.add_argument(
        "--confirmed",
        action="store_true",
        help="Skip interactive confirmation prompt.",
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    args = _parse_args(argv)

    if args.mode == "scheduled":
        log.error("Scheduled mode is not yet implemented.")
        return 1

    # -- prospect mode --
    if not args.input.exists():
        log.error("Input file not found: %s", args.input)
        return 1

    if not args.confirmed:
        answer = input(
            f"Create prospect jobs from {args.input}? [y/N] "
        ).strip().lower()
        if answer != "y":
            log.info("Aborted by user.")
            return 0

    creator = JobCreator(redis_url=args.redis_url)

    try:
        count = creator.create_prospect_jobs(args.input, args.filters)
    except Exception:
        log.exception("Failed to create prospect jobs")
        return 1

    log.info("Done — %d jobs pushed to Redis", count)
    return count


if __name__ == "__main__":
    sys.exit(main())
