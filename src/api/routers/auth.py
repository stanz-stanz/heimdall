"""``/console/auth/{login,logout,whoami}`` — Stage A auth router.

Stage A spec §3.1 / §3.4 / §3.5 / §6.3 / §7.3.

This is the first slice that integrates every prior auth primitive:

- Slice 2 — ``verify_password`` / ``hash_password`` (Argon2id).
- Slice 3a — ``issue_session`` / ``revoke_session`` /
  ``validate_session_by_hash`` (session ticket lifecycle).
- Slice 3b — ``write_console_audit_row`` (audit row writer, paired
  with the mutation in the same SQLite transaction per §7.5).
- Slice 3c — ``check_should_block`` / ``record_failure`` /
  ``clear_failures`` (per-IP login rate limiter; fail-open per
  §3.1.a).
- Slice 3d — ``SessionAuthMiddleware`` whitelist for
  ``/console/auth/login`` and ``/console/auth/whoami``; logout is
  middleware-protected (cookie + CSRF).

**Login flow (§3.1).** Three normative phases in order:

1. **Rate-limit pre-check** against Redis. The credential SELECT and
   Argon2id verify NEVER run until this gate passes. Fail-open on
   Redis errors (slice 3c handles the warning + fall-through).
2. **Credential lookup + Argon2id verify.** ``LOWER(username)`` lookup
   filtered on ``disabled_at IS NULL``. If the username is unknown,
   verify still runs against a fixed dummy Argon2id hash so the
   wire-timing of "no such user" matches "wrong password" (§3.1
   "if no row matched, run against a dummy hash to keep timing
   flat"). The dummy hash is computed lazily on first miss and
   cached module-side.
3. **Session issue + audit + Set-Cookie.** Inside a single
   ``with conn:`` block: ``issue_session`` (slice 3a) → ``UPDATE
   operators SET last_login_at, last_login_ip`` → ``write_console_
   audit_row(action='auth.login_ok')``. The block commits both
   inserts atomically; if any step raises, both roll back.

The single-failure path (no-such-user / wrong-password / disabled
operator) returns 401 ``{"error": "invalid_credentials"}`` — same
shape, same body, regardless of which check failed. The user-
enumeration oracle is closed at every layer (response body, response
timing, rate-limit counter, audit-row shape).

**Logout flow (§3.4).** Middleware-protected; handler reads
``request.state.{operator_id, session_id}`` already populated by
slice 3d. ``revoke_session`` + ``write_console_audit_row(action=
'auth.logout')`` inside one ``with conn:`` block. Response is 204
with both cookies cleared (``Max-Age=0``).

**Whoami flow (§3.5).** Middleware-bypassed (whitelisted in slice
3d). Four wire states:

- 204 No Content — ``operators`` table has zero rows total. Genuine
  empty bootstrap; SPA renders "no operators seeded" splash.
- 409 Conflict + ``{"error": "all_operators_disabled"}`` — rows
  exist but every row has ``disabled_at IS NOT NULL``. Operational
  posture, not an outage; SPA renders "all operators disabled"
  splash.
- 200 OK + harmonised body — at least one active operator exists
  and the cookie matches an active session. The body shape is
  ``{operator: {...}, session: {expires_at, absolute_expires_at},
  csrf_token}`` — same shape as login per Federico's harmonisation
  (2026-04-28).
- 401 Unauthorized — at least one active operator exists but the
  request is unauthenticated.

**No refresh on whoami.** Whoami is a state probe, not an
authenticated action. Sliding the session window on a probe would
silently extend lifetime even when the user isn't really using the
console. The middleware-routed real endpoints DO refresh; whoami
doesn't. No audit row written (read-side audit is a Stage A.5
concern per §7.3); no Set-Cookie on any branch.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from loguru import logger
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from src.api.auth.audit import write_console_audit_row
from src.api.auth.hashing import hash_password, verify_password
from src.api.auth.middleware import CSRF_COOKIE, SESSION_COOKIE
from src.api.auth.rate_limit import (
    check_should_block,
    clear_failures,
    record_failure,
)
from src.api.auth.sessions import (
    ABSOLUTE_TTL_MIN,
    issue_session,
    revoke_session,
    validate_session_by_hash,
)
from src.db.console_connection import DEFAULT_CONSOLE_DB_PATH, get_console_conn

router = APIRouter(prefix="/console/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Constants + lazy dummy-hash for the timing-oracle defense
# ---------------------------------------------------------------------------


# Cookie lifetime matches the absolute TTL — the server is the source
# of truth for validity (the row's expires_at can revoke earlier),
# and SameSite=Strict + HttpOnly are what protect cross-site abuse.
_COOKIE_MAX_AGE_SECONDS: int = ABSOLUTE_TTL_MIN * 60

# ``HEIMDALL_COOKIE_SECURE`` defaults to ``"1"`` (production posture).
# Dev (``localhost:8001`` plain HTTP) sets ``HEIMDALL_COOKIE_SECURE=0``.
_COOKIE_SECURE_DEFAULT = "1"


# Lazy dummy-hash cache. Computing one ~50ms Argon2id hash at import
# time would slow every test collection that touches this module.
# First-failure latency is the only place the cost surfaces.
_dummy_hash_cache: str | None = None


def _dummy_hash() -> str:
    global _dummy_hash_cache
    if _dummy_hash_cache is None:
        _dummy_hash_cache = hash_password("heimdall-timing-flat-dummy-input")
    return _dummy_hash_cache


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _client_ip(request: Request) -> str:
    """Trusted source IP — ``request.client.host`` only.

    Per §3.1.a we never read ``X-Forwarded-For`` here: that header is
    operator-controlled at the reverse proxy. Any production deploy
    that puts a proxy in front of api MUST set
    ``forwarded-allow-ips`` on uvicorn so the trusted upstream value
    lands in ``request.client.host``."""
    client = request.client
    if client is None or not client.host:
        return "unknown"
    return client.host


def _db_path(request: Request) -> str:
    return getattr(
        request.app.state, "console_db_path", DEFAULT_CONSOLE_DB_PATH
    )


def _redis(request: Request) -> Any | None:
    """Redis client from ``app.state.redis`` or None if the lifespan
    couldn't connect. Slice 3c's helpers fail-open on a None client by
    design — the login still proceeds against Argon2id, just without
    the throttle bookkeeping."""
    return getattr(request.app.state, "redis", None)


def _service_unavailable() -> JSONResponse:
    return JSONResponse(
        {"error": "service_unavailable"}, status_code=503
    )


def _set_session_cookies(
    response: Response, *, token: str, csrf_token: str, secure: bool
) -> None:
    """Set both cookies with §4.1's attribute set. Production deploys
    pass ``secure=True`` (HTTPS termination at the proxy). Dev passes
    False so plain-HTTP localhost still works."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf_token,
        max_age=_COOKIE_MAX_AGE_SECONDS,
        httponly=False,  # SPA reads this via document.cookie
        secure=secure,
        samesite="strict",
        path="/",
    )


