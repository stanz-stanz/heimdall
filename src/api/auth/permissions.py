"""Permission enum + ``@require_permission`` decorator (Stage A.5 §4.2).

The decorator gates every mutating ``/console/*`` HTTP handler. It runs
*after* :class:`SessionAuthMiddleware` (slice 3d) has populated
``request.state.{operator_id, session_id, role_hint, request_id}``, so a
401 from this decorator is defense-in-depth — the middleware is the
canonical 401 surface.

WS handlers do NOT use this decorator. They run an inline permission
check inside ``_authenticate_ws`` (spec §4.2.5, locked v2). The audit
vocabulary (``auth.permission_denied`` action, ``Permission.X.value``
target_id) is shared across both paths.

Fork (h) — locked 2026-05-02. ``ROLE_PERMISSIONS`` keys on ``'owner'``,
matching the seeded reality at ``src/db/console_connection.py:155``.
The spec text used ``'operator'``; see spec §11.8 and the
``docs/decisions/log.md`` 2026-05-02 evening entry for the
resolution. The lookup case-normalises + whitespace-strips so a
``'Owner'`` / ``'  owner  '`` typo cannot permanently lock the
operator out of the console. Note: spec §11.2 already had a Fork
(b) for ``config_changes`` scope — unrelated; this fork is (h).

Audit-write fail-secure rule (peer-review P1, 2026-05-02). If the
deny-path INSERT into ``console.audit_log`` raises a
:class:`sqlite3.OperationalError`, the decorator logs at WARNING and
**still raises 403**. An audit-layer fault must never swallow the
deny decision — that's a fail-open vector.
"""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
import typing
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

from fastapi import HTTPException, Request
from loguru import logger

from src.api.auth.audit import write_console_audit_row
from src.db.console_connection import (
    DEFAULT_CONSOLE_DB_PATH,
    get_console_conn,
)


class Permission(str, Enum):
    """Code-backed permission vocabulary for FastAPI handlers (spec §4.2.1).

    Stage A.5 D3 (locked 2026-04-27 evening): table-backed RBAC is
    deferred until Heimdall has more than two real roles or requires
    runtime role administration. The single ``'owner'`` mapping in
    :data:`ROLE_PERMISSIONS` grants every permission below.

    Each permission stamps onto ``console.audit_log.action`` (deny
    rows) and ``command_audit.command_name`` (clients.db) for the
    gated mutation, so the audit timeline reads as the permission
    name rather than a free-text route literal. ``Permission(str, Enum)``
    means ``Permission.X == 'x'`` is True and ``permission.value``
    yields the lowercase string used in audit rows (spec §9 #9).
    """

    CONSOLE_READ = "console.read"
    RETENTION_FORCE_RUN = "retention.force_run"
    RETENTION_CANCEL = "retention.cancel"
    RETENTION_RETRY = "retention.retry"
    CONFIG_WRITE = "config.write"
    COMMAND_DISPATCH = "command.dispatch"
    DEMO_RUN = "demo.run"


# Single role in v1 (D3, fork (h) = 'owner' per spec §11.8). Maps OWNER →
# all permissions. Future: 'observer': frozenset({Permission.CONSOLE_READ}).
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": frozenset(Permission),
}


F = TypeVar("F", bound=Callable[..., Any])


def _has_request_param(handler: Callable[..., Any]) -> bool:
    """True iff the handler declares a ``Request``-annotated param.

    Resolves PEP 563 string annotations via :func:`typing.get_type_hints`
    so handlers defined under ``from __future__ import annotations``
    (every module in this codebase) compare class-to-class rather than
    string-to-class. The check is annotation-only — a parameter merely
    named ``request`` but annotated to another type (e.g. ``request: dict``)
    would not give the runtime wrapper anywhere to read ``request.state``
    from, so naming alone is insufficient evidence of intent.
    """
    try:
        hints = typing.get_type_hints(handler)
    except (NameError, TypeError):
        # Forward refs to module-local types that don't resolve at
        # decoration time. Refuse the handler so the misuse surfaces
        # immediately rather than at first request.
        return False
    return any(annotation is Request for annotation in hints.values())


def _extract_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
    """Pull the ``Request`` out of the wrapped call's args/kwargs.

    Tries kwargs first (FastAPI's normal injection path for
    ``request: Request`` parameters), then scans positional args for
    an instance — covers handlers where ``request`` is a positional
    after a path parameter (e.g. ``async def h(job_id: int, request: Request)``).
    """
    candidate = kwargs.get("request")
    if isinstance(candidate, Request):
        return candidate
    for arg in args:
        if isinstance(arg, Request):
            return arg
    # Test paths supply duck-typed Request stand-ins (SimpleNamespace);
    # the isinstance check would reject them. Fall through to
    # attribute-presence detection so unit tests do not need a real
    # FastAPI Request.
    if candidate is not None and hasattr(candidate, "state"):
        return candidate  # type: ignore[return-value]
    for arg in args:
        if hasattr(arg, "state") and hasattr(arg, "app"):
            return arg
    return None


