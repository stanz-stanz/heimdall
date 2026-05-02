"""Tests for src.api.auth.audit — Stage A console.audit_log writer.

Stage A spec §7.1 + §8.2 (test_audit_log_writer.py block). The helper
``write_console_audit_row`` writes one row into ``console.audit_log``
and returns the new row id. It does NOT commit — the caller's
transaction (``with conn:``) is the boundary, so the audit row
commits or rolls back atomically with the mutation it records.

The helper reads ``operator_id`` / ``session_id`` / ``request_id``
from ``request.state`` (populated by SessionAuthMiddleware in slice
3d). For unauthenticated calls (e.g. ``auth.login_failed`` rows
written before the operator is identified), middleware leaves these
attributes unset and the helper records ``NULL`` deliberately.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import src.core.secrets as core_secrets
from src.api.auth.audit import write_console_audit_row
from src.db.console_connection import get_console_conn, init_db_console


# ---------------------------------------------------------------------------
# Env-isolation fixture — same rationale as test_auth_sessions.py
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
# Test helpers
# ---------------------------------------------------------------------------


def _fake_request(
    *,
    operator_id: int | None = None,
    session_id: int | None = None,
    request_id: str | None = None,
    client_host: str | None = "192.0.2.1",
    user_agent: str | None = "pytest-ua",
) -> Any:
    """Minimal duck-typed Request stand-in.

    The audit writer only reads attributes, never calls methods, so a
    SimpleNamespace with the right shape suffices and we avoid coupling
    every audit test to FastAPI's TestClient.
    """
    state_kwargs: dict[str, Any] = {}
    if operator_id is not None:
        state_kwargs["operator_id"] = operator_id
    if session_id is not None:
        state_kwargs["session_id"] = session_id
    if request_id is not None:
        state_kwargs["request_id"] = request_id

    headers = {"user-agent": user_agent} if user_agent is not None else {}
    client = SimpleNamespace(host=client_host) if client_host is not None else None

    return SimpleNamespace(
        state=SimpleNamespace(**state_kwargs),
        client=client,
        headers=headers,
    )


@pytest.fixture
def console_conn(tmp_path: Path) -> sqlite3.Connection:
    """Fresh console.db with one operator (id=1) and one session (id=1)
    so audit rows can satisfy the FK constraints on operator_id /
    session_id."""
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
    conn.execute(
        "INSERT INTO sessions "
        "(id, token_hash, csrf_token, operator_id, "
        " issued_at, expires_at, absolute_expires_at) "
        "VALUES (1, 'h1', 'c1', 1, "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:15:00Z', "
        "'2026-04-28T21:00:00Z')"
    )
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Field population — happy path
# ---------------------------------------------------------------------------


def test_writes_row_with_all_expected_fields_populated(
    console_conn: sqlite3.Connection,
) -> None:
    """An authenticated operator action with the X-Request-ID middleware
    in play populates every column the writer is responsible for:
    occurred_at, operator_id, session_id, action, target_type,
    target_id, payload_json, source_ip, user_agent, request_id.

    Stage A.5 §6.6 adjustment: the request fixture now seeds a
    request_id (mirrors what RequestIdMiddleware would have populated
    on the real HTTP path) so the assertion locks the request_id
    propagation contract. The NULL-on-state-unset path is covered by
    the dedicated ``test_request_id_null_when_state_unset`` below."""
    request = _fake_request(
        operator_id=1, session_id=1, request_id="req-all-fields-1"
    )

    row_id = write_console_audit_row(
        console_conn,
        request,
        action="auth.login_ok",
        target_type="operator",
        target_id=1,
        payload={"username": "alice"},
    )
    console_conn.commit()
    assert isinstance(row_id, int) and row_id > 0

    row = console_conn.execute(
        "SELECT * FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()
    assert row["occurred_at"].endswith("Z")
    # Sanity check the timestamp is recent UTC.
    occurred = datetime.strptime(row["occurred_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
    assert (datetime.now(UTC) - occurred).total_seconds() < 5

    assert row["operator_id"] == 1
    assert row["session_id"] == 1
    assert row["action"] == "auth.login_ok"
    assert row["target_type"] == "operator"
    assert row["target_id"] == "1"  # spec stores as TEXT for FK flexibility
    assert json.loads(row["payload_json"]) == {"username": "alice"}
    assert row["source_ip"] == "192.0.2.1"
    assert row["user_agent"] == "pytest-ua"
    assert row["request_id"] == "req-all-fields-1"


# ---------------------------------------------------------------------------
# Operator/session id propagation from request.state
# ---------------------------------------------------------------------------


def test_unauthenticated_request_writes_nulls_for_operator_and_session(
    console_conn: sqlite3.Connection,
) -> None:
    """A pre-auth row (e.g. ``auth.login_failed``) — middleware never
    populated request.state.operator_id / session_id, so the helper
    records NULL deliberately. Forensic tools read this as 'no
    identified operator at the time of the event'."""
    request = _fake_request()  # no operator_id, no session_id

    row_id = write_console_audit_row(
        console_conn,
        request,
        action="auth.login_failed",
        target_type="operator",
        target_id="alice",
        payload={"reason": "invalid_credentials"},
    )
    console_conn.commit()

    row = console_conn.execute(
        "SELECT operator_id, session_id, target_id FROM audit_log WHERE id = ?",
        (row_id,),
    ).fetchone()
    assert row["operator_id"] is None
    assert row["session_id"] is None
    assert row["target_id"] == "alice"


