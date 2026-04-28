"""Tests for src.api.routers.auth — Stage A login / logout / whoami.

Stage A spec §3.1 / §3.4 / §3.5 / §6.3 / §7.3 + §8.2
(test_auth_login_logout.py block).

Endpoints under test:

- ``POST /console/auth/login`` — three-phase: rate-limit pre-check →
  credential lookup + Argon2id verify → session issue + audit + Set-
  Cookie. The rate-limit gate is the FIRST step; the credential SELECT
  + Argon2 verify NEVER run when the IP is throttled.
- ``POST /console/auth/logout`` — session-required, CSRF-checked,
  revokes the row, writes ``auth.logout`` audit, clears both cookies.
- ``GET /console/auth/whoami`` — bypasses the middleware, runs its
  own four-state machine: 204 (empty bootstrap) / 409 (all disabled)
  / 200 (authed) / 401 (unauthed).

**Response-body harmonisation (Federico, 2026-04-28).** Login and
whoami both return the shape ``{operator: {...}, session: {expires_at,
absolute_expires_at}, csrf_token}``. The spec drafted login flat with
``expires_at`` at the top level; whoami nested under ``session``. We
harmonised on the nested form because ``session`` scopes growth (any
future session metadata lands under that key without polluting the
top level), and the SPA can read login + whoami responses
interchangeably.

Most tests use a tiny FastAPI app with the auth router mounted plus
the new SessionAuthMiddleware (slice 3d) — fast, focused, isolated.
One integration test exercises the real ``create_app()`` factory to
catch wiring assumptions before slice 3f does the legacy-Basic-Auth
rename + middleware swap (per Federico's caution: don't let unit
tests overfit to a toy app in a way that hides integration
assumptions from 3f).
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.core.secrets as core_secrets
from src.api.auth.hashing import hash_password
from src.api.auth.middleware import SessionAuthMiddleware
from src.api.auth.sessions import issue_session
from src.api.routers.auth import router as auth_router
from src.db.console_connection import (
    DEFAULT_CONSOLE_DB_PATH,
    get_console_conn,
    init_db_console,
)


# ---------------------------------------------------------------------------
# Env-isolation fixture — same shape as test_auth_sessions.py
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_console_seed_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets_dir = tmp_path / "run-secrets"
    secrets_dir.mkdir()
    monkeypatch.setattr(core_secrets, "_SECRETS_DIR", secrets_dir)
    monkeypatch.delenv("CONSOLE_USER", raising=False)
    monkeypatch.delenv("CONSOLE_PASSWORD", raising=False)


# ---------------------------------------------------------------------------
# DB / app fixtures
# ---------------------------------------------------------------------------


_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def console_db_path(tmp_path: Path) -> str:
    """Initialised console.db with one active operator (alice / owner /
    `_PASSWORD`).

    The hash is computed via the real Argon2id wrapper so verify_password
    in the login handler exercises the full PHC verify path."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    conn = get_console_conn(db_path)
    conn.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', ?, 'owner', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')",
        (hash_password(_PASSWORD),),
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def fake_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


def _build_app(
    console_db_path: str, redis_client: Any | None
) -> FastAPI:
    """Tiny FastAPI app with the auth router + SessionAuthMiddleware.

    ``redis_client`` is stashed on ``app.state.redis`` so the login
    handler's rate-limit gate finds it. Pass ``None`` to exercise the
    no-redis branch (slice 3c's check_should_block fail-open)."""
    app = FastAPI()
    app.state.redis = redis_client
    app.state.console_db_path = console_db_path
    app.add_middleware(
        SessionAuthMiddleware, console_db_path=console_db_path
    )
    app.include_router(auth_router)
    return app


@pytest.fixture
def client(
    console_db_path: str, fake_redis: fakeredis.FakeRedis
) -> TestClient:
    return TestClient(_build_app(console_db_path, fake_redis))


