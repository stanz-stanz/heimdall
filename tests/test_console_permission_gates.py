"""Parametrised allow / deny tests for the 18 gated /console/* HTTP routes
(Stage A.5 commit (2) wave B).

Spec §4.2.1 + §6.4. Each route is gated by exactly one ``Permission``;
``ROLE_PERMISSIONS["owner"]`` grants every permission. The deny case
re-seeds the operator with ``role_hint='observer'`` (not in the role
mapping → empty granted set) and asserts:

- ``r.status_code == 403``
- ``r.json() == {"error": "permission_denied", "permission": <value>}``
- exactly one ``console.audit_log`` row with
  ``action='auth.permission_denied'``, ``target_id=<value>``,
  ``payload_json`` containing ``{"role_hint": "observer"}``

The allow case asserts ``r.status_code != 403`` — the route may
return 200 / 400 / 404 / 503 depending on test data; the contract
under test is *the decorator allowed through*. Public routes get a
separate test that asserts NO ``auth.permission_denied`` row appears
even with the observer-role session.

Fork (b) — locked 2026-05-02. ``ROLE_PERMISSIONS = {"owner": ...}``;
spec text used ``"operator"``, seeded reality is ``"owner"`` (see
``docs/decisions/log.md`` and the wave-A commit message). The
``'observer'`` deny role is illustrative only — any non-``'owner'``
string lands in the empty granted set and produces 403.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

import src.core.secrets as core_secrets
from src.api.app import create_app
from src.db.connection import init_db
from src.db.console_connection import get_console_conn
from tests._console_auth_helpers import (
    login_console_client,
    seed_console_operator,
)


# ===========================================================================
# Route inventory (spec §4.2.1) — frozen for the gates sweep.
# ===========================================================================

# (method, path, permission_value, body_or_None)
GATED_ROUTES: list[tuple[str, str, str, Any]] = [
    # --- 12 CONSOLE_READ routes ---
    ("GET", "/console/status", "console.read", None),
    ("GET", "/console/dashboard", "console.read", None),
    ("GET", "/console/pipeline/last", "console.read", None),
    ("GET", "/console/campaigns", "console.read", None),
    (
        "GET",
        "/console/campaigns/0426-restaurants/prospects",
        "console.read",
        None,
    ),
    ("GET", "/console/briefs/list", "console.read", None),
    ("GET", "/console/clients/list", "console.read", None),
    ("GET", "/console/clients/trial-expiring", "console.read", None),
    ("GET", "/console/clients/retention-queue", "console.read", None),
    ("GET", "/console/settings", "console.read", None),
    ("GET", "/console/logs", "console.read", None),
    ("GET", "/console/briefs", "console.read", None),
    # --- Retention controls ---
    ("POST", "/console/retention-jobs/1/force-run", "retention.force_run", {}),
    ("POST", "/console/retention-jobs/1/cancel", "retention.cancel", {}),
    ("POST", "/console/retention-jobs/1/retry", "retention.retry", {}),
    # --- Config write ---
    ("PUT", "/console/settings/filters", "config.write", {}),
    # --- Command dispatch ---
    ("POST", "/console/commands/run-pipeline", "command.dispatch", {}),
    # --- Demo replay ---
    ("POST", "/console/demo/start", "demo.run", {"domain": "example.com"}),
]

# Public routes (spec §4.2.6 + §4.2.1 public table). No decorator.
# An observer-role authenticated session must reach these without
# 403 + permission_denied audit row. The list mirrors the public-
# route table in spec §4.2.1 (login / logout / whoami / signup /
# health / results); /static/* is omitted because the SPA shell is
# served by a different mechanism (slice 3g.5 bypass).
PUBLIC_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/console/auth/whoami", None),
    # /console/auth/login takes a body but is exercised here only to
    # confirm absence of decorator gating; a malformed login still
    # 4xxs but never 403s with permission_denied.
    ("POST", "/console/auth/login", {"username": "x", "password": "y"}),
    ("POST", "/console/auth/logout", {}),
    ("POST", "/signup/validate", {"token": "x"}),
    ("GET", "/health", None),
    ("GET", "/results/0", None),
]


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(autouse=True)
def _isolate_console_seed_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets_dir = tmp_path / "run-secrets"
    secrets_dir.mkdir()
    monkeypatch.setattr(core_secrets, "_SECRETS_DIR", secrets_dir)
    monkeypatch.delenv("CONSOLE_USER", raising=False)
    monkeypatch.delenv("CONSOLE_PASSWORD", raising=False)


def _build_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    monkeypatch.chdir(tmp_path)

    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    for name in ("filters", "interpreter", "delivery"):
        (config_dir / f"{name}.json").write_text("{}", encoding="utf-8")

    db_file = tmp_path / "clients.db"
    init_db(str(db_file)).close()

    console_db_path = tmp_path / "console.db"
    monkeypatch.setenv("CONSOLE_DB_PATH", str(console_db_path))
    monkeypatch.setenv("HEIMDALL_COOKIE_SECURE", "0")

    app = create_app(
        redis_url="redis://fake:6379/0",
        results_dir=str(tmp_path / "results"),
        briefs_dir=str(tmp_path / "briefs"),
    )
    app.state.db_path = str(db_file)
    return app, console_db_path


def _set_operator_role(console_db_path: Path, role_hint: str) -> None:
    conn = get_console_conn(console_db_path)
    try:
        conn.execute("UPDATE operators SET role_hint = ?", (role_hint,))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def owner_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient logged in as the seeded ``'owner'`` operator (allow path)."""
    app, console_db_path = _build_app(tmp_path, monkeypatch)
    with TestClient(app) as tc:
        seed_console_operator(console_db_path)
        login_console_client(tc)
        yield tc, console_db_path


