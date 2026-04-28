"""Authenticated TestClient helper for console tests.

``create_app`` mounts ``SessionAuthMiddleware`` unconditionally
(slice 3f baseline; slice 3g (f) retired the legacy Basic-Auth
fallback per spec §7.10 Option B), so any test that exercises
``/console/*`` endpoints needs a logged-in session cookie before its
requests will reach the handler. This module exposes two minimal
building blocks:

- :func:`seed_console_operator` writes one operator row into the
  caller-supplied ``console.db`` with a known password hash.
- :func:`login_console_client` POSTs ``/console/auth/login`` against
  an open ``TestClient``, persists the session cookie in the client's
  cookie jar, and sets ``X-CSRF-Token`` as a default header so
  state-changing test calls don't need to thread the token manually.

Use both from inside ``with TestClient(app) as tc:`` — the FastAPI
lifespan must have already run ``init_db_console`` on the temp DB
before the seed insert can find the ``operators`` table.

Tests should also monkeypatch ``CONSOLE_DB_PATH`` to a tmp_path-relative
location and set ``HEIMDALL_COOKIE_SECURE=0`` so ``TestClient``'s
plain-HTTP cookie jar can carry the session forward.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.api.auth.hashing import hash_password
from src.db.console_connection import get_console_conn

CONSOLE_TEST_USERNAME = "console-test"
CONSOLE_TEST_PASSWORD = "console-test-pw-not-secret"
CONSOLE_TEST_DISPLAY = "Console Test"


def seed_console_operator(console_db_path: str | Path) -> None:
    """Insert a single operator row with a known password into
    ``console_db_path``. Idempotent — a second call is a no-op."""
    conn = get_console_conn(str(console_db_path))
    try:
        existing = conn.execute(
            "SELECT 1 FROM operators WHERE username = ?",
            (CONSOLE_TEST_USERNAME,),
        ).fetchone()
        if existing is not None:
            return
        now = "2026-04-28T09:00:00Z"
        conn.execute(
            "INSERT INTO operators "
            "(username, display_name, password_hash, role_hint, "
            " created_at, updated_at) "
            "VALUES (?, ?, ?, 'owner', ?, ?)",
            (
                CONSOLE_TEST_USERNAME,
                CONSOLE_TEST_DISPLAY,
                hash_password(CONSOLE_TEST_PASSWORD),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def login_console_client(client: TestClient) -> str:
    """POST ``/console/auth/login`` on *client* and return the
    ``csrf_token``. The session + CSRF cookies land in the client's
    cookie jar automatically; the CSRF token is also installed as a
    default ``X-CSRF-Token`` header so subsequent state-changing
    requests don't need to thread it manually. Tests that want to
    assert CSRF rejection can override per-call via ``headers={...}``.
    """
    resp = client.post(
        "/console/auth/login",
        json={
            "username": CONSOLE_TEST_USERNAME,
            "password": CONSOLE_TEST_PASSWORD,
        },
    )
    assert resp.status_code == 200, resp.text
    csrf_token = resp.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = csrf_token
    return csrf_token