def test_explicit_operator_session_kwargs_override_request_state(
    console_conn: sqlite3.Connection,
) -> None:
    """The login handler writes auth.login_ok BEFORE middleware
    populates request.state — the new operator/session must come in
    via explicit kwargs so the audit row carries the right FKs.
    Without this override, login_ok rows would record NULL for both
    columns and the audit log would lose the link from a successful
    login to the operator and session it minted.
    """
    request = _fake_request()  # request.state empty — pre-middleware
    row_id = write_console_audit_row(
        console_conn,
        request,
        action="auth.login_ok",
        target_type="operator",
        target_id=1,
        operator_id=1,
        session_id=1,
    )
    console_conn.commit()
    row = console_conn.execute(
        "SELECT operator_id, session_id FROM audit_log WHERE id = ?",
        (row_id,),
    ).fetchone()
    assert row["operator_id"] == 1
    assert row["session_id"] == 1


def test_explicit_kwargs_take_precedence_over_request_state(
    console_conn: sqlite3.Connection,
) -> None:
    """Even when request.state HAS operator_id / session_id, an
    explicit kwarg wins. Locks the override semantics so future
    handlers can rely on them deterministically."""
    request = _fake_request(operator_id=99, session_id=99)
    row_id = write_console_audit_row(
        console_conn,
        request,
        action="auth.login_ok",
        operator_id=1,
        session_id=1,
    )
    console_conn.commit()
    row = console_conn.execute(
        "SELECT operator_id, session_id FROM audit_log WHERE id = ?",
        (row_id,),
    ).fetchone()
    assert row["operator_id"] == 1
    assert row["session_id"] == 1


def test_target_id_int_serialized_as_string(
    console_conn: sqlite3.Connection,
) -> None:
    """Spec stores target_id as TEXT for FK flexibility (int / cvr /
    config name). The helper coerces ints to str at write time so
    downstream queries don't have to type-cast."""
    request = _fake_request(operator_id=1, session_id=1)
    row_id = write_console_audit_row(
        console_conn, request, action="auth.logout", target_type="session", target_id=1
    )
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT target_id FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["target_id"]
    assert stored == "1"
    assert isinstance(stored, str)


# ---------------------------------------------------------------------------
# Payload JSON serialization
# ---------------------------------------------------------------------------


def test_payload_json_roundtrips_simple_dict(
    console_conn: sqlite3.Connection,
) -> None:
    request = _fake_request(operator_id=1, session_id=1)
    payload = {"k": "v", "n": 7, "nested": {"a": [1, 2, 3]}}
    row_id = write_console_audit_row(
        console_conn, request, action="cmd.dispatch", payload=payload
    )
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT payload_json FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["payload_json"]
    assert json.loads(stored) == payload


def test_payload_json_default_str_falls_back_for_datetime(
    console_conn: sqlite3.Connection,
) -> None:
    """Spec §7.1: 'Serializes payload via json.dumps(payload, default=str)'.

    A datetime in the payload would otherwise raise TypeError; the
    fallback stringifies it instead, making the helper robust to
    handlers that drop a timestamp into the payload without thinking.
    """
    request = _fake_request(operator_id=1, session_id=1)
    when = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)
    row_id = write_console_audit_row(
        console_conn, request, action="cmd.dispatch", payload={"when": when}
    )
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT payload_json FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["payload_json"]
    decoded = json.loads(stored)
    assert decoded["when"] == str(when)


def test_payload_none_writes_null(
    console_conn: sqlite3.Connection,
) -> None:
    """Omitted payload writes NULL into payload_json — empty-dict vs
    no-payload remains distinguishable in forensic queries."""
    request = _fake_request(operator_id=1, session_id=1)
    row_id = write_console_audit_row(console_conn, request, action="cmd.dispatch")
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT payload_json FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["payload_json"]
    assert stored is None


# ---------------------------------------------------------------------------
# Request metadata — IP, UA truncation, request_id
# ---------------------------------------------------------------------------


def test_user_agent_truncated_to_512_chars(
    console_conn: sqlite3.Connection,
) -> None:
    """A pathological UA gets capped at 512 chars at write time, per
    schema comment + spec §7.1."""
    long_ua = "Z" * 2048
    request = _fake_request(operator_id=1, session_id=1, user_agent=long_ua)
    row_id = write_console_audit_row(console_conn, request, action="auth.login_ok")
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT user_agent FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["user_agent"]
    assert stored is not None
    assert len(stored) == 512


