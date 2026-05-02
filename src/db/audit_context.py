"""Audit-context binding for D2 hybrid trigger-captured writes.

Stage A.5 spec §4.1.4 (revised 2026-05-01 after the SQLite TEMP-table-in-
trigger limitation surfaced during implementation). Original spec used a
``CREATE TEMP TABLE _audit_context`` that triggers on regular tables would
read via subqueries. SQLite docs at
https://www.sqlite.org/lang_createtrigger.html state: "It is not valid to
refer to temporary tables [...] from within the trigger body" when the
trigger is on a non-temp table. The TEMP approach raises ``no such table:
main._audit_context`` on first trigger fire.

**Replacement.** A per-connection user-defined SQL function
``audit_context(key) -> value`` is registered via
:meth:`sqlite3.Connection.create_function`. Triggers call
``audit_context('intent')`` etc. instead of subquerying. Per-connection
state lives on a ``HeimdallConnection`` subclass attribute
(``conn._audit_ctx`` — a dict; the subclass exposes ``__dict__`` which the
base ``sqlite3.Connection`` does not).

**Type contract.** ``audit_context()`` returns native Python ``int`` for
``operator_id`` and ``session_id`` (the trigger writes them into INTEGER
columns), TEXT for ``intent`` / ``request_id`` / ``actor_kind``. Returning
native ints rather than stringified ``'42'`` avoids the silent type-
coercion failure that SQLite would otherwise apply to malformed values.

**Mandatory registration.** Every write-capable connection MUST have
``audit_context`` registered before any audited DML fires. The canonical
path is :func:`src.db.connection.init_db`, which calls
:func:`install_audit_context` after schema load. Connections opened
outside ``init_db`` (raw ``sqlite3.connect``) skip registration and will
crash at first trigger fire — that is intentional fail-fast behaviour.

**Bypass detection.** A wrapper-bypass UPDATE (no ``with bind_audit_context``)
still fires the trigger; ``audit_context()`` returns ``None`` for every key
because ``conn._audit_ctx`` is empty. Actor columns land NULL —
forensically detectable at audit-review time. The contract is preserved
across the redesign.

Cron-path callers (claim_due_retention_jobs, release_stuck_retention_jobs,
retention runner lifecycle) MUST pass ``actor_kind="system"`` with
operator_id / session_id / request_id all None.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator


def install_audit_context(conn: sqlite3.Connection) -> None:
    """Register the ``audit_context()`` SQL function on this connection.

    Idempotent. The function takes one TEXT argument (the key) and
    returns the bound value (``int`` for id keys, ``str`` for the rest)
    or ``None`` if no value is bound. Triggers invoke it as
    ``audit_context('intent')``.

    Requires ``conn`` to be an instance of :class:`HeimdallConnection`
    (the subclass with ``__dict__`` support). The base
    ``sqlite3.Connection`` cannot host the per-connection state dict.
    """
    if not hasattr(conn, "_audit_ctx"):
        conn._audit_ctx = {}  # type: ignore[attr-defined]

    def _fn(key: str) -> int | str | None:
        return conn._audit_ctx.get(key)  # type: ignore[attr-defined]

    conn.create_function("audit_context", 1, _fn, deterministic=False)


@contextmanager
def bind_audit_context(
    conn: sqlite3.Connection,
    *,
    intent: str,
    operator_id: int | None = None,
    session_id: int | None = None,
    request_id: str | None = None,
    actor_kind: str = "operator",
) -> Iterator[sqlite3.Connection]:
    """Bind audit context for trigger reads. Restores on exit.

    Args:
        conn: Open connection to ``clients.db`` (must be a
            ``HeimdallConnection`` — i.e. opened via
            :func:`src.db.connection.init_db`). The caller's transaction
            (typically ``with conn:``) is the boundary.
        intent: Application-level intent string (e.g. ``retention.force_run``,
            ``retention.cancel``, ``trial.activated``,
            ``subscription.cancelled``). Spec §4.1.5.
        operator_id: Console operator id. ``None`` for system-driven
            (cron) writes.
        session_id: Console session id. ``None`` for system writes.
        request_id: X-Request-ID populated by the middleware. ``None``
            for system writes that have no upstream HTTP request.
        actor_kind: ``operator`` (default) or ``system``. Cron-path
            callers MUST pass ``"system"`` with all three id fields
            ``None``.

    Yields:
        The same connection, with ``conn._audit_ctx`` populated. On
        exit the dict is restored to the snapshot taken at enter so a
        nested bind composes correctly. On non-nested exit the dict
        is empty so a subsequent bypass UPDATE on the same connection
        does not inherit stale actor metadata.
    """
    install_audit_context(conn)
    saved = dict(conn._audit_ctx)  # type: ignore[attr-defined]
    bound: dict[str, int | str | None] = {
        "intent": intent,
        "operator_id": operator_id,
        "session_id": session_id,
        "request_id": request_id,
        "actor_kind": actor_kind,
    }
    conn._audit_ctx.update(bound)  # type: ignore[attr-defined]
    # Keys that bound to None should NOT shadow the saved snapshot's
    # values when restoring on exit, but during the with-block they
    # need to read as None (not whatever was in saved). Achieved by
    # the snapshot+restore pattern below.
    try:
        yield conn
    finally:
        conn._audit_ctx.clear()  # type: ignore[attr-defined]
        conn._audit_ctx.update(saved)  # type: ignore[attr-defined]
