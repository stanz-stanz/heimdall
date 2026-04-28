"""Session ticket lifecycle for the operator console.

Stage A spec §3.2 / §3.3 / §3.4 / §4 / §7.5. Owns issue / validate /
refresh / revoke against ``console.db``'s ``sessions`` table. Used by
the login handler, the SessionAuthMiddleware (slice 3d), and the
WebSocket handler in ``/console/ws`` (later slice).

**Transaction split.** Per §7.5 every audit-paired session mutation
must commit in the same SQLite transaction as its audit-log row, so
``issue_session`` and ``revoke_session`` deliberately do NOT
self-commit — the caller wraps them plus the audit insert in a single
``with conn:`` block (or explicit ``BEGIN`` / ``COMMIT``).
``refresh_session`` is different: it has no paired audit row in
Stage A and is invoked from read-only authenticated requests
(SessionAuthMiddleware, WebSocket handler) where the caller has no
other write to commit. The middleware/handler pattern is "open conn,
authenticate, close conn"; without a self-commit the slid expires_at
is rolled back on close and the operator times out after the
original IDLE_TTL despite continued activity. ``refresh_session``
therefore commits its own UPDATE.

Token model (§4.2): the plaintext token is 32 bytes from the OS
CSPRNG, base64url-encoded (43 chars). The browser holds the plaintext
in the ``heimdall_session`` cookie. The server stores ONLY
``sha256(token).hexdigest()`` in ``sessions.token_hash`` — a DB-only
leak does not equate to a session-impersonation oracle. The CSRF
token is the same kind of secret stored verbatim, because the SPA must
echo it back as ``X-CSRF-Token`` and there is no security gain in
hashing a value the client already holds (§4.4).

Sliding-window refresh (§3.3): each authenticated request slides
``expires_at`` forward to ``min(now + IDLE_TTL, absolute_expires_at)``.
Writes are debounced to once per 60 seconds against the row's own
``last_seen_at``, which keeps multi-worker correctness trivial (the
synchronisation point is SQLite, not an in-process cache).
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


# ---------------------------------------------------------------------------
# TTL constants — env-driven, read once at import
# ---------------------------------------------------------------------------


def _ttl_minutes(env_name: str, default_min: int) -> int:
    """Read a positive-integer TTL from *env_name*, falling back to
    *default_min* when the variable is unset, blank, or non-numeric.

    Avoids crashing module import on a common ``.env`` misconfiguration
    (e.g. ``CONSOLE_SESSION_IDLE_TTL_MIN=`` with an empty value). The
    spec only commits to the env-override semantics for *valid* integer
    values; bad input is treated as "stick with the default" rather
    than as a startup failure.
    """
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default_min
    try:
        parsed = int(raw)
    except ValueError:
        return default_min
    if parsed <= 0:
        return default_min
    return parsed


IDLE_TTL_MIN: int = _ttl_minutes("CONSOLE_SESSION_IDLE_TTL_MIN", 15)
ABSOLUTE_TTL_MIN: int = _ttl_minutes("CONSOLE_SESSION_ABSOLUTE_TTL_MIN", 720)
REFRESH_DEBOUNCE_SEC: int = 60


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IssuedSession:
    """The plaintext-bearing handle returned by :func:`issue_session`.

    The plaintext ``token`` and ``csrf_token`` are intended for one
    purpose only: setting cookies on the response. They must never be
    logged, persisted, or returned to a different operator. Once the
    Set-Cookie header has been written, drop the reference.
    """

    token: str  # plaintext, 43 chars base64url, never persisted
    csrf_token: str  # plaintext, 43 chars base64url, persisted verbatim
    session_id: int
    operator_id: int
    issued_at: str
    expires_at: str
    absolute_expires_at: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# User-Agent strings can legitimately reach a few hundred characters, but
# nothing past that is forensically useful. Truncate at write time so a
# malicious or pathological client cannot inflate console.db / its WAL.
_MAX_UA_LEN = 512


def _truncate_ua(ua: str | None) -> str | None:
    if ua is None:
        return None
    return ua[:_MAX_UA_LEN]


def _select_active_session_sql() -> str:
    """SELECT used by validate / refresh / by-hash. Single source of
    truth for "session is active right now"."""
    return (
        "SELECT s.id, s.token_hash, s.csrf_token, s.operator_id, "
        "       s.issued_at, s.expires_at, s.absolute_expires_at, "
        "       s.revoked_at, s.last_seen_at, s.last_seen_ip, "
        "       s.last_seen_ua "
        "FROM sessions s "
        "JOIN operators o ON o.id = s.operator_id "
        "WHERE s.token_hash = ? "
        "  AND s.revoked_at IS NULL "
        "  AND s.expires_at > ? "
        "  AND s.absolute_expires_at > ? "
        "  AND o.disabled_at IS NULL"
    )


# ---------------------------------------------------------------------------
# issue_session
# ---------------------------------------------------------------------------


def issue_session(
    conn: sqlite3.Connection,
    operator_id: int,
    ip: str | None = None,
    ua: str | None = None,
) -> IssuedSession:
    """Insert a new ``sessions`` row for *operator_id* and return the
    plaintext handle.

    Caller is responsible for setting ``heimdall_session`` and
    ``heimdall_csrf`` cookies from the returned token + csrf_token.
    """
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)

    now = _now()
    issued_at = _iso(now)
    absolute_at = now + timedelta(minutes=ABSOLUTE_TTL_MIN)
    # Clamp the initial idle expiry at the absolute cap, mirroring the
    # same min() rule that refresh_session() applies. Without this, an
    # operator who configures ABSOLUTE_TTL < IDLE_TTL would receive a
    # cookie advertising a longer lifetime than the server honors.
    initial_expiry = min(now + timedelta(minutes=IDLE_TTL_MIN), absolute_at)
    expires_at = _iso(initial_expiry)
    absolute_expires_at = _iso(absolute_at)

    # Defense-in-depth: refuse to mint a session for a disabled or
    # non-existent operator. The login handler is the primary guard
    # (it filters disabled operators before reaching this helper), but
    # if an operator is disabled in the small window between credential
    # verification and session issuance, or if a future caller passes
    # an id without checking, the INSERT...SELECT short-circuits to
    # zero rows and the helper raises rather than minting a dead-on-
    # arrival cookie.
    cursor = conn.execute(
        "INSERT INTO sessions "
        "(token_hash, csrf_token, operator_id, "
        " issued_at, expires_at, absolute_expires_at, "
        " last_seen_at, last_seen_ip, last_seen_ua) "
        # last_seen_at deliberately NULL at issue: the 60-second
        # refresh debounce is anchored on last_seen_at, so seeding it
        # with issued_at would suppress the very first refresh after
        # login and the session's idle window would never slide past
        # the initial 15 minutes. NULL means "not yet seen on a
        # request"; the first authenticated request fires the refresh
        # without debounce.
        "SELECT ?, ?, ?, ?, ?, ?, NULL, ?, ? "
        "WHERE EXISTS ("
        "    SELECT 1 FROM operators "
        "    WHERE id = ? AND disabled_at IS NULL"
        ")",
        (
            token_hash,
            csrf_token,
            operator_id,
            issued_at,
            expires_at,
            absolute_expires_at,
            ip,
            _truncate_ua(ua),
            operator_id,
        ),
    )
    if cursor.rowcount == 0:
        raise ValueError(
            f"cannot issue session for operator_id={operator_id}: "
            "operator is disabled or does not exist"
        )

    return IssuedSession(
        token=token,
        csrf_token=csrf_token,
        session_id=cursor.lastrowid or 0,
        operator_id=operator_id,
        issued_at=issued_at,
        expires_at=expires_at,
        absolute_expires_at=absolute_expires_at,
    )


# ---------------------------------------------------------------------------
# validate_session — plaintext + by-hash
# ---------------------------------------------------------------------------


def validate_session(
    conn: sqlite3.Connection, token: str
) -> sqlite3.Row | None:
    """Hash *token* and return the active session row, or ``None``.

    Active means: not revoked, both expiry timestamps in the future,
    operator not disabled. The SHA-256 step is the only place the
    plaintext is touched — it lives only in this stack frame.
    """
    if not token:
        return None
    return validate_session_by_hash(conn, _hash_token(token))


def validate_session_by_hash(
    conn: sqlite3.Connection, token_hash: str
) -> sqlite3.Row | None:
    """SELECT the active session row by its stored hash.

    For callers (middleware, WS handler) that have already computed
    ``sha256(cookie_value)`` and don't want to redundantly hash twice.
    """
    if not token_hash:
        return None
    now = _iso(_now())
    return conn.execute(
        _select_active_session_sql(), (token_hash, now, now)
    ).fetchone()


# ---------------------------------------------------------------------------
# refresh_session — sliding-window with absolute cap and 60s debounce
# ---------------------------------------------------------------------------


def refresh_session(
    conn: sqlite3.Connection,
    token: str,
    ip: str | None = None,
    ua: str | None = None,
) -> sqlite3.Row | None:
    """Slide ``expires_at`` forward and update last-seen forensics.

    Returns the (possibly untouched) session row when the session is
    still valid, or ``None`` when it isn't (revoked / expired / operator
    disabled / unknown token).

    Debounce: if ``last_seen_at`` is younger than ``REFRESH_DEBOUNCE_SEC``,
    no UPDATE is issued — the row is returned unchanged. This is the
    write-amplification mitigation from spec §3.2 ("we don't UPDATE on
    every request — only when last_seen_at is stale by ≥60 seconds").

    Cap: the new ``expires_at`` is clamped at ``absolute_expires_at`` so
    a long-lived browser tab does not silently extend past the 12-hour
    hard cap.
    """
    row = validate_session(conn, token)
    if row is None:
        return row

    now = _now()
    last_seen_raw = row["last_seen_at"]
    if last_seen_raw is not None:
        last_seen = datetime.strptime(last_seen_raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
        if (now - last_seen).total_seconds() < REFRESH_DEBOUNCE_SEC:
            return row

    desired_expiry = now + timedelta(minutes=IDLE_TTL_MIN)
    absolute = datetime.strptime(
        row["absolute_expires_at"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=UTC)
    new_expires_at = _iso(min(desired_expiry, absolute))
    new_last_seen = _iso(now)
    now_iso = new_last_seen

    # CAS-style UPDATE: re-check both expiry timestamps and the operator
    # row in the WHERE clause so a sub-millisecond gap between
    # validate_session() and the UPDATE cannot silently resurrect an
    # idle-expired or absolute-expired session. If the session crossed
    # an expiry boundary in that window, the UPDATE affects 0 rows; the
    # subsequent validate-by-hash returns None, the caller treats the
    # request as unauthenticated.
    debounce_floor = _iso(now - timedelta(seconds=REFRESH_DEBOUNCE_SEC))

    # COALESCE preserves prior forensic values when the current request
    # cannot supply them (request.client is None, no User-Agent header).
    # Blanking last-known IP / UA on every metadata-less refresh would
    # permanently erase the last good forensic snapshot — a soft form of
    # self-DOS for incident analysis. NULL inputs leave the column
    # unchanged; non-NULL inputs overwrite as before.
    #
    # The WHERE clause encodes three CAS guards:
    #   - revoked_at / expires_at / absolute_expires_at / disabled_at —
    #     session must still be active at write time (closes the
    #     validate→update race that would otherwise resurrect an
    #     expired session).
    #   - last_seen_at IS NULL OR < (now - debounce) — atomic debounce.
    #     With uvicorn --workers >1, two concurrent refreshes against
    #     the same session would both pass the Python-side debounce
    #     check; this predicate makes only ONE of them win the write,
    #     preserving the "at most one write per 60s" contract.
    cursor = conn.execute(
        "UPDATE sessions "
        "SET expires_at = ?, last_seen_at = ?, "
        "    last_seen_ip = COALESCE(?, last_seen_ip), "
        "    last_seen_ua = COALESCE(?, last_seen_ua) "
        "WHERE token_hash = ? "
        "  AND revoked_at IS NULL "
        "  AND expires_at > ? "
        "  AND absolute_expires_at > ? "
        "  AND (last_seen_at IS NULL OR last_seen_at < ?) "
        "  AND operator_id IN ("
        "      SELECT id FROM operators WHERE disabled_at IS NULL"
        "  )",
        (
            new_expires_at,
            new_last_seen,
            ip,
            _truncate_ua(ua),
            row["token_hash"],
            now_iso,
            now_iso,
            debounce_floor,
        ),
    )
    # Self-commit: callers (middleware, WS handler) typically have no
    # other write to pair us with — without this, the slid expires_at
    # is rolled back on connection close and the session times out
    # despite activity. issue / revoke take the opposite stance
    # because they're paired with audit-log writes per §7.5.
    conn.commit()

    # On a 0-row UPDATE we can't tell from rowcount alone whether the
    # session crossed an expiry edge or another worker won the
    # debounce race. Re-validate to disambiguate: if the session is
    # still active, the lost race was benign (the other worker did the
    # write) and we return the now-fresh row; otherwise we return None.
    return validate_session_by_hash(conn, row["token_hash"])


# ---------------------------------------------------------------------------
# revoke_session — idempotent logout
# ---------------------------------------------------------------------------


def revoke_session(conn: sqlite3.Connection, token: str) -> None:
    """Mark the session revoked. Idempotent: an already-revoked session
    keeps its original ``revoked_at`` timestamp. An unknown token is a
    no-op (no row created, no exception).
    """
    if not token:
        return
    token_hash = _hash_token(token)
    conn.execute(
        "UPDATE sessions SET revoked_at = ? "
        "WHERE token_hash = ? AND revoked_at IS NULL",
        (_iso(_now()), token_hash),
    )
