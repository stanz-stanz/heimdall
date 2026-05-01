"""Retention execution runner — one ``tick()`` per scheduler poll.

This is the orchestration layer between the scheduler daemon's timer
thread and the action handlers in :mod:`src.retention.actions`. The
scheduler calls :func:`tick` every 300 seconds (see
``src/scheduler/daemon.py::_start_retention_timer``); each tick:

1. Reaps any ``status='running'`` rows stranded by a crashed executor.
2. Atomically claims up to N due pending jobs.
3. Dispatches each to its handler inside the claim transaction. On
   Sentinel anonymise / purge, writes ``offboarding_triggered`` +
   ``authorisation_revoked`` to ``conversion_events`` (before / after
   the cascade for the latter, so the audit row survives the
   consent_records delete).
4. On success, marks the job ``completed``. On failure, reschedules
   with exponential backoff (15m / 1h / 4h / 24h / terminal).
5. On terminal failure (attempt 5), fires the operator alert via the
   injected ``alert_cb`` — defaults to a Redis publish on
   ``operator:retention-alert`` so the delivery bot can compose the
   Telegram message.

CVRs with the ``DRYRUN-`` prefix (e.g. synthetic targets from
``scripts/dev/cert_change_dry_run.py``) are skipped — their retention
jobs exist for test purposes and must never touch real action handlers.

The ``'export'`` action currently raises ``NotImplementedError`` — GDPR
DSAR export has its own ADR (not yet written). The dispatcher surfaces
the NotImplementedError as a terminal failure on first attempt (no
point retrying code that is not yet written).
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from src.db.audit_context import bind_audit_context
from src.db.connection import _now
from src.db.conversion import _validate_conversion_event_type
from src.db.retention import (
    claim_due_retention_jobs,
    get_retention_job,
    reap_stuck_running_jobs,
)
from src.retention.actions import (
    anonymise_client,
    purge_bookkeeping,
    purge_client,
)

# ---------------------------------------------------------------------------
# Backoff schedule (architect §5). Attempt N is 1-indexed (first failure
# = attempt 1). Attempt 5 is terminal — no further retry, fire the alert.
# ---------------------------------------------------------------------------

_BACKOFF_MINUTES: dict[int, int] = {
    1: 15,
    2: 60,
    3: 240,
    4: 1440,
    # 5 → terminal, no scheduled_for bump
}
MAX_ATTEMPTS = 5

# Alert channel — see architect's proposal §5 ("Alerting" paragraph).
# The delivery bot subscribes and composes the Telegram message. We
# publish JSON with cvr / action / scheduled_for / last_error so the
# operator can act from the alert without opening the console.
RETENTION_ALERT_CHANNEL = "operator:retention-alert"

# Prefix used by cert_change_dry_run and similar synthetic-target
# scripts. B7 decision: the runner skips these so a dry-run's retention
# artefacts never touch the real action handlers.
DRYRUN_CVR_PREFIX = "DRYRUN-"

# Parse "attempt N: ..." out of notes. Previous failures store attempt
# counters in-band (we do not have an explicit ``attempt`` column —
# ``retention_jobs`` schema is frozen for this PR).
_ATTEMPT_RE = re.compile(r"^attempt (\d+):", re.IGNORECASE)


AlertCallback = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_attempt(notes: str | None) -> int:
    """Return the previous attempt count parsed out of ``notes``.

    Looks for ``"attempt N:"`` at the head of the string. Returns 0 if
    the field is empty / does not match.
    """
    if not notes:
        return 0
    match = _ATTEMPT_RE.match(notes)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _backoff_iso(now_iso: str, minutes: int) -> str:
    """Return ``now + minutes`` as ISO-8601 UTC."""
    if now_iso.endswith("Z"):
        ref = datetime.strptime(now_iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    else:
        ref = datetime.fromisoformat(now_iso)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=UTC)
    # Normalise to UTC before stamping the literal `Z` suffix. _now() always
    # returns Z-suffixed UTC, so this is a no-op in production — defensive
    # against future / test callers passing offset-aware non-UTC inputs
    # (Codex flagged 2026-04-25 / pass 3).
    return (
        (ref + timedelta(minutes=minutes))
        .astimezone(UTC)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _mark_completed_in_txn(
    conn: sqlite3.Connection, job_id: int, notes: str
) -> None:
    """Stamp status=completed + executed_at. Caller owns the commit."""
    conn.execute(
        """
        UPDATE retention_jobs
           SET status = 'completed', executed_at = ?, notes = ?
         WHERE id = ?
        """,
        (_now(), notes, job_id),
    )


def _reschedule_with_backoff(
    conn: sqlite3.Connection,
    job_id: int,
    attempt: int,
    error: str,
) -> bool:
    """Bump the attempt counter and either reschedule or mark failed.

    Writes ``attempt N: <error>`` into ``notes``. Returns True iff the
    job is now terminal (``status='failed'``).
    """
    if attempt < MAX_ATTEMPTS:
        minutes = _BACKOFF_MINUTES[attempt]
        next_at = _backoff_iso(_now(), minutes)
        conn.execute(
            """
            UPDATE retention_jobs
               SET status = 'pending',
                   scheduled_for = ?,
                   claimed_at = NULL,
                   notes = ?
             WHERE id = ?
            """,
            (next_at, f"attempt {attempt}: {error}", job_id),
        )
        conn.commit()
        return False

    # Terminal: stamp failed + preserve the last error in notes.
    conn.execute(
        """
        UPDATE retention_jobs
           SET status = 'failed',
               executed_at = ?,
               notes = ?
         WHERE id = ?
        """,
        (_now(), f"attempt {attempt}: {error}", job_id),
    )
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Alert callback factories
# ---------------------------------------------------------------------------


def _default_redis_alert(redis_conn: Any) -> AlertCallback:
    """Build an alert callback that publishes on ``operator:retention-alert``.

    The delivery bot subscribes to this channel and composes / sends the
    Telegram message. Publishing is best-effort — any exception is
    logged and swallowed (the DB has already recorded status='failed',
    which the operator console surfaces independently).
    """

    def _publish(payload: dict[str, Any]) -> None:
        try:
            redis_conn.publish(RETENTION_ALERT_CHANNEL, json.dumps(payload))
        except Exception as exc:
            logger.bind(payload=payload).warning(
                "retention_alert_publish_failed: {}", exc
            )

    return _publish


# ---------------------------------------------------------------------------
# Audit-event emission inside the dispatch transaction
# ---------------------------------------------------------------------------


def _emit_event_in_txn(
    conn: sqlite3.Connection,
    *,
    cvr: str,
    event_type: str,
    source: str,
    payload: dict,
) -> None:
    """Append a conversion_events row WITHOUT committing.

    Mirrors :func:`src.db.conversion.record_conversion_event` byte-for-byte
    on the INSERT side, but deliberately omits the ``conn.commit()`` call
    that helper performs. The retention dispatcher composes one logical
    transaction per job — action handler mutations + this audit row +
    the runner's ``_mark_completed_in_txn`` stamp — and commits once at
    the end. If the action raises, the runner ``rollback()``s and the
    audit row goes away with the rest of the work, preserving forensic
    consistency (no orphan ``offboarding_triggered`` for a job that
    never executed).

    The committing helper :func:`record_conversion_event` is left intact
    for other callers (signup, onboarding handlers) that DO want the
    immediate-commit semantic.
    """
    _validate_conversion_event_type(event_type)
    now = _now()
    payload_json = json.dumps(payload) if payload is not None else None
    conn.execute(
        """
        INSERT INTO conversion_events
            (cvr, event_type, source, payload_json, occurred_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (cvr, event_type, source, payload_json, now, now),
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------


def _dispatch_action(
    conn: sqlite3.Connection,
    job_row: dict,
) -> dict:
    """Run the right action handler for ``job_row['action']``.

    For Sentinel-semantic actions (``anonymise`` and ``purge`` on a
    client whose plan was Sentinel) we wrap the action with the 7-row
    audit trail:

    - ``offboarding_triggered`` before the action (captures intent +
      timestamp).
    - ``authorisation_revoked`` after the action (captures final
      revocation — must land BEFORE the purge cascade touches
      conversion_events itself, hence inserted before the cascade even
      though semantically "after").

    All three INSERTs go through :func:`_emit_event_in_txn`, which does
    NOT commit. The runner's ``_mark_completed_in_txn`` + final
    ``conn.commit()`` commits the action mutations and the audit rows
    together. If the action raises, the runner rollback wipes everything
    — including the audit row — preserving forensic-trail integrity (no
    orphan ``offboarding_triggered`` for a job that never executed).

    For Watchman the audit trail lives via ``signup_tokens`` +
    ``signup`` conversion event (Q6) and we do not emit the 7-row rows.
    """
    action = job_row["action"]

    if action == "export":
        # B8: export requires a GDPR DSAR ADR. Not shipping in this PR.
        raise NotImplementedError("export deferred to GDPR DSAR ADR")

    if action == "anonymise":
        # Anonymise is Sentinel-only (Watchman has no anonymise stage
        # post-2026-04-24). Emit offboarding_triggered first, run the
        # action, then authorisation_revoked. All three writes share
        # the runner's commit; rollback on action failure clears them.
        _emit_event_in_txn(
            conn,
            cvr=job_row["cvr"],
            event_type="offboarding_triggered",
            source="retention_cron",
            payload={"job_id": job_row["id"], "action": action},
        )
        result = anonymise_client(conn, job_row)
        _emit_event_in_txn(
            conn,
            cvr=job_row["cvr"],
            event_type="authorisation_revoked",
            source="retention_cron",
            payload={"job_id": job_row["id"], "action": action},
        )
        return result

    if action == "purge":
        # offboarding_triggered before the cascade wipes everything. We
        # do NOT insert authorisation_revoked for purge because the
        # cascade deletes conversion_events wholesale and the audit row
        # would vanish in the same transaction — Q6 ruling was that
        # Watchman's audit is signup_tokens + signup, not the 7-row
        # trail. For Sentinel reaching purge (edge case) the
        # authorisation_revoked row was already written at the earlier
        # anonymise step.
        _emit_event_in_txn(
            conn,
            cvr=job_row["cvr"],
            event_type="offboarding_triggered",
            source="retention_cron",
            payload={"job_id": job_row["id"], "action": action},
        )
        return purge_client(conn, job_row)

    if action == "purge_bookkeeping":
        # Sentinel +5y. No consent row left to revoke; no audit-trail
        # row to emit — conversion_events for this CVR were deleted at
        # the earlier purge. Pure DB mutation.
        return purge_bookkeeping(conn, job_row)

    raise ValueError(f"Unknown retention action: {action!r}")


# ---------------------------------------------------------------------------
# Entry point: one tick
# ---------------------------------------------------------------------------


def tick(
    conn: sqlite3.Connection,
    *,
    alert_cb: AlertCallback | None = None,
    limit: int = 10,
    reap_timeout_seconds: int = 3600,
) -> int:
    """Run one retention cron tick. Returns number of jobs processed.

    Sequence:

    1. :func:`reap_stuck_running_jobs` — rescue crashed executors.
    2. :func:`claim_due_retention_jobs` — atomic claim of due rows.
    3. For each claimed row:
       a. Skip if CVR starts with ``DRYRUN-``.
       b. Dispatch to the action handler inside a single commit.
       c. On success, mark completed with row counts in ``notes``.
       d. On failure, parse previous attempt from notes, apply backoff
          (attempts 1-4) or terminal-fail + alert (attempt 5).

    Args:
        conn: Read-write SQLite connection. Dedicated to this tick;
            caller owns the connection lifecycle.
        alert_cb: Optional callback invoked on terminal failure with
            ``{cvr, action, scheduled_for, last_error, job_id}``. If
            omitted, terminal failures are only recorded in the DB
            (the scheduler daemon injects the Redis publisher).
        limit: Max jobs claimed per tick (default 10).
        reap_timeout_seconds: Claim age beyond which a ``running`` row
            is assumed crashed and demoted back to pending.

    Returns:
        Total number of jobs processed (completed + failed + skipped).
    """
    processed = 0

    # Step 1: reap. Stage A.5 spec §11.6: cron-path callers MUST stamp
    # config_changes rows with actor_kind='system' so forensic queries
    # can separate runner-driven from operator-driven retention writes.
    try:
        with bind_audit_context(
            conn, intent="retention.reap", actor_kind="system"
        ):
            reaped = reap_stuck_running_jobs(
                conn, timeout_seconds=reap_timeout_seconds
            )
        if reaped:
            logger.info("retention_reaped: {} stuck running row(s)", reaped)
    except Exception:
        # A reap failure is not fatal to the tick — the claim below can
        # still find recently-scheduled pending rows.
        logger.opt(exception=True).warning("retention_reap_failed")

    # Step 2: claim. The UPDATE retention_jobs SET status='running' fires
    # trg_retention_jobs_audit_update once per claimed row; each row
    # lands in config_changes with intent='retention.claim'.
    try:
        with bind_audit_context(
            conn, intent="retention.claim", actor_kind="system"
        ):
            claimed = claim_due_retention_jobs(conn, limit=limit)
    except Exception:
        logger.opt(exception=True).error("retention_claim_failed")
        return 0

    if not claimed:
        return 0

    # Step 3: dispatch
    for job in claimed:
        processed += 1
        cvr = job["cvr"]
        bound = logger.bind(cvr=cvr, job_id=job["id"], action=job["action"])

        # B7: skip DRYRUN-* CVRs.
        if cvr.startswith(DRYRUN_CVR_PREFIX):
            bound.info("retention_skip_dryrun")
            # Mark completed so the row does not get re-claimed next
            # tick; note the skip for auditability.
            with bind_audit_context(
                conn,
                intent="retention.dryrun_skip",
                actor_kind="system",
            ):
                conn.execute(
                    """
                    UPDATE retention_jobs
                       SET status = 'completed', executed_at = ?, notes = ?
                     WHERE id = ?
                    """,
                    (_now(), "skipped: DRYRUN cvr", job["id"]),
                )
                conn.commit()
            continue

        # Sibling-cascade / external-update guard: another claimed job in
        # the same tick may have cascaded a DELETE on this row (e.g. two
        # ``purge`` rows for the same CVR — the first purge_client wipes
        # ``retention_jobs`` siblings, taking this one with it), or an
        # external writer may have flipped the row to 'completed' /
        # 'cancelled' between the claim and this dispatch. Re-fetch and
        # confirm status='running' before doing any work; otherwise skip
        # silently (do NOT increment processed, do NOT alert).
        current = get_retention_job(conn, job["id"])
        if current is None or current.get("status") != "running":
            processed -= 1
            bound.bind(
                current_status=(current or {}).get("status")
            ).debug("retention_claim_no_longer_eligible")
            continue

        previous_attempt = _parse_attempt(job.get("notes"))

        # Each per-job run wraps under intent='retention.<action>' so
        # every config_changes row produced by the action handler
        # (clients UPDATE, consent_records UPDATE, signup_tokens DELETE,
        # client_domains DELETE, retention_jobs cascade DELETEs) carries
        # a uniform stamp for the whole logical step.
        action_intent = f"retention.{job['action']}"
        try:
            with bind_audit_context(
                conn, intent=action_intent, actor_kind="system"
            ):
                result = _dispatch_action(conn, job)
                _mark_completed_in_txn(
                    conn,
                    job_id=job["id"],
                    notes=f"ok: {json.dumps(result, default=str)[:500]}",
                )
                conn.commit()
            bound.bind(result=result).info("retention_job_completed")
        except NotImplementedError as exc:
            # Export path — terminal on first attempt, no retry loop
            # because retrying does not help (the code is not written).
            attempt = MAX_ATTEMPTS
            conn.rollback()
            with bind_audit_context(
                conn,
                intent="retention.terminal_fail",
                actor_kind="system",
            ):
                _reschedule_with_backoff(
                    conn, job_id=job["id"], attempt=attempt, error=str(exc)
                )
            bound.warning("retention_job_not_implemented: {}", exc)
            if alert_cb is not None:
                alert_cb(
                    {
                        "cvr": cvr,
                        "action": job["action"],
                        "job_id": job["id"],
                        "scheduled_for": job["scheduled_for"],
                        "last_error": str(exc),
                    }
                )
        except Exception as exc:
            attempt = previous_attempt + 1
            conn.rollback()
            # On the failure branch the original action_intent was rolled
            # back; the retention_jobs UPDATE that records the backoff /
            # terminal-fail attempt is its own separate write. Stamp it
            # with a distinct intent so post-incident greps can tell
            # "the action ran" from "the failure was logged".
            backoff_intent = (
                "retention.terminal_fail" if attempt >= MAX_ATTEMPTS
                else "retention.backoff"
            )
            with bind_audit_context(
                conn, intent=backoff_intent, actor_kind="system"
            ):
                terminal = _reschedule_with_backoff(
                    conn, job_id=job["id"], attempt=attempt, error=str(exc)
                )
            bound.bind(attempt=attempt).opt(exception=True).warning(
                "retention_job_failed"
            )
            if terminal and alert_cb is not None:
                alert_cb(
                    {
                        "cvr": cvr,
                        "action": job["action"],
                        "job_id": job["id"],
                        "scheduled_for": job["scheduled_for"],
                        "last_error": str(exc),
                    }
                )

    return processed
