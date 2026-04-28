"""SessionAuthMiddleware — HTTP-only ASGI gate for the operator console.

Stage A spec §3.2 / §4.4 / §5.6 + §8.2 (test_auth_middleware.py block).

Authenticates ``/console/*`` and ``/app/*`` HTTP requests via the
``heimdall_session`` cookie. The cookie carries a 256-bit plaintext
token (``secrets.token_urlsafe(32)``); the server stores only its
SHA-256 digest in ``sessions.token_hash``. On every request the
middleware computes ``sha256(presented_cookie_value)`` and looks up
the matching ``token_hash`` row — the plaintext is never compared
against the stored value directly. A DB-only leak is therefore not
equivalent to a session-impersonation oracle (§4.2).

WebSocket scope is explicitly NOT authenticated here. Per §5.2 +
§5.6, Starlette's HTTP middleware does not reliably gate WebSocket
upgrades, so WS auth lives inside the ``/console/ws`` handler which
reads the same cookie before ``ws.accept()`` and closes with code
4401 on failure. The middleware defensively passes WS scopes (and
``lifespan`` scopes) straight through to the inner app — if a future
Starlette version were to start passing WS scopes through HTTP
middleware, the early return is a no-op rather than a half-broken
auth path.

Why a pure ASGI callable, not ``BaseHTTPMiddleware``: the latter is
HTTP-only by construction and would silently skip WS scopes anyway,
but the raw ``async __call__`` form makes the scope-branching
defensive guard explicit and grep-able. It also keeps the middleware
free of the ``StreamingResponse`` body consumption that
``BaseHTTPMiddleware`` performs — we only need to read headers and
cookies, never the body.

Whitelist behaviour:
- Public prefixes (``/health``, ``/results/``, ``/signup/``,
  ``/static/``) are not protected; the middleware only enforces on
  ``/console/*`` and ``/app/*``, matching ``BasicAuthMiddleware``'s
  prefix scope today.
- ``/console/auth/login`` and ``/console/auth/whoami`` are exact-path
  bypasses inside the protected prefix: login is the cookie-issuance
  entry point, and whoami runs its own bootstrap state machine
  (204/409/200/401 per §3.5) regardless of session state.

Failure modes (HTTP scope, protected prefix):
- Cookie missing → 401 ``{"error": "not_authenticated"}``, no
  ``Set-Cookie`` (nothing to clear).
- Cookie present but does not hash to any row, or the matching row is
  revoked / idle-expired / absolute-expired / belongs to a disabled
  operator → 401 + ``Set-Cookie: heimdall_session=; Max-Age=0`` and
  ``heimdall_csrf=; Max-Age=0`` so the browser drops the stale ticket.
  The disabled-operator branch does NOT write an
  ``auth.session_rejected_disabled`` audit row in slice 3d (Federico's
  call (b), 2026-04-28); audit-row plumbing lands in slice 3e where
  login/logout/whoami also wire their audit writes.
- POST/PUT/PATCH/DELETE with missing or non-matching ``X-CSRF-Token``
  header → 403 ``{"error": "csrf_mismatch"}``. The session is NOT
  revoked — a buggy SPA must not log the operator out (§4.4).
- ``refresh_session`` returns None (CAS lost on expiry edge or
  operator disabled in the sub-millisecond gap) → 401 + clear-cookies.

On success the middleware populates ``request.state`` with
``operator_id`` / ``session_id`` / ``role_hint`` so the audit-log
writer (slice 3b) and downstream handlers can read them without
re-fetching.
"""

from __future__ import annotations

import hashlib
import secrets as stdlib_secrets
import sqlite3
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.api.auth.audit import write_console_audit_row
from src.api.auth.sessions import refresh_session, validate_session_by_hash
from src.db.console_connection import get_console_conn

# ---------------------------------------------------------------------------
# Wire contract — cookie names + path scope
# ---------------------------------------------------------------------------

SESSION_COOKIE = "heimdall_session"
CSRF_COOKIE = "heimdall_csrf"
CSRF_HEADER = "X-CSRF-Token"

