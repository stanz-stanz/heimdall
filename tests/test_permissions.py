"""Tests for src.api.auth.permissions — Stage A.5 RBAC decorator (Wave A).

Stage A.5 spec §4.2 + §6.4. The Permission enum + require_permission
decorator gate the operator-console HTTP surface. WS gates are inline
(spec §4.2.5) and tested in tests/test_console_ws_auth.py (Wave C).

Fork (b) — locked 2026-05-02: ROLE_PERMISSIONS = {"owner": ...}; the
spec text used "operator" but the seeded reality is "owner". Decorator
case-normalises the lookup so 'Owner' / '  owner  ' typos do not lock
the operator out of the console.

Async note. The repo's other suites use FastAPI's sync ``TestClient``;
``pytest-asyncio`` is in ``pyproject.toml`` but not present in the
local venv. The decorator's wrapper is ``async def``, so unit tests
drive it via :func:`asyncio.run` through the local ``_drive`` helper.
TestClient-based integration coverage lives in
``tests/test_console_permission_gates.py`` (Wave B).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException, Request

import src.core.secrets as core_secrets
from src.api.auth.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    require_permission,
)
from src.db.console_connection import get_console_conn, init_db_console


# ---------------------------------------------------------------------------
# Env-isolation — same pattern as tests/test_audit_log_writer.py
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
def console_db(tmp_path: Path) -> str:
    """Fresh console.db with one operator (id=1) + one session (id=1)
    so deny-path audit rows can satisfy the FK constraints."""
    db_path = tmp_path / "console.db"
    init_db_console(db_path).close()
    conn = get_console_conn(db_path)
    try:
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
    finally:
        conn.close()
    return str(db_path)


def _make_request(
    *,
    db_path: str,
    operator_id: int | None = 1,
    session_id: int | None = 1,
    role_hint: str | None = "owner",
    request_id: str | None = None,
) -> Any:
    """Duck-typed Request for decorator unit tests.

    The decorator only reads ``request.state``, ``request.app.state``,
    ``request.client``, and ``request.headers``; a SimpleNamespace tree
    avoids needing a real FastAPI app to exercise the decorator.
    """
    state_kwargs: dict[str, Any] = {}
    if operator_id is not None:
        state_kwargs["operator_id"] = operator_id
    if session_id is not None:
        state_kwargs["session_id"] = session_id
    if role_hint is not None:
        state_kwargs["role_hint"] = role_hint
    if request_id is not None:
        state_kwargs["request_id"] = request_id

    return SimpleNamespace(
        state=SimpleNamespace(**state_kwargs),
        app=SimpleNamespace(state=SimpleNamespace(console_db_path=db_path)),
        client=SimpleNamespace(host="192.0.2.1"),
        headers={"user-agent": "pytest-ua"},
    )


def _drive(handler: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a decorated async handler from a sync test body."""
    return asyncio.run(handler(*args, **kwargs))


# ===========================================================================
# Task 1 — Permission enum + ROLE_PERMISSIONS
# ===========================================================================


def test_permission_enum_has_seven_values() -> None:
    """Spec §4.2.1: 7 permissions cover the 18 HTTP routes + 2 WS gates."""
    expected = {
        "console.read",
        "retention.force_run",
        "retention.cancel",
        "retention.retry",
        "config.write",
        "command.dispatch",
        "demo.run",
    }
    assert {p.value for p in Permission} == expected
    assert len(list(Permission)) == 7


def test_permission_enum_is_str_subclass() -> None:
    """Permission(str, Enum) → ``permission.value`` is the lowercase
    string used in audit rows; ``permission == 'x'`` is True (spec §9 #9).
    """
    assert isinstance(Permission.CONSOLE_READ, str)
    assert Permission.CONSOLE_READ == "console.read"
    assert Permission.CONSOLE_READ.value == "console.read"


def test_role_permissions_owner_maps_to_all() -> None:
    """Fork (b) — single 'owner' role maps to every permission."""
    assert ROLE_PERMISSIONS["owner"] == frozenset(Permission)


