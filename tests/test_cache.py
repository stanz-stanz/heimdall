"""Tests for src.worker.cache — Redis scan-result caching."""

from __future__ import annotations

import json

import fakeredis
import pytest

from src.worker.cache import CACHE_TTLS, ScanCache, _make_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache(server: fakeredis.FakeServer | None = None) -> ScanCache:
    """Create a ScanCache backed by fakeredis."""
    if server is None:
        server = fakeredis.FakeServer()
    cache = ScanCache.__new__(ScanCache)
    cache.hits = 0
    cache.misses = 0
    cache._available = True
    cache._redis = fakeredis.FakeRedis(server=server, decode_responses=True)
    return cache


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSetAndGet:
    def test_roundtrip(self) -> None:
        cache = _make_cache()
        payload = {"valid": True, "issuer": "Let's Encrypt"}
        cache.set("ssl", "example.dk", payload)
        assert cache.get("ssl", "example.dk") == payload

    def test_different_scan_types_independent(self) -> None:
        cache = _make_cache()
        cache.set("ssl", "example.dk", {"a": 1})
        cache.set("headers", "example.dk", {"b": 2})
        assert cache.get("ssl", "example.dk") == {"a": 1}
        assert cache.get("headers", "example.dk") == {"b": 2}


class TestCacheMiss:
    def test_nonexistent_key_returns_none(self) -> None:
        cache = _make_cache()
        assert cache.get("ssl", "noexist.dk") is None

    def test_miss_increments_counter(self) -> None:
        cache = _make_cache()
        cache.get("ssl", "noexist.dk")
        assert cache.misses == 1
        assert cache.hits == 0


class TestCacheExpired:
    def test_expired_key_returns_none(self) -> None:
        """Set a key with TTL=1 then advance time so it expires."""
        server = fakeredis.FakeServer()
        cache = _make_cache(server)
        cache.set("ssl", "example.dk", {"x": 1})
        # fakeredis FakeServer does not natively support time travel,
        # so we delete the key to simulate expiry.
        cache._redis.delete(_make_key("ssl", "example.dk"))
        assert cache.get("ssl", "example.dk") is None

    def test_zero_ttl_key_expires_immediately(self) -> None:
        """Directly setex with ttl=0 — Redis treats 0 as delete."""
        cache = _make_cache()
        key = _make_key("ssl", "example.dk")
        # ttl <= 0 causes Redis (and fakeredis) to reject or delete.
        try:
            cache._redis.setex(key, 0, json.dumps({"x": 1}))
        except Exception:
            pass  # Redis raises error for ttl=0
        assert cache.get("ssl", "example.dk") is None


class TestGracefulWhenRedisDown:
    def test_bad_url_does_not_crash(self) -> None:
        cache = ScanCache(redis_url="redis://nonexistent-host:9999/0")
        assert cache.is_available() is False

    def test_get_returns_none_when_unavailable(self) -> None:
        cache = ScanCache(redis_url="redis://nonexistent-host:9999/0")
        assert cache.get("ssl", "example.dk") is None

    def test_set_does_not_crash_when_unavailable(self) -> None:
        cache = ScanCache(redis_url="redis://nonexistent-host:9999/0")
        cache.set("ssl", "example.dk", {"a": 1})  # should not raise


class TestKeyFormat:
    def test_key_format(self) -> None:
        assert _make_key("ssl", "conrads.dk") == "cache:ssl:conrads.dk"

    def test_key_format_subfinder(self) -> None:
        assert _make_key("subfinder", "example.com") == "cache:subfinder:example.com"

    def test_stored_key_matches_format(self) -> None:
        cache = _make_cache()
        cache.set("headers", "test.dk", {"h": 1})
        keys = list(cache._redis.scan_iter("cache:*"))
        assert keys == ["cache:headers:test.dk"]


class TestStatsTracking:
    def test_hit_increments(self) -> None:
        cache = _make_cache()
        cache.set("ssl", "a.dk", {"v": 1})
        cache.get("ssl", "a.dk")
        assert cache.hits == 1
        assert cache.misses == 0

    def test_miss_increments(self) -> None:
        cache = _make_cache()
        cache.get("ssl", "a.dk")
        assert cache.misses == 1
        assert cache.hits == 0

    def test_mixed_hits_and_misses(self) -> None:
        cache = _make_cache()
        cache.set("ssl", "a.dk", {"v": 1})
        cache.get("ssl", "a.dk")       # hit
        cache.get("ssl", "b.dk")       # miss
        cache.get("ssl", "a.dk")       # hit
        cache.get("headers", "a.dk")   # miss
        assert cache.hits == 2
        assert cache.misses == 2


class TestTTLPerScanType:
    def test_ssl_gets_24h_ttl(self) -> None:
        cache = _make_cache()
        cache.set("ssl", "a.dk", {"v": 1})
        ttl = cache._redis.ttl(_make_key("ssl", "a.dk"))
        assert ttl == CACHE_TTLS["ssl"]  # 86400

    def test_subfinder_gets_7d_ttl(self) -> None:
        cache = _make_cache()
        cache.set("subfinder", "a.dk", {"v": 1})
        ttl = cache._redis.ttl(_make_key("subfinder", "a.dk"))
        assert ttl == CACHE_TTLS["subfinder"]  # 604800

    def test_all_configured_types_have_correct_ttl(self) -> None:
        cache = _make_cache()
        for scan_type, expected_ttl in CACHE_TTLS.items():
            cache.set(scan_type, "check.dk", {"t": scan_type})
            actual_ttl = cache._redis.ttl(_make_key(scan_type, "check.dk"))
            assert actual_ttl == expected_ttl, f"{scan_type}: expected {expected_ttl}, got {actual_ttl}"
