"""Scheduler daemon — BRPOP loop on queue:operator-commands."""

from __future__ import annotations

import datetime
import json
import signal
import sys
import time
from pathlib import Path

import redis
from loguru import logger


_shutdown_requested = False


def _handle_signal(signum: int, frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("Shutdown signal received ({})", signal.Signals(signum).name)


def run_daemon(redis_url: str, input_path: Path, filters_path: Path) -> None:
    """BRPOP loop on queue:operator-commands. Dispatches commands to handlers."""
    global _shutdown_requested

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    conn = redis.Redis.from_url(redis_url, decode_responses=True)
    try:
        conn.ping()
    except redis.ConnectionError:
        logger.error("Cannot connect to Redis at {}", redis_url)
        sys.exit(1)

    logger.info("Scheduler daemon started — listening on queue:operator-commands")

    while not _shutdown_requested:
        try:
            result = conn.brpop("queue:operator-commands", timeout=5)
        except redis.ConnectionError:
            logger.warning("Redis connection lost — retrying in 5s")
            time.sleep(5)
            continue

        if result is None:
            continue  # timeout, loop back

        _, raw = result
        try:
            cmd = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Invalid command JSON: {}", raw)
            continue

        command = cmd.get("command", "")
        payload = cmd.get("payload", {})
        logger.info("Received command: {} payload={}", command, payload)

        try:
            if command == "run-pipeline":
                _handle_run_pipeline(conn, input_path, filters_path)
            elif command == "interpret":
                _handle_interpret(conn, payload)
            elif command == "send":
                _handle_send(conn, payload)
            else:
                logger.warning("Unknown command: {}", command)
                _publish_result(conn, command, "error", f"Unknown command: {command}")
        except Exception:
            logger.opt(exception=True).error("Command failed: {}", command)
            _publish_result(conn, command, "error", "Command failed — check logs")

    logger.info("Scheduler daemon stopped")


def _publish_result(conn: redis.Redis, command: str, status: str, message: str) -> None:
    """Publish command result to console:command-results channel."""
    conn.publish("console:command-results", json.dumps({
        "type": "command_result",
        "payload": {"command": command, "status": status, "message": message},
        "ts": datetime.datetime.now(datetime.timezone.utc).timestamp(),
    }))


def _publish_activity(conn: redis.Redis, message: str) -> None:
    """Publish activity event to console:activity channel."""
    conn.publish("console:activity", json.dumps({
        "type": "activity",
        "payload": {"message": message},
        "ts": datetime.datetime.now(datetime.timezone.utc).timestamp(),
    }))


def _publish_progress(
    conn: redis.Redis,
    run_id: str,
    completed: int,
    total: int,
    current_domain: str = "",
) -> None:
    """Publish pipeline progress to console:pipeline-progress channel."""
    pct = int((completed / total * 100)) if total > 0 else 0
    conn.publish("console:pipeline-progress", json.dumps({
        "type": "pipeline_progress",
        "payload": {
            "run_id": run_id,
            "completed": completed,
            "domain_count": total,
            "current_domain": current_domain,
            "pct": pct,
        },
        "ts": datetime.datetime.now(datetime.timezone.utc).timestamp(),
    }))


def _handle_run_pipeline(
    conn: redis.Redis,
    input_path: Path,
    filters_path: Path,
) -> None:
    """Run the prospect pipeline: extract domains, enrichment, scan jobs."""
    from src.scheduler.job_creator import JobCreator

    _publish_activity(conn, "Pipeline started")
    _publish_result(conn, "run-pipeline", "started", "Pipeline is running")

    # Extract the Redis URL from the connection for JobCreator
    connection_kwargs = conn.connection_pool.connection_kwargs
    redis_host = connection_kwargs.get("host", "localhost")
    redis_port = connection_kwargs.get("port", 6379)
    redis_db = connection_kwargs.get("db", 0)
    redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
    creator = JobCreator(redis_url=redis_url)

    # Prevent concurrent runs
    lock_acquired = conn.set("scheduler:lock", "1", nx=True, ex=3600)
    if not lock_acquired:
        msg = "Another pipeline is already running"
        logger.warning(msg)
        _publish_result(conn, "run-pipeline", "error", msg)
        return

    try:
        domains = creator.extract_prospect_domains(input_path, filters_path)
        if not domains:
            _publish_result(conn, "run-pipeline", "completed", "No domains extracted")
            return

        _publish_activity(conn, f"Extracted {len(domains)} domains")

        # Enrichment phase
        logger.info("Starting enrichment for {} domains", len(domains))
        enrichment_count = creator.create_enrichment_jobs(domains)
        if enrichment_count > 0:
            creator.wait_for_enrichment(timeout=3600)

        _publish_activity(conn, "Enrichment complete — creating scan jobs")

        # Scan jobs
        count = creator.create_scan_jobs_for_domains(domains)
        msg = f"Pipeline queued {count} scan jobs for {len(domains)} domains"
        _publish_activity(conn, msg)
        _publish_result(conn, "run-pipeline", "completed", msg)

    except Exception as exc:
        _publish_result(conn, "run-pipeline", "error", str(exc))
        raise
    finally:
        conn.delete("scheduler:lock")


def _handle_interpret(conn: redis.Redis, payload: dict) -> None:
    """Run interpretation on a campaign's prospects."""
    campaign = payload.get("campaign", "")
    if not campaign:
        _publish_result(conn, "interpret", "error", "Missing campaign parameter")
        return

    limit = payload.get("limit", 10)
    min_severity = payload.get("min_severity")

    _publish_activity(conn, f"Interpreting up to {limit} prospects in {campaign}")

    from src.outreach.interpret import run_interpret

    result = run_interpret(
        campaign=campaign,
        min_severity=min_severity,
        limit=limit,
    )

    msg = (
        f"Interpreted {result.get('interpreted', 0)} prospects"
        f" ({result.get('cache_hits', 0)} cache hits)"
    )
    _publish_activity(conn, msg)
    _publish_result(conn, "interpret", "completed", msg)


def _handle_send(conn: redis.Redis, payload: dict) -> None:
    """Run send on a campaign's interpreted prospects."""
    campaign = payload.get("campaign", "")
    if not campaign:
        _publish_result(conn, "send", "error", "Missing campaign parameter")
        return

    limit = payload.get("limit")

    _publish_activity(conn, f"Sending outreach for {campaign}")

    from src.outreach.send import run_send

    result = run_send(
        campaign=campaign,
        limit=limit,
    )

    msg = f"Sent {result.get('sent', 0)} messages for {campaign}"
    _publish_activity(conn, msg)
    _publish_result(conn, "send", "completed", msg)
