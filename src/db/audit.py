"""``command_audit`` writer for ``clients.db``.

Stage A.5 spec §4.1.6. The api-INSERT-driven side of the audit pair: while
``config_changes`` is trigger-driven (one row per UPDATE / DELETE on tier-1
tables, populated via the ``_audit_context`` TEMP table — see
``src/db/audit_context.py``), ``command_audit`` is hand-written from the
api because the api owns the operator-command surface end-to-end
(``/console/commands/{command}`` → dispatch → outcome).

Pair shape (master spec §1.3.b):

- ``console.audit_log`` row: ``action='command.dispatch'``,
  ``target_type='command'``, ``target_id=command_name``,
  ``request_id=<rid>``. Written by api in ``console_command``
  (``src/api/console.py:862``).
- ``command_audit`` row: ``command_name=<name>``,
  ``outcome='ok' | 'error' | 'partial'``, ``request_id=<same rid>``.
  Written by scheduler / worker on command completion, threading the
  same request_id back through to the writer.

The two rows correlate via ``request_id`` across the two databases.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    """ISO-8601 UTC timestamp with millisecond precision.

    Matches the ``strftime('%Y-%m-%dT%H:%M:%fZ', 'now')`` used by the
    ``config_changes`` triggers so cross-row ordering reads consistently
    in mixed-source forensic reviews.
    """
    now = datetime.now(UTC)
    millis = now.microsecond // 1000
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def write_command_audit_row(
    conn: sqlite3.Connection,
    *,
    command_name: str,
    outcome: str,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
    error_detail: str | None = None,
    operator_id: int | None = None,
    session_id: int | None = None,
    request_id: str | None = None,
    actor_kind: str = "operator",
) -> int:
    """INSERT one row into ``clients.db.command_audit``.

    The helper does NOT commit — the caller's transaction
    (typically ``with conn:`` in the writer container) is the boundary.

    Args:
        conn: Open connection to ``clients.db``.
        command_name: Operator command name
            (e.g. ``run-pipeline``, ``interpret``, ``send``).
        outcome: ``ok`` | ``error`` | ``partial``. ``error_detail`` is
            populated when outcome != ``ok``.
        target_type: Optional coarse type tag
            (e.g. ``pipeline_run``, ``domain``, ``delivery``).
        target_id: Optional identifier paired with ``target_type``.
            Coerced to ``str`` for the TEXT column.
        payload: Optional dict serialized via ``json.dumps(..., default=str)``.
            Caller is responsible for stripping any secret-bearing fields
            BEFORE handing the payload here.
        error_detail: Optional free-text on the failure branch.
            ``None`` on the happy path.
        operator_id: Console operator id. ``None`` for system-driven
            (cron) command runs.
        session_id: Console session id. ``None`` for system writes.
        request_id: X-Request-ID for cross-DB correlation with the
            api's ``console.audit_log`` row.
        actor_kind: ``operator`` (default) | ``system``.

    Returns:
        The autoincrement ``id`` of the inserted ``command_audit`` row.
    """
    payload_json = (
        json.dumps(payload, default=str) if payload is not None else None
    )
    target_id_str = str(target_id) if target_id is not None else None

    cursor = conn.execute(
        "INSERT INTO command_audit "
        "(occurred_at, command_name, target_type, target_id, "
        " outcome, payload_json, error_detail, "
        " operator_id, session_id, request_id, actor_kind) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            _now_iso(),
            command_name,
            target_type,
            target_id_str,
            outcome,
            payload_json,
            error_detail,
            operator_id,
            session_id,
            request_id,
            actor_kind,
        ),
    )
    return cursor.lastrowid or 0