# Match BasicAuthMiddleware.PROTECTED_PREFIXES (``/console`` + ``/app``)
# but enforce a path-segment boundary so ``/consolex`` or ``/apple``
# do NOT silently inherit auth — the legacy middleware's bare
# ``startswith`` would over-match those, which is broader than spec
# §5.6's ``/console/*`` + ``/app/*`` scope. Each entry is matched by
# ``path == prefix`` (the bare segment) or ``path.startswith(prefix +
# "/")`` (anything beneath it).
_PROTECTED_PREFIXES = ("/console", "/app")

# Exact-path whitelist inside the protected prefix. Login is the
# entry point that ISSUES the cookie; whoami runs its own 204/409/
# 200/401 state machine per §3.5 and must reach the handler regardless
# of session state.
_AUTH_BYPASS_PATHS = frozenset(
    {
        "/console/auth/login",
        "/console/auth/whoami",
    }
)

# State-changing methods require a matching ``X-CSRF-Token`` header
# (§4.4). Safe methods (GET/HEAD/OPTIONS) skip the CSRF check — the
# threat model only covers requests that mutate server state.
_CSRF_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class SessionAuthMiddleware:
    """ASGI middleware that authenticates HTTP requests via the
    ``heimdall_session`` cookie. See module docstring for the contract.

    Constructor arguments:
        app: The inner ASGI app to forward authenticated requests to.
        console_db_path: Filesystem path to ``console.db``. Required so
            tests can inject a temp DB; production wiring (slice 3e)
            passes ``app.state.console_db_path`` from the FastAPI app
            factory.
    """

    def __init__(self, app: ASGIApp, *, console_db_path: str) -> None:
        self.app = app
        self.console_db_path = console_db_path

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        # Defensive scope branching (§5.6). The middleware is HTTP-only;
        # WebSocket auth lives in the ``/console/ws`` handler. ``lifespan``
        # passes through unconditionally so app startup / shutdown is
        # never gated on auth state.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Public prefixes (``/health``, ``/results/...``, ``/signup/...``,
        # ``/static/...``) are not protected.
        if not _is_protected(path):
            await self.app(scope, receive, send)
            return

        # Auth-bypass exact paths inside the protected prefix.
        if path in _AUTH_BYPASS_PATHS:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        cookie_value = request.cookies.get(SESSION_COOKIE)

        if not cookie_value:
            # Nothing to clear — don't advertise the cookie names to a
            # probing attacker via unsolicited Set-Cookie headers.
            response = _unauthenticated(clear_cookies=False)
            await response(scope, receive, send)
            return

        presented_hash = hashlib.sha256(cookie_value.encode("utf-8")).hexdigest()

        conn = get_console_conn(self.console_db_path)
        try:
            row = validate_session_by_hash(conn, presented_hash)
            if row is None:
                # Slice 3e (item F): if the rejected cookie maps to an
                # otherwise-active session whose operator was disabled,
                # write an ``auth.session_rejected_disabled`` audit row
                # before the 401. Other miss reasons (no such session,
                # revoked, idle/absolute expired) stay silent — the
                # revoke or expiry is its own audited event upstream.
                _maybe_write_disabled_operator_audit(
                    conn, request, presented_hash
                )
                response = _unauthenticated(clear_cookies=True)
                await response(scope, receive, send)
                return

            # CSRF check on state-changing methods only (§4.4). Run
            # BEFORE the refresh write so a CSRF mismatch is a pure
            # rejection — no row mutation, no log noise.
            if scope.get("method", "").upper() in _CSRF_METHODS:
                if not _csrf_ok(request, row["csrf_token"]):
                    response = _csrf_mismatch()
                    await response(scope, receive, send)
                    return

            # Sliding-window refresh. ``refresh_session`` self-commits
            # (slice 3a contract — caller has no audit-row pair to
            # commit alongside). Returns None when the session crosses
            # an expiry edge in the validate→update window or the
            # operator was disabled in that gap.
            client = scope.get("client") or (None, None)
            ip = client[0] if client else None
            ua = request.headers.get("user-agent")
            refreshed = refresh_session(conn, cookie_value, ip=ip, ua=ua)
            if refreshed is None:
                response = _unauthenticated(clear_cookies=True)
                await response(scope, receive, send)
                return

            operator_id = refreshed["operator_id"]
            session_id = refreshed["id"]
            role_hint = _fetch_role_hint(conn, operator_id)
        finally:
            conn.close()

        # Populate ``request.state`` for the audit-log writer (slice 3b)
        # and downstream handlers. ``scope['state']`` is the canonical
        # backing dict for ``Request.state`` in Starlette.
        state = scope.setdefault("state", {})
        state["operator_id"] = operator_id
        state["session_id"] = session_id
        state["role_hint"] = role_hint

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_protected(path: str) -> bool:
    """Match ``/console`` and ``/console/...`` but NOT ``/consolex``."""
    for prefix in _PROTECTED_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _csrf_ok(request: Request, expected_csrf: str) -> bool:
    """Constant-time compare of ``X-CSRF-Token`` header against the
    session's ``csrf_token``. Empty strings on either side count as
    missing — ``secrets.compare_digest('', '')`` returns True, which
    would let a malformed session whose csrf_token column was blanked
    accept any caller that forgot to send the header. Treat empty as
    a fast 403."""
    presented = request.headers.get(CSRF_HEADER, "")
    if not presented or not expected_csrf:
        return False
    return stdlib_secrets.compare_digest(presented, expected_csrf)


