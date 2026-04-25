"""Watchman trial-expiry scanner.

Called periodically (typically from the scheduler daemon on a 5-min
cadence) to detect clients whose Watchman trial has elapsed. Each
expired trial is transitioned to ``status='watchman_expired'`` and
handed to the retention cron via :func:`schedule_churn_retention` —
which, for Watchman, schedules a single immediate ``purge`` job
(revised 2026-04-24: free trial retains no data past expiry).

This module only *schedules* retention; it never deletes anything
itself. The retention runner in ``src/retention/runner.py`` claims the
job and performs the hard-delete cascade.

State transitions:

- ``watchman_active`` + ``trial_expires_at <= now()`` →
  ``watchman_expired`` + retention job scheduled at the trial anchor.

Clients already in any other status are left alone — the scanner is
conservative and idempotent, so a crash mid-sweep is safe to re-run.

Atomicity note: the status flip and the retention schedule happen
under two separate commits. A crash between them leaves a
``watchman_expired`` row with no pending retention job; a startup
reconciler (future work) should catch that drift. The window is
millisecond-scale and the reconciler is cheap.

See ``project_retention_cron_decisions.md`` (memory) and the revised
D16 banner on ``docs/architecture/retention-cron-options.md``.
"""

from __future__ import annotations

import sqlite3

from loguru import logger

from src.db.clients import get_client
from src.db.connection import _now
from src.db.retention import schedule_churn_retention

_EXPIRY_CHURN_REASON = "watchman trial expired without conversion"

# Mirrors ``src/retention/runner.DRYRUN_CVR_PREFIX``. Synthetic targets
# from dev dry-run scripts (``scripts/dev/cert_change_dry_run.py`` and
# friends) must never have their state machine touched by real production
# sweeps — re-declared locally to keep this module dependency-free.
_DRYRUN_CVR_PREFIX = "DRYRUN-"


def find_expired_trials(
    conn: sqlite3.Connection,
    now: str | None = None,
) -> list[dict]:
    """Clients in ``watchman_active`` whose ``trial_expires_at <= now``.

    Returned oldest-first (smallest ``trial_expires_at`` first) so the
    sweep clears the most overdue trials before newer ones. Uses the
    ``idx_clients_trial_expires`` partial index.
    """
    when = now or _now()
    rows = conn.execute(
        """
        SELECT * FROM clients
         WHERE status = 'watchman_active'
           AND trial_expires_at IS NOT NULL
           AND trial_expires_at <= ?
         ORDER BY trial_expires_at ASC
        """,
        (when,),
    ).fetchall()
    return [dict(r) for r in rows]


def expire_watchman_trial(
    conn: sqlite3.Connection,
    cvr: str,
    *,
    now: str | None = None,
) -> tuple[dict, bool]:
    """Mark one Watchman trial expired and schedule its hard-purge.

    Args:
        conn: Database connection.
        cvr: CVR of the client to expire.
        now: ISO-8601 UTC override (used by the sweep helper to keep
            a single sweep self-consistent). Defaults to live clock.

    Returns:
        ``(client_row, transitioned)``. ``client_row`` is the current
        DB state for the CVR after the call (post-CAS re-read).
        ``transitioned`` is ``True`` only when *this* call performed
        the ``watchman_active → watchman_expired`` flip (CAS UPDATE
        rowcount == 1). It is ``False`` when the CAS lost to a
        concurrent writer (rowcount == 0) — even if the row's status
        is now ``'watchman_expired'`` because another worker won the
        race. Callers must rely on ``transitioned`` for accounting,
        not on the row's status, to avoid double-counting concurrent
        sweeps.

    Raises:
        KeyError: If the client does not exist.
        ValueError: If the client is not in ``watchman_active`` — the
            scanner refuses to expire anything else to avoid racing
            the onboarding state machine (prospect / onboarding /
            active / paused / churned transitions are owned elsewhere).
    """
    when = now or _now()

    client = get_client(conn, cvr)
    if client is None:
        raise KeyError(f"Client with CVR {cvr!r} not found")

    if client["status"] != "watchman_active":
        raise ValueError(
            f"Client {cvr!r} is in status {client['status']!r}; "
            "expire_watchman_trial only transitions from 'watchman_active'"
        )

    # Step 1: flip status. The ``AND status = 'watchman_active'`` guard
    # turns the UPDATE into a compare-and-swap so a concurrent writer
    # (e.g. Sentinel conversion) flipping ``status`` between our SELECT
    # above and this UPDATE cannot be silently overwritten — instead we
    # observe rowcount=0 and bail without scheduling a purge.
    cursor = conn.execute(
        "UPDATE clients SET status = 'watchman_expired', updated_at = ? "
        "WHERE cvr = ? AND status = 'watchman_active'",
        (when, cvr),
    )
    conn.commit()

    if cursor.rowcount == 0:
        # Status was changed under us — abort. Do NOT call
        # schedule_churn_retention; the new owner of the row decides
        # retention. The sweep's per-row try/except handles this as a
        # non-fatal outcome.
        logger.bind(context={
            "cvr": cvr,
            "stale_status": client["status"],
        }).warning("trial_expiry_raced")
        # Defensive: get_client should not return None here — the row
        # existed at the SELECT above and nothing in this codepath
        # deletes clients rows. If it somehow does, treat as race-loss
        # and return the stale snapshot we already have.
        current = get_client(conn, cvr)
        return (current if current is not None else client), False

    # Step 2: schedule the immediate purge anchored at the trial-expiry
    # timestamp (or, if that's somehow NULL, the sweep's ``now``). The
    # retention runner picks it up on the next tick and hard-deletes
    # every row attached to this CVR.
    anchor = client.get("trial_expires_at") or when
    jobs = schedule_churn_retention(
        conn,
        cvr,
        plan="watchman",
        anchor_at=anchor,
        churn_reason=_EXPIRY_CHURN_REASON,
    )

    logger.bind(context={
        "cvr": cvr,
        "anchor": anchor,
        "retention_job_id": jobs[0]["id"],
    }).info("watchman_trial_expired")

    return get_client(conn, cvr), True  # type: ignore[return-value]


