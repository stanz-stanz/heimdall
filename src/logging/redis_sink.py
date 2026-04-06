"""Loguru sink that publishes log entries to Redis pub/sub for the operator console.

Usage — call after setup_logging() in each container entrypoint:

    from src.logging.redis_sink import add_redis_sink
    add_redis_sink(redis_url)

The sink runs a background daemon thread that drains a bounded queue and
publishes to Redis. If Redis is down or the queue is full, entries are
silently dropped. Container stderr logging is unaffected.
"""

from __future__ import annotations

import json
import queue
import socket
import sys
import threading
import traceback

import redis as redis_lib

_SOURCE = socket.gethostname()
_CHANNEL = "console:logs"


class _RedisSinkWorker(threading.Thread):
    """Background daemon thread that publishes log entries to Redis."""

    daemon = True

    def __init__(self, redis_url: str) -> None:
        super().__init__(name="redis-log-sink")
        self._q: queue.Queue = queue.Queue(maxsize=1000)
        self._redis_url = redis_url

    def run(self) -> None:
        conn = None
        while True:
            try:
                entry = self._q.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                if conn is None:
                    conn = redis_lib.Redis.from_url(
                        self._redis_url,
                        decode_responses=True,
                        socket_timeout=0.5,
                        socket_connect_timeout=0.5,
                    )
                conn.publish(_CHANNEL, entry)
            except Exception as exc:
                conn = None  # force reconnect on next entry
                # Print to stderr — never to loguru (avoids infinite recursion)
                print(f"redis-log-sink: publish failed: {exc}", file=sys.stderr)

    def enqueue(self, entry_json: str) -> None:
        """Non-blocking enqueue. Drops silently if the queue is full."""
        try:
            self._q.put_nowait(entry_json)
        except queue.Full:
            pass


def _make_sink(worker: _RedisSinkWorker):
    """Create a loguru sink function bound to the given worker thread."""

    def sink(message) -> None:
        record = message.record
        entry = {
            "ts": record["time"].timestamp(),
            "level": record["level"].name,
            "source": _SOURCE,
            "module": record["name"] or "root",
            "message": record["message"],
        }

        # Flatten context dict if present (domain, job_id, etc.)
        ctx = record["extra"].get("context")
        if ctx and isinstance(ctx, dict):
            entry["ctx"] = ctx

        # Include formatted exception if present
        if record["exception"]:
            try:
                entry["exc"] = "".join(
                    traceback.format_exception(
                        type(record["exception"].value),
                        record["exception"].value,
                        record["exception"].traceback,
                    )
                )
            except Exception:
                entry["exc"] = str(record["exception"])

        worker.enqueue(json.dumps(entry, default=str))

    return sink


def add_redis_sink(redis_url: str) -> None:
    """Add a Redis pub/sub log sink to loguru. No-op if redis_url is empty."""
    if not redis_url:
        return

    from loguru import logger

    worker = _RedisSinkWorker(redis_url)
    worker.start()
    logger.add(_make_sink(worker), level="INFO", format="{message}")
