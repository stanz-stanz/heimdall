"""Audit-log writer for ``console.audit_log``.

Stage A spec §7.1 + §7.5. Every operator-mutating endpoint on the api
calls :func:`write_console_audit_row` inside the same SQLite
transaction as its mutation, so the two rows commit (or roll back)
atomically inside ``console.db``.

The helper is deliberately not a decorator — Stage A keeps audit
writes grep-able next to the mutation they record. The decorator
design space (target_id sources, payload shape, dry-run skipping,
cross-DB selection) is a Stage A.5 concern that compounds with the
``Permission`` enum and X-Request-ID middleware.

Caller contract:
- Open ``console.db`` connection (e.g. via ``get_console_conn``).
- Begin transaction (Python's sqlite3 default does this implicitly).
- Run the mutation.
- Call :func:`write_console_audit_row`.
- Commit on the caller's ``with conn:`` exit (or explicit COMMIT).

The helper does NOT commit. If the caller's transaction raises, both
the mutation and the audit row roll back together.

Slice 3g spec §7.9 also relocated :func:`maybe_write_disabled_operator_audit`
to this module from ``src/api/auth/middleware.py`` so the HTTP middleware
and the WebSocket handler at ``/console/ws`` (slice 3g) share a single
implementation. The probe SELECT and audit-row write are identical
across both call sites; the only difference is the request-shape passed
in (real Starlette ``Request`` for HTTP, ``_build_pseudo_request`` adapter
for WS scope per slice 3g spec §4.2).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from loguru import logger


# Schema enforces no SQL-level limit on user_agent, but a pathological
# client could otherwise inflate the WAL. Match the truncation cap in
# src.api.auth.sessions._truncate_ua so the two write paths agree on
# the maximum stored size.
_MAX_UA_LEN = 512


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise_target_id(value: str | int | None) -> str | None:
    """Coerce target_id to a string for the TEXT column.

    The schema (``console-db-schema.sql`` §3) keeps ``target_id`` as
    TEXT so a single index works across int IDs (sessions, operators),
    CVR strings (clients), and config-name strings (settings).
    Stringifying at write time means downstream queries don't have to
    type-cast.
    """
    if value is None:
        return None
    return str(value)


def write_console_audit_row(
    conn: sqlite3.Connection,
    request: Any,
    *,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    payload: dict[str, Any] | None = None,
    operator_id: int | None = None,
    session_id: int | None = None,
    request_id: str | None = None,
) -> int:
    """INSERT one row into ``console.audit_log``. Return the new id.

    Reads operator / session / request-id from ``request.state`` by
    default — SessionAuthMiddleware (slice 3d) populates those
    attributes on authenticated requests. The login handler is the
    canonical exception: ``auth.login_ok`` is written immediately
    after :func:`src.api.auth.sessions.issue_session` returns, before
    any middleware has touched ``request.state`` for this request,
    so the new operator_id / session_id are not yet on state. The
    explicit ``operator_id`` / ``session_id`` kwargs let the login
    handler pair the row with the right FKs without mutating
    ``request.state`` as a side effect.

    For pre-auth events that legitimately have no operator association
    (``auth.login_failed`` rows where credentials never validated)
    callers omit both kwargs and the helper records ``NULL``.

    ``request.client.host`` is the trusted source IP — never read
    ``X-Forwarded-For`` here (operator-controlled at the proxy layer).

    Args:
        conn: Open connection to ``console.db``. The helper does NOT
            commit; the caller's transaction is the boundary.
        request: A FastAPI/Starlette ``Request`` (or duck-typed
            equivalent in tests). The helper only reads attributes:
            ``state``, ``client``, ``headers``.
        action: Free-text in Stage A (e.g. ``auth.login_ok``,
            ``cmd.dispatch``). Stage A.5 will migrate to a
            ``Permission`` enum value.
        target_type: Coarse type tag for queries
            (``operator`` / ``session`` / ``websocket`` / ``command``).
        target_id: Identifier paired with ``target_type``. Coerced to
            ``str`` for the TEXT column.
        payload: Optional dict serialized via ``json.dumps(..., default=str)``
            so datetime / Path / similar values stringify rather than
            raising. Caller is responsible for stripping any secret-
            bearing fields BEFORE handing the payload to this helper.
        operator_id: Override for ``request.state.operator_id``. Use
            in the login flow where state isn't yet populated.
        session_id: Override for ``request.state.session_id``.
        request_id: Override for ``request.state.request_id``. Stage
            A.5 wires X-Request-ID middleware that populates state;
            until then this kwarg lets a handler thread a request id
            through manually if it has one.

    Returns:
        The autoincrement id of the inserted ``audit_log`` row.
    """
    state = getattr(request, "state", None)
    if operator_id is None:
        operator_id = (
            getattr(state, "operator_id", None) if state is not None else None
        )
    if session_id is None:
        session_id = (
            getattr(state, "session_id", None) if state is not None else None
        )
    if request_id is None:
        request_id = (
            getattr(state, "request_id", None) if state is not None else None
        )

    client = getattr(request, "client", None)
    source_ip = getattr(client, "host", None) if client is not None else None

    headers = getattr(request, "headers", {}) or {}
    raw_ua = headers.get("user-agent", "")
    user_agent = raw_ua[:_MAX_UA_LEN] if raw_ua is not None else ""

    payload_json = (
        json.dumps(payload, default=str) if payload is not None else None
    )

    cursor = conn.execute(
        "INSERT INTO audit_log "
        "(occurred_at, operator_id, session_id, action, "
        " target_type, target_id, payload_json, "
        " source_ip, user_agent, request_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _now_iso(),
            operator_id,
            session_id,
            action,
            target_type,
            _normalise_target_id(target_id),
            payload_json,
            source_ip,
            user_agent,
            request_id,
        ),
    )
    return cursor.lastrowid or 0


def maybe_write_disabled_operator_audit(
    conn: sqlite3.Connection,
    request: Any,
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
    at WARNING and falls through. The caller still returns the 401 /
    closes the WS with 4401 — this helper exists to capture forensic
    state, not to gate the rejection.

    Originally lived in ``src/api/auth/middleware.py`` (slice 3e item
    F). Relocated here in slice 3g per spec §7.9 so the HTTP middleware
    and the ``/console/ws`` handler share a single implementation. The
    ``request`` arg is duck-typed: it just needs ``.state``, ``.client``,
    ``.headers`` for :func:`write_console_audit_row` to populate the
    audit row. The WS handler passes a ``_build_pseudo_request`` adapter
    over the WebSocket scope (slice 3g spec §4.2).
    """
    now_iso = _now_iso()
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