def test_role_permissions_only_owner_in_v1() -> None:
    """v1 is single-role; future structured RBAC adds 'observer'/'editor'."""
    assert set(ROLE_PERMISSIONS.keys()) == {"owner"}


# ===========================================================================
# Task 2 — Decoration-time validation (fail at import, not first call)
# ===========================================================================


def test_require_permission_rejects_sync_handler_at_decoration() -> None:
    with pytest.raises(TypeError, match="async"):
        @require_permission(Permission.CONSOLE_READ)
        def sync_handler(request: Request):  # type: ignore[unused-ignore]
            return {"ok": True}


def test_require_permission_rejects_handler_without_request_param() -> None:
    with pytest.raises(TypeError, match="Request"):
        @require_permission(Permission.CONSOLE_READ)
        async def no_request_handler():
            return {"ok": True}


def test_require_permission_rejects_param_named_request_with_wrong_annotation() -> None:
    """A param literally named ``request`` but annotated to a non-Request
    type provides nowhere to read ``request.state`` from. Decoration-time
    validation must reject it (Codex 2026-05-02 finding)."""
    with pytest.raises(TypeError, match="Request"):
        @require_permission(Permission.CONSOLE_READ)
        async def wrong_annotation(request: dict):
            return {"ok": True}


def test_require_permission_accepts_handler_with_request_kwarg() -> None:
    """Decoration-time validation passes when the handler declares a
    ``request: Request`` parameter — even if not the first param."""

    @require_permission(Permission.CONSOLE_READ)
    async def handler(job_id: int, request: Request):
        return {"job_id": job_id}

    assert handler is not None  # decoration succeeded


# ===========================================================================
# Task 3 — Allow path + case normalisation
# ===========================================================================


def test_require_permission_allow_path(console_db: str) -> None:
    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        return {"ok": True, "from": "handler"}

    request = _make_request(db_path=console_db, role_hint="owner")
    assert _drive(handler, request=request) == {"ok": True, "from": "handler"}


def test_require_permission_allows_capitalized_owner(
    console_db: str,
) -> None:
    """Case-(b) lockout mitigation: 'Owner' must allow."""

    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        return {"ok": True}

    request = _make_request(db_path=console_db, role_hint="Owner")
    assert _drive(handler, request=request) == {"ok": True}


def test_require_permission_allows_whitespace_owner(
    console_db: str,
) -> None:
    """Whitespace-stripping prevents a trailing-space typo lockout."""

    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        return {"ok": True}

    request = _make_request(db_path=console_db, role_hint="  owner  ")
    assert _drive(handler, request=request) == {"ok": True}


# ===========================================================================
# Task 4 — 401 path (no operator on state)
# ===========================================================================


def test_require_permission_401_when_no_operator(console_db: str) -> None:
    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        pytest.fail("handler must not run on 401 path")

    request = _make_request(
        db_path=console_db, operator_id=None, role_hint=None
    )
    with pytest.raises(HTTPException) as exc:
        _drive(handler, request=request)
    assert exc.value.status_code == 401
    assert exc.value.detail == {"error": "not_authenticated"}


