"""Tests for src.api.auth.middleware — Stage A SessionAuthMiddleware.

Stage A spec §3.2 / §4.4 / §5.6 + §8.2 (test_auth_middleware.py block).

The middleware is a pure ASGI callable (NOT BaseHTTPMiddleware) so it
can defensively no-op on ``scope['type'] == 'websocket'`` per §5.6 —
WebSocket auth lives in the handler at ``/console/ws`` (slice later).

Behaviour locked here:
- ``/console/*`` and ``/app/*`` are protected; everything else passes
  through. The whitelist for ``/console/auth/login`` and
  ``/console/auth/whoami`` is exact-path so the auth entry points and
  the bootstrap probe stay reachable without a session cookie.
- DB lookup is by ``sha256(cookie_value)`` against
  ``sessions.token_hash`` — the raw cookie value is NEVER used as a DB
  key. The cookie-vs-DB-key separation is asserted directly.
- 401 on cookie missing / invalid / revoked / expired / disabled
  operator. When a cookie was presented the response carries
  ``Set-Cookie: heimdall_session=; Max-Age=0`` (and the same for
  ``heimdall_csrf``) so the browser drops a stale ticket. No
  ``Set-Cookie`` when no cookie was presented (nothing to clear).
- CSRF check fires on POST/PUT/PATCH/DELETE only. Mismatch → 403, no
  session revoke (a buggy SPA must not log the operator out).
- Sliding-window refresh is delegated to ``refresh_session`` (slice
  3a's CAS-guarded helper). The slid ``last_seen_at`` survives the
  middleware's per-request connection close because
  ``refresh_session`` self-commits.
- ``request.state.operator_id`` / ``request.state.session_id`` /
  ``request.state.role_hint`` populate on the authenticated branch
  for the audit-log writer (slice 3b) and downstream handlers.

The disabled-operator audit row (``auth.session_rejected_disabled``)
is intentionally NOT written by slice 3d — Federico's call (b)
deferred it to slice 3e where the audit-row plumbing is the slice's
focus. The disabled-operator test below asserts the 401 + clear-cookie
contract; the audit-row assertion will land in 3e's test file.
"""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import src.core.secrets as core_secrets
from src.api.auth.middleware import SessionAuthMiddleware
from src.api.auth.sessions import issue_session
from src.db.console_connection import get_console_conn, init_db_console


# ---------------------------------------------------------------------------
# Env-isolation fixture — same rationale as test_auth_sessions.py
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_console_seed_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop ``init_db_console`` from auto-seeding operator #0 in tests."""
    secrets_dir = tmp_path / "run-secrets"
    secrets_dir.mkdir()
    monkeypatch.setattr(core_secrets, "_SECRETS_DIR", secrets_dir)
    monkeypatch.delenv("CONSOLE_USER", raising=False)
    monkeypatch.delenv("CONSOLE_PASSWORD", raising=False)


