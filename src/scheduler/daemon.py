"""Scheduler daemon — BRPOP loop on queue:operator-commands."""

from __future__ import annotations

import datetime
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

import redis
from loguru import logger

_shutdown_requested = False
_MONITORING_CONFIG_PATH = Path("/config/monitoring.json")
_MONITORING_CONFIG_FALLBACK = Path(__file__).resolve().parents[2] / "config" / "monitoring.json"


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

    monitoring_cfg = _load_monitoring_config()
    _start_monitoring_timer(conn, monitoring_cfg)
    _start_retention_timer(conn)

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
            elif command == "monitor-clients":
                _handle_monitor_clients(conn, payload)
            else:
                logger.warning("Unknown command: {}", command)
                _publish_result(conn, command, "error", f"Unknown command: {command}")
        except Exception as exc:
            logger.opt(exception=True).error("Command failed: {}", command)
            try:
                _publish_result(conn, command, "error", f"Command failed: {exc}")
            except Exception:
                print(f"CRITICAL: daemon could not publish error to console: {exc}",
                      file=sys.stderr)

    logger.info("Scheduler daemon stopped")


def _publish_result(conn: redis.Redis, command: str, status: str, message: str) -> None:
    """Publish command result to console:command-results channel."""
    conn.publish("console:command-results", json.dumps({
        "type": "command_result",
        "payload": {"command": command, "status": status, "message": message},
        "ts": datetime.datetime.now(datetime.UTC).timestamp(),
    }))


def _publish_activity(conn: redis.Redis, message: str) -> None:
    """Publish activity event to console:activity channel."""
    conn.publish("console:activity", json.dumps({
        "type": "activity",
        "payload": {"message": message},
        "ts": datetime.datetime.now(datetime.UTC).timestamp(),
    }))


