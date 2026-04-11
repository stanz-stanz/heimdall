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
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import redis
from loguru import logger

from src.consent.validator import check_consent
from src.prospecting.config import ENRICHMENT_RETRY_LIMIT
from src.core.logging_config import setup_logging
from src.prospecting.scanners.registry import (
    _init_scan_type_map,
    _validate_approval_tokens,
)
from src.prospecting.scanners.subfinder import run_subfinder
from src.scheduler.job_creator import ENRICHMENT_COUNTER_KEY

from .cache import ScanCache
from .scan_job import execute_scan_job

# Module-level flag for graceful shutdown
_shutdown_requested: bool = False

# Healthcheck file — touched after each idle poll and completed job so Docker
# can verify the worker is alive via a HEALTHCHECK instruction.
HEALTHCHECK_FILE = "/tmp/healthcheck"


def _handle_signal(signum: int, _frame: object) -> None:  # pragma: no cover
    """Set the shutdown flag on SIGTERM / SIGINT."""
    global _shutdown_requested
    _shutdown_requested = True
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down after current job", sig_name)


def _parse_args(argv: list | None = None) -> argparse.Namespace:
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
    parser.add_argument(
        "--max-level",
        type=int,
        default=int(os.environ.get("WORKER_MAX_LEVEL", "0")),
        help="Maximum scan level this worker handles (0=passive only, 1=active probing). Default: 0",
    )
    return parser.parse_args(argv)


