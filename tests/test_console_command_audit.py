"""Tests for the §4.1.6 ``command.dispatch`` audit row written by
``console_command`` (Stage A.5 commit (2) wave B).

The api-side handler at ``src/api/console.py:console_command`` queues
the operator command via ``redis_conn.lpush`` then writes one
``console.audit_log`` row paired with the eventual scheduler/worker-
side ``command_audit`` row in ``clients.db`` (master spec §1.3.b
pair shape; A.5 spec §4.1.6).

Ordering rule (peer-review P1, 2026-05-02). The audit row is written
**only after** ``lpush`` returns successfully. If Redis raises, the
exception bubbles to FastAPI 500 and no audit row is written —
otherwise the audit log would claim a dispatch that never reached
the queue. The pair semantics depend on the row matching a future
``command_audit`` row by ``request_id``; an orphan dispatch row with
no follow-up is forensically misleading.

A.5 deliberately does NOT test the worker-side ``command_audit`` row
here — the scheduler is mocked out in this fixture (fakeredis), so
no worker ever drains the queue. Worker-side tests live in
``tests/test_scheduler_daemon.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

import src.core.secrets as core_secrets
from src.api.app import create_app
from src.db.connection import init_db
from tests._console_auth_helpers import (
    login_console_client,
    seed_console_operator,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal to drive POST /console/commands/{command} and query the
# resulting console.audit_log rows directly.
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


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Authenticated TestClient + fakeredis + temp console.db.

    Yields ``(tc, console_db_path, fake_redis)`` so tests can drive
    POST requests, query the audit log, and (where needed) patch the
    Redis client. Mirrors the ``client`` fixture in
    ``tests/test_request_id_middleware.py`` so the audit-row pattern
    is consistent across the A.5 test suite.
    """
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *a, **kw: fake)
    monkeypatch.chdir(tmp_path)

    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "filters.json").write_text("{}", encoding="utf-8")
    (config_dir / "interpreter.json").write_text("{}", encoding="utf-8")
    (config_dir / "delivery.json").write_text("{}", encoding="utf-8")

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

    with TestClient(app) as tc:
        seed_console_operator(console_db_path)
        login_console_client(tc)
        yield tc, console_db_path, fake


def _select_dispatch_rows(
    console_db_path: Path, command: str
) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(console_db_path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT action, target_type, target_id, request_id, "
            "       operator_id, session_id "
            "FROM audit_log "
            "WHERE action = 'command.dispatch' AND target_id = ?",
            (command,),
        ).fetchall()
    finally:
        conn.close()


# ===========================================================================
# Happy path — audit row written after successful lpush
# ===========================================================================


def test_command_dispatch_writes_audit_row(client: Any) -> None:
    tc, console_db_path, fake = client

    resp = tc.post("/console/commands/run-pipeline", json={})
    assert resp.status_code == 200

    rows = _select_dispatch_rows(console_db_path, "run-pipeline")
    assert len(rows) == 1
    row = rows[0]
    assert row["action"] == "command.dispatch"
    assert row["target_type"] == "command"
    assert row["target_id"] == "run-pipeline"
    assert row["operator_id"] is not None  # populated by SessionAuth
    assert row["session_id"] is not None

    # Order check: the lpush'd item is in the fakeredis queue. Both
    # writes succeeded, both side-effects observable.
    assert fake.llen("queue:operator-commands") == 1


def test_command_dispatch_audit_carries_request_id(client: Any) -> None:
    """X-Request-ID round-trips from the inbound header through
    RequestIdMiddleware (commit 3) onto the audit row, proving the
    cross-DB correlation contract holds for command dispatch."""
    tc, console_db_path, _ = client

    rid = "r-cmd-dispatch-1"
    resp = tc.post(
        "/console/commands/interpret",
        json={"campaign": "0426-restaurants"},
        headers={"X-Request-ID": rid},
    )
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == rid

    rows = _select_dispatch_rows(console_db_path, "interpret")
    assert len(rows) == 1
    assert rows[0]["request_id"] == rid


# ===========================================================================
# Failure path — Redis lpush raises, NO audit row written
# ===========================================================================


def test_command_dispatch_audit_skipped_on_redis_failure(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redis lpush raises → no audit row written. Documents the
    lpush-then-audit ordering rule (peer-review P1 #2, 2026-05-02):
    the audit log must never claim a dispatch that did not actually
    queue.

    TestClient by default re-raises unhandled handler exceptions
    (``raise_server_exceptions=True``) for debugging convenience; in
    production the same exception flows through Starlette's
    ServerErrorMiddleware and returns 500. The contract being tested
    here — *no audit row on lpush failure* — is independent of the
    response surface.
    """
    tc, console_db_path, fake = client

    def _broken_lpush(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("simulated redis outage")

    monkeypatch.setattr(fake, "lpush", _broken_lpush)

    with pytest.raises(RuntimeError, match="simulated redis outage"):
        tc.post("/console/commands/send", json={"campaign": "x"})

    rows = _select_dispatch_rows(console_db_path, "send")
    assert len(rows) == 0


# ===========================================================================
# Forensic-asymmetry doc test (peer-review P2)
# ===========================================================================


def test_command_dispatch_row_independent_of_worker_command_audit(
    client: Any,
) -> None:
    """The api-side ``command.dispatch`` row in console.audit_log does
    NOT depend on the worker-side ``command_audit`` row in clients.db.
    The two rows correlate by ``request_id`` but are written by
    different processes; this fixture has no scheduler/worker, so the
    worker-side row never appears — yet the api-side row must.

    Documents asymmetric forensic protection: the dispatch ordering
    rule (lpush-then-audit) protects against Redis-side failure but
    not against worker-side ``command_audit`` failure. Operators can
    detect orphans via ``request_id`` join across the two databases."""
    tc, console_db_path, _ = client

    rid = "r-orphan-doc-1"
    resp = tc.post(
        "/console/commands/run-pipeline",
        json={},
        headers={"X-Request-ID": rid},
    )
    assert resp.status_code == 200

    api_rows = _select_dispatch_rows(console_db_path, "run-pipeline")
    assert len(api_rows) == 1
    assert api_rows[0]["request_id"] == rid

    # No worker ran in this fixture; the clients.db command_audit
    # table receives no row. Confirms the api-side is independent of
    # worker-side completion.
    clients_db_path = tc.app.state.db_path
    conn = sqlite3.connect(clients_db_path)
    try:
        worker_rows = conn.execute(
            "SELECT id FROM command_audit WHERE request_id = ?",
            (rid,),
        ).fetchall()
    finally:
        conn.close()
    assert worker_rows == []