def _publish_progress(
    conn: redis.Redis,
    run_id: str,
    completed: int,
    total: int,
    current_domain: str = "",
) -> None:
    """Publish pipeline progress to console:pipeline-progress channel."""
    pct = int(completed / total * 100) if total > 0 else 0
    conn.publish("console:pipeline-progress", json.dumps({
        "type": "pipeline_progress",
        "payload": {
            "run_id": run_id,
            "completed": completed,
            "domain_count": total,
            "current_domain": current_domain,
            "pct": pct,
        },
        "ts": datetime.datetime.now(datetime.UTC).timestamp(),
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


def _load_monitoring_config() -> dict:
    """Read config/monitoring.json from the container mount or repo fallback."""
    for path in (_MONITORING_CONFIG_PATH, _MONITORING_CONFIG_FALLBACK):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                logger.warning("monitoring.json parse error at {}: {}", path, exc)
    logger.warning("monitoring.json not found — CT monitoring timer disabled")
    return {}


def _start_monitoring_timer(conn: redis.Redis, cfg: dict) -> None:
    """Start a daemon thread that enqueues monitor-clients once per day.

    Targets the hour-of-day given by ``ct_poll_schedule_hour_utc`` in cfg.
    Tolerates missing config (no timer started). Best-effort; errors logged.
    """
    hour = cfg.get("ct_poll_schedule_hour_utc")
    if hour is None:
        return

    def _timer_loop() -> None:
        logger.info("CT monitoring timer started — target hour UTC={}", hour)
        last_fired_date: str | None = None
        while not _shutdown_requested:
            now = datetime.datetime.now(datetime.UTC)
            today = now.strftime("%Y-%m-%d")
            if now.hour == hour and last_fired_date != today:
                try:
                    conn.lpush(
                        "queue:operator-commands",
                        json.dumps({"command": "monitor-clients", "payload": {}}),
                    )
                    logger.info("Enqueued monitor-clients at {}", now.isoformat())
                    last_fired_date = today
                except Exception as exc:
                    logger.warning("Failed to enqueue monitor-clients: {}", exc)
            time.sleep(60)

    t = threading.Thread(target=_timer_loop, name="ct-monitoring-timer", daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Retention-execution timer (D16 — 2026-04-24)
# ---------------------------------------------------------------------------

# 5-minute cadence. Mirrors architect's recommendation in
# docs/architecture/retention-cron-options.md §2 (Option A).
_RETENTION_TICK_SECONDS = 300


def _resolve_retention_db_path() -> str:
    """Resolve the daemon's DB path with the same precedence as ``init_db``.

    Used by both the retention timer (:func:`_start_retention_timer`) and
    the CT-monitor handler (:func:`_handle_monitor_clients`) so the two
    callers can never point at different files.

    Order:
      1. ``DB_PATH`` env var (full file path, takes precedence).
      2. ``CLIENT_DATA_DIR + /clients.db`` (deployed default, prod sets this).
      3. ``src.db.connection._DEFAULT_DB_PATH`` (canonical fallback —
         matches what ``init_db()`` uses with no args; keeps dev/prod
         parity so the daemon never points at a different file from the
         rest of the app).
    """
    explicit = os.environ.get("DB_PATH")
    if explicit:
        return explicit
    client_data_dir = os.environ.get("CLIENT_DATA_DIR")
    if client_data_dir:
        return os.path.join(client_data_dir, "clients.db")
    from src.db.connection import _DEFAULT_DB_PATH

    return _DEFAULT_DB_PATH


def _start_retention_timer(conn: redis.Redis) -> None:
    """Start a daemon thread that runs ``src.retention.runner.tick`` every 5 min.

    Peer of ``_start_monitoring_timer``. The tick:
    - reaps stuck 'running' rows,
    - atomically claims due pending rows,
    - dispatches each to its action handler,
    - handles backoff / terminal-failure alerting via Redis publish.

    A top-level try/except inside the loop ensures that a deadlocked
    retention execution (or a surprise exception in the runner) cannot
    starve the command BRPOP loop. The thread runs daemon=True so
    SIGTERM shutdown does not wait on it.
    """

    def _timer_loop() -> None:
        # Lazy imports keep module-import of daemon light (tests that
        # only exercise the command dispatcher do not need sqlite or
        # retention deps wired up).
        from src.db.connection import init_db
        from src.db.migrate import LegacyDataIntegrityError
        from src.retention.runner import _default_redis_alert, tick

        db_path = _resolve_retention_db_path()
        logger.info(
            "Retention timer started — cadence={}s db={}",
            _RETENTION_TICK_SECONDS,
            db_path,
        )

        alert_cb = _default_redis_alert(conn)

        while not _shutdown_requested:
            try:
                if not os.path.exists(db_path):
                    # DB not yet initialised (fresh container start
                    # ordering) — sleep and retry. Common on cold boot.
                    logger.debug(
                        "Retention timer: DB not found at {}, waiting", db_path
                    )
                else:
                    db = init_db(db_path)
                    try:
                        n = tick(db, alert_cb=alert_cb)
                        if n:
                            logger.info(
                                "Retention tick processed {} job(s)", n
                            )
                    finally:
                        db.close()
            except LegacyDataIntegrityError as e:
                # Bookkeeping-data integrity violation (e.g. duplicate
                # payment_events rows blocking the (provider, external_id,
                # event_type) UNIQUE migration). Refuse to silently
                # continue — the operator must clean up the offending
                # rows before the daemon can resume. Container restart
                # policy will keep retrying until the duplicates are
                # resolved, which is the intended fail-loud behavior.
                #
                # `os._exit(2)` (NOT `sys.exit(2)`) because we are inside
                # a non-main thread: sys.exit only raises SystemExit in
                # the current thread, leaving the daemon process alive
                # without retention coverage. os._exit terminates the
                # whole process immediately so the container restart
                # policy can surface the stop condition.
                logger.critical(
                    "FATAL retention_tick_db_integrity: {} — process exiting "
                    "non-zero so the container restart policy surfaces the "
                    "stop condition. Operator action required.",
                    e,
                )
                os._exit(2)
            except Exception:
                # Swallow ordinary transient errors so the tick loop
                # keeps running. The DB and Redis paths both have their
                # own internal logging; the opt(exception) gives us a
                # stack trace in console logs.
                logger.opt(exception=True).warning("retention_tick_failed")

            # Sleep in 5-second slices so shutdown does not wait the
            # full 300 s. Same shape as the monitoring timer uses 60 s
            # slices for its hourly cadence.
            slept = 0
            while slept < _RETENTION_TICK_SECONDS and not _shutdown_requested:
                time.sleep(5)
                slept += 5

    t = threading.Thread(
        target=_timer_loop, name="retention-timer", daemon=True
    )
    t.start()


def _handle_monitor_clients(conn: redis.Redis, payload: dict) -> None:
    """Poll CertSpotter for every Sentinel client with monitoring enabled.

    Iterates clients.db, delegates each eligible client to
    ``src.client_memory.ct_monitor.poll_and_diff_client``. Watchman-tier
    clients and those with ``monitoring_enabled = 0`` are skipped.
    """
    from src.client_memory.ct_monitor import poll_and_diff_client
    from src.db.connection import init_db

    db_path = _resolve_retention_db_path()
    if not os.path.exists(db_path):
        _publish_result(conn, "monitor-clients", "error", f"DB not found: {db_path}")
        return

    db = init_db(db_path)
    try:
        rows = db.execute(
            """
            SELECT c.cvr, cd.domain
            FROM clients c
            JOIN client_domains cd ON cd.cvr = c.cvr
            WHERE c.plan = 'sentinel'
              AND c.monitoring_enabled = 1
              AND c.status IN ('active','onboarding')
              AND cd.is_primary = 1
            """
        ).fetchall()
    except Exception as exc:
        db.close()
        _publish_result(conn, "monitor-clients", "error", f"Query failed: {exc}")
        return

    if not rows:
        _publish_activity(conn, "CT monitoring: no Sentinel clients with monitoring enabled")
        _publish_result(conn, "monitor-clients", "completed", "No eligible clients")
        db.close()
        return

    _publish_activity(conn, f"CT monitoring: polling {len(rows)} Sentinel client(s)")

    total_changes = 0
    polled = 0
    for row in rows:
        cvr = row["cvr"]
        domain = row["domain"]
        try:
            summary = poll_and_diff_client(cvr, domain, db, conn)
            total_changes += summary.get("changes", 0)
            polled += 1
        except Exception as exc:
            logger.opt(exception=True).warning(
                "CT monitor failed for cvr={} domain={}: {}", cvr, domain, exc
            )

    db.close()

    msg = f"CT monitoring complete: {polled}/{len(rows)} polled, {total_changes} change(s)"
    _publish_activity(conn, msg)
    _publish_result(conn, "monitor-clients", "completed", msg)
