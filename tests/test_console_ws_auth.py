"""Handler-level WebSocket auth on /console/ws + /console/demo/ws/{scan_id}.

Stage A slice 3g (d) + (e) per ``docs/architecture/stage-a-slice-3g-spec.md``
§4 + §5. Master spec §5.3 + §5.5 + §5.7 + §5.8 + §8.2.

The handler is the gate (master §5.2 Option 2): the HTTP middleware
explicitly does NOT touch ``scope['type'] == 'websocket'`` (§5.6), so
each WS endpoint reads ``ws.cookies['heimdall_session']``, hashes via
SHA-256, validates against ``console.db``, and either accepts the
upgrade + writes a ``liveops.ws_connected`` audit row, or
``accept()`` + ``close(code=4401)`` BEFORE any pubsub setup. Disabled
operators are paired with an ``auth.session_rejected_disabled`` row
per §7.9 Option A so the WS path mirrors the HTTP middleware's
forensic trail.

Eight cases per master §8.2 — seven failure paths (parameterised
across both WS endpoints) plus a handler-reach assertion that locks
in the middleware-bypasses-WS-scope contract. The fixtures mount the
real ``SessionAuthMiddleware`` via ``create_app`` so the integration
shape matches production wiring.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import fakeredis
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.app import create_app
from src.db.console_connection import get_console_conn
from tests._console_auth_helpers import (
    CONSOLE_TEST_USERNAME,
    login_console_client,
    seed_console_operator,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _operator_id(console_db_path: Path) -> int:
    """Resolve the seeded operator's id by username."""
    conn = get_console_conn(str(console_db_path))
    try:
        row = conn.execute(
            "SELECT id FROM operators WHERE username = ?",
            (CONSOLE_TEST_USERNAME,),
        ).fetchone()
        assert row is not None, "console-test operator not seeded"
        return row["id"]
    finally:
        conn.close()


def _session_id_for_operator(console_db_path: Path, operator_id: int) -> int:
    """Resolve the most-recent session for ``operator_id``."""
    conn = get_console_conn(str(console_db_path))
    try:
        row = conn.execute(
            "SELECT id FROM sessions WHERE operator_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (operator_id,),
        ).fetchone()
        assert row is not None, "no session row found for operator"
        return row["id"]
    finally:
        conn.close()


def _audit_rows(
    console_db_path: Path, *, action: str | None = None
) -> list[dict]:
    """Read audit_log rows, optionally filtered by ``action``."""
    conn = get_console_conn(str(console_db_path))
    try:
        if action is None:
            cur = conn.execute(
                "SELECT id, occurred_at, operator_id, session_id, action, "
                "       target_type, target_id, payload_json "
                "FROM audit_log ORDER BY id ASC"
            )
        else:
            cur = conn.execute(
                "SELECT id, occurred_at, operator_id, session_id, action, "
                "       target_type, target_id, payload_json "
                "FROM audit_log WHERE action = ? ORDER BY id ASC",
                (action,),
            )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _expire_session_idle(console_db_path: Path, operator_id: int) -> None:
    """Drag the session's ``expires_at`` into the past."""
    conn = get_console_conn(str(console_db_path))
    try:
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE operator_id = ?",
            (_iso(datetime.now(UTC) - timedelta(minutes=1)), operator_id),
        )
        conn.commit()
    finally:
        conn.close()


def _expire_session_absolute(console_db_path: Path, operator_id: int) -> None:
    """Drag the session's ``absolute_expires_at`` into the past."""
    conn = get_console_conn(str(console_db_path))
    try:
        conn.execute(
            "UPDATE sessions SET absolute_expires_at = ? WHERE operator_id = ?",
            (_iso(datetime.now(UTC) - timedelta(minutes=1)), operator_id),
        )
        conn.commit()
    finally:
        conn.close()


def _revoke_session(console_db_path: Path, operator_id: int) -> None:
    conn = get_console_conn(str(console_db_path))
    try:
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE operator_id = ?",
            (_iso(datetime.now(UTC)), operator_id),
        )
        conn.commit()
    finally:
        conn.close()