# ---------------------------------------------------------------------------
# DB / session fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def console_db_path(tmp_path: Path) -> str:
    """Initialised console.db with one active operator (id=1, alice/owner)."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    conn = get_console_conn(db_path)
    conn.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', '$argon2id$placeholder', 'owner', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def seeded_session(console_db_path: str) -> tuple[str, str, int]:
    """Issue an active session for operator id=1.

    Returns ``(plaintext_token, csrf_token, session_id)``. The DB row
    has ``last_seen_at = NULL`` so the first authenticated request
    fires a refresh without the 60-second debounce blocking it.
    """
    conn = get_console_conn(console_db_path)
    issued = issue_session(conn, operator_id=1, ip="127.0.0.1", ua="seed-ua")
    conn.commit()
    conn.close()
    return issued.token, issued.csrf_token, issued.session_id


def _set_session_field(
    db_path: str, token: str, **fields: str | None
) -> None:
    """Surgically mutate a session row by token (helper for time-warp tests)."""
    h = hashlib.sha256(token.encode()).hexdigest()
    sets = ", ".join(f"{k} = ?" for k in fields)
    params = (*fields.values(), h)
    conn = get_console_conn(db_path)
    conn.execute(f"UPDATE sessions SET {sets} WHERE token_hash = ?", params)
    conn.commit()
    conn.close()


def _iso_offset(seconds: int) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ---------------------------------------------------------------------------
# App factory — the middleware-under-test mounted on a tiny app
# ---------------------------------------------------------------------------


def _build_app(console_db_path: str) -> FastAPI:
    """Build a minimal FastAPI app exercising every code path the
    middleware decides on.

    Routes intentionally span both protected prefixes (``/console/*``,
    ``/app/*``), the auth-bypass exact paths (``/console/auth/login``,
    ``/console/auth/whoami``), and the public prefixes (``/health``,
    ``/results/...``, ``/signup/...``, ``/static/...``) — one assertion
    per branch keeps the test surface honest."""
    app = FastAPI()
    app.add_middleware(SessionAuthMiddleware, console_db_path=console_db_path)

    @app.get("/console/dashboard")
    async def dashboard(request: Request) -> dict[str, Any]:
        return {
            "operator_id": getattr(request.state, "operator_id", None),
            "session_id": getattr(request.state, "session_id", None),
            "role_hint": getattr(request.state, "role_hint", None),
        }

    @app.post("/console/retention-jobs/1/cancel")
    async def cancel(request: Request) -> dict[str, Any]:
        return {"operator_id": getattr(request.state, "operator_id", None)}

    @app.get("/console/auth/login")
    async def login_get() -> dict[str, str]:
        return {"login": "form"}

    @app.post("/console/auth/login")
    async def login_post() -> dict[str, str]:
        return {"login": "ok"}

    @app.get("/console/auth/whoami")
    async def whoami() -> dict[str, str]:
        return {"whoami": "probe"}

    @app.get("/app/spa")
    async def spa() -> dict[str, str]:
        return {"spa": "ok"}

    @app.get("/app")
    async def app_root() -> dict[str, str]:
        return {"spa_shell": "root"}

    @app.get("/app/")
    async def app_root_slash() -> dict[str, str]:
        return {"spa_shell": "root_slash"}

    @app.get("/app/index.html")
    async def app_index_html() -> dict[str, str]:
        return {"spa_shell": "index"}

    @app.get("/app/assets/{filename:path}")
    async def app_assets(filename: str) -> dict[str, str]:
        return {"asset": filename}

    @app.post("/app/index.html")
    async def app_index_html_post() -> dict[str, str]:  # pragma: no cover
        return {"spa_shell": "post_should_not_reach"}

    @app.get("/app/whatever-else")
    async def app_other() -> dict[str, str]:  # pragma: no cover
        return {"reached": "should_not"}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/results/{client_id}")
    async def results(client_id: str) -> dict[str, str]:
        return {"client_id": client_id}

    @app.get("/signup/start")
    async def signup() -> dict[str, str]:
        return {"signup": "ok"}

    @app.get("/static/asset.css")
    async def static_asset() -> dict[str, str]:
        return {"asset": "ok"}

    return app


@pytest.fixture
def client(console_db_path: str) -> TestClient:
    return TestClient(_build_app(console_db_path))


# ---------------------------------------------------------------------------
# Public-prefix bypass
# ---------------------------------------------------------------------------


def test_health_bypasses_auth(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_results_bypasses_auth(client: TestClient) -> None:
    resp = client.get("/results/acme")
    assert resp.status_code == 200


def test_signup_bypasses_auth(client: TestClient) -> None:
    resp = client.get("/signup/start")
    assert resp.status_code == 200


def test_static_bypasses_auth(client: TestClient) -> None:
    """``/static/*`` is the legacy public asset mount and is NOT under
    ``/console`` or ``/app`` — it must pass through."""
    resp = client.get("/static/asset.css")
    assert resp.status_code == 200


def test_login_path_bypasses_auth(client: TestClient) -> None:
    """``/console/auth/login`` must reach the handler without a cookie
    — that's the entry point that issues the cookie in the first
    place. Spec §5.6 whitelist."""
    resp = client.post("/console/auth/login")
    assert resp.status_code == 200


def test_whoami_path_bypasses_auth(client: TestClient) -> None:
    """``/console/auth/whoami`` runs its own bootstrap state machine
    (204/409/200/401 per §3.5) regardless of session state — the
    middleware must not pre-empt it with a 401."""
    resp = client.get("/console/auth/whoami")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Cookie-missing / cookie-invalid → 401
# ---------------------------------------------------------------------------


def test_console_without_cookie_returns_401(client: TestClient) -> None:
    resp = client.get("/console/dashboard")
    assert resp.status_code == 401
    assert resp.json() == {"error": "not_authenticated"}


def test_console_without_cookie_does_not_set_clear_cookies(
    client: TestClient,
) -> None:
    """No cookie was presented, so there's nothing to clear. Avoid
    emitting unsolicited ``Set-Cookie`` headers — they would advertise
    the cookie names to a probing attacker without need."""
    resp = client.get("/console/dashboard")
    assert "set-cookie" not in {k.lower() for k in resp.headers.keys()}


def test_app_prefix_requires_auth(client: TestClient) -> None:
    """Parity with today's BasicAuthMiddleware: ``/app`` is protected."""
    resp = client.get("/app/spa")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SPA shell + assets bypass (slice 3g/3g.5)
# ---------------------------------------------------------------------------


def test_spa_root_no_slash_bypasses_auth(client: TestClient) -> None:
    """``GET /app`` is StaticFiles' redirect-to-/app/ entrypoint and must
    reach the inner app without a session cookie. The SPA bundle is what
    DRIVES auth state via ``/console/auth/whoami`` — gating the bundle
    itself is the chicken-and-egg bug slice 3g.5 exists to fix."""
    resp = client.get("/app")
    assert resp.status_code == 200
    assert resp.json() == {"spa_shell": "root"}


def test_spa_root_slash_bypasses_auth(client: TestClient) -> None:
    """``GET /app/`` is what StaticFiles(html=True) serves the index for."""
    resp = client.get("/app/")
    assert resp.status_code == 200
    assert resp.json() == {"spa_shell": "root_slash"}


def test_spa_index_html_bypasses_auth(client: TestClient) -> None:
    resp = client.get("/app/index.html")
    assert resp.status_code == 200
    assert resp.json() == {"spa_shell": "index"}


def test_spa_known_asset_filename_bypasses_auth(client: TestClient) -> None:
    """Real vite-emitted asset filename from a current build."""
    resp = client.get("/app/assets/index-LQ5IcGwD.js")
    assert resp.status_code == 200
    assert resp.json() == {"asset": "index-LQ5IcGwD.js"}


def test_spa_arbitrary_asset_name_bypasses_auth(client: TestClient) -> None:
    """Hashed bundle names change per vite build — the bypass is by
    prefix (``/app/assets/``), not by exact filename."""
    resp = client.get("/app/assets/index-anyHash1234.css")
    assert resp.status_code == 200
    assert resp.json() == {"asset": "index-anyHash1234.css"}


def test_app_other_path_still_requires_auth(client: TestClient) -> None:
    """Bypass is conservative: only the listed shell paths and the
    ``/app/assets/`` prefix. Everything else under ``/app/*`` stays
    gated so a future ``/app/api/secret`` route can't accidentally leak."""
    resp = client.get("/app/whatever-else")
    assert resp.status_code == 401


def test_spa_bypass_does_not_relax_post(client: TestClient) -> None:
    """The bypass is GET/HEAD only — state-changing methods on the same
    URLs must still 401. StaticFiles only answers safe methods anyway,
    but pinning method-restriction here defends against a future router
    that accidentally registers a POST handler under the same path."""
    resp = client.post("/app/index.html")
    assert resp.status_code == 401


def test_console_path_not_widened_by_spa_bypass(client: TestClient) -> None:
    """Regression: the SPA bypass must not affect ``/console/*``. A
    cookie-less GET to a non-whitelisted ``/console`` path stays 401."""
    resp = client.get("/console/dashboard")
    assert resp.status_code == 401


def test_protected_prefix_does_not_overmatch_lookalike_paths(
    console_db_path: str,
) -> None:
    """``/consolex`` / ``/apple`` are NOT under the protected prefix.

    Codex P2 (slice 3d): the bare ``startswith('/console')`` over-
    matches ``/consolex`` and silently auth-gates anything with that
    prefix. The fix enforces a path-segment boundary
    (``path == '/console'`` or ``path.startswith('/console/')``) so
    only true descendants are protected. Locking the regression here
    so the boundary doesn't quietly drift back."""
    app = FastAPI()
    app.add_middleware(SessionAuthMiddleware, console_db_path=console_db_path)

    @app.get("/consolex")
    async def consolex() -> dict[str, str]:
        return {"reached": "yes"}

    @app.get("/apple")
    async def apple() -> dict[str, str]:
        return {"reached": "yes"}

    test_client = TestClient(app)

    resp_a = test_client.get("/consolex")
    assert resp_a.status_code == 200
    assert resp_a.json() == {"reached": "yes"}

    resp_b = test_client.get("/apple")
    assert resp_b.status_code == 200
    assert resp_b.json() == {"reached": "yes"}


def test_invalid_cookie_returns_401_and_clears_cookies(
    client: TestClient,
) -> None:
    resp = client.get(
        "/console/dashboard",
        cookies={"heimdall_session": "totally-not-a-real-token"},
    )
    assert resp.status_code == 401
    raw = resp.headers.get_list("set-cookie")
    joined = " | ".join(raw)
    assert "heimdall_session=" in joined
    assert "heimdall_csrf=" in joined
    # Both must carry an expiry-in-the-past or Max-Age=0 marker so the
    # browser drops them. Starlette emits Max-Age=0 + Expires=Thu, 01
    # Jan 1970 ... — assert on the Max-Age form which is the contract.
    assert "Max-Age=0" in joined or "max-age=0" in joined.lower()


# ---------------------------------------------------------------------------
# DB lookup uses sha256(cookie), NOT the raw cookie value
# ---------------------------------------------------------------------------


def test_lookup_uses_token_hash_not_raw_cookie(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    """Security review 2026-04-28 evening (spec §8.2): assert the
    middleware looks up by ``sha256(cookie)``, not the cookie value
    itself.

    Two assertions:
    1. Sending the plaintext token as the cookie → 200 (the middleware
       computes sha256 internally and finds the row).
    2. Sending the stored ``token_hash`` as the cookie → 401 (because
       sha256(token_hash) != token_hash for a 64-char hex string —
       there is no row whose token_hash hashes to the presented hash).
    """
    plaintext, _csrf, _sid = seeded_session
    db_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    assert db_hash != plaintext

    resp_ok = client.get(
        "/console/dashboard",
        cookies={"heimdall_session": plaintext},
    )
    assert resp_ok.status_code == 200, resp_ok.text

    resp_no = client.get(
        "/console/dashboard",
        cookies={"heimdall_session": db_hash},
    )
    assert resp_no.status_code == 401


# ---------------------------------------------------------------------------
# Valid cookie → 200 + request.state populated
# ---------------------------------------------------------------------------


def test_valid_cookie_attaches_state_to_request(
    client: TestClient,
    seeded_session: tuple[str, str, int],
) -> None:
    plaintext, _csrf, session_id = seeded_session
    resp = client.get(
        "/console/dashboard",
        cookies={"heimdall_session": plaintext},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["operator_id"] == 1
    assert body["session_id"] == session_id
    assert body["role_hint"] == "owner"


def test_valid_cookie_slides_last_seen_at(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    """A successful authenticated request must call ``refresh_session``
    and persist the slid ``last_seen_at``. ``last_seen_at`` starts NULL
    (slice 3a contract: first refresh is not debounced)."""
    plaintext, _csrf, _sid = seeded_session
    h = hashlib.sha256(plaintext.encode()).hexdigest()

    conn = get_console_conn(console_db_path)
    before = conn.execute(
        "SELECT last_seen_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["last_seen_at"]
    conn.close()
    assert before is None

    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 200

    conn = get_console_conn(console_db_path)
    after = conn.execute(
        "SELECT last_seen_at, last_seen_ip FROM sessions WHERE token_hash = ?",
        (h,),
    ).fetchone()
    conn.close()
    assert after["last_seen_at"] is not None


# ---------------------------------------------------------------------------
# Revoked / expired / disabled-operator → 401 + clear-cookie
# ---------------------------------------------------------------------------


def test_revoked_session_returns_401_and_clears_cookies(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    plaintext, _csrf, _sid = seeded_session
    _set_session_field(console_db_path, plaintext, revoked_at=_iso_offset(0))

    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 401
    joined = " | ".join(resp.headers.get_list("set-cookie"))
    assert "heimdall_session=" in joined
    assert "heimdall_csrf=" in joined


def test_idle_expired_session_returns_401_and_clears_cookies(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    plaintext, _csrf, _sid = seeded_session
    _set_session_field(console_db_path, plaintext, expires_at=_iso_offset(-1))

    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 401
    joined = " | ".join(resp.headers.get_list("set-cookie"))
    assert "heimdall_session=" in joined
    assert "heimdall_csrf=" in joined


def test_absolute_expired_session_returns_401_and_clears_cookies(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    plaintext, _csrf, _sid = seeded_session
    _set_session_field(
        console_db_path, plaintext, absolute_expires_at=_iso_offset(-1)
    )

    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 401


def test_disabled_operator_session_returns_401_clears_cookies_and_writes_audit(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    """Disabling the operator mid-session invalidates live sessions
    immediately — slice 3a's SELECT filters on ``disabled_at IS NULL``.

    Slice 3e item F: in addition to the 401 + clear-cookie contract,
    the middleware writes an ``auth.session_rejected_disabled`` row
    to ``console.audit_log`` with the operator/session pair so a
    later forensic review can spot disabled-operator session-reuse
    attempts. Other miss reasons (revoked / idle-expired / absolute-
    expired) DO NOT write this row — see the negative-control tests
    below."""
    plaintext, _csrf, sid = seeded_session
    conn = get_console_conn(console_db_path)
    conn.execute(
        "UPDATE operators SET disabled_at = ? WHERE id = 1",
        (_iso_offset(0),),
    )
    conn.commit()
    conn.close()

    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 401
    joined = " | ".join(resp.headers.get_list("set-cookie"))
    assert "heimdall_session=" in joined
    assert "heimdall_csrf=" in joined

    conn = get_console_conn(console_db_path)
    rows = conn.execute(
        "SELECT operator_id, session_id, target_type, target_id "
        "FROM audit_log WHERE action = 'auth.session_rejected_disabled'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    row = rows[0]
    assert row["operator_id"] == 1
    assert row["session_id"] == sid
    assert row["target_type"] == "session"
    assert row["target_id"] == str(sid)


def test_revoked_session_does_not_write_disabled_audit_row(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    """Negative control for item F: a revoked session is rejected by
    the middleware but does NOT trigger the disabled-operator probe
    insert (the row records "operator was disabled mid-session", not
    "any rejection")."""
    plaintext, _csrf, _sid = seeded_session
    _set_session_field(console_db_path, plaintext, revoked_at=_iso_offset(0))

    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 401

    conn = get_console_conn(console_db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM audit_log "
        "WHERE action = 'auth.session_rejected_disabled'"
    ).fetchone()[0]
    conn.close()
    assert count == 0


def test_idle_expired_session_does_not_write_disabled_audit_row(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    """Negative control for item F: idle-expired sessions stay
    silent — the only state we audit is "session active, operator
    disabled"."""
    plaintext, _csrf, _sid = seeded_session
    _set_session_field(console_db_path, plaintext, expires_at=_iso_offset(-1))

    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 401

    conn = get_console_conn(console_db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM audit_log "
        "WHERE action = 'auth.session_rejected_disabled'"
    ).fetchone()[0]
    conn.close()
    assert count == 0


# ---------------------------------------------------------------------------
# CSRF — POST/PUT/PATCH/DELETE only
# ---------------------------------------------------------------------------


def test_post_without_csrf_header_returns_403(
    client: TestClient,
    seeded_session: tuple[str, str, int],
) -> None:
    plaintext, _csrf, _sid = seeded_session
    resp = client.post(
        "/console/retention-jobs/1/cancel",
        cookies={"heimdall_session": plaintext},
    )
    assert resp.status_code == 403
    assert resp.json() == {"error": "csrf_mismatch"}


def test_post_with_wrong_csrf_header_returns_403_no_revoke(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    """A buggy SPA must not log the operator out on CSRF mismatch — the
    session row must remain unrevoked so the next request with the
    correct header succeeds."""
    plaintext, _csrf, _sid = seeded_session
    h = hashlib.sha256(plaintext.encode()).hexdigest()

    resp = client.post(
        "/console/retention-jobs/1/cancel",
        cookies={"heimdall_session": plaintext},
        headers={"X-CSRF-Token": "totally-wrong"},
    )
    assert resp.status_code == 403

    conn = get_console_conn(console_db_path)
    revoked_at = conn.execute(
        "SELECT revoked_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["revoked_at"]
    conn.close()
    assert revoked_at is None, "CSRF mismatch must NOT revoke the session"


def test_post_with_matching_csrf_header_returns_200(
    client: TestClient,
    seeded_session: tuple[str, str, int],
) -> None:
    plaintext, csrf, _sid = seeded_session
    resp = client.post(
        "/console/retention-jobs/1/cancel",
        cookies={"heimdall_session": plaintext},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json() == {"operator_id": 1}


def test_get_without_csrf_header_returns_200(
    client: TestClient,
    seeded_session: tuple[str, str, int],
) -> None:
    """Safe methods (GET/HEAD/OPTIONS) skip the CSRF check entirely —
    the threat model only covers state-changing requests."""
    plaintext, _csrf, _sid = seeded_session
    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Defensive WebSocket-scope no-op (spec §5.6)
# ---------------------------------------------------------------------------


def test_websocket_scope_passes_through_to_inner_app(
    console_db_path: str,
) -> None:
    """If a WS scope ever reaches this middleware (Starlette's HTTP
    middleware shouldn't be invoked for ws scopes today, but spec §5.6
    requires defensive insurance), it must forward to the inner app
    untouched — no DB lookup, no auth check.

    Driven through raw ASGI rather than TestClient because the goal is
    to assert the early-return on ``scope['type'] == 'websocket'``."""
    inner_called: list[dict[str, Any]] = []

    async def inner_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        inner_called.append(scope)

    async def receive() -> dict[str, Any]:  # pragma: no cover — never called
        return {"type": "websocket.connect"}

    async def send(_message: dict[str, Any]) -> None:  # pragma: no cover
        pass

    middleware = SessionAuthMiddleware(
        inner_app, console_db_path=console_db_path
    )
    ws_scope: dict[str, Any] = {
        "type": "websocket",
        "path": "/console/ws",
        "headers": [],
    }
    asyncio.run(middleware(ws_scope, receive, send))

    assert len(inner_called) == 1
    assert inner_called[0] is ws_scope, "WS scope must forward verbatim"


def test_lifespan_scope_passes_through_to_inner_app(
    console_db_path: str,
) -> None:
    """``lifespan`` startup/shutdown messages must also pass through —
    the middleware is HTTP-only by design."""
    forwarded: list[str] = []

    async def inner_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        forwarded.append(scope["type"])

    async def receive() -> dict[str, Any]:  # pragma: no cover
        return {"type": "lifespan.startup"}

    async def send(_message: dict[str, Any]) -> None:  # pragma: no cover
        pass

    middleware = SessionAuthMiddleware(
        inner_app, console_db_path=console_db_path
    )
    asyncio.run(middleware({"type": "lifespan"}, receive, send))
    assert forwarded == ["lifespan"]


# ---------------------------------------------------------------------------
# CSRF: empty-string header is treated as missing
# ---------------------------------------------------------------------------


def test_post_with_empty_csrf_header_returns_403(
    client: TestClient,
    seeded_session: tuple[str, str, int],
) -> None:
    """An empty string is not a token. ``secrets.compare_digest('', '')``
    returns True, so a naive comparison would let an empty cookie/empty
    header pair through against a malformed session whose csrf_token
    column was somehow blanked. Treat empty as missing."""
    plaintext, _csrf, _sid = seeded_session
    resp = client.post(
        "/console/retention-jobs/1/cancel",
        cookies={"heimdall_session": plaintext},
        headers={"X-CSRF-Token": ""},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Refresh-CAS-loss returns 401 (operator was disabled between validate and
# refresh — refresh_session returns None on lost CAS, middleware must NOT
# fall through to the protected handler with stale state)
# ---------------------------------------------------------------------------


def test_refresh_cas_loss_returns_401(
    client: TestClient,
    console_db_path: str,
    seeded_session: tuple[str, str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If validate passes but refresh's CAS UPDATE finds zero rows —
    e.g. the operator was disabled in the sub-millisecond gap, or the
    session crossed an idle-expiry boundary — refresh_session returns
    None. The middleware must treat that as 'no longer authenticated'
    and 401 with cleared cookies, not pass through to the handler."""
    import src.api.auth.middleware as middleware_module

    plaintext, _csrf, _sid = seeded_session

    def fake_refresh(*args: Any, **kwargs: Any) -> sqlite3.Row | None:
        return None

    monkeypatch.setattr(
        middleware_module, "refresh_session", fake_refresh
    )

    resp = client.get(
        "/console/dashboard", cookies={"heimdall_session": plaintext}
    )
    assert resp.status_code == 401
    joined = " | ".join(resp.headers.get_list("set-cookie"))
    assert "heimdall_session=" in joined
    assert "heimdall_csrf=" in joined


# ---------------------------------------------------------------------------
# Stage A.5 §6.6 — request_id plumbing through the seeded scope
# ---------------------------------------------------------------------------


def test_request_id_propagates_through_session_auth_to_handler(
    console_db_path: str,
    seeded_session: tuple[str, str, int],
) -> None:
    """When ``RequestIdMiddleware`` mounts OUTERMOST and
    ``SessionAuthMiddleware`` mounts inside it (production order per
    spec §4.3.3), the inbound ``X-Request-ID`` value lands on
    ``request.state.request_id`` AT the handler — i.e.
    SessionAuthMiddleware's ``scope.setdefault("state", {})`` does
    not clobber the request_id that RequestIdMiddleware already
    populated.

    Locks the contract that future middleware reordering or state
    rewrites cannot silently drop the correlation id."""
    from src.api.auth.request_id import RequestIdMiddleware

    plaintext, _csrf, _sid = seeded_session

    app = FastAPI()
    # add_middleware pushes onto the head of the stack, so the LAST
    # add_middleware call is the OUTERMOST layer. Spec §4.3.3 order:
    # [RequestId → RequestLogging → SessionAuth → handler] at runtime.
    # We omit RequestLoggingMiddleware here — it's covered by
    # tests/test_request_id_middleware.py — and exercise just the
    # RequestId-on-top-of-SessionAuth pair that the spec adjustment
    # asks us to lock.
    app.add_middleware(SessionAuthMiddleware, console_db_path=console_db_path)
    app.add_middleware(RequestIdMiddleware)

    @app.get("/console/dashboard")
    async def dashboard(request: Request) -> dict[str, Any]:
        return {
            "operator_id": getattr(request.state, "operator_id", None),
            "session_id": getattr(request.state, "session_id", None),
            "request_id": getattr(request.state, "request_id", None),
        }

    rid = "rid-mw-corr-1"
    with TestClient(app) as tc:
        resp = tc.get(
            "/console/dashboard",
            cookies={"heimdall_session": plaintext},
            headers={"X-Request-ID": rid},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["operator_id"] == 1
    assert body["session_id"] is not None
    assert body["request_id"] == rid
    # Echo on response too — RequestIdMiddleware injects on
    # http.response.start.
    assert resp.headers["x-request-id"] == rid
