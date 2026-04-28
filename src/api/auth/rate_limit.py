"""Per-IP login rate limiter — Stage A spec §3.1.a.

Wraps a Redis client to expose three primitives the login handler
calls in order:

1. :func:`check_should_block` — STEP 1 of the login flow. Decides
   whether the request should short-circuit with 429 before the
   credential lookup + Argon2id verify ever run.
2. :func:`record_failure` — STEP 2-fail path. Increments the per-IP
   fail counter; the FIRST INCR also installs the 15-minute TTL.
3. :func:`clear_failures` — STEP 3-success path. Deletes the counter
   so a legitimate operator who recovers from a typo gets fresh quota.

Key shape is exactly ``auth:fail:<ip>`` — no environment prefix, no
namespace — so ops alerts grepping Redis keys can match without
guessing.

**Fail-open on Redis errors.** Spec §3.1.a explicitly chooses
"throttle off" over "auth offline" when Redis is unavailable: locking
the operator out of the control plane during a Redis blip is a worse
failure mode than a brief throttling gap. Argon2id at ~50ms gives
~20 attempts/s/IP as the worst-case throughput while Redis is down,
which is well below the rate at which a weak password falls. The
choice is recorded here so a future change cannot silently flip it.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Constants — wire contract (do not change without spec amendment)
# ---------------------------------------------------------------------------

KEY_PREFIX = "auth:fail:"
THRESHOLD = 5
WINDOW_SEC = 900  # 15 minutes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _key(ip: str) -> str:
    return f"{KEY_PREFIX}{ip}"


def _clamp_retry_after(ttl_seconds: int) -> int:
    """Clamp ``ttl_seconds`` into ``[1, WINDOW_SEC]``.

    A redis ``TTL`` of -1 (key has no expiry — TTL was lost via manual
    ops) or -2 (key vanished between GET and TTL) would otherwise
    produce a negative or zero ``Retry-After`` header, which is
    operationally meaningless. Clamping at the floor keeps the header
    truthful; clamping at the ceiling keeps it from advertising a
    longer lockout than the window actually lasts.
    """
    if ttl_seconds < 1:
        return 1
    if ttl_seconds > WINDOW_SEC:
        return WINDOW_SEC
    return ttl_seconds


# ---------------------------------------------------------------------------
# check_should_block — STEP 1
# ---------------------------------------------------------------------------


def check_should_block(redis_client: Any, ip: str) -> tuple[bool, int]:
    """Return ``(blocked, retry_after_seconds)`` for the source IP.

    When ``blocked`` is True, the caller MUST short-circuit the login
    with 429 + ``Retry-After: <retry_after_seconds>``; the credential
    lookup and Argon2id verify must NEVER run for that request (they
    are the steps the limiter exists to gate).

    On any Redis exception, returns ``(False, 0)`` and logs a WARNING
    — fail-open per §3.1.a. The login then proceeds against
    Argon2id without throttle protection until Redis recovers.
    """
    key = _key(ip)
    try:
        raw = redis_client.get(key)
        count = int(raw) if raw is not None else 0
        if count < THRESHOLD:
            return False, 0
        ttl = redis_client.ttl(key)
    except Exception as exc:
        logger.warning(
            "rate-limit check fail-open ({}); proceeding without throttle "
            "(spec §3.1.a)",
            exc,
        )
        return False, 0
    return True, _clamp_retry_after(int(ttl))


# ---------------------------------------------------------------------------
# record_failure — STEP 2 fail path
# ---------------------------------------------------------------------------


def record_failure(redis_client: Any, ip: str) -> None:
    """Increment the per-IP fail counter; install TTL whenever it's missing.

    Spec §3.1.a: 'Subsequent INCRs in the same window inherit the TTL
    set by the first one ... a sliding window would let an attacker
    pace 4 attempts every 14 min indefinitely.' We honour that with a
    TTL-aware re-arm: after the INCR, if the key has no TTL (-1, the
    first INCR's just-created state OR a recovery from a failed prior
    EXPIRE), we install ``WINDOW_SEC``. If the key already has a
    positive TTL, we DO NOT touch it — that's the sliding-window
    invariant.

    The naive "set TTL only when INCR returns 1" approach has a
    durable-lockout failure mode: if the first INCR succeeds but the
    paired EXPIRE raises, the counter sits at 1 with no TTL, and every
    subsequent INCR returns 2, 3, 4, ... without ever re-arming the
    expiry. Once it crosses THRESHOLD the IP is locked out indefinitely
    until a successful login or manual Redis cleanup. The TTL probe
    after every INCR closes that.

    The TTL probe cannot be exploited as a sliding-window oracle: a
    ``TTL = -1`` state is only reachable via a first INCR or a Redis
    ops anomaly (manual ``PERSIST``, prior EXPIRE outage); none of
    those are attacker-controlled, and resetting the window from a
    legitimate -1 state is operationally a recovery, not a reset.

    Fail-open on Redis exceptions — a counter that didn't increment is
    operationally equivalent to "Redis was down for this attempt"; the
    login still gets 401 from the credentials path, just without the
    throttle bookkeeping. The next attempt that lands while Redis is
    healthy starts (or continues) the counter normally.
    """
    key = _key(ip)
    try:
        redis_client.incr(key)
        # Probe the TTL: -1 means "no TTL set" (first INCR for a fresh
        # key, or recovery from a previously-failed EXPIRE); -2 means
        # "key disappeared between INCR and TTL" — the natural-expiry
        # boundary case where the window legitimately ticked over
        # between the INCR roundtrip and the TTL roundtrip. We treat
        # both as "no TTL set, arm one"; in the -2 boundary case
        # EXPIRE on a non-existent key is a Redis no-op, so the
        # increment is effectively absorbed by the window expiry —
        # which is exactly the spec contract ("5 fails in 15 min", not
        # "5 fails ever"). A Lua-script fix that recreated the key
        # after natural expiry would extend the lockout into a window
        # the spec says is fresh; we explicitly do not do that. Any
        # positive value means the TTL is already armed and we leave
        # it alone — that's the spec's anti-sliding-window contract.
        ttl = redis_client.ttl(key)
        if ttl is None or int(ttl) < 0:
            try:
                redis_client.expire(key, WINDOW_SEC)
            except Exception as exc:
                # Even the recovery EXPIRE can fail. Log at DEBUG and
                # move on; the next record_failure call will probe
                # again and try to recover. Spec §3.1.a allots one
                # WARNING per request and that goes to
                # check_should_block; secondary-path failures during
                # the same outage are noise we don't want in alerts.
                logger.debug(
                    "rate-limit expire fail-open after successful incr "
                    "({}); counter for {} has no TTL — next attempt will "
                    "retry the arm",
                    exc,
                    key,
                )
    except Exception as exc:
        # WARNING, not DEBUG: a static log level cannot distinguish
        # "Redis was already down for this request's pre-check" (in
        # which case this is a duplicate signal) from "Redis went
        # down between check_should_block and record_failure" (in
        # which case this is the ONLY signal that throttle bookkeeping
        # is missing for this request). Between rare duplicate noise
        # during a full outage and silent loss of signal during a
        # partial outage, prefer noise — ops needs to see the throttle
        # is degraded, even at the cost of an occasional duplicate
        # line during a full Redis outage.
        logger.warning(
            "rate-limit record-failure fail-open ({}); counter not "
            "incremented this attempt",
            exc,
        )


# ---------------------------------------------------------------------------
# clear_failures — STEP 3 success path
# ---------------------------------------------------------------------------


def clear_failures(redis_client: Any, ip: str) -> None:
    """Delete the per-IP fail counter. Idempotent against a missing key.

    Fail-open: a Redis outage during success-clearing must not block
    the login itself from completing. The next failed attempt from
    this IP after Redis recovers will simply create a fresh counter.
    """
    key = _key(ip)
    try:
        redis_client.delete(key)
    except Exception as exc:
        # DEBUG, not WARNING — see record_failure for the rationale
        # ("one line per request" goes to the pre-check).
        logger.debug(
            "rate-limit clear fail-open ({}); per-IP counter for {} not "
            "cleared this login",
            exc,
            key,
        )
