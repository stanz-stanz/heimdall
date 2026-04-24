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
) -> dict:
    """Mark one Watchman trial expired and schedule its hard-purge.

    Args:
        conn: Database connection.
        cvr: CVR of the client to expire.
        now: ISO-8601 UTC override (used by the sweep helper to keep
            a single sweep self-consistent). Defaults to live clock.

    Returns:
        The updated client row. ``status`` is ``'watchman_expired'``
        and ``data_retention_mode`` is ``'purge_scheduled'``.

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

    # Step 1: flip status. The retention schedule in step 2 will own
    # the data_retention_mode / churn_purge_at fields.
    conn.execute(
        "UPDATE clients SET status = 'watchman_expired', updated_at = ? WHERE cvr = ?",
        (when, cvr),
    )
    conn.commit()

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

    logger.bind(
        cvr=cvr,
        anchor=anchor,
        retention_job_id=jobs[0]["id"],
    ).info("watchman_trial_expired")

    return get_client(conn, cvr)  # type: ignore[return-value]


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
        try:
            expire_watchman_trial(conn, cvr, now=when)
            count += 1
        except Exception as exc:  # noqa: BLE001 — sweep must not abort on one row
            logger.bind(cvr=cvr).error(
                "trial_expiry_failed: {}", exc
            )
    return count