@pytest.fixture
def authed_session(
    console_db_path: str,
) -> tuple[str, str, int]:
    """Pre-issue a session for alice. Returns (token, csrf_token,
    session_id) — used by logout/whoami tests that don't care about
    exercising the login endpoint's session-issuance path."""
    conn = get_console_conn(console_db_path)
    issued = issue_session(conn, operator_id=1, ip="127.0.0.1", ua="seed")
    conn.commit()
    conn.close()
    return issued.token, issued.csrf_token, issued.session_id


def _audit_rows(db_path: str, action_filter: str | None = None) -> list:
    conn = get_console_conn(db_path)
    if action_filter:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE action = ? "
            "ORDER BY id DESC",
            (action_filter,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC"
        ).fetchall()
    conn.close()
    return rows


# ===========================================================================
# LOGIN
# ===========================================================================


def test_login_returns_200_with_set_cookies_and_harmonised_body(
    client: TestClient,
) -> None:
    """Happy path: 200 + Set-Cookie × 2 + body in the harmonised
    ``{operator, session, csrf_token}`` shape."""
    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body.keys()) == {"operator", "session", "csrf_token"}
    assert body["operator"] == {
        "id": 1,
        "username": "alice",
        "display_name": "Alice",
        "role_hint": "owner",
    }
    assert set(body["session"].keys()) == {
        "expires_at",
        "absolute_expires_at",
    }
    assert body["session"]["expires_at"].endswith("Z")
    assert body["session"]["absolute_expires_at"].endswith("Z")
    assert isinstance(body["csrf_token"], str)
    assert len(body["csrf_token"]) == 43  # secrets.token_urlsafe(32)

    cookies = resp.headers.get_list("set-cookie")
    joined = " | ".join(cookies)
    assert "heimdall_session=" in joined
    assert "heimdall_csrf=" in joined
    assert "HttpOnly" in joined  # session cookie at minimum
    # SameSite=Strict is the contract per §4.1; case-insensitive match
    assert "samesite=strict" in joined.lower()


def test_login_persists_token_hash_not_plaintext(
    client: TestClient,
    console_db_path: str,
) -> None:
    """Security review (§4.2 + §8.2): the stored ``token_hash`` is
    ``sha256(cookie_value)``, NOT the cookie value itself."""
    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 200

    cookie_jar = {
        c.split("=", 1)[0].strip(): c.split("=", 1)[1].split(";", 1)[0]
        for c in resp.headers.get_list("set-cookie")
    }
    cookie_value = cookie_jar["heimdall_session"]

    conn = get_console_conn(console_db_path)
    row = conn.execute(
        "SELECT token_hash FROM sessions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row["token_hash"] == hashlib.sha256(
        cookie_value.encode()
    ).hexdigest()
    assert row["token_hash"] != cookie_value  # the cookie-vs-DB-key separation


def test_login_updates_last_login_at_and_ip(
    client: TestClient,
    console_db_path: str,
) -> None:
    """Spec §3.1 step 3 — ``UPDATE operators SET last_login_at, *_ip``
    inside the same transaction as the session insert."""
    conn = get_console_conn(console_db_path)
    before = conn.execute(
        "SELECT last_login_at FROM operators WHERE id = 1"
    ).fetchone()["last_login_at"]
    conn.close()
    assert before is None

    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 200

    conn = get_console_conn(console_db_path)
    row = conn.execute(
        "SELECT last_login_at, last_login_ip FROM operators WHERE id = 1"
    ).fetchone()
    conn.close()
    assert row["last_login_at"] is not None
    assert row["last_login_ip"] is not None


def test_login_writes_login_ok_audit_row(
    client: TestClient,
    console_db_path: str,
) -> None:
    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 200

    rows = _audit_rows(console_db_path, action_filter="auth.login_ok")
    assert len(rows) == 1
    row = rows[0]
    assert row["operator_id"] == 1
    assert row["session_id"] is not None
    assert row["target_type"] == "operator"
    assert row["target_id"] == "1"


def test_login_clears_rate_limit_counter_on_success(
    client: TestClient,
    fake_redis: fakeredis.FakeRedis,
) -> None:
    """A legitimate operator who recovers from a typo gets fresh quota."""
    fake_redis.set("auth:fail:testclient", "3", ex=900)
    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 200
    assert fake_redis.get("auth:fail:testclient") is None