@pytest.fixture
def observer_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient logged in as an operator whose ``role_hint='observer'``
    — not in :data:`ROLE_PERMISSIONS` so every gated route 403s."""
    app, console_db_path = _build_app(tmp_path, monkeypatch)
    with TestClient(app) as tc:
        seed_console_operator(console_db_path)
        login_console_client(tc)
        # Re-seed the role AFTER login so the session cookie is valid
        # but role_hint is now outside ROLE_PERMISSIONS. SessionAuth
        # re-fetches role_hint per request via _fetch_role_hint, so
        # the deny path triggers immediately on the next call.
        _set_operator_role(console_db_path, "observer")
        yield tc, console_db_path


def _drive(
    tc: TestClient, method: str, path: str, body: Any
) -> Any:
    """Single-call dispatcher for the 4 HTTP verbs used in the inventory."""
    if method == "GET":
        return tc.get(path)
    if method == "POST":
        return tc.post(path, json=body or {})
    if method == "PUT":
        return tc.put(path, json=body or {})
    raise AssertionError(f"unsupported method: {method}")


def _select_deny_rows(
    console_db_path: Path, target_id: str | None = None
) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(console_db_path))
    conn.row_factory = sqlite3.Row
    try:
        if target_id is None:
            return conn.execute(
                "SELECT action, target_type, target_id, payload_json "
                "FROM audit_log WHERE action = 'auth.permission_denied'"
            ).fetchall()
        return conn.execute(
            "SELECT action, target_type, target_id, payload_json "
            "FROM audit_log "
            "WHERE action = 'auth.permission_denied' AND target_id = ?",
            (target_id,),
        ).fetchall()
    finally:
        conn.close()


# ===========================================================================
# Allow path — owner role can reach every gated route (decorator passes).
# ===========================================================================


@pytest.mark.parametrize(
    "method,path,permission,body",
    GATED_ROUTES,
    ids=[f"{m}_{p}" for m, p, _, _ in GATED_ROUTES],
)
def test_owner_role_allowed_on_every_gated_route(
    owner_client: Any,
    method: str,
    path: str,
    permission: str,
    body: Any,
) -> None:
    tc, console_db_path = owner_client
    resp = _drive(tc, method, path, body)
    # Anything but 403 means the decorator allowed through. The route
    # may legitimately 404 / 400 / 503 due to missing test data —
    # the contract under test is *not denied*.
    assert resp.status_code != 403, (
        f"{method} {path} unexpectedly 403'd for 'owner' role: "
        f"body={resp.text}"
    )
    assert resp.status_code != 401, (
        f"{method} {path} returned 401 — auth fixture broken"
    )
    # Allow path must NOT write a permission_denied audit row.
    assert _select_deny_rows(console_db_path, permission) == []


# ===========================================================================
# Deny path — observer role 403s on every gated route + audit row.
# ===========================================================================


@pytest.mark.parametrize(
    "method,path,permission,body",
    GATED_ROUTES,
    ids=[f"{m}_{p}" for m, p, _, _ in GATED_ROUTES],
)
def test_observer_role_denied_on_every_gated_route(
    observer_client: Any,
    method: str,
    path: str,
    permission: str,
    body: Any,
) -> None:
    tc, console_db_path = observer_client
    resp = _drive(tc, method, path, body)
    assert resp.status_code == 403
    assert resp.json() == {
        "detail": {
            "error": "permission_denied",
            "permission": permission,
        }
    }

    rows = _select_deny_rows(console_db_path, permission)
    assert len(rows) == 1, (
        f"{method} {path} expected 1 deny row for {permission}; "
        f"got {len(rows)}"
    )
    row = rows[0]
    assert row["target_type"] == "permission"
    assert row["target_id"] == permission
    assert json.loads(row["payload_json"]) == {"role_hint": "observer"}


# ===========================================================================
# Public routes — observer role still reaches them (no decorator).
# ===========================================================================


@pytest.mark.parametrize(
    "method,path,body",
    PUBLIC_ROUTES,
    ids=[f"{m}_{p}" for m, p, _ in PUBLIC_ROUTES],
)
def test_public_routes_not_gated_by_decorator(
    observer_client: Any,
    method: str,
    path: str,
    body: Any,
) -> None:
    """Spec §9 #6: public surfaces (auth/whoami, /health, /signup/*,
    /static/*, /results/*) carry no ``@require_permission`` decorator.
    An observer-role session may still get 4xx from independent gates
    (origin allowlist on ``/signup/validate``, missing-resource 404 on
    ``/results/0``, malformed-body on ``/console/auth/login``); the
    contract under test is *the require_permission decorator does not
    fire on these paths*, observable as absence of any
    ``auth.permission_denied`` row in console.audit_log.
    """
    tc, console_db_path = observer_client
    _drive(tc, method, path, body)
    # No permission_denied audit row should have been written
    # by hitting any public route, regardless of the actual status.
    assert _select_deny_rows(console_db_path) == []


# ===========================================================================
# Unauthenticated baseline — 401 precedes 403 (decorator's defense-in-depth).
# ===========================================================================


def test_unauth_post_returns_401_not_403(tmp_path: Path, monkeypatch) -> None:
    """Spec §6.4: authenticated 401 path. With no session cookie, the
    SessionAuthMiddleware rejects with 401 BEFORE the decorator
    fires; the decorator's own 401 branch is defense-in-depth and
    not exercised on this path."""
    app, console_db_path = _build_app(tmp_path, monkeypatch)
    with TestClient(app) as tc:
        seed_console_operator(console_db_path)
        # Skip login — no session cookie.
        resp = tc.post("/console/commands/run-pipeline", json={})
    assert resp.status_code == 401
    # No permission_denied row — that's a 403-tier event.
    assert _select_deny_rows(console_db_path) == []


# ===========================================================================
# Permission count assertion (spec §4.2.5 + §12)
# ===========================================================================


def test_seven_distinct_permissions_in_inventory() -> None:
    """Spec §4.2.1 fork (c) = 7 permissions. The 18-route inventory
    must use exactly the same 7 values (CONSOLE_READ + 3 retention
    + CONFIG_WRITE + COMMAND_DISPATCH + DEMO_RUN HTTP)."""
    used = {p for _, _, p, _ in GATED_ROUTES}
    assert used == {
        "console.read",
        "retention.force_run",
        "retention.cancel",
        "retention.retry",
        "config.write",
        "command.dispatch",
        "demo.run",
    }
    assert len(GATED_ROUTES) == 18