def _write_deny_audit(
    request: Any,
    permission: Permission,
    role_hint: str | None,
    operator_id: int | None,
    session_id: int | None,
) -> None:
    """Open ``console.db``, INSERT one ``auth.permission_denied`` row, close.

    Caller's responsibility: handle :class:`sqlite3.OperationalError`
    around the call to keep the deny decision fail-secure (the 403
    raises even if this helper raises). Module-level so tests can
    monkeypatch the writer to simulate db faults.
    """
    db_path = getattr(
        getattr(request.app, "state", None), "console_db_path", None
    ) or DEFAULT_CONSOLE_DB_PATH
    conn = get_console_conn(db_path)
    try:
        with conn:
            write_console_audit_row(
                conn,
                request,
                action="auth.permission_denied",
                target_type="permission",
                target_id=permission.value,
                payload={"role_hint": role_hint},
                operator_id=operator_id,
                session_id=session_id,
            )
    finally:
        conn.close()


def require_permission(permission: Permission) -> Callable[[F], F]:
    """Decorator factory — gate a console handler on ``permission``.

    Decoration-time invariants (raise :class:`TypeError` at import):
      * handler must be ``async def`` (FastAPI dispatches sync handlers
        on a worker thread, but this decorator's wrapper is async-only
        for ``await handler(...)`` symmetry);
      * handler must declare a ``request: Request`` parameter so the
        wrapper can read ``request.state``.

    Runtime contract (spec §4.2.2, peer-reviewed 2026-05-02):
      1. Extract ``Request`` from kwargs first, then args.
      2. Read ``operator_id``, ``session_id``, ``role_hint``,
         ``request_id`` from ``request.state`` exactly once.
      3. ``operator_id is None`` → ``HTTPException(401, {"error":
         "not_authenticated"})``. No audit row (middleware path).
      4. ``permission not in ROLE_PERMISSIONS.get((role_hint or "")
         .lower().strip(), frozenset())`` → fail-secure deny:
            * try-write the ``auth.permission_denied`` audit row via
              :func:`asyncio.to_thread` (sync sqlite3 off the event
              loop, consistent with ``_run_retention_action``);
            * on :class:`sqlite3.OperationalError` log WARNING and
              fall through;
            * raise ``HTTPException(403, {"error": "permission_denied",
              "permission": permission.value})``.
      5. Allow → ``return await handler(*args, **kwargs)``.

    Connection lifecycle: SessionAuthMiddleware has already opened +
    closed its ``console.db`` connection by the time this decorator
    runs (FastAPI ``BaseHTTPMiddleware`` lifecycle). Per-request open
    on the deny path is correct; the allow path opens no connection.
    Do not "optimise" by hoisting the connection through ``request.state``
    — that would re-introduce a cross-request leak vector.
    """

    def decorator(handler: F) -> F:
        if not inspect.iscoroutinefunction(handler):
            raise TypeError(
                "require_permission requires an async handler; got "
                f"{handler!r}. FastAPI dispatches sync handlers on a "
                "worker thread, but the decorator's wrapper is async."
            )
        if not _has_request_param(handler):
            raise TypeError(
                "require_permission handler must declare a "
                "`request: Request` parameter so the decorator can "
                f"read request.state; got {handler!r}."
            )

        @wraps(handler)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request = _extract_request(args, kwargs)
            if request is None:
                raise RuntimeError(
                    "require_permission could not locate Request in "
                    f"args/kwargs for {handler!r}; the decoration-time "
                    "guard should have caught this."
                )

            state = request.state
            operator_id = getattr(state, "operator_id", None)
            session_id = getattr(state, "session_id", None)
            role_hint = getattr(state, "role_hint", None)

            if operator_id is None:
                raise HTTPException(
                    status_code=401,
                    detail={"error": "not_authenticated"},
                )

            granted = ROLE_PERMISSIONS.get(
                (role_hint or "").lower().strip(), frozenset()
            )
            if permission not in granted:
                try:
                    await asyncio.to_thread(
                        _write_deny_audit,
                        request,
                        permission,
                        role_hint,
                        operator_id,
                        session_id,
                    )
                except sqlite3.OperationalError as exc:
                    logger.warning(
                        "permission_denied_audit_write_failed "
                        "permission={} err={}",
                        permission.value,
                        exc,
                    )
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "permission_denied",
                        "permission": permission.value,
                    },
                )

            return await handler(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
