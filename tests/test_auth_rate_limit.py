"""Tests for src.api.auth.rate_limit — Stage A login rate limiter.

Stage A spec §3.1.a. The module exposes three primitives wrapped
around a Redis client:

- ``check_should_block(redis, ip) -> (blocked, retry_after)``
  Step 1 of the login flow — read the per-IP fail counter and decide
  whether to short-circuit with 429.
- ``record_failure(redis, ip) -> None``
  Step 2-fail path — INCR the counter, set TTL on the first INCR only
  so the sliding-window-reset bug never re-emerges.
- ``clear_failures(redis, ip) -> None``
  Step 3-success path — DELETE the counter so a legitimate operator
  who recovers from a typo gets fresh quota.

All three are fail-open on Redis errors: the spec explicitly chooses
"throttle off" over "auth offline" when Redis is unavailable
(§3.1.a — locking the operator out of the control plane during a
Redis outage is a worse failure mode than a brief throttling gap).

Key format is exactly ``auth:fail:<ip>`` — no environment prefix, no
namespace — so ops alerts that grep Redis keys can match without
guessing.
"""

from __future__ import annotations

import logging

import fakeredis
import pytest

from src.api.auth import rate_limit
from src.api.auth.rate_limit import (
    KEY_PREFIX,
    THRESHOLD,
    WINDOW_SEC,
    check_should_block,
    clear_failures,
    record_failure,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def redis() -> fakeredis.FakeStrictRedis:
    """Fresh in-memory fake Redis. Each test gets an isolated db."""
    return fakeredis.FakeStrictRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# Constants — key format + threshold
# ---------------------------------------------------------------------------


def test_constants_match_spec() -> None:
    """Spec §3.1.a: 5 fails, 15-min window, exact key prefix."""
    assert KEY_PREFIX == "auth:fail:"
    assert THRESHOLD == 5
    assert WINDOW_SEC == 900


def test_key_format_is_exactly_auth_fail_ip(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """Lock the on-the-wire key shape so ops alerts grepping Redis
    keys never have to guess at namespacing."""
    record_failure(redis, "203.0.113.42")
    keys = redis.keys("*")
    assert keys == ["auth:fail:203.0.113.42"]


# ---------------------------------------------------------------------------
# record_failure — INCR + first-call TTL
# ---------------------------------------------------------------------------


def test_record_failure_first_call_increments_to_one_and_sets_ttl(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """First failure for a new IP creates the key at 1 with a 900s TTL."""
    record_failure(redis, "1.2.3.4")
    assert redis.get("auth:fail:1.2.3.4") == "1"
    ttl = redis.ttl("auth:fail:1.2.3.4")
    # TTL should be set to ~WINDOW_SEC; allow a small slack for clock.
    assert WINDOW_SEC - 5 <= ttl <= WINDOW_SEC


def test_record_failure_subsequent_calls_increment_without_resetting_ttl(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """Second + third failures must NOT call expire() again — the TTL
    inherits from the first INCR. Otherwise an attacker pacing 4
    attempts every 14 minutes would never trip the limiter (spec §3.1.a:
    'Subsequent INCRs in the same window inherit the TTL set by the
    first one ... a sliding window would let an attacker pace 4
    attempts every 14 min indefinitely')."""
    record_failure(redis, "1.2.3.4")

    # Manually shrink the TTL to simulate time passing.
    redis.expire("auth:fail:1.2.3.4", 100)

    record_failure(redis, "1.2.3.4")
    record_failure(redis, "1.2.3.4")

    assert redis.get("auth:fail:1.2.3.4") == "3"
    ttl_after = redis.ttl("auth:fail:1.2.3.4")
    # The TTL must NOT have been reset back to ~900; it should still
    # reflect the shrunken value (now somewhere between 95 and 100).
    assert ttl_after <= 100, (
        "subsequent INCRs must not reset the TTL — a sliding window "
        "lets an attacker pace below the threshold indefinitely"
    )


def test_record_failure_per_ip_counters_isolated(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """Different source IPs have independent counters. Spec §3.1.a:
    'Per-IP only, by design.'"""
    for _ in range(5):
        record_failure(redis, "1.1.1.1")
    record_failure(redis, "2.2.2.2")
    assert redis.get("auth:fail:1.1.1.1") == "5"
    assert redis.get("auth:fail:2.2.2.2") == "1"


# ---------------------------------------------------------------------------
# check_should_block — threshold + retry_after
# ---------------------------------------------------------------------------


def test_check_returns_not_blocked_when_below_threshold(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """4 fails — still under THRESHOLD=5 — login is allowed to proceed."""
    for _ in range(4):
        record_failure(redis, "1.2.3.4")
    blocked, retry_after = check_should_block(redis, "1.2.3.4")
    assert blocked is False
    assert retry_after == 0


def test_check_returns_blocked_at_threshold(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """5 fails — exactly at threshold — login is blocked."""
    for _ in range(5):
        record_failure(redis, "1.2.3.4")
    blocked, retry_after = check_should_block(redis, "1.2.3.4")
    assert blocked is True
    assert 1 <= retry_after <= WINDOW_SEC


def test_check_returns_blocked_above_threshold(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """6+ fails — well over threshold — still blocked."""
    for _ in range(6):
        record_failure(redis, "1.2.3.4")
    blocked, retry_after = check_should_block(redis, "1.2.3.4")
    assert blocked is True
    assert 1 <= retry_after <= WINDOW_SEC


def test_check_returns_not_blocked_for_unknown_ip(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """No prior failures for this IP → no key in Redis → not blocked."""
    blocked, retry_after = check_should_block(redis, "9.9.9.9")
    assert blocked is False
    assert retry_after == 0


def test_check_clamps_retry_after_minimum_to_one(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """A key past threshold whose TTL was lost (-1) or expired (-2)
    must still return Retry-After >= 1, never 0/negative. Spec §3.1.a:
    'clamp to [1, 900] to defend against TTL of -1 / -2 edge cases'."""
    # Set the key past threshold with no TTL.
    redis.set("auth:fail:1.2.3.4", str(THRESHOLD + 2))
    # PERSIST removes the TTL (TTL=-1).
    redis.persist("auth:fail:1.2.3.4")

    blocked, retry_after = check_should_block(redis, "1.2.3.4")
    assert blocked is True
    assert retry_after == 1


def test_check_clamps_retry_after_maximum_to_window(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """A pathological TTL > WINDOW_SEC clamps down to the window so
    the Retry-After header never lies about how long the lockout lasts."""
    redis.set("auth:fail:1.2.3.4", str(THRESHOLD))
    redis.expire("auth:fail:1.2.3.4", WINDOW_SEC * 10)

    blocked, retry_after = check_should_block(redis, "1.2.3.4")
    assert blocked is True
    assert retry_after <= WINDOW_SEC


# ---------------------------------------------------------------------------
# clear_failures — success path
# ---------------------------------------------------------------------------


def test_clear_failures_removes_the_counter(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """Successful login must reset quota — the next bad attempt from
    the same IP starts a fresh 1/5 counter, not 6/5."""
    for _ in range(4):
        record_failure(redis, "1.2.3.4")
    clear_failures(redis, "1.2.3.4")
    assert redis.exists("auth:fail:1.2.3.4") == 0
    blocked, _ = check_should_block(redis, "1.2.3.4")
    assert blocked is False


def test_clear_failures_unknown_ip_is_noop(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """Calling clear on an IP with no counter is silent — no exception,
    no row created."""
    clear_failures(redis, "9.9.9.9")
    assert redis.exists("auth:fail:9.9.9.9") == 0


# ---------------------------------------------------------------------------
# Fail-open on Redis errors (§3.1.a)
# ---------------------------------------------------------------------------


class _BrokenRedis:
    """Stand-in that raises on every operation — simulates Redis-down."""

    def get(self, *args: object, **kwargs: object) -> object:
        raise ConnectionError("redis is down")

    def incr(self, *args: object, **kwargs: object) -> object:
        raise ConnectionError("redis is down")

    def expire(self, *args: object, **kwargs: object) -> object:
        raise ConnectionError("redis is down")

    def ttl(self, *args: object, **kwargs: object) -> object:
        raise ConnectionError("redis is down")

    def delete(self, *args: object, **kwargs: object) -> object:
        raise ConnectionError("redis is down")


def test_check_fails_open_when_redis_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Spec §3.1.a 'Redis-down behaviour: fail-open': when Redis
    raises, the rate-limit gate logs a WARNING and returns
    not-blocked so the login proceeds against Argon2id."""
    caplog.set_level(logging.WARNING)
    blocked, retry_after = check_should_block(_BrokenRedis(), "1.2.3.4")
    assert blocked is False
    assert retry_after == 0
    # The warning is logged via loguru — caplog won't see it without
    # the loguru-pytest bridge, so we don't assert on caplog here.
    # The functional fail-open behaviour is what locks the contract.


def test_record_failure_fails_open_when_redis_raises() -> None:
    """A Redis outage during the failure-recording path must not
    prevent the 401 from going out. The helper swallows the exception."""
    record_failure(_BrokenRedis(), "1.2.3.4")  # must not raise


def test_clear_failures_fails_open_when_redis_raises() -> None:
    """A Redis outage during the success-clearing path must not block
    a legitimate login from completing. The helper swallows the
    exception (the next failed attempt from this IP will simply start
    a fresh counter once Redis is back)."""
    clear_failures(_BrokenRedis(), "1.2.3.4")  # must not raise


def test_record_failure_fails_open_only_partially_broken_redis(
    redis: fakeredis.FakeStrictRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If INCR succeeds but expire raises (a plausible split-failure
    after a partial network blip), the helper must still not crash —
    the counter exists, the next call will see it and continue."""
    real_expire = redis.expire

    def flaky_expire(*args: object, **kwargs: object) -> object:
        raise ConnectionError("network blip during expire")

    monkeypatch.setattr(redis, "expire", flaky_expire)
    record_failure(redis, "1.2.3.4")  # must not raise
    # Restore expire so cleanup works.
    monkeypatch.setattr(redis, "expire", real_expire)
    # The counter was incremented even though expire failed.
    assert redis.get("auth:fail:1.2.3.4") == "1"


def test_record_failure_recovers_ttl_on_subsequent_call_after_expire_outage(
    redis: fakeredis.FakeStrictRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a first-INCR+failed-EXPIRE used to leave the key
    with no TTL forever — every subsequent INCR returned 2, 3, 4...
    without re-arming, and once the count crossed THRESHOLD the IP was
    locked out indefinitely. The helper must probe the TTL on every
    INCR and re-arm whenever it's -1 so a transient EXPIRE outage
    self-heals on the next attempt.
    """
    real_expire = redis.expire
    expire_calls = {"count": 0}

    def flaky_expire(*args: object, **kwargs: object) -> object:
        expire_calls["count"] += 1
        if expire_calls["count"] == 1:
            raise ConnectionError("expire outage during first INCR")
        return real_expire(*args, **kwargs)

    monkeypatch.setattr(redis, "expire", flaky_expire)

    # First failure: INCR=1, EXPIRE raises → counter at 1, TTL=-1.
    record_failure(redis, "1.2.3.4")
    assert redis.get("auth:fail:1.2.3.4") == "1"
    assert redis.ttl("auth:fail:1.2.3.4") == -1, (
        "first EXPIRE outage must leave TTL=-1 (the bug under test)"
    )

    # Second failure: EXPIRE works this time. The helper must probe
    # the TTL, see -1, and re-arm. After this call: counter=2, TTL≈900.
    record_failure(redis, "1.2.3.4")
    assert redis.get("auth:fail:1.2.3.4") == "2"
    ttl_after = redis.ttl("auth:fail:1.2.3.4")
    assert WINDOW_SEC - 5 <= ttl_after <= WINDOW_SEC, (
        f"recovery EXPIRE must re-arm to ~{WINDOW_SEC}s, got TTL={ttl_after}"
    )


def test_record_failure_does_not_extend_ttl_when_already_armed(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """The TTL-probe-and-rearm logic must NOT touch an already-armed
    key — that would re-introduce the sliding window the spec
    explicitly avoids. Concretely: shrink the TTL manually, call
    record_failure, assert the TTL was NOT bumped back to ~900."""
    record_failure(redis, "1.2.3.4")
    redis.expire("auth:fail:1.2.3.4", 100)

    record_failure(redis, "1.2.3.4")
    ttl_after = redis.ttl("auth:fail:1.2.3.4")
    # Must still reflect the shrunken window (100 or just below);
    # MUST NOT have been bumped back to ~WINDOW_SEC.
    assert ttl_after <= 100


# ---------------------------------------------------------------------------
# End-to-end Stage A login rate-limit lifecycle (without the router)
# ---------------------------------------------------------------------------


def test_full_lifecycle_models_router_flow_check_then_record(
    redis: fakeredis.FakeStrictRedis,
) -> None:
    """Walk the Stage A login-router flow exactly: STEP 1 check →
    STEP 2 verify (assumed to fail here) → STEP 2-fail record. The
    sixth attempt must short-circuit at STEP 1 with blocked=True
    BEFORE record_failure runs — that is the documented ordering and
    locks in 5x 401s followed by 1x 429.
    """
    ip = "203.0.113.7"

    # First five attempts — each one passes the pre-check and records
    # a failure (simulating a wrong-password 401).
    for attempt in range(1, 6):
        blocked, _ = check_should_block(redis, ip)
        assert blocked is False, (
            f"attempt {attempt}: pre-check should not block until 6th"
        )
        record_failure(redis, ip)

    # Sixth attempt: pre-check sees count=5, returns blocked. The
    # router would short-circuit with 429 here and NEVER call
    # record_failure (saturated counter doesn't compound, §3.1.a).
    blocked, retry_after = check_should_block(redis, ip)
    assert blocked is True, "sixth attempt must be blocked at STEP 1"
    assert retry_after >= 1

    # Successful login (after the operator waits out the lockout, or
    # after a separate IP) clears the counter for the IP that succeeded.
    clear_failures(redis, ip)
    blocked, _ = check_should_block(redis, ip)
    assert blocked is False, "post-success-clear must reset quota"

    # Fresh quota — four more failed attempts can run without tripping.
    for attempt in range(1, 5):
        blocked, _ = check_should_block(redis, ip)
        assert blocked is False, (
            f"post-clear attempt {attempt}: should still be under threshold"
        )
        record_failure(redis, ip)


def test_log_levels_match_operational_contract() -> None:
    """Pin the log-level wiring so a future refactor can't quietly
    silence the throttle-degraded signal:

    - ``check_should_block`` emits WARNING on Redis errors (canonical
      pre-check fail-open signal — spec §3.1.a 'one line per request').
    - ``record_failure`` ALSO emits WARNING on Redis errors. A static
      level can't distinguish 'duplicate during full outage' from
      'sole signal during partial outage'; we accept the rare
      duplicate to avoid silent-loss-of-signal when Redis goes down
      between pre-check and recording.
    - ``clear_failures`` emits DEBUG on Redis errors. A failed clear
      is a success-path side effect (counter persists 15 more min);
      no operational alert needed.
    """
    import inspect

    check_block = inspect.getsource(rate_limit.check_should_block)
    record_src = inspect.getsource(rate_limit.record_failure)
    clear_src = inspect.getsource(rate_limit.clear_failures)

    assert "logger.warning(" in check_block, (
        "pre-check must emit WARNING on Redis fail-open"
    )
    assert "logger.warning(" in record_src, (
        "record_failure must emit WARNING on Redis fail-open — "
        "otherwise a partial outage between pre-check and recording "
        "leaves operators with no signal"
    )
    assert "logger.warning(" not in clear_src, (
        "clear_failures must NOT emit WARNING — it's a success-path "
        "side effect; failed clears are operationally marginal"
    )
    # Sanity: clear_failures DOES still log (at DEBUG), so a future
    # refactor that drops the log entirely is also caught.
    assert "logger.debug(" in clear_src