def _write_result(base_dir: str, client_id: str, domain: str, result: dict) -> Path:
    """Write scan result JSON to disk.  Creates directories as needed."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
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
    expects from ``_cached_or_run("subfinder", run_subfinder, [domain])``.

    Always increments the enrichment counter, even on failure, to avoid
    hanging the scheduler's wait_for_enrichment loop.
    """
    batch_index = job.get("batch_index", 0)
    total_batches = job.get("total_batches", 1)
    stagger_delay = job.get("stagger_delay", 0)
    domains = job.get("domains", [])
    job_id = job.get("job_id", "")

    logger.bind(context={
        "job_id": job_id,
        "batch_index": batch_index,
        "total_batches": total_batches,
        "domain_count": len(domains),
        "stagger_delay": stagger_delay,
    }).info("enrichment_job_started")

    t0 = time.monotonic()

    try:
        # Stagger to avoid API rate-limit collisions between workers
        if stagger_delay > 0:
            logger.info(
                "Staggering enrichment batch %d by %ds",
                batch_index,
                stagger_delay,
            )
            for _ in range(stagger_delay):
                if _shutdown_requested:
                    logger.info("Shutdown requested during stagger — aborting enrichment batch %d", batch_index)
                    return  # finally block will increment counter
                time.sleep(1)

        # Run subfinder in batch mode
        results = _run_subfinder_with_retry(domains)

        # Store results per domain in cache — format must match what
        # _cached_or_run("subfinder", run_subfinder, [domain]) would store.
        # run_subfinder([domain]) returns {domain: [subdomains]}.
        # _cached_or_run stores the return value directly via cache.set().
        cached_count = 0
        for domain in domains:
            domain_result = {domain: results.get(domain, [])}
            cache.set("subfinder", domain, domain_result)
            cached_count += 1

        elapsed = time.monotonic() - t0
        logger.bind(context={
            "job_id": job_id,
            "batch_index": batch_index,
            "domain_count": len(domains),
            "cached_count": cached_count,
            "subdomains_found": sum(len(v) for v in results.values()),
            "duration_ms": int(elapsed * 1000),
        }).info("enrichment_job_completed")
    except Exception:
        elapsed = time.monotonic() - t0
        logger.opt(exception=True).bind(context={
            "job_id": job_id,
            "batch_index": batch_index,
            "domain_count": len(domains),
            "duration_ms": int(elapsed * 1000),
        }).error("enrichment_job_failed")
    finally:
        # Always increment — don't hang the scheduler
        try:
            redis_conn.incr(ENRICHMENT_COUNTER_KEY)
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            logger.warning(
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
            results = run_subfinder(domains)
            if attempt > 0:
                logger.info(
                    "subfinder succeeded on retry attempt %d", attempt
                )
            return results
        except Exception as exc:
            last_error = exc
            if attempt < retry_limit:
                logger.warning(
                    "subfinder failed (attempt %d/%d): %s — retrying",
                    attempt + 1,
                    1 + retry_limit,
                    exc,
                )
            else:
                logger.error(
                    "subfinder failed after %d attempts: %s",
                    1 + retry_limit,
                    exc,
                )

    # Return empty results rather than raising — the enrichment job
    # must always complete so the counter gets incremented
    return {}


def main(argv: list | None = None) -> None:
    """Worker main loop: validate Valdi, connect to Redis, process jobs."""
    args = _parse_args(argv)
    setup_logging(level=args.log_level, fmt=args.log_format)
    from src.logging.redis_sink import add_redis_sink
    add_redis_sink(os.environ.get("REDIS_URL", ""))

    logger.info("Heimdall worker starting")

    # ------------------------------------------------------------------
    # 0. Check CT database availability
    # ------------------------------------------------------------------
    ct_db_path = args.ct_db
    if os.path.isfile(ct_db_path):
        logger.info("CT database found at %s", ct_db_path)
    else:
        logger.warning("CT database not found at %s — crt.sh queries will return empty results", ct_db_path)

    # Set module-level CT_DB_PATH for scan_job to use
    import src.worker.scan_job as _scan_job_mod

    from .scan_job import _CT_DB_PATH as _unused  # noqa: F401
    _scan_job_mod._CT_DB_PATH = ct_db_path

    # ------------------------------------------------------------------
    # 1. Validate Valdi approval tokens (fail-fast)
    # ------------------------------------------------------------------
    max_level = args.max_level
    _init_scan_type_map()
    approvals = _validate_approval_tokens(max_level=max_level)
    if approvals is None:
        logger.error("BLOCKED — Valdi approval token validation failed. Worker refusing to start.")
        sys.exit(1)
    logger.info("Valdi approval tokens validated (max_level=%d)", max_level)

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
        logger.error("Cannot connect to Redis at %s: %s", args.redis_url, exc)
        sys.exit(1)
    logger.info("Connected to Redis at %s", args.redis_url)

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
    logger.info("Worker ready — waiting for jobs on queue:enrichment, queue:scan")

    _redis_failures = 0
    while not _shutdown_requested:
        try:
            item = redis_conn.brpop(
                ["queue:enrichment", "queue:scan"], timeout=30
            )
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            _redis_failures += 1
            backoff = min(2 ** _redis_failures, 30)
            logger.warning(
                "Redis BRPOP error (attempt %d, backoff %ds): %s",
                _redis_failures, backoff, exc,
            )
            time.sleep(backoff)
            continue

        _redis_failures = 0

        if item is None:
            # Timeout, no job available — loop back and check shutdown flag
            Path(HEALTHCHECK_FILE).touch()
            continue

        queue_name, raw_job = item

        try:
            job = json.loads(raw_job)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Malformed job JSON: %s — skipping", exc)
            continue

        job_type = job.get("job_type", "scan")
        job_id = job.get("job_id", "")

        # ------------------------------------------------------------------
        # Route: enrichment job
        # ------------------------------------------------------------------
        if job_type == "enrichment":
            logger.bind(context={"job_id": job_id, "queue": queue_name}).info("enrichment_job_received")
            _execute_enrichment_job(job, cache, redis_conn)
            continue

        # ------------------------------------------------------------------
        # Route: scan job (default)
        # ------------------------------------------------------------------
        domain = job.get("domain", "unknown")
        client_id = job.get("client_id", "prospect")

        logger.bind(context={"job_id": job_id, "domain": domain, "client_id": client_id}).info("job_started")

        # Gate 2: Consent check (Valdí) — Level 1+ requires valid consent
        # NOTE: a missing level field defaults to 0 (backward compat with
        # prospect jobs that predate the level field). Invalid types BLOCK.
        # TODO: once all job creators set level explicitly, change the
        # missing-field case from default-to-0 to block.
        raw_level = job.get("level")
        if raw_level is None:
            # Prospecting jobs (Level 0) always set level=0 explicitly.
            # A missing level field is unexpected — default to 0 for
            # backward compatibility with existing prospect jobs, but
            # log a warning so it gets fixed.
            job_level = 0
            logger.bind(context={
                "job_id": job_id, "domain": domain,
                "client_id": client_id,
                "message": "Job has no 'level' field — defaulting to 0",
            }).warning("gate2_missing_level")
        elif not isinstance(raw_level, int) or isinstance(raw_level, bool):
            logger.bind(context={
                "job_id": job_id, "domain": domain,
                "client_id": client_id,
                "raw_level": str(raw_level),
                "type": type(raw_level).__name__,
            }).error("gate2_invalid_level")
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
            logger.opt(exception=True).bind(context={
                "job_id": job_id, "domain": domain,
                "client_id": client_id, "level_requested": job_level,
            }).error("gate2_crash — scan BLOCKED")
            continue

        logger.bind(context={
            "job_id": job_id, "domain": domain, "client_id": client_id,
            "level_requested": job_level,
            "level_authorised": consent.level_authorised,
            "allowed": consent.allowed, "reason": consent.reason,
            "authorised_by_role": consent.authorised_by_role,
        }).info("gate2_consent_check")
        if not consent.allowed:
            logger.bind(context={
                "job_id": job_id, "domain": domain,
                "client_id": client_id, "reason": consent.reason,
            }).warning("gate2_blocked")
            continue

        # Level mismatch: re-queue if this worker can't handle the job's level
        if job_level > max_level:
            requeue_count = job.get("_requeue_count", 0) + 1
            if requeue_count > 5:
                logger.bind(context={
                    "job_id": job_id, "domain": domain,
                    "job_level": job_level, "requeue_count": requeue_count,
                }).error("level_mismatch_dropped — exceeded requeue limit")
                continue

            logger.bind(context={
                "job_id": job_id, "domain": domain,
                "job_level": job_level, "worker_max_level": max_level,
                "requeue_count": requeue_count,
            }).info("level_mismatch_requeue")
            try:
                job["_requeue_count"] = requeue_count
                redis_conn.lpush("queue:scan", json.dumps(job))
            except (redis.ConnectionError, redis.TimeoutError) as exc:
                logger.error("Failed to re-queue level-%d job %s: %s", job_level, job_id, exc)
            continue

        try:
            result = execute_scan_job(job, cache, redis_conn=redis_conn)
        except Exception:
            logger.opt(exception=True).error("Unhandled error processing job for %s", domain)
            continue

        # Write result to disk
        try:
            filepath = _write_result(args.results_dir, client_id, domain, result)
            logger.bind(context={"domain": domain, "path": str(filepath)}).info("result_written")
        except OSError as exc:
            logger.error("Failed to write result for %s: %s", domain, exc)

        # Save to client database (fail-safe: errors logged, not fatal)
        try:
            from src.db.connection import init_db
            from src.db.worker_hook import save_scan_to_db

            client_data_dir = os.environ.get("CLIENT_DATA_DIR", "data/clients")
            db_path = os.path.join(client_data_dir, "clients.db")
            db_conn = init_db(db_path)
            save_scan_to_db(db_conn, job, result)
        except Exception:
            logger.opt(exception=True).error("db_hook_error for %s", domain)

        # Publish scan-complete event (clients only — prospects use batch outreach)
        if client_id != "prospect":
            try:
                event_payload = json.dumps({
                    "job_id": job_id,
                    "domain": domain,
                    "client_id": client_id,
                    "status": result.get("status", "unknown"),
                })
                redis_conn.publish("client-scan-complete", event_payload)
            except (redis.ConnectionError, redis.TimeoutError) as exc:
                logger.warning("Failed to publish client-scan-complete for %s: %s", domain, exc)

        Path(HEALTHCHECK_FILE).touch()

        logger.bind(context={
            "job_id": job_id,
            "domain": domain,
            "status": result.get("status"),
            "cache_stats": result.get("cache_stats"),
            "total_ms": int(result.get("timing", {}).get("total_ms", 0)),
        }).info("job_completed")

    logger.info("Worker shut down gracefully")


if __name__ == "__main__":
    main()