def test_require_permission_401_writes_no_audit_row(console_db: str) -> None:
    """401 is a middleware-path concern — the decorator does NOT write
    a permission_denied row for unauthenticated requests."""

    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        pytest.fail("handler must not run on 401 path")

    request = _make_request(
        db_path=console_db, operator_id=None, role_hint=None
    )
    with pytest.raises(HTTPException):
        _drive(handler, request=request)

    conn = get_console_conn(console_db)
    try:
        rows = conn.execute(
            "SELECT id FROM audit_log WHERE action = 'auth.permission_denied'"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 0


# ===========================================================================
# Task 5 — Deny + audit row, parametrised over role-hint shapes
# ===========================================================================


@pytest.mark.parametrize(
    "role_hint,case_label",
    [
        (None, "null"),
        ("", "empty"),
        ("observer", "unknown"),
    ],
)
def test_require_permission_denies_and_audits(
    console_db: str, role_hint: str | None, case_label: str
) -> None:
    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        pytest.fail("handler must not run on deny path")

    request = _make_request(
        db_path=console_db,
        operator_id=1,
        session_id=1,
        role_hint=role_hint,
        request_id=f"r-{case_label}-1",
    )

    with pytest.raises(HTTPException) as exc:
        _drive(handler, request=request)
    assert exc.value.status_code == 403
    assert exc.value.detail == {
        "error": "permission_denied",
        "permission": "console.read",
    }

    conn = get_console_conn(console_db)
    try:
        rows = conn.execute(
            "SELECT action, target_type, target_id, payload_json, "
            "       operator_id, session_id, request_id "
            "FROM audit_log WHERE action = 'auth.permission_denied'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["target_type"] == "permission"
    assert row["target_id"] == "console.read"
    assert row["operator_id"] == 1
    assert row["session_id"] == 1
    assert row["request_id"] == f"r-{case_label}-1"
    assert json.loads(row["payload_json"]) == {"role_hint": role_hint}


# ===========================================================================
# Audit-write failure — fail-secure (P1 #3 from peer review)
# ===========================================================================


def test_decorator_audit_write_failure_still_raises_403(
    console_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the deny-audit INSERT raises (db locked / disk full), the
    decorator must log + still raise 403. Fail-secure: never let an
    audit-layer fault swallow the deny decision."""
    import src.api.auth.permissions as perm_module

    def _broken_writer(*args: Any, **kwargs: Any) -> None:
        raise sqlite3.OperationalError("simulated db lock")

    monkeypatch.setattr(perm_module, "_write_deny_audit", _broken_writer)

    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        pytest.fail("handler must not run on deny path")

    request = _make_request(
        db_path=console_db, role_hint="observer", operator_id=1, session_id=1
    )
    with pytest.raises(HTTPException) as exc:
        _drive(handler, request=request)
    assert exc.value.status_code == 403
    assert exc.value.detail == {
        "error": "permission_denied",
        "permission": "console.read",
    }


# ===========================================================================
# Allow + handler-raises — no spurious deny audit row
# ===========================================================================


def test_handler_raises_after_allow_no_deny_audit_row(console_db: str) -> None:
    """Allow-path handler raises a non-RBAC exception → bubble through;
    the decorator must NOT write an auth.permission_denied row (which
    would falsely suggest a gate failure in forensic review)."""

    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        raise RuntimeError("handler failure unrelated to RBAC")

    request = _make_request(db_path=console_db, role_hint="owner")
    with pytest.raises(RuntimeError, match="handler failure"):
        _drive(handler, request=request)

    conn = get_console_conn(console_db)
    try:
        rows = conn.execute(
            "SELECT id FROM audit_log WHERE action = 'auth.permission_denied'"
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 0


# ===========================================================================
# role_hint read-once (P2 from peer review)
# ===========================================================================


def test_role_hint_read_once_from_state(console_db: str) -> None:
    """Decorator reads request.state.role_hint exactly once — once for
    the lookup; the audit-row payload reuses the cached value rather
    than re-reading state (which could disagree if state mutates)."""
    read_count = {"n": 0}

    class StateProbe:
        operator_id = 1
        session_id = 1
        request_id = None

        def __init__(self) -> None:
            self._role = "owner"

        @property
        def role_hint(self) -> str:
            read_count["n"] += 1
            return self._role

    request = SimpleNamespace(
        state=StateProbe(),
        app=SimpleNamespace(state=SimpleNamespace(console_db_path=console_db)),
        client=SimpleNamespace(host="192.0.2.1"),
        headers={"user-agent": "pytest-ua"},
    )

    @require_permission(Permission.CONSOLE_READ)
    async def handler(request: Request):
        return {"ok": True}

    _drive(handler, request=request)
    assert read_count["n"] == 1


# ===========================================================================
# Positional Request extraction
# ===========================================================================


def test_require_permission_extracts_request_from_args(console_db: str) -> None:
    """Some FastAPI handlers take ``request`` as the second positional
    arg (after a path param). Decorator must extract it from args."""

    @require_permission(Permission.CONSOLE_READ)
    async def handler(job_id: int, request: Request):
        return {"job_id": job_id}

    request = _make_request(db_path=console_db, role_hint="owner")
    assert _drive(handler, 42, request) == {"job_id": 42}