def test_user_agent_missing_header_writes_empty_string(
    console_conn: sqlite3.Connection,
) -> None:
    """``request.headers.get('user-agent', '')`` per spec — empty
    string when the header is absent, not None. Distinguishes 'no UA
    sent' from 'no request at all'."""
    request = _fake_request(operator_id=1, session_id=1, user_agent=None)
    row_id = write_console_audit_row(console_conn, request, action="auth.login_ok")
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT user_agent FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["user_agent"]
    assert stored == ""


def test_source_ip_pulled_from_request_client_host(
    console_conn: sqlite3.Connection,
) -> None:
    """Spec §3.1.a: source_ip MUST come from request.client.host (the
    trusted upstream value), never X-Forwarded-For (operator-controlled
    at the proxy)."""
    request = _fake_request(
        operator_id=1, session_id=1, client_host="203.0.113.42"
    )
    row_id = write_console_audit_row(console_conn, request, action="auth.login_ok")
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT source_ip FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["source_ip"]
    assert stored == "203.0.113.42"


def test_source_ip_null_when_request_has_no_client(
    console_conn: sqlite3.Connection,
) -> None:
    """``request.client`` can legitimately be None (test client, ASGI
    paths without a peer). The helper records NULL rather than
    crashing."""
    request = _fake_request(operator_id=1, session_id=1, client_host=None)
    row_id = write_console_audit_row(console_conn, request, action="auth.login_ok")
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT source_ip FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["source_ip"]
    assert stored is None


def test_request_id_propagated_when_set(
    console_conn: sqlite3.Connection,
) -> None:
    """Stage A.5 X-Request-ID middleware populates ``request.state.
    request_id`` on every HTTP and WebSocket scope; the helper reads
    that attribute and lands the value on the audit row. End-to-end
    correlation across the two databases is exercised in
    ``tests/test_request_id_middleware.py::
    test_request_id_propagated_across_two_dbs``.
    """
    request = _fake_request(
        operator_id=1, session_id=1, request_id="req-abc123"
    )
    row_id = write_console_audit_row(console_conn, request, action="auth.login_ok")
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT request_id FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["request_id"]
    assert stored == "req-abc123"


def test_request_id_null_when_state_unset(
    console_conn: sqlite3.Connection,
) -> None:
    """When ``request.state.request_id`` is unset (e.g. a unit-test
    path that bypasses the X-Request-ID middleware), the column
    stays NULL — the helper does not invent a value."""
    request = _fake_request(operator_id=1, session_id=1)
    row_id = write_console_audit_row(console_conn, request, action="auth.login_ok")
    console_conn.commit()
    stored = console_conn.execute(
        "SELECT request_id FROM audit_log WHERE id = ?", (row_id,)
    ).fetchone()["request_id"]
    assert stored is None


# ---------------------------------------------------------------------------
# Transactional contract — caller commits / rolls back
# ---------------------------------------------------------------------------


def test_helper_does_not_self_commit(tmp_path: Path) -> None:
    """The audit row stays uncommitted until the caller commits.

    A fresh reader-side connection must NOT see the audit row before
    the writer commits. This is the contract that ties the audit row
    to the mutation it records — both commit together or both don't.
    """
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()

    writer = get_console_conn(db_path)
    writer.execute(
        "INSERT INTO operators "
        "(id, username, display_name, password_hash, role_hint, "
        " created_at, updated_at) "
        "VALUES (1, 'alice', 'Alice', '$argon2id$placeholder', 'owner', "
        "'2026-04-28T09:00:00Z', '2026-04-28T09:00:00Z')"
    )
    writer.commit()

    request = _fake_request(operator_id=1)
    write_console_audit_row(writer, request, action="auth.login_ok")
    # Deliberately no commit on the writer.

    reader = get_console_conn(db_path)
    visible = reader.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    reader.close()
    assert visible == 0

    writer.rollback()
    after_rollback = writer.execute(
        "SELECT COUNT(*) FROM audit_log"
    ).fetchone()[0]
    writer.close()
    assert after_rollback == 0


def test_rollback_removes_the_row(
    console_conn: sqlite3.Connection,
) -> None:
    """Spec §7.5: 'If any step raises, both rows in this DB roll back.'

    Simulate a paired-write failure: write the audit row, then roll
    back instead of committing. The row must vanish completely so the
    audit log never records an event whose mutation didn't actually
    land.
    """
    request = _fake_request(operator_id=1, session_id=1)
    write_console_audit_row(
        console_conn,
        request,
        action="cmd.dispatch",
        payload={"cmd": "force-run"},
    )
    console_conn.rollback()

    count = console_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert count == 0
