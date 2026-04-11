"""CertStream subscriber: filters .dk domains and stores certificates locally.

Run as::

    python -m src.ct_collector.main [--db-path /data/ct/certificates.db]

Subscribes to the CertStream WebSocket feed, extracts certificate data for
.dk domains, and inserts into a local SQLite database.  A background thread
handles periodic cleanup and WAL checkpointing.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import tempfile
import threading
import time
from datetime import UTC, datetime
from typing import Any

import certstream
from loguru import logger

from src.prospecting.logging_config import setup_logging

from .db import cleanup_old_entries, get_db_stats, init_db

# Module-level flag for graceful shutdown
_shutdown_requested: bool = False


def _handle_signal(signum: int, _frame: object) -> None:  # pragma: no cover
    """Set the shutdown flag on SIGTERM / SIGINT."""
    global _shutdown_requested
    _shutdown_requested = True
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down", sig_name)


def _is_dk_domain(domain: str, suffix: str = ".dk") -> bool:
    """Return True if *domain* ends with the given suffix."""
    if not domain:
        return False
    return domain.lower().rstrip(".").endswith(suffix)


def _extract_cert_data(message: dict) -> dict[str, Any] | None:
    """Parse a CertStream message and extract certificate data if .dk.

    Returns a dict with keys matching :func:`db.insert_certificate` params,
    or None if the message is not a certificate update or contains no .dk domains.
    """
    if message.get("message_type") != "certificate_update":
        return None

    data = message.get("data", {})
    leaf = data.get("leaf_cert", {})
    if not leaf:
        return None

    # Collect all domains from the certificate
    all_domains = leaf.get("all_domains", [])
    subject_cn = leaf.get("subject", {}).get("CN", "")

    if not all_domains and not subject_cn:
        return None

    # Check if any domain is .dk
    has_dk = False
    for d in all_domains:
        if _is_dk_domain(d):
            has_dk = True
            break
    if not has_dk and subject_cn:
        has_dk = _is_dk_domain(subject_cn)

    if not has_dk:
        return None

    common_name = subject_cn or (all_domains[0] if all_domains else "")
    issuer = leaf.get("issuer", {})
    issuer_name = issuer.get("O", issuer.get("CN", ""))
    not_before = leaf.get("not_before", "")
    not_after = leaf.get("not_after", "")

    # Filter SAN domains to only .dk
    san_domains = [d for d in all_domains if _is_dk_domain(d)]

    return {
        "common_name": common_name,
        "issuer_name": issuer_name,
        "not_before": str(not_before),
        "not_after": str(not_after),
        "san_domains": san_domains,
        "seen_at": datetime.now(UTC).isoformat(),
    }


def _write_status(
    status_file: str,
    ws_connected: bool,
    last_cert_seen_at: str | None,
    certs_last_hour: int,
    db_stats: dict[str, Any],
) -> None:
    """Atomic write of collector status to a JSON file."""
    status = {
        "ws_connected": ws_connected,
        "last_cert_seen_at": last_cert_seen_at,
        "certs_last_hour": certs_last_hour,
        "db_stats": db_stats,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    # Write to temp file then rename for atomicity
    dir_name = os.path.dirname(status_file) or "."
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=dir_name, suffix=".tmp", delete=False
        ) as tmp:
            json.dump(status, tmp, indent=2, default=str, ensure_ascii=False)
            tmp_path = tmp.name
        os.replace(tmp_path, status_file)
    except OSError as exc:
        logger.bind(context={"error": str(exc)}).warning("status_write_failed")


def _cleanup_loop(db_path: str, interval_hours: int) -> None:
    """Daemon thread: periodic cleanup + WAL checkpoint.

    Opens a lightweight connection (no large cache) to avoid OOM in
    the 256 MB container budget.
    """
    interval_seconds = interval_hours * 3600
    while not _shutdown_requested:
        # Sleep in small increments to check shutdown flag
        for _ in range(interval_seconds):
            if _shutdown_requested:
                return
            time.sleep(1)

        if _shutdown_requested:
            return

        try:
            import sqlite3 as _sqlite3

            conn = _sqlite3.connect(db_path, timeout=30)
            conn.row_factory = _sqlite3.Row
            try:
                deleted = cleanup_old_entries(conn, days=90)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.bind(context={"deleted": deleted}).info("cleanup_loop_complete")
            finally:
                conn.close()
        except Exception as exc:
            logger.bind(context={"error": str(exc)}).warning("cleanup_loop_error")


def _parse_args(argv: list | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Heimdall CertStream CT collector")
    parser.add_argument(
        "--db-path",
        default=os.environ.get("CT_DB_PATH", "/data/ct/certificates.db"),
        help="Path to SQLite CT database (default: /data/ct/certificates.db)",
    )
    parser.add_argument(
        "--certstream-url",
        default=os.environ.get("CERTSTREAM_URL", "wss://certstream.calidog.io/"),
        help="CertStream WebSocket URL",
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
        "--domain-filter",
        default=os.environ.get("DOMAIN_FILTER", ".dk"),
        help="Domain suffix filter (default: .dk)",
    )
    parser.add_argument(
        "--cleanup-interval-hours",
        type=int,
        default=int(os.environ.get("CLEANUP_INTERVAL_HOURS", "24")),
        help="Hours between cleanup runs (default: 24)",
    )
    parser.add_argument(
        "--status-file",
        default=os.environ.get("STATUS_FILE", "/data/ct/collector_status.json"),
        help="Path to status JSON file (default: /data/ct/collector_status.json)",
    )
    return parser.parse_args(argv)


def main(argv: list | None = None) -> None:
    """CertStream subscriber main loop."""
    args = _parse_args(argv)
    setup_logging(level=args.log_level, fmt=args.log_format)
    from src.logging.redis_sink import add_redis_sink
    add_redis_sink(os.environ.get("REDIS_URL", ""))

    logger.info("CertStream CT collector starting")

    # Initialise database
    conn = init_db(args.db_path)
    logger.info("Database ready at %s", args.db_path)

    # Start cleanup daemon thread
    cleanup_thread = threading.Thread(
        target=_cleanup_loop,
        args=(args.db_path, args.cleanup_interval_hours),
        daemon=True,
    )
    cleanup_thread.start()
    logger.info("Cleanup thread started (interval: %dh)", args.cleanup_interval_hours)

    # Register signal handlers
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Tracking for status reporting
    last_cert_seen_at: str | None = None
    certs_last_hour: int = 0
    hour_start = time.monotonic()
    insert_count: int = 0
    batch_buffer: list[dict] = []
    batch_size = 50
    last_status_write = time.monotonic()
    status_interval = 60  # seconds

    # Exponential backoff for reconnection
    backoff_base = 1.0
    backoff_max = 120.0
    backoff_current = backoff_base

    def _on_message(message: dict, context: Any) -> None:
        nonlocal last_cert_seen_at, certs_last_hour, hour_start
        nonlocal insert_count, batch_buffer, backoff_current
        nonlocal last_status_write

        if _shutdown_requested:
            return

        # Reset backoff on successful message
        backoff_current = backoff_base

        cert_data = _extract_cert_data(message)
        if cert_data is None:
            return

        batch_buffer.append(cert_data)

        if len(batch_buffer) >= batch_size:
            from .db import insert_certificates_batch

            inserted = insert_certificates_batch(conn, batch_buffer)
            insert_count += inserted
            batch_buffer.clear()

            if inserted > 0:
                last_cert_seen_at = datetime.now(UTC).isoformat()
                certs_last_hour += inserted

        # Reset hourly counter
        elapsed = time.monotonic() - hour_start
        if elapsed >= 3600:
            logger.bind(context={"certs_inserted": certs_last_hour, "total": insert_count}).info("hourly_stats")
            certs_last_hour = 0
            hour_start = time.monotonic()

        # Periodic status write
        if time.monotonic() - last_status_write >= status_interval:
            _write_status(
                args.status_file,
                ws_connected=True,
                last_cert_seen_at=last_cert_seen_at,
                certs_last_hour=certs_last_hour,
                db_stats=get_db_stats(conn),
            )
            last_status_write = time.monotonic()

    def _on_error(instance: Any, exception: Exception) -> None:
        logger.bind(context={"error": str(exception)}).warning("certstream_error")

    logger.info("Connecting to CertStream at %s", args.certstream_url)

    while not _shutdown_requested:
        try:
            certstream.listen_for_events(
                _on_message,
                url=args.certstream_url,
                on_error=_on_error,
            )
        except Exception as exc:
            if _shutdown_requested:
                break
            logger.bind(context={"error": str(exc), "backoff_s": backoff_current}).warning("certstream_disconnected")
            # Flush any remaining batch buffer before reconnect
            if batch_buffer:
                from .db import insert_certificates_batch

                insert_certificates_batch(conn, batch_buffer)
                batch_buffer.clear()

            _write_status(
                args.status_file,
                ws_connected=False,
                last_cert_seen_at=last_cert_seen_at,
                certs_last_hour=certs_last_hour,
                db_stats=get_db_stats(conn),
            )

            time.sleep(backoff_current)
            backoff_current = min(backoff_current * 2, backoff_max)

    # Flush remaining
    if batch_buffer:
        from .db import insert_certificates_batch

        insert_certificates_batch(conn, batch_buffer)

    conn.close()
    logger.info("CertStream CT collector shut down gracefully (total inserted: %d)", insert_count)


if __name__ == "__main__":
    main()