def run_trial_expiry_sweep(
    conn: sqlite3.Connection,
    now: str | None = None,
) -> int:
    """Expire every Watchman trial whose clock has run out.

    Returns the count of trials transitioned this sweep. Failures on
    individual clients are logged and skipped — a single bad row does
    not stop the sweep.
    """
    when = now or _now()
    expired = find_expired_trials(conn, now=when)
    count = 0
    for client in expired:
        cvr = client["cvr"]
        # Skip synthetic dry-run CVRs so dev fixtures left behind in the
        # DB never ride the production state-machine. Mirrors the same
        # B7-default-lean behaviour in src/retention/runner.py.
        if cvr.startswith(_DRYRUN_CVR_PREFIX):
            logger.bind(context={"cvr": cvr}).debug("trial_expiry_skip_dryrun")
            continue
        try:
            result_client, transitioned = expire_watchman_trial(
                conn, cvr, now=when
            )
            # Only count actual transitions. ``transitioned`` is True
            # only when this worker's CAS UPDATE succeeded (rowcount==1).
            # The status-based check is unsafe in the concurrent-worker
            # case: another worker may have already flipped the row to
            # 'watchman_expired' before our re-read, which would make a
            # status check spuriously count this no-op as a local success.
            if transitioned:
                count += 1
            else:
                logger.bind(context={
                    "cvr": cvr,
                    "stale_status": result_client["status"],
                }).debug("trial_expiry_sweep_raced")
        except Exception as exc:  # noqa: BLE001 — sweep must not abort on one row
            logger.bind(context={"cvr": cvr}).error(
                "trial_expiry_failed: {}", exc
            )
    return count


def reconcile_watchman_expired_orphans(
    conn: sqlite3.Connection,
    now: str | None = None,
) -> int:
    """Recover any ``watchman_expired`` clients with no retention job.

    :func:`expire_watchman_trial` flips the status and schedules the
    retention job under two separate commits. If the process crashes
    between them — or if an operator sets ``status='watchman_expired'``
    manually — the client is stuck: the purge will never fire.

    This reconciler finds every ``watchman_expired`` row on the
    ``watchman`` plan that has no ``purge`` / ``purge_bookkeeping``
    retention job in any non-terminal state (pending / running) or
    completed state, and schedules the missing purge at the trial-expiry
    anchor.

    Returns the count of orphans reconciled this run. Intended to be
    called once at scheduler-daemon startup, before the trial-expiry
    sweep begins its regular cadence.
    """
    when = now or _now()
    orphans = conn.execute(
        """
        SELECT c.cvr, c.trial_expires_at
          FROM clients c
         WHERE c.status = 'watchman_expired'
           AND c.plan = 'watchman'
           AND NOT EXISTS (
               SELECT 1 FROM retention_jobs r
                WHERE r.cvr = c.cvr
                  AND r.action IN ('purge', 'purge_bookkeeping')
                  AND r.status IN ('pending', 'running', 'completed')
           )
        """,
    ).fetchall()

    count = 0
    for row in orphans:
        cvr = row["cvr"]
        anchor = row["trial_expires_at"] or when
        try:
            jobs = schedule_churn_retention(
                conn,
                cvr,
                plan="watchman",
                anchor_at=anchor,
                churn_reason=f"reconciled — {_EXPIRY_CHURN_REASON}",
            )
            logger.bind(context={
                "cvr": cvr,
                "retention_job_id": jobs[0]["id"],
            }).warning("watchman_expired_orphan_reconciled")
            count += 1
        except Exception as exc:  # noqa: BLE001 — don't abort startup on one row
            logger.bind(context={"cvr": cvr}).error(
                "watchman_expired_reconcile_failed: {}", exc
            )
    return count
