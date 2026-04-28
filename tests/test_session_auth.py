"""Integration tests for SessionAuthMiddleware mounted by ``create_app``.

RENAMED from ``tests/test_console_auth.py`` per Stage A spec D7
(2026-04-28). The previous file asserted the legacy ``Basic`` auth
contract on ``/console/*``; slice 3f swapped the default mount to
``SessionAuthMiddleware``, and slice 3g (f) retired the legacy fallback
entirely per spec §7.10 Option B — every assertion here is cookie-based.
The ``test_no_middleware_when_env_vars_absent`` case is repurposed as
``test_no_middleware_when_no_operators_seeded`` per §8.2 — empty
``operators`` table now means ``/console/*`` returns 401, not "open".

This file owns the protected-route 401 contract under the real
``create_app`` factory; ``tests/test_auth_middleware.py`` covers the
ASGI-level middleware unit tests, and the empty-operators 204 contract
for ``/console/auth/whoami`` lives in ``tests/test_auth_login_logout.py``.
"""

from __future__ import annotations

from pathlib import Path

import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.api.app import SessionAuthMiddleware, create_app
from tests._console_auth_helpers import (
    login_console_client,
    seed_console_operator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def configured_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``CONSOLE_DB_PATH`` at a per-test temp file and disable
    cookie ``Secure`` so TestClient (plain HTTP) can carry the session
    cookie forward. Returns the resolved console.db path."""
    db = tmp_path / "console.db"
    monkeypatch.setenv("CONSOLE_DB_PATH", str(db))
    monkeypatch.setenv("HEIMDALL_COOKIE_SECURE", "0")
    return db


def _build_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Construct a real FastAPI app via ``create_app`` with fakeredis
    patched in. ``configured_env`` (if used) must run before this."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    return create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
        messages_dir=str(tmp_path / "messages"),
    )


@pytest.fixture
def authed_client(
    configured_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Logged-in TestClient against a real ``create_app`` factory."""
    app = _build_app(tmp_path, monkeypatch)
    with TestClient(app) as tc:
        seed_console_operator(configured_env)
        login_console_client(tc)
        yield tc


@pytest.fixture
def unauthed_client(
    configured_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """TestClient with the operator seeded but no login round trip."""
    app = _build_app(tmp_path, monkeypatch)
    with TestClient(app) as tc:
        seed_console_operator(configured_env)
        yield tc


# ---------------------------------------------------------------------------
# Cookie-based auth on /console/*
# ---------------------------------------------------------------------------


def test_console_rejects_without_cookie(unauthed_client: TestClient) -> None:
    """No cookie → 401 with ``not_authenticated`` body and no
    ``WWW-Authenticate`` realm header (Stage A drops Basic Auth)."""
    resp = unauthed_client.get("/console/dashboard")
    assert resp.status_code == 401
    assert resp.json() == {"error": "not_authenticated"}
    assert "WWW-Authenticate" not in resp.headers


def test_console_accepts_valid_session(authed_client: TestClient) -> None:
    """Logged-in cookie jar → request reaches the handler."""
    resp = authed_client.get("/console/status")
    assert resp.status_code != 401


def test_invalid_cookie_rejected_and_cleared(
    unauthed_client: TestClient,
) -> None:
    """Bogus cookie that hashes to no row → 401 + clear-cookie."""
    resp = unauthed_client.get(
        "/console/dashboard",
        cookies={"heimdall_session": "definitely-not-a-real-token"},
    )
    assert resp.status_code == 401
    set_cookie = resp.headers.get_list("set-cookie")
    assert any(
        "heimdall_session=" in h and "Max-Age=0" in h for h in set_cookie
    )


def test_app_prefix_protected(unauthed_client: TestClient) -> None:
    """``/app/*`` (the SPA shell) is protected, parity with today's
    legacy Basic Auth scope. Slice 3f keeps the originally-spec'd §5.6
    posture; the SPA login slice + handler-level WS auth ship together
    in the next slice and only then does the SPA actually load."""
    resp = unauthed_client.get("/app/")
    assert resp.status_code == 401


def test_health_no_auth_required(unauthed_client: TestClient) -> None:
    resp = unauthed_client.get("/health")
    assert resp.status_code == 200


def test_results_no_auth_required(unauthed_client: TestClient) -> None:
    resp = unauthed_client.get("/results/test-client")
    assert resp.status_code != 401


# ---------------------------------------------------------------------------
# Empty-operators contract (D7 rename of the bootstrap test)
# ---------------------------------------------------------------------------


def test_no_middleware_when_no_operators_seeded(
    configured_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the ``operators`` table is empty (no seed ran), the previous
    Basic-Auth flow exposed the console (open). After 3f, the protected
    paths return 401 — the absence of operators is no longer a bypass.
    """
    monkeypatch.delenv("CONSOLE_USER", raising=False)
    monkeypatch.delenv("CONSOLE_PASSWORD", raising=False)
    app = _build_app(tmp_path, monkeypatch)
    with TestClient(app) as tc:
        resp = tc.get("/console/dashboard")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Middleware-stack assertion for the single Stage A branch in create_app
# ---------------------------------------------------------------------------


def test_session_auth_middleware_mounted(
    configured_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 3g (f) retired the legacy fallback per spec §7.10 Option B:
    ``SessionAuthMiddleware`` is the only auth middleware mounted, and
    the session auth router is unconditionally included."""
    app = _build_app(tmp_path, monkeypatch)
    classes = [m.cls for m in getattr(app, "user_middleware", [])]
    assert SessionAuthMiddleware in classes
    routes = {getattr(r, "path", None) for r in app.routes}
    assert "/console/auth/login" in routes
    assert "/console/auth/logout" in routes
    assert "/console/auth/whoami" in routes
