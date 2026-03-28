"""Redis cache layer for scan results.

Provides per-scan-type caching with configurable TTLs. Degrades gracefully
when Redis is unavailable — get() returns None (cache miss), set() silently
skips. The pipeline works without cache; it is just slower.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Optional

import redis

log = logging.getLogger(__name__)

# TTLs in seconds, keyed by scan type ID used in the worker.
# Source of truth: docs/architecture/pi5-docker-architecture.md § Caching Strategy.
CACHE_TTLS: Dict[str, int] = {
    "ssl": 86400,           # 24h
    "headers": 86400,       # 24h
    "meta": 86400,          # 24h
    "httpx": 86400,         # 24h
    "webanalyze": 86400,    # 24h
    "subfinder": 604800,    # 7d
    "crtsh": 604800,        # 7d
    "dnsx": 86400,          # 24h
    "ghw": 604800,          # 7d
    "nuclei": 86400,        # 24h
}

DEFAULT_TTL: int = 86400  # fallback if scan_type not in CACHE_TTLS


def _make_key(scan_type: str, domain: str) -> str:
    """Build the Redis key for a cached scan result."""
    return f"cache:{scan_type}:{domain}"


class ScanCache:
    """Thin wrapper around a Redis connection for scan-result caching.

    Parameters
    ----------
    redis_url:
        Redis connection string, e.g. ``redis://localhost:6379/0``.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self.hits: int = 0
        self.misses: int = 0
        self._available: bool = False

        try:
            self._redis: redis.Redis = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Verify connectivity with a lightweight command.
            self._redis.ping()
            self._available = True
            log.info("ScanCache connected to Redis at %s", redis_url)
        except (redis.ConnectionError, redis.TimeoutError, OSError) as exc:
            log.warning("Redis unavailable (%s) — cache disabled, pipeline will run without caching", exc)
            self._redis = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return whether Redis is reachable."""
        return self._available

    def get(self, scan_type: str, domain: str) -> Optional[dict]:
        """Return cached result or ``None`` on miss / expiry / unavailable."""
        if not self._available:
            self.misses += 1
            return None

        key = _make_key(scan_type, domain)
        try:
            raw: Optional[str] = self._redis.get(key)
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            log.warning("Redis GET failed for %s: %s", key, exc)
            self.misses += 1
            return None

        if raw is None:
            self.misses += 1
            return None

        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            log.warning("Corrupt cache entry for %s: %s", key, exc)
            self.misses += 1
            return None

        self.hits += 1
        return result

    def set(self, scan_type: str, domain: str, result: dict) -> None:
        """Store *result* with the TTL defined in :data:`CACHE_TTLS`."""
        if not self._available:
            return

        key = _make_key(scan_type, domain)
        ttl = CACHE_TTLS.get(scan_type, DEFAULT_TTL)
        try:
            self._redis.setex(key, ttl, json.dumps(result))
        except (redis.ConnectionError, redis.TimeoutError) as exc:
            log.warning("Redis SET failed for %s: %s", key, exc)