def _disable_operator(console_db_path: Path, operator_id: int) -> None:
    conn = get_console_conn(str(console_db_path))
    try:
        conn.execute(
            "UPDATE operators SET disabled_at = ? WHERE id = ?",
            (_iso(datetime.now(UTC)), operator_id),
        )
        conn.commit()
    finally:
        conn.close()


def _session_last_seen(console_db_path: Path, operator_id: int) -> str | None:
    """Read ``sessions.last_seen_at`` for the operator's active session.

    Used by rejection-path tests to assert ``_authenticate_ws`` only
    runs ``validate_session_by_hash`` (read-only SELECT) and never
    ``refresh_session`` (UPDATE) — the WS auth gate must not slide
    the session window for a request that never authenticates."""
    conn = get_console_conn(str(console_db_path))
    try:
        row = conn.execute(
            "SELECT last_seen_at FROM sessions "
            "WHERE operator_id = ? ORDER BY id DESC LIMIT 1",
            (operator_id,),
        ).fetchone()
        return None if row is None else row["last_seen_at"]
    finally:
        conn.close()


def _pubsub_subscriber_counts(client: TestClient) -> dict[str, int]:
    """Snapshot per-channel subscriber counts on the WS-handler channels.

    Master spec §5.3 — the WS auth gate runs BEFORE any pubsub setup
    on a rejected upgrade. The handler subscribes to four channels on
    success (``console:pipeline-progress``, ``console:activity``,
    ``console:command-results``, ``console:logs``); a regression that
    subscribed any of them BEFORE the auth check would still pass the
    close-code assertion, so this helper locks the contract by
    counting subscribers per channel.

    Note: ``console:logs`` is ALSO subscribed by the app's lifespan
    background task in ``_listen_console_logs``, so the absolute count
    on that channel is non-zero from app startup. Tests use this
    helper to snapshot pre/post and assert no DELTA — handler
    subscriptions show up as +1 on whichever channels the handler
    touched."""
    redis_conn = getattr(client.app.state, "redis", None)
    handler_channels = (
        "console:pipeline-progress",
        "console:activity",
        "console:command-results",
        "console:logs",
    )
    if redis_conn is None:
        return {ch: 0 for ch in handler_channels}
    counts = redis_conn.pubsub_numsub(*handler_channels)
    # ``pubsub_numsub`` returns a list of (channel, count) pairs;
    # decode_responses=True keeps both as plain strings/ints.
    return {
        (ch.decode() if isinstance(ch, bytes) else ch): int(n)
        for ch, n in counts
    }