def _fetch_role_hint(conn: sqlite3.Connection, operator_id: int) -> str | None:
    """Single-row fetch of ``operators.role_hint``. Slice 3a's session
    SELECT does not return ``role_hint``; rather than amend that
    cross-slice contract, the middleware does its own one-column read.
    Operators is a tiny table, so the round-trip cost is negligible."""
    row = conn.execute(
        "SELECT role_hint FROM operators WHERE id = ?", (operator_id,)
    ).fetchone()
    if row is None:  # pragma: no cover — validate already filtered this out
        return None
    return row["role_hint"]


def _unauthenticated(*, clear_cookies: bool) -> JSONResponse:
    """Build a 401 JSONResponse, optionally with cookie-clearing
    Set-Cookie headers. The browser drops a cookie when ``Max-Age=0``;
    Starlette's ``delete_cookie`` emits exactly that shape."""
    response = JSONResponse(
        {"error": "not_authenticated"}, status_code=401
    )
    if clear_cookies:
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")
    return response


def _maybe_write_disabled_operator_audit(
    conn: sqlite3.Connection,
    request: Request,
    presented_hash: str,
) -> None:
    """Write ``auth.session_rejected_disabled`` iff the cookie maps to
    an otherwise-active session whose operator was disabled.

    The probe SELECT mirrors slice 3a's session-active filter (not
    revoked, not idle-expired, not absolute-expired) but inverts the
    operator filter to ``disabled_at IS NOT NULL``. If a row matches,
    we know the rejection reason was specifically "operator disabled
    while session was alive" — that's the only state where we write
    the row. Other miss reasons stay silent so we don't drown the
    audit log in routine expired-cookie events.

    Best-effort: a probe SELECT failure or audit-write failure logs
    at WARNING and falls through. The 401 is still returned by the
    caller — this helper exists to capture forensic state, not to
    gate the rejection."""
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        row = conn.execute(
            "SELECT s.id, s.operator_id "
            "FROM sessions s "
            "JOIN operators o ON o.id = s.operator_id "
            "WHERE s.token_hash = ? "
            "  AND s.revoked_at IS NULL "
            "  AND s.expires_at > ? "
            "  AND s.absolute_expires_at > ? "
            "  AND o.disabled_at IS NOT NULL",
            (presented_hash, now_iso, now_iso),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        logger.warning(
            "session_rejected_disabled probe failed: {}", exc
        )
        return

    if row is None:
        return

    try:
        with conn:
            write_console_audit_row(
                conn,
                request,
                action="auth.session_rejected_disabled",
                target_type="session",
                target_id=row["id"],
                operator_id=row["operator_id"],
                session_id=row["id"],
            )
    except sqlite3.OperationalError as exc:
        logger.warning(
            "session_rejected_disabled audit insert failed: {}", exc
        )


def _csrf_mismatch() -> JSONResponse:
    """403 with the ``csrf_mismatch`` sentinel string. No clear-cookie
    here — the session is intact, the SPA just didn't send the header
    correctly. ``logger.bind`` is called at INFO so a buggy SPA shows
    up in operational logs without flooding WARN."""
    logger.bind(context={"reason": "csrf_mismatch"}).info("auth_csrf_mismatch")
    return JSONResponse({"error": "csrf_mismatch"}, status_code=403)