def _cookie_secure() -> bool:
    return os.environ.get("HEIMDALL_COOKIE_SECURE", _COOKIE_SECURE_DEFAULT) == "1"


# ---------------------------------------------------------------------------
# Request models — Pydantic validates body shape before the handler runs
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=1024)


# ---------------------------------------------------------------------------
# POST /console/auth/login
# ---------------------------------------------------------------------------


@router.post("/login")
async def login(request: Request, body: LoginRequest) -> Response:
    ip = _client_ip(request)
    redis_client = _redis(request)

    # STEP 1 — rate-limit pre-check. ``check_should_block`` is fail-
    # open: a Redis outage returns ``(False, 0)`` and we proceed
    # against Argon2id.
    if redis_client is not None:
        blocked, retry_after = check_should_block(redis_client, ip)
        if blocked:
            return JSONResponse(
                {"error": "rate_limited"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

    try:
        conn = get_console_conn(_db_path(request))
    except sqlite3.OperationalError:
        logger.opt(exception=True).warning("login_db_open_failed")
        return _service_unavailable()

    try:
        return await _login_with_conn(
            request=request,
            body=body,
            conn=conn,
            ip=ip,
            redis_client=redis_client,
        )
    except sqlite3.OperationalError:
        # A DB error mid-flow is an availability problem, not an
        # attacker signal — do NOT increment the rate-limit counter
        # (§3.1 "What counts as a fail" rules 503 out).
        logger.opt(exception=True).warning("login_db_op_failed")
        return _service_unavailable()
    finally:
        conn.close()


async def _login_with_conn(
    *,
    request: Request,
    body: LoginRequest,
    conn: sqlite3.Connection,
    ip: str,
    redis_client: Any | None,
) -> Response:
    """Inner workflow with the open connection — separated so the
    outer ``try/except sqlite3.OperationalError`` covers every DB op
    without needing a deeply nested try."""
    # STEP 2 — credential lookup. ``LOWER(username)`` matches the
    # UNIQUE index on operators (§1.1).
    username_lookup = body.username.strip().lower()
    operator = conn.execute(
        "SELECT id, username, display_name, password_hash, role_hint "
        "FROM operators "
        "WHERE LOWER(username) = ? AND disabled_at IS NULL",
        (username_lookup,),
    ).fetchone()

    # Argon2id verify on whichever path we landed in. The no-row
    # branch verifies against a fixed dummy hash so wire-timing for
    # "no such user" matches "wrong password" — the user-enumeration
    # oracle is closed at the timing layer too, not just response
    # bodies.
    if operator is None:
        verify_password(_dummy_hash(), body.password)
        password_ok = False
    else:
        password_ok = verify_password(
            operator["password_hash"], body.password
        )

    if not password_ok:
        # Order matters: commit the ``auth.login_failed`` audit row
        # BEFORE incrementing the rate-limit counter. If the audit
        # INSERT raises ``OperationalError``, the outer handler
        # converts to 503 and §3.1.a's "503 is NOT a fail" rule must
        # hold — the counter must NOT advance on a DB error. Bumping
        # the counter first would let a transient DB outage masquerade
        # as a credential-failure signal.
        #
        # Audit row pairs with no other mutation here, so a single
        # ``with conn:`` block scopes the commit. The handler records
        # the attempted username (operator-controlled string) so
        # forensic correlation remains possible without leaking
        # whether the username existed.
        with conn:
            write_console_audit_row(
                conn,
                request,
                action="auth.login_failed",
                target_type="operator",
                target_id=body.username,
                operator_id=None,
                session_id=None,
            )
        if redis_client is not None:
            record_failure(redis_client, ip)
        return JSONResponse(
            {"error": "invalid_credentials"}, status_code=401
        )

    # STEP 3 — success. Clear the per-IP fail counter so a legitimate
    # operator who recovered from a typo gets fresh quota.
    if redis_client is not None:
        clear_failures(redis_client, ip)

    ua = request.headers.get("user-agent")
    with conn:
        issued = issue_session(
            conn, operator_id=operator["id"], ip=ip, ua=ua
        )
        conn.execute(
            "UPDATE operators "
            "SET last_login_at = ?, last_login_ip = ? "
            "WHERE id = ?",
            (_now_iso(), ip, operator["id"]),
        )
        write_console_audit_row(
            conn,
            request,
            action="auth.login_ok",
            target_type="operator",
            target_id=operator["id"],
            operator_id=operator["id"],
            session_id=issued.session_id,
        )

    # Body harmonised with whoami per Federico's 2026-04-28 call:
    # ``session`` scopes growth (future session metadata lands under
    # that key without polluting the top level) and login + whoami
    # are interchangeable to the SPA.
    response = JSONResponse(
        {
            "operator": {
                "id": operator["id"],
                "username": operator["username"],
                "display_name": operator["display_name"],
                "role_hint": operator["role_hint"],
            },
            "session": {
                "expires_at": issued.expires_at,
                "absolute_expires_at": issued.absolute_expires_at,
            },
            "csrf_token": issued.csrf_token,
        }
    )
    _set_session_cookies(
        response,
        token=issued.token,
        csrf_token=issued.csrf_token,
        secure=_cookie_secure(),
    )
    return response


# ---------------------------------------------------------------------------
# POST /console/auth/logout
# ---------------------------------------------------------------------------


@router.post("/logout")
async def logout(request: Request) -> Response:
    """Revoke the active session, clear cookies, write audit row.

    Middleware-protected: a request that reaches this handler has
    already passed cookie validation + CSRF check. ``request.state``
    carries ``operator_id`` and ``session_id`` set by slice 3d's
    middleware before forwarding."""
    operator_id = getattr(request.state, "operator_id", None)
    session_id = getattr(request.state, "session_id", None)
    cookie = request.cookies.get(SESSION_COOKIE)

    # Defensive: middleware should have already 401'd these branches,
    # but a misconfigured deploy that bypasses the middleware should
    # still fail closed rather than write a NULL audit row.
    if operator_id is None or session_id is None or not cookie:
        return JSONResponse(
            {"error": "not_authenticated"}, status_code=401
        )

    try:
        conn = get_console_conn(_db_path(request))
    except sqlite3.OperationalError:
        logger.opt(exception=True).warning("logout_db_open_failed")
        return _service_unavailable()

    try:
        with conn:
            revoke_session(conn, cookie)
            write_console_audit_row(
                conn,
                request,
                action="auth.logout",
                target_type="session",
                target_id=session_id,
                operator_id=operator_id,
                session_id=session_id,
            )
    except sqlite3.OperationalError:
        logger.opt(exception=True).warning("logout_db_op_failed")
        return _service_unavailable()
    finally:
        conn.close()

    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return response


# ---------------------------------------------------------------------------
# GET /console/auth/whoami
# ---------------------------------------------------------------------------


@router.get("/whoami")
async def whoami(request: Request) -> Response:
    """Four-state probe: 204 (empty bootstrap) / 409 (all disabled) /
    200 (authed) / 401 (unauthed).

    Bypasses ``SessionAuthMiddleware`` (whitelisted in slice 3d) so
    the bootstrap branches can run without a cookie. Read-only — no
    refresh, no audit row, no Set-Cookie on any branch.
    """
    try:
        conn = get_console_conn(_db_path(request))
    except sqlite3.OperationalError:
        logger.opt(exception=True).warning("whoami_db_open_failed")
        return _service_unavailable()

    try:
        # State 1 — empty bootstrap. Cheap COUNT against a tiny table.
        total = conn.execute(
            "SELECT COUNT(*) FROM operators"
        ).fetchone()[0]
        if total == 0:
            return Response(status_code=204)

        # State 2 — all disabled. Distinct from state 1 because the
        # operational response is "re-enable an operator", not "seed
        # the bootstrap".
        active = conn.execute(
            "SELECT COUNT(*) FROM operators WHERE disabled_at IS NULL"
        ).fetchone()[0]
        if active == 0:
            return JSONResponse(
                {"error": "all_operators_disabled"}, status_code=409
            )

        # State 3 / 4 — cookie validation. Whoami runs its own check
        # rather than relying on the middleware (which it bypasses).
        cookie = request.cookies.get(SESSION_COOKIE)
        if not cookie:
            return JSONResponse(
                {"error": "not_authenticated"}, status_code=401
            )

        token_hash = hashlib.sha256(cookie.encode("utf-8")).hexdigest()
        session_row = validate_session_by_hash(conn, token_hash)
        if session_row is None:
            return JSONResponse(
                {"error": "not_authenticated"}, status_code=401
            )

        operator = conn.execute(
            "SELECT id, username, display_name, role_hint "
            "FROM operators WHERE id = ?",
            (session_row["operator_id"],),
        ).fetchone()
    except sqlite3.OperationalError:
        logger.opt(exception=True).warning("whoami_db_op_failed")
        return _service_unavailable()
    finally:
        conn.close()

    return JSONResponse(
        {
            "operator": {
                "id": operator["id"],
                "username": operator["username"],
                "display_name": operator["display_name"],
                "role_hint": operator["role_hint"],
            },
            "session": {
                "expires_at": session_row["expires_at"],
                "absolute_expires_at": session_row["absolute_expires_at"],
            },
            "csrf_token": session_row["csrf_token"],
        }
    )