def _assert_no_ws_side_effects(
    client: TestClient,
    console_db_path: Path,
    *,
    operator_id: int | None,
    pre_last_seen: str | None,
    pre_subs: dict[str, int],
) -> None:
    """Lock the two rejection-path invariants per master spec §5.3.

    1. Pubsub subscriber counts on the four WS-handler channels must
       not have advanced since *pre_subs* — auth runs before any
       ``redis_conn.pubsub().subscribe(...)`` call site in the handler.
       Compare deltas (not absolute values) because the app's lifespan
       background tasks already subscribe to ``console:logs``.
    2. ``sessions.last_seen_at`` must not have advanced for the
       operator's session row (skipped when no session exists, e.g.
       the no-cookie / unknown-cookie cases)."""
    post_subs = _pubsub_subscriber_counts(client)
    assert post_subs == pre_subs, (
        f"WS-handler pubsub subscriptions advanced on rejection: "
        f"{pre_subs} → {post_subs}. Master spec §5.3 — auth gate runs "
        "BEFORE any pubsub setup."
    )
    if operator_id is not None:
        post_last_seen = _session_last_seen(console_db_path, operator_id)
        assert post_last_seen == pre_last_seen, (
            f"sessions.last_seen_at advanced on a rejected WS auth "
            f"({pre_last_seen!r} → {post_last_seen!r}). The handler "
            "must call validate_session_by_hash only, never "
            "refresh_session, on the rejection path."
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def configured_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Per-test ``console.db`` path + plain-HTTP cookie jar settings."""
    db = tmp_path / "console.db"
    monkeypatch.setenv("CONSOLE_DB_PATH", str(db))
    monkeypatch.setenv("HEIMDALL_COOKIE_SECURE", "0")
    monkeypatch.delenv("HEIMDALL_LEGACY_BASIC_AUTH", raising=False)
    return db


def _build_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    """Logged-in TestClient — cookie jar primed with session + CSRF."""
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
# Parameterised matrix of failure cases — both /console/ws + demo WS
# ---------------------------------------------------------------------------


WS_PATHS = [
    pytest.param("/console/ws", id="console-ws"),
    pytest.param("/console/demo/ws/test-scan-id", id="demo-ws"),
]


def _expect_4401_close(client: TestClient, path: str) -> None:
    """Connect to *path* and assert the server closes with code 4401.

    Per spec §5.3 the handler accepts the upgrade then sends a
    ``websocket.close(code=4401)`` frame. The Starlette TestClient
    surfaces this as ``WebSocketDisconnect`` on the next typed receive
    call (``receive_text`` / ``receive_json`` / ``receive_bytes``);
    the untyped ``ws.receive()`` would return the close message as a
    dict without raising, which would mask a regression.
    """
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(path) as ws:
            ws.receive_text()
    assert exc_info.value.code == 4401, (
        f"expected 4401 close on {path}, got {exc_info.value.code}"
    )


# ---------------------------------------------------------------------------
# Failure cases (1-of-2: no cookie, unknown cookie, revoked, idle-expired,
# absolute-expired, disabled-operator) — parameterised across both endpoints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ws_path", WS_PATHS)
def test_ws_no_cookie_closes_4401(
    unauthed_client: TestClient, configured_env: Path, ws_path: str
) -> None:
    """No cookie → handler closes with 4401, no audit row written, no
    pubsub subscription created (master §5.3)."""
    pre_subs = _pubsub_subscriber_counts(unauthed_client)

    _expect_4401_close(unauthed_client, ws_path)

    rows = _audit_rows(configured_env)
    # No login happened (auth.login_*) and no successful WS accept
    # happened (liveops.ws_connected); the audit log must be empty.
    assert rows == []
    _assert_no_ws_side_effects(
        unauthed_client,
        configured_env,
        operator_id=None,
        pre_last_seen=None,
        pre_subs=pre_subs,
    )


@pytest.mark.parametrize("ws_path", WS_PATHS)
def test_ws_unknown_cookie_closes_4401(
    unauthed_client: TestClient, configured_env: Path, ws_path: str
) -> None:
    """Cookie that does not hash to any row → 4401, no ws_connected
    row, no pubsub subscription created."""
    unauthed_client.cookies.set("heimdall_session", "definitely-not-a-real-token")
    pre_subs = _pubsub_subscriber_counts(unauthed_client)

    _expect_4401_close(unauthed_client, ws_path)

    rows = _audit_rows(configured_env, action="liveops.ws_connected")
    assert rows == []
    _assert_no_ws_side_effects(
        unauthed_client,
        configured_env,
        operator_id=None,
        pre_last_seen=None,
        pre_subs=pre_subs,
    )


@pytest.mark.parametrize("ws_path", WS_PATHS)
def test_ws_revoked_session_closes_4401(
    authed_client: TestClient, configured_env: Path, ws_path: str
) -> None:
    """Revoked session → 4401, no ws_connected audit row, no pubsub
    subscription, ``sessions.last_seen_at`` unchanged."""
    operator_id = _operator_id(configured_env)
    _revoke_session(configured_env, operator_id)
    pre_last_seen = _session_last_seen(configured_env, operator_id)
    pre_subs = _pubsub_subscriber_counts(authed_client)

    _expect_4401_close(authed_client, ws_path)

    rows = _audit_rows(configured_env, action="liveops.ws_connected")
    assert rows == []
    _assert_no_ws_side_effects(
        authed_client,
        configured_env,
        operator_id=operator_id,
        pre_last_seen=pre_last_seen,
        pre_subs=pre_subs,
    )


@pytest.mark.parametrize("ws_path", WS_PATHS)
def test_ws_idle_expired_closes_4401(
    authed_client: TestClient, configured_env: Path, ws_path: str
) -> None:
    """Session whose ``expires_at`` is in the past → 4401, no pubsub
    subscription, ``last_seen_at`` unchanged."""
    operator_id = _operator_id(configured_env)
    _expire_session_idle(configured_env, operator_id)
    pre_last_seen = _session_last_seen(configured_env, operator_id)
    pre_subs = _pubsub_subscriber_counts(authed_client)

    _expect_4401_close(authed_client, ws_path)

    rows = _audit_rows(configured_env, action="liveops.ws_connected")
    assert rows == []
    _assert_no_ws_side_effects(
        authed_client,
        configured_env,
        operator_id=operator_id,
        pre_last_seen=pre_last_seen,
        pre_subs=pre_subs,
    )


@pytest.mark.parametrize("ws_path", WS_PATHS)
def test_ws_absolute_expired_closes_4401(
    authed_client: TestClient, configured_env: Path, ws_path: str
) -> None:
    """Session whose ``absolute_expires_at`` is in the past → 4401, no
    pubsub subscription, ``last_seen_at`` unchanged."""
    operator_id = _operator_id(configured_env)
    _expire_session_absolute(configured_env, operator_id)
    pre_last_seen = _session_last_seen(configured_env, operator_id)
    pre_subs = _pubsub_subscriber_counts(authed_client)

    _expect_4401_close(authed_client, ws_path)

    rows = _audit_rows(configured_env, action="liveops.ws_connected")
    assert rows == []
    _assert_no_ws_side_effects(
        authed_client,
        configured_env,
        operator_id=operator_id,
        pre_last_seen=pre_last_seen,
        pre_subs=pre_subs,
    )


@pytest.mark.parametrize("ws_path", WS_PATHS)
def test_ws_disabled_operator_closes_4401(
    authed_client: TestClient, configured_env: Path, ws_path: str
) -> None:
    """Operator disabled mid-session → 4401 + ``auth.session_rejected_disabled``
    audit row (§7.9 Option A — symmetry with the HTTP middleware), no
    pubsub subscription, ``last_seen_at`` unchanged."""
    operator_id = _operator_id(configured_env)
    session_id = _session_id_for_operator(configured_env, operator_id)
    _disable_operator(configured_env, operator_id)
    pre_last_seen = _session_last_seen(configured_env, operator_id)
    pre_subs = _pubsub_subscriber_counts(authed_client)

    _expect_4401_close(authed_client, ws_path)

    connect_rows = _audit_rows(configured_env, action="liveops.ws_connected")
    assert connect_rows == []

    rejected = _audit_rows(
        configured_env, action="auth.session_rejected_disabled"
    )
    assert len(rejected) == 1, rejected
    row = rejected[0]
    assert row["operator_id"] == operator_id
    assert row["session_id"] == session_id
    assert row["target_type"] == "session"
    assert row["target_id"] == str(session_id)
    _assert_no_ws_side_effects(
        authed_client,
        configured_env,
        operator_id=operator_id,
        pre_last_seen=pre_last_seen,
        pre_subs=pre_subs,
    )


# ---------------------------------------------------------------------------
# Happy path — separate per endpoint because the post-accept behavior
# differs (ping/pong on /console/ws vs replay-stream on /console/demo/ws).
# ---------------------------------------------------------------------------


def test_ws_valid_cookie_accepts_console_ws(
    authed_client: TestClient, configured_env: Path
) -> None:
    """Valid session cookie → handler accepts, ping/pong works,
    ``liveops.ws_connected`` audit row written paired with the active session."""
    operator_id = _operator_id(configured_env)
    session_id = _session_id_for_operator(configured_env, operator_id)

    with authed_client.websocket_connect("/console/ws") as ws:
        ws.send_json({"type": "ping"})
        # Server may also push queue_status / log_batch frames; drain
        # until pong arrives.
        for _ in range(10):
            resp = ws.receive_json()
            if resp.get("type") == "pong":
                break
        else:
            raise AssertionError("Did not receive pong after 10 frames")

    rows = _audit_rows(configured_env, action="liveops.ws_connected")
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["operator_id"] == operator_id
    assert row["session_id"] == session_id
    assert row["target_type"] == "websocket"
    assert row["target_id"] is None
    assert row["payload_json"] is not None
    assert "/console/ws" in row["payload_json"]


def test_ws_valid_cookie_accepts_demo_ws(
    authed_client: TestClient, configured_env: Path
) -> None:
    """Valid cookie → demo handler runs the auth prelude, writes the
    ``liveops.ws_connected`` row, then closes the unknown scan_id with
    1008 (existing post-auth check). The audit row proves auth ran."""
    operator_id = _operator_id(configured_env)
    session_id = _session_id_for_operator(configured_env, operator_id)

    # No prior demo_start, so the scan_id is unknown — the handler
    # closes with 1008 after the auth + audit prelude. ``receive_text``
    # raises ``WebSocketDisconnect`` on close (the untyped ``receive``
    # would return the close message as a dict and mask regressions).
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with authed_client.websocket_connect(
            "/console/demo/ws/no-such-scan"
        ) as ws:
            ws.receive_text()
    # 1008 (Policy Violation) is the existing "Unknown scan_id" close;
    # 4401 would mean auth failed, which is the failure mode we are
    # trying to rule out here.
    assert exc_info.value.code == 1008, (
        f"expected 1008 unknown-scan close, got {exc_info.value.code}"
    )

    rows = _audit_rows(configured_env, action="liveops.ws_connected")
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["operator_id"] == operator_id
    assert row["session_id"] == session_id
    assert row["target_type"] == "websocket"
    assert row["target_id"] is None
    assert row["payload_json"] is not None
    assert "/console/demo/ws" in row["payload_json"]
    assert "no-such-scan" in row["payload_json"]


# ---------------------------------------------------------------------------
# Lock-in: HTTP middleware does NOT auth the WS upgrade
# ---------------------------------------------------------------------------


def test_ws_middleware_does_not_auth_upgrade(
    unauthed_client: TestClient,
    configured_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec §5.2 Option 2 + §5.6 — the HTTP middleware bypasses WS scope,
    so an unauthenticated WS upgrade reaches the handler (which is what
    closes the connection with 4401). Wrap the WS auth helper so we
    can prove it actually ran. If a future Starlette version started
    routing WS scope through HTTP middleware, the middleware would
    short-circuit with HTTP 401 and the wrapped helper would never be
    called — this test guards against that regression."""
    from src.api import console as console_module

    calls: list[dict] = []
    real_authenticate = console_module._authenticate_ws

    async def recording_authenticate_ws(websocket, **kwargs):
        calls.append({"path": websocket.scope.get("path", "")})
        return await real_authenticate(websocket, **kwargs)

    monkeypatch.setattr(
        console_module, "_authenticate_ws", recording_authenticate_ws
    )

    # No cookie present — middleware would reject any /console/* HTTP
    # request with 401 before the handler runs. The WS path must still
    # reach the handler, so the recorder captures the call.
    _expect_4401_close(unauthed_client, "/console/ws")

    assert len(calls) == 1, (
        "Handler-level _authenticate_ws was not invoked — middleware "
        "appears to have intercepted the WS upgrade. Slice 3g design "
        "lock violated; see master spec §5.2 Option 2."
    )
    assert calls[0]["path"] == "/console/ws"