def test_login_wrong_password_returns_401_and_increments_counter(
    client: TestClient,
    console_db_path: str,
    fake_redis: fakeredis.FakeRedis,
) -> None:
    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"error": "invalid_credentials"}
    assert int(fake_redis.get("auth:fail:testclient")) == 1

    rows = _audit_rows(console_db_path, action_filter="auth.login_failed")
    assert len(rows) == 1
    row = rows[0]
    assert row["operator_id"] is None
    assert row["session_id"] is None


def test_login_unknown_username_returns_401_and_increments_counter(
    client: TestClient,
    console_db_path: str,
    fake_redis: fakeredis.FakeRedis,
) -> None:
    """Unknown-username path must look identical to wrong-password (no
    user-enumeration oracle in body, status, OR rate-limit counter)."""
    resp = client.post(
        "/console/auth/login",
        json={"username": "nobody", "password": _PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json() == {"error": "invalid_credentials"}
    assert int(fake_redis.get("auth:fail:testclient")) == 1

    rows = _audit_rows(console_db_path, action_filter="auth.login_failed")
    assert len(rows) == 1
    assert rows[0]["operator_id"] is None
    # target_id records the attempted username so forensic correlation
    # remains possible even though the wire response is identical to
    # the wrong-password case.
    assert rows[0]["target_id"] == "nobody"


def test_login_disabled_operator_returns_401_and_increments_counter(
    client: TestClient,
    console_db_path: str,
    fake_redis: fakeredis.FakeRedis,
) -> None:
    conn = get_console_conn(console_db_path)
    conn.execute(
        "UPDATE operators SET disabled_at = ? WHERE id = 1",
        ("2026-04-28T10:00:00Z",),
    )
    conn.commit()
    conn.close()

    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json() == {"error": "invalid_credentials"}
    assert int(fake_redis.get("auth:fail:testclient")) == 1


def test_login_empty_operators_table_returns_401(
    tmp_path: Path,
    fake_redis: fakeredis.FakeRedis,
) -> None:
    """Spec §3.5: login when operators table is empty manifests as
    no-such-user — 401, not a special "bootstrap" status (whoami's
    204 covers the bootstrap UI signal)."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()  # no operator inserted

    test_client = TestClient(_build_app(str(db_path), fake_redis))
    resp = test_client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 401
    assert resp.json() == {"error": "invalid_credentials"}


def test_login_username_lookup_is_case_insensitive(
    client: TestClient,
) -> None:
    """The operators UNIQUE index is on ``LOWER(username)`` and the
    handler must normalise on read so ``Alice`` / ``ALICE`` / ``alice``
    all reach the same row."""
    resp = client.post(
        "/console/auth/login",
        json={"username": "ALICE", "password": _PASSWORD},
    )
    assert resp.status_code == 200


def test_login_rate_limit_blocks_after_5_fails(
    client: TestClient,
    fake_redis: fakeredis.FakeRedis,
) -> None:
    """After five 401s from the same IP, the sixth attempt returns 429
    + Retry-After header. The 6th attempt MUST NOT reach the operator
    SELECT — gate is the FIRST step (§3.1)."""
    for _ in range(5):
        resp = client.post(
            "/console/auth/login",
            json={"username": "alice", "password": "wrong"},
        )
        assert resp.status_code == 401

    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},  # CORRECT password
    )
    assert resp.status_code == 429
    assert resp.json() == {"error": "rate_limited"}
    retry = int(resp.headers["retry-after"])
    assert 1 <= retry <= 900


def test_login_rate_limit_redis_down_falls_open(
    console_db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis-unavailable must NOT translate to auth-down (§3.1.a) —
    log a WARNING and let the credential path proceed."""

    class BrokenRedis:
        def get(self, *_args: Any, **_kwargs: Any) -> str:
            raise ConnectionError("simulated outage")

        def incr(self, *_args: Any, **_kwargs: Any) -> int:
            raise ConnectionError("simulated outage")

        def expire(self, *_args: Any, **_kwargs: Any) -> bool:
            raise ConnectionError("simulated outage")

        def ttl(self, *_args: Any, **_kwargs: Any) -> int:
            raise ConnectionError("simulated outage")

        def delete(self, *_args: Any, **_kwargs: Any) -> int:
            raise ConnectionError("simulated outage")

    test_client = TestClient(_build_app(console_db_path, BrokenRedis()))
    resp = test_client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 200, resp.text


def test_login_503_on_db_error_does_not_increment_counter(
    client: TestClient,
    fake_redis: fakeredis.FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DB outage must surface as 503 and NOT compound the rate-limit
    counter (a DB error is not an attacker signal)."""
    import src.api.routers.auth as auth_module

    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise sqlite3.OperationalError("simulated outage")

    monkeypatch.setattr(auth_module, "get_console_conn", explode)

    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": _PASSWORD},
    )
    assert resp.status_code == 503
    assert resp.json() == {"error": "service_unavailable"}
    assert fake_redis.get("auth:fail:testclient") is None


def test_login_audit_insert_failure_returns_503_without_incrementing(
    client: TestClient,
    fake_redis: fakeredis.FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex P1 (slice 3e): if the ``auth.login_failed`` audit-row
    INSERT raises mid-flow, the handler returns 503 — the per-IP
    rate-limit counter MUST NOT advance. Spec §3.1.a: "503 is NOT a
    fail (DB error is not an attacker signal)".

    Reordering bug guard: ``record_failure`` runs AFTER the audit
    transaction commits. A pre-commit increment would let a transient
    DB outage masquerade as a credential-failure signal."""
    import src.api.routers.auth as auth_module

    def explode_on_audit(*_args: Any, **_kwargs: Any) -> None:
        raise sqlite3.OperationalError("simulated audit-insert outage")

    monkeypatch.setattr(
        auth_module, "write_console_audit_row", explode_on_audit
    )

    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert resp.status_code == 503
    assert resp.json() == {"error": "service_unavailable"}
    assert fake_redis.get("auth:fail:testclient") is None


class _ExitRaisingConn:
    """Connection wrapper whose ``with`` exit always raises on the
    success path, simulating a failed commit-on-exit. Used to lock
    Codex P3's commit-time failure shape."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real

    def __getattr__(self, name: str) -> Any:
        # ``commit`` on sqlite3.Connection is a C-extension slot and
        # cannot be monkey-patched on the instance — hence the wrapper
        # rather than a setattr-based stub.
        return getattr(self._real, name)

    def __enter__(self) -> Any:
        return self._real.__enter__()

    def __exit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> bool:
        # Body raised already → rollback and propagate that exception
        # (don't override with our simulated failure).
        if exc_type is not None:
            self._real.rollback()
            return False
        # Body completed → simulate commit failure on exit.
        self._real.rollback()
        raise sqlite3.OperationalError("simulated commit-on-exit outage")


def test_login_commit_failure_returns_503_without_incrementing(
    client: TestClient,
    fake_redis: fakeredis.FakeRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex P3 (slice 3e): the audit INSERT call can succeed but the
    commit-on-``with conn:``-exit can still fail. Both shapes must
    produce 503 with no counter increment.

    The production handler is correct for both paths (``record_failure``
    runs after the ``with conn:`` block in either case), but locking
    both shapes prevents a future refactor from quietly moving the
    counter call back inside the block where only one of the two
    failure points would protect it."""
    import src.api.routers.auth as auth_module

    real_factory = auth_module.get_console_conn

    def wrapping_factory(*args: Any, **kwargs: Any) -> Any:
        return _ExitRaisingConn(real_factory(*args, **kwargs))

    monkeypatch.setattr(
        auth_module, "get_console_conn", wrapping_factory
    )

    resp = client.post(
        "/console/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert resp.status_code == 503
    assert resp.json() == {"error": "service_unavailable"}
    assert fake_redis.get("auth:fail:testclient") is None


# ===========================================================================
# LOGOUT
# ===========================================================================


def test_logout_returns_204_clears_cookies_revokes_session_writes_audit(
    client: TestClient,
    console_db_path: str,
    authed_session: tuple[str, str, int],
) -> None:
    token, csrf, session_id = authed_session
    h = hashlib.sha256(token.encode()).hexdigest()

    resp = client.post(
        "/console/auth/logout",
        cookies={"heimdall_session": token},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 204

    joined = " | ".join(resp.headers.get_list("set-cookie"))
    assert "heimdall_session=" in joined
    assert "heimdall_csrf=" in joined
    assert "max-age=0" in joined.lower()

    conn = get_console_conn(console_db_path)
    row = conn.execute(
        "SELECT revoked_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()
    conn.close()
    assert row["revoked_at"] is not None

    rows = _audit_rows(console_db_path, action_filter="auth.logout")
    assert len(rows) == 1
    assert rows[0]["session_id"] == session_id
    assert rows[0]["operator_id"] == 1
    assert rows[0]["target_type"] == "session"
    assert rows[0]["target_id"] == str(session_id)


def test_logout_without_session_returns_401(client: TestClient) -> None:
    """Logout without a cookie hits the SessionAuthMiddleware and
    bounces with 401 before the handler runs."""
    resp = client.post("/console/auth/logout")
    assert resp.status_code == 401


def test_logout_twice_returns_401_on_second_call(
    client: TestClient,
    authed_session: tuple[str, str, int],
) -> None:
    token, csrf, _sid = authed_session

    first = client.post(
        "/console/auth/logout",
        cookies={"heimdall_session": token},
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 204

    second = client.post(
        "/console/auth/logout",
        cookies={"heimdall_session": token},
        headers={"X-CSRF-Token": csrf},
    )
    assert second.status_code == 401  # session is revoked → middleware 401s


def test_logout_without_csrf_header_returns_403(
    client: TestClient,
    authed_session: tuple[str, str, int],
) -> None:
    token, _csrf, _sid = authed_session
    resp = client.post(
        "/console/auth/logout",
        cookies={"heimdall_session": token},
    )
    assert resp.status_code == 403


# ===========================================================================
# WHOAMI — four-state machine (204 / 409 / 200 / 401)
# ===========================================================================


def test_whoami_returns_204_when_operators_table_empty(
    tmp_path: Path,
    fake_redis: fakeredis.FakeRedis,
) -> None:
    """State 1: zero operator rows total → 204 No Content with empty body."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()

    test_client = TestClient(_build_app(str(db_path), fake_redis))
    resp = test_client.get("/console/auth/whoami")
    assert resp.status_code == 204
    assert resp.content == b""
    # No Set-Cookie on bootstrap branches.
    assert "set-cookie" not in {k.lower() for k in resp.headers.keys()}

    rows = _audit_rows(str(db_path))
    assert rows == []


def test_whoami_returns_409_when_all_operators_disabled(
    tmp_path: Path,
    fake_redis: fakeredis.FakeRedis,
) -> None:
    """State 2: rows exist but every row has ``disabled_at IS NOT NULL``
    → 409 Conflict with all-disabled sentinel."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    conn = get_console_conn(db_path)
    conn.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at, disabled_at) "
        "VALUES (1, 'alice', 'Alice', '$argon2id$x', 'owner', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z', "
        "'2026-04-28T10:00:00Z')"
    )
    conn.commit()
    conn.close()

    test_client = TestClient(_build_app(str(db_path), fake_redis))
    resp = test_client.get("/console/auth/whoami")
    assert resp.status_code == 409
    assert resp.json() == {"error": "all_operators_disabled"}
    assert "set-cookie" not in {k.lower() for k in resp.headers.keys()}

    rows = _audit_rows(str(db_path))
    assert rows == []


def test_whoami_returns_200_with_valid_session_and_harmonised_body(
    client: TestClient,
    authed_session: tuple[str, str, int],
) -> None:
    """State 3: valid cookie + active operator → 200 with the harmonised
    ``{operator, session, csrf_token}`` body shape (matches login)."""
    token, csrf, _sid = authed_session
    resp = client.get(
        "/console/auth/whoami",
        cookies={"heimdall_session": token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"operator", "session", "csrf_token"}
    assert body["operator"] == {
        "id": 1,
        "username": "alice",
        "display_name": "Alice",
        "role_hint": "owner",
    }
    assert set(body["session"].keys()) == {
        "expires_at",
        "absolute_expires_at",
    }
    assert body["csrf_token"] == csrf


def test_whoami_returns_401_when_unauthenticated_with_active_operators(
    client: TestClient,
) -> None:
    """State 4: at least one active operator exists, request has no
    valid cookie → 401 ``not_authenticated``."""
    resp = client.get("/console/auth/whoami")
    assert resp.status_code == 401
    assert resp.json() == {"error": "not_authenticated"}


def test_whoami_with_invalid_cookie_returns_401(
    client: TestClient,
) -> None:
    """Whoami bypasses the middleware so the cookie-clearing helpers
    never fire — invalid cookie just returns 401 with no Set-Cookie."""
    resp = client.get(
        "/console/auth/whoami",
        cookies={"heimdall_session": "not-a-real-token"},
    )
    assert resp.status_code == 401
    assert "set-cookie" not in {k.lower() for k in resp.headers.keys()}


def test_whoami_falls_through_when_some_disabled_some_active(
    client: TestClient,
    console_db_path: str,
    authed_session: tuple[str, str, int],
) -> None:
    """A second operator with ``disabled_at`` set must NOT poison the
    "active operators exist" branch — alice is still active and her
    cookie should still 200."""
    conn = get_console_conn(console_db_path)
    conn.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at, disabled_at) "
        "VALUES (2, 'bob', 'Bob', '$argon2id$x', 'analyst', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z', "
        "'2026-04-28T10:00:00Z')"
    )
    conn.commit()
    conn.close()

    token, _csrf, _sid = authed_session
    resp = client.get(
        "/console/auth/whoami",
        cookies={"heimdall_session": token},
    )
    assert resp.status_code == 200


def test_whoami_does_not_refresh_session(
    client: TestClient,
    console_db_path: str,
    authed_session: tuple[str, str, int],
) -> None:
    """Whoami is a state probe, not an authenticated action — sliding
    the session window on a probe would silently extend lifetime even
    when the user isn't really using the console. The middleware-
    routed real endpoints DO refresh; whoami doesn't.

    Locked here so a future change can't quietly add a refresh side-
    effect that breaks the no-write contract (no audit row, no DB
    state mutation per §3.5)."""
    token, _csrf, _sid = authed_session
    h = hashlib.sha256(token.encode()).hexdigest()

    conn = get_console_conn(console_db_path)
    before = conn.execute(
        "SELECT last_seen_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["last_seen_at"]
    conn.close()
    assert before is None  # fresh from issue_session

    resp = client.get(
        "/console/auth/whoami",
        cookies={"heimdall_session": token},
    )
    assert resp.status_code == 200

    conn = get_console_conn(console_db_path)
    after = conn.execute(
        "SELECT last_seen_at FROM sessions WHERE token_hash = ?", (h,)
    ).fetchone()["last_seen_at"]
    conn.close()
    assert after is None, "whoami must not refresh — last_seen_at stayed NULL"


def test_whoami_does_not_write_audit_row(
    client: TestClient,
    console_db_path: str,
    authed_session: tuple[str, str, int],
) -> None:
    """Read-side audit is out of scope for Stage A (§7.3)."""
    token, _csrf, _sid = authed_session
    resp = client.get(
        "/console/auth/whoami",
        cookies={"heimdall_session": token},
    )
    assert resp.status_code == 200
    assert _audit_rows(console_db_path) == []


# ===========================================================================
# Integration test — real create_app() factory (per Federico's caution)
# ===========================================================================


def test_integration_full_login_whoami_logout_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walk the full auth lifecycle through the real ``create_app()``
    factory — login → whoami → logout → re-login. This catches wiring
    assumptions that a toy app would hide.

    Specifically validates:
    - Lifespan init order: ``init_db_console`` runs BEFORE any request
      lands on the auth router (otherwise the operators table SELECT
      would fail).
    - ``app.state.redis`` resolution: the rate-limit gate finds the
      Redis instance attached during lifespan startup, not the toy
      stash from ``app.state.redis = …`` in unit tests.
    - ``app.state.console_db_path`` propagation through the middleware
      and the auth router.
    - No path conflict between the new ``/console/auth/*`` endpoints
      and the existing ``console_router`` from ``src/api/console.py``.

    Slice 3f mounts ``SessionAuthMiddleware`` inside ``create_app`` —
    the test relies on that wiring rather than re-adding the middleware
    out-of-band, so the integration coverage matches the production
    factory exactly.
    """
    db_path = tmp_path / "console.db"
    monkeypatch.setenv("CONSOLE_DB_PATH", str(db_path))
    monkeypatch.delenv("CONSOLE_USER", raising=False)
    monkeypatch.delenv("CONSOLE_PASSWORD", raising=False)
    monkeypatch.delenv("HEIMDALL_LEGACY_BASIC_AUTH", raising=False)
    # TestClient is HTTP, not HTTPS — Secure cookies won't be echoed
    # back to the next request. Production deploys keep
    # HEIMDALL_COOKIE_SECURE=1; this override is local to the test so
    # the cookie jar can carry the session forward through
    # whoami/logout.
    monkeypatch.setenv("HEIMDALL_COOKIE_SECURE", "0")

    from src.api.app import create_app

    fake = fakeredis.FakeRedis(decode_responses=True)
    with patch("redis.Redis.from_url", return_value=fake):
        app = create_app(
            redis_url="redis://fake:6379",
            results_dir=str(tmp_path / "results"),
            messages_dir=str(tmp_path / "messages"),
            briefs_dir=str(tmp_path / "briefs"),
            clients_dir=str(tmp_path / "clients"),
        )

    with TestClient(app) as test_client:
        # Lifespan has run — init_db_console created the schema. Seed
        # the operator manually (CONSOLE_USER is unset, so the auto-
        # seed path took the silent no-op branch).
        conn = get_console_conn(str(db_path))
        conn.execute(
            "INSERT INTO operators "
            "(id, username, display_name, password_hash, role_hint, "
            " created_at, updated_at) "
            "VALUES (1, 'alice', 'Alice', ?, 'owner', "
            "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')",
            (hash_password(_PASSWORD),),
        )
        conn.commit()
        conn.close()

        # Login.
        login = test_client.post(
            "/console/auth/login",
            json={"username": "alice", "password": _PASSWORD},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert set(body.keys()) == {"operator", "session", "csrf_token"}
        csrf = body["csrf_token"]

        # Whoami — same client carries cookies via the test client jar.
        whoami = test_client.get("/console/auth/whoami")
        assert whoami.status_code == 200
        assert whoami.json()["operator"]["username"] == "alice"

        # Logout.
        logout = test_client.post(
            "/console/auth/logout",
            headers={"X-CSRF-Token": csrf},
        )
        assert logout.status_code == 204

        # Whoami after logout → 401.
        whoami_after = test_client.get("/console/auth/whoami")
        assert whoami_after.status_code == 401

        # Clear the now-cleared cookies from the jar before re-login —
        # TestClient persists Set-Cookie clears as deleted, but reset
        # explicitly so the re-login starts fresh.
        test_client.cookies.clear()

        # Re-login → 200, counter cleared after the previous success.
        relogin = test_client.post(
            "/console/auth/login",
            json={"username": "alice", "password": _PASSWORD},
        )
        assert relogin.status_code == 200

    # The default DB path env var must not leak into other tests.
    assert os.environ.get("CONSOLE_DB_PATH") == str(db_path)
    monkeypatch.delenv("CONSOLE_DB_PATH", raising=False)
    # Sanity: the test's DB is NOT the package default.
    assert str(db_path) != DEFAULT_CONSOLE_DB_PATH
