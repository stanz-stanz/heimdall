"""Worker entry point: validate Valdi, connect to Redis, process scan jobs.

Run as::

    python -m src.worker.main [--redis-url redis://localhost:6379/0] [--log-format json]

The worker blocks on BRPOP waiting for jobs on ``queue:enrichment`` and
``queue:scan`` Redis lists (enrichment has priority).  Scan job results are
written to ``/data/results/{client_id}/{domain}/{date}.json`` and a
``scan-complete`` event is published via Redis pub/sub.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import redis

from src.prospecting.config import ENRICHMENT_RETRY_LIMIT
from src.prospecting.logging_config import setup_logging
from src.prospecting.scanner import _init_scan_type_map, _run_subfinder, _validate_approval_tokens
from src.scheduler.job_creator import ENRICHMENT_COUNTER_KEY

from src.consent.validator import check_consent

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
    parser.add_argument(
        "--ct-db",
        default=os.environ.get("CT_DB_PATH", "/data/ct/certificates.db"),
        help="Path to local CT certificate database (default: /data/ct/certificates.db)",
    )
    parser.add_argument(
        "--client-data-dir",
        default=os.environ.get("CLIENT_DATA_DIR", "/data/clients"),
        help="Base directory for client authorisation data (default: /data/clients)",
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


def _execute_enrichment_job(
    job: dict[str, Any],
    cache: ScanCache,
    redis_conn: redis.Redis,
) -> None:
    """Execute a batch subfinder enrichment job.

    Runs subfinder in batch mode (-dL) for all domains in the job, then
    stores results in the cache with the same format that scan_job.py
    expects from ``_cached_or_run("subfinder", _run_subfinder, [domain])``.

    Always increments the enrichment counter, even on failure, to avoid
    hanging the scheduler's wait_for_enrichment loop.
    """
    batch_index = job.get("batch_index", 0)
    total_batches = job.get("total_batches", 1)
    stagger_delay = job.get("stagger_delay", 0)
    domains = job.get("domains", [])
    job_id = job.get("job_id", "")

    log.info(
        "enrichment_job_started",
        extra={
            "context": {
                "job_id": job_id,
                "batch_index": batch_index,
                "total_batches": total_batches,
                "domain_count": len(domains),
                "stagger_delay": stagger_delay,
            },
        },
    )

    t0 = time.monotonic()

    try:
        # Stagger to avoid API rate-limit collisions between workers
        if stagger_delay > 0:
            log.info(
                "Staggering enrichment batch %d by %ds",
                batch_index,
                stagger_delay,
            )
            for _ in range(stagger_delay):
                if _shutdown_requested:
                    log.info("Shutdown requested during stagger — aborting enrichment batch %d", batch_index)
                    return  # finally block will increment counter
                time.sleep(1)

        # Run subfinder in batch mode
        results = _run_subfinder_with_retry(domains)

        # Store results per domain in cache — format must match what
        # _cached_or_run("subfinder", _run_subfinder, [domain]) would store.
        # _run_subfinder([domain]) returns {domain: [subdomains]}.
        # _cached_or_run stores the return value directly via cache.set().
        cached_count = 0
        for domain in domains:
            domain_result = {domain: results.get(domain, [])}
            cache.set("subfinder", domain, domain_result)
            cached_count += 1

        elapsed = time.monotonic() - t0
        log.info(
            "enrichment_job_completed",
            extra={
                "context": {
                    "job_id": job_id,
                    "batch_index": batch_index,
                    "domain_count": len(domains),
                    "cached_count": cached_count,
                    "subdomains_found": sum(len(v) for v in results.values()),
                    "duration_ms": int(elapsed * 1000),
                },
            },
        )
    except Exception:
        elapsed = time.monotonic() - t0
        log.exception(
            "enrichment_job_failed",
            extra={
                "context": {
                    "job_id": job_id,
                    "batch_index": batch_index,
                    "domain_count": len(domains),
                    "duration_ms": int(elapsed * 1000),
                },
            },
        )
    finally:
        # Always increment — don't hang the scheduler
        try:
            redis_conn.incr(ENRICHMENT_COUNTER_KEY)
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            log.warning(
                "Failed to increment enrichment counter: %s", exc
            )


def _run_subfinder_with_retry(
    domains: list[str],
    retry_limit: int = ENRICHMENT_RETRY_LIMIT,
) -> dict[str, list[str]]:
    """Run subfinder with retry on failure."""
    last_error: Exception | None = None

    for attempt in range(1 + retry_limit):
        try:
            results = _run_subfinder(domains)
            if attempt > 0:
                log.info(
                    "subfinder succeeded on retry attempt %d", attempt
                )
            return results
        except Exception as exc:
            last_error = exc
            if attempt < retry_limit:
                log.warning(
                    "subfinder failed (attempt %d/%d): %s — retrying",
                    attempt + 1,
                    1 + retry_limit,
                    exc,
                )
            else:
                log.error(
                    "subfinder failed after %d attempts: %s",
                    1 + retry_limit,
                    exc,
                )

    # Return empty results rather than raising — the enrichment job
    # must always complete so the counter gets incremented
    return {}


def main(argv: Optional[list] = None) -> None:
    """Worker main loop: validate Valdi, connect to Redis, process jobs."""
    args = _parse_args(argv)
    setup_logging(level=args.log_level, fmt=args.log_format)

    log.info("Heimdall worker starting")

    # ------------------------------------------------------------------
    # 0. Check CT database availability
    # ------------------------------------------------------------------
    ct_db_path = args.ct_db
    if os.path.isfile(ct_db_path):
        log.info("CT database found at %s", ct_db_path)
    else:
        log.warning("CT database not found at %s — crt.sh queries will return empty results", ct_db_path)

    # Set module-level CT_DB_PATH for scan_job to use
    from .scan_job import _CT_DB_PATH as _unused  # noqa: F401
    import src.worker.scan_job as _scan_job_mod
    _scan_job_mod._CT_DB_PATH = ct_db_path

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
    # 5. BRPOP loop — enrichment queue has priority over scan queue
    # ------------------------------------------------------------------
    log.info("Worker ready — waiting for jobs on queue:enrichment, queue:scan")

    while not _shutdown_requested:
        try:
            item = redis_conn.brpop(
                ["queue:enrichment", "queue:scan"], timeout=30
            )
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            log.warning("Redis BRPOP error: %s — retrying", exc)
            continue

        if item is None:
            # Timeout, no job available — loop back and check shutdown flag
            continue

        queue_name, raw_job = item

        try:
            job = json.loads(raw_job)
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("Malformed job JSON: %s — skipping", exc)
            continue

        job_type = job.get("job_type", "scan")
        job_id = job.get("job_id", "")

        # ------------------------------------------------------------------
        # Route: enrichment job
        # ------------------------------------------------------------------
        if job_type == "enrichment":
            log.info(
                "enrichment_job_received",
                extra={"context": {"job_id": job_id, "queue": queue_name}},
            )
            _execute_enrichment_job(job, cache, redis_conn)
            continue

        # ------------------------------------------------------------------
        # Route: scan job (default)
        # ------------------------------------------------------------------
        domain = job.get("domain", "unknown")
        client_id = job.get("client_id", "prospect")

        log.info(
            "job_started",
            extra={"context": {"job_id": job_id, "domain": domain, "client_id": client_id}},
        )

        # Gate 2: Consent check (Valdí) — Level 1+ requires valid consent
        # SAFETY: if the level field is missing, malformed, or ambiguous,
        # we BLOCK rather than default to Level 0. A missing field is a
        # bug, not a reason to skip consent checks.
        raw_level = job.get("level")
        if raw_level is None:
            # Prospecting jobs (Level 0) always set level=0 explicitly.
            # A missing level field is unexpected — default to 0 for
            # backward compatibility with existing prospect jobs, but
            # log a warning so it gets fixed.
            job_level = 0
            log.warning(
                "gate2_missing_level",
                extra={"context": {
                    "job_id": job_id, "domain": domain,
                    "client_id": client_id,
                    "message": "Job has no 'level' field — defaulting to 0",
                }},
            )
        elif not isinstance(raw_level, int) or isinstance(raw_level, bool):
            log.error(
                "gate2_invalid_level",
                extra={"context": {
                    "job_id": job_id, "domain": domain,
                    "client_id": client_id,
                    "raw_level": str(raw_level),
                    "type": type(raw_level).__name__,
                }},
            )
            continue
        else:
            job_level = raw_level

        try:
            consent = check_consent(
                client_dir=Path(args.client_data_dir),
                client_id=client_id,
                domain=domain,
                level_requested=job_level,
            )
        except Exception:
            # SAFETY: if consent check crashes for ANY reason, BLOCK.
            log.exception(
                "gate2_crash — scan BLOCKED",
                extra={"context": {
                    "job_id": job_id, "domain": domain,
                    "client_id": client_id, "level_requested": job_level,
                }},
            )
            continue

        log.info(
            "gate2_consent_check",
            extra={"context": {
                "job_id": job_id, "domain": domain, "client_id": client_id,
                "level_requested": job_level,
                "level_authorised": consent.level_authorised,
                "allowed": consent.allowed, "reason": consent.reason,
                "authorised_by_role": consent.authorised_by_role,
            }},
        )
        if not consent.allowed:
            log.warning(
                "gate2_blocked",
                extra={"context": {
                    "job_id": job_id, "domain": domain,
                    "client_id": client_id, "reason": consent.reason,
                }},
            )
            continue

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
                    "total_ms": int(result.get("timing", {}).get("total_ms", 0)),
                },
            },
        )

    log.info("Worker shut down gracefully")


if __name__ == "__main__":
    main()
