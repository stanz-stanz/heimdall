"""Worker entry point: validate Valdi, connect to Redis, process scan jobs.

Run as::

    python -m src.worker.main [--redis-url redis://localhost:6379/0] [--log-format json]

The worker blocks on BRPOP waiting for jobs on the ``queue:scan`` Redis list.
Each job is a JSON object with at least a ``domain`` key.  Results are written
to ``/data/results/{client_id}/{domain}/{date}.json`` and a ``scan-complete``
event is published via Redis pub/sub.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import redis

from src.prospecting.logging_config import setup_logging
from src.prospecting.scanner import _init_scan_type_map, _validate_approval_tokens

from .cache import ScanCache
from .scan_job import execute_scan_job

log = logging.getLogger(__name__)

# Module-level flag for graceful shutdown
_shutdown_requested: bool = False


def _handle_signal(signum: int, _frame: object) -> None:  # pragma: no cover
    """Set the shutdown flag on SIGTERM / SIGINT."""
    global _shutdown_requested
    _shutdown_requested = True
    sig_name = signal.Signals(signum).name
    log.info("Received %s — shutting down after current job", sig_name)


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heimdall scan worker")
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        help="Redis connection URL (default: redis://localhost:6379/0)",
    )
    parser.add_argument(
        "--log-format",
        choices=("text", "json"),
        default=os.environ.get("LOG_FORMAT", "json"),
        help="Log output format (default: json)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        help="Log level (default: INFO)",
    )
    parser.add_argument(
        "--results-dir",
        default=os.environ.get("RESULTS_DIR", "/data/results"),
        help="Base directory for result JSON files (default: /data/results)",
    )
    return parser.parse_args(argv)


def _write_result(base_dir: str, client_id: str, domain: str, result: dict) -> Path:
    """Write scan result JSON to disk.  Creates directories as needed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(base_dir) / client_id / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / f"{today}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    return filepath


def main(argv: Optional[list] = None) -> None:
    """Worker main loop: validate Valdi, connect to Redis, process jobs."""
    args = _parse_args(argv)
    setup_logging(level=args.log_level, fmt=args.log_format)

    log.info("Heimdall worker starting")

    # ------------------------------------------------------------------
    # 1. Validate Valdi approval tokens (fail-fast)
    # ------------------------------------------------------------------
    _init_scan_type_map()
    approvals = _validate_approval_tokens()
    if approvals is None:
        log.error("BLOCKED — Valdi approval token validation failed. Worker refusing to start.")
        sys.exit(1)
    log.info("Valdi approval tokens validated successfully")

    # ------------------------------------------------------------------
    # 2. Connect to Redis
    # ------------------------------------------------------------------
    try:
        redis_conn = redis.Redis.from_url(
            args.redis_url,
            decode_responses=True,
            socket_connect_timeout=10,
        )
        redis_conn.ping()
    except (redis.ConnectionError, redis.TimeoutError, OSError) as exc:
        log.error("Cannot connect to Redis at %s: %s", args.redis_url, exc)
        sys.exit(1)
    log.info("Connected to Redis at %s", args.redis_url)

    # ------------------------------------------------------------------
    # 3. Create ScanCache
    # ------------------------------------------------------------------
    cache = ScanCache(redis_url=args.redis_url)

    # ------------------------------------------------------------------
    # 4. Register signal handlers for graceful shutdown
    # ------------------------------------------------------------------
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # ------------------------------------------------------------------
    # 5. BRPOP loop
    # ------------------------------------------------------------------
    log.info("Worker ready — waiting for jobs on queue:scan")

    while not _shutdown_requested:
        try:
            item = redis_conn.brpop("queue:scan", timeout=30)
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            log.warning("Redis BRPOP error: %s — retrying", exc)
            continue

        if item is None:
            # Timeout, no job available — loop back and check shutdown flag
            continue

        _queue_name, raw_job = item

        try:
            job = json.loads(raw_job)
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("Malformed job JSON: %s — skipping", exc)
            continue

        domain = job.get("domain", "unknown")
        client_id = job.get("client_id", "prospect")
        job_id = job.get("job_id", "")

        log.info(
            "job_started",
            extra={"context": {"job_id": job_id, "domain": domain, "client_id": client_id}},
        )

        try:
            result = execute_scan_job(job, cache)
        except Exception:
            log.exception("Unhandled error processing job for %s", domain)
            continue

        # Write result to disk
        try:
            filepath = _write_result(args.results_dir, client_id, domain, result)
            log.info(
                "result_written",
                extra={"context": {"domain": domain, "path": str(filepath)}},
            )
        except OSError as exc:
            log.error("Failed to write result for %s: %s", domain, exc)

        # Publish scan-complete event
        try:
            event_payload = json.dumps({
                "job_id": job_id,
                "domain": domain,
                "client_id": client_id,
                "status": result.get("status", "unknown"),
            })
            redis_conn.publish("scan-complete", event_payload)
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            log.warning("Failed to publish scan-complete for %s: %s", domain, exc)

        log.info(
            "job_completed",
            extra={
                "context": {
                    "job_id": job_id,
                    "domain": domain,
                    "status": result.get("status"),
                    "cache_stats": result.get("cache_stats"),
                    "total_ms": int(result.get("timing", {}).get("total", 0) * 1000),
                },
            },
        )

    log.info("Worker shut down gracefully")


if __name__ == "__main__":
    main()
