"""Retention-job helpers for GDPR-aligned offboarding.

Tiered retention policy (D16, 2026-04-23, revised 2026-04-24):

- **Watchman non-converter**: hard-purge at the anchor (trial-expiry
  timestamp). No anonymise stage — a free trial retains nothing past
  expiry. The next cron tick claims and executes the purge.
- **Sentinel cancelled**: anonymise at anchor + 30 days, then a
  separate ``purge_bookkeeping`` job at anchor + 5 years for
  ``subscriptions`` + ``payment_events`` only (Bogføringsloven 5-year
  invoice retention).

:func:`schedule_churn_retention` is the canonical entry point; it
schedules the plan-appropriate jobs, flips
``clients.data_retention_mode`` to ``'purge_scheduled'``, and stamps
``clients.churn_purge_at`` with the final scheduled date for operator
console visibility.

A cron / scheduler picks up rows via :func:`list_due_retention_jobs`,
executes the action, and marks completion via
:func:`mark_retention_job_completed` / :func:`mark_retention_job_failed`.

See the 2026-04-23 entry in ``docs/decisions/log.md`` and the schema in
``docs/architecture/client-db-schema.sql``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from src.db.clients import get_client
from src.db.connection import _now

VALID_RETENTION_ACTIONS: set[str] = {
    "anonymise",
    "purge",
    # Bogføringsloven 5-year bookkeeping purge for Sentinel — runs against
    # subscriptions + payment_events only, after all other retention is done.
    "purge_bookkeeping",
    "export",
}

VALID_RETENTION_JOB_STATUSES: set[str] = {
    "pending",
    # 'running' is claimed by the executor; see claim_due_retention_jobs.
    # A startup reaper moves long-stuck 'running' rows back to 'pending'.
    "running",
    "completed",
    "failed",
    "cancelled",
}

VALID_DATA_RETENTION_MODES: set[str] = {
    "standard",
    "anonymised",
    "purge_scheduled",
    "purged",
}

# Tiered retention windows, in days from the churn anchor.
#
# Watchman has no constant here: a free trial retains no data past the
# trial-expiry anchor. The purge runs at the anchor (scheduled_for =
# anchor), claimed by the next cron tick.
SENTINEL_ANONYMISE_DAYS = 30
# Bogføringsloven: Danish bookkeeping law requires retention of invoice
# records for five years after the end of the financial year they belong
# to. We approximate "end of financial year + 5y" as anchor + 5 × 365 d;
# this is conservative (the real boundary is later, not sooner, so the
# delete is always after the legal minimum).
SENTINEL_BOOKKEEPING_PURGE_DAYS = 5 * 365


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_action(action: str) -> None:
    if action not in VALID_RETENTION_ACTIONS:
        raise ValueError(
            f"Invalid retention action {action!r}. "
            f"Must be one of: {sorted(VALID_RETENTION_ACTIONS)}"
        )


def _validate_status(status: str) -> None:
    if status not in VALID_RETENTION_JOB_STATUSES:
        raise ValueError(
            f"Invalid retention job status {status!r}. "
            f"Must be one of: {sorted(VALID_RETENTION_JOB_STATUSES)}"
        )


def _validate_mode(mode: str) -> None:
    if mode not in VALID_DATA_RETENTION_MODES:
        raise ValueError(
            f"Invalid data_retention_mode {mode!r}. "
            f"Must be one of: {sorted(VALID_DATA_RETENTION_MODES)}"
        )


# ---------------------------------------------------------------------------
# Low-level CRUD
# ---------------------------------------------------------------------------


def schedule_retention_job(
    conn: sqlite3.Connection,
    cvr: str,
    action: str,
    scheduled_for: str,
    *,
    notes: str | None = None,
) -> dict:
    """Insert a single retention job row.

    Args:
        conn: Database connection.
        cvr: Client CVR.
        action: One of :data:`VALID_RETENTION_ACTIONS`.
        scheduled_for: ISO-8601 UTC timestamp when the job should execute.
        notes: Optional free-text context (e.g. ``"watchman non-converter"``).

    Raises:
        ValueError: If ``action`` is not recognised.
    """
    _validate_action(action)

    now = _now()
    cursor = conn.execute(
        """
        INSERT INTO retention_jobs
            (cvr, action, scheduled_for, status, notes, created_at)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (cvr, action, scheduled_for, notes, now),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM retention_jobs WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def list_due_retention_jobs(
    conn: sqlite3.Connection,
    now: str | None = None,
) -> list[dict]:
    """Pending retention jobs whose ``scheduled_for`` is on or before ``now``.

    Ordered by ``scheduled_for`` ascending so the oldest overdue runs
    first. The cron / scheduler should claim jobs in this order.
    """
    when = now or _now()
    rows = conn.execute(
        """
        SELECT * FROM retention_jobs
         WHERE status = 'pending' AND scheduled_for <= ?
         ORDER BY scheduled_for ASC, id ASC
        """,
        (when,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_retention_jobs_for_cvr(
    conn: sqlite3.Connection, cvr: str
) -> list[dict]:
    """All retention jobs for ``cvr``, soonest first."""
    rows = conn.execute(
        """
        SELECT * FROM retention_jobs
         WHERE cvr = ?
         ORDER BY scheduled_for ASC, id ASC
        """,
        (cvr,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_retention_job(
    conn: sqlite3.Connection, job_id: int
) -> dict | None:
    row = conn.execute(
        "SELECT * FROM retention_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    return dict(row) if row else None


def mark_retention_job_completed(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    notes: str | None = None,
) -> dict:
    """Transition a job from ``pending`` to ``completed``.

    Stamps ``executed_at``. Optionally overwrites ``notes``.

    Raises:
        KeyError: If the job does not exist.
    """
    job = get_retention_job(conn, job_id)
    if job is None:
        raise KeyError(f"Retention job {job_id} not found")

    now = _now()
    if notes is not None:
        conn.execute(
            """
            UPDATE retention_jobs
               SET status = 'completed', executed_at = ?, notes = ?
             WHERE id = ?
            """,
            (now, notes, job_id),
        )
    else:
        conn.execute(
            """
            UPDATE retention_jobs
               SET status = 'completed', executed_at = ?
             WHERE id = ?
            """,
            (now, job_id),
        )
    conn.commit()
    return get_retention_job(conn, job_id)  # type: ignore[return-value]


def mark_retention_job_failed(
    conn: sqlite3.Connection,
    job_id: int,
    error: str,
) -> dict:
    """Transition a job from ``pending`` to ``failed`` with an error note.

    Raises:
        KeyError: If the job does not exist.
    """
    job = get_retention_job(conn, job_id)
    if job is None:
        raise KeyError(f"Retention job {job_id} not found")

    now = _now()
    conn.execute(
        """
        UPDATE retention_jobs
           SET status = 'failed', executed_at = ?, notes = ?
         WHERE id = ?
        """,
        (now, error, job_id),
    )
    conn.commit()
    return get_retention_job(conn, job_id)  # type: ignore[return-value]


def cancel_retention_job(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    notes: str | None = None,
) -> dict:
    """Cancel a pending retention job (e.g. client re-activates)."""
    job = get_retention_job(conn, job_id)
    if job is None:
        raise KeyError(f"Retention job {job_id} not found")

    now = _now()
    if notes is not None:
        conn.execute(
            """
            UPDATE retention_jobs
               SET status = 'cancelled', executed_at = ?, notes = ?
             WHERE id = ?
            """,
            (now, notes, job_id),
        )
    else:
        conn.execute(
            """
            UPDATE retention_jobs
               SET status = 'cancelled', executed_at = ?
             WHERE id = ?
            """,
            (now, job_id),
        )
    conn.commit()
    return get_retention_job(conn, job_id)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Client-level retention mode
# ---------------------------------------------------------------------------


def set_data_retention_mode(
    conn: sqlite3.Connection,
    cvr: str,
    mode: str,
    *,
    churn_purge_at: str | None = None,
) -> dict:
    """Set ``clients.data_retention_mode`` (and optionally ``churn_purge_at``).

    Raises:
        ValueError: If ``mode`` is not recognised.
        KeyError: If the client does not exist.
    """
    _validate_mode(mode)

    client = get_client(conn, cvr)
    if client is None:
        raise KeyError(f"Client with CVR {cvr!r} not found")

    now = _now()
    if churn_purge_at is not None:
        conn.execute(
            """
            UPDATE clients
               SET data_retention_mode = ?,
                   churn_purge_at = ?,
                   updated_at = ?
             WHERE cvr = ?
            """,
            (mode, churn_purge_at, now, cvr),
        )
    else:
        conn.execute(
            """
            UPDATE clients
               SET data_retention_mode = ?,
                   updated_at = ?
             WHERE cvr = ?
            """,
            (mode, now, cvr),
        )
    conn.commit()
    return get_client(conn, cvr)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Plan-aware churn scheduling (D16)
# ---------------------------------------------------------------------------


def _iso_plus_days(anchor_iso: str, days: int) -> str:
    """Add ``days`` to ``anchor_iso`` (ISO-8601 UTC) and return ISO-8601 UTC."""
    # Accept either "YYYY-MM-DDTHH:MM:SSZ" or ISO-8601 with an explicit offset.
    if anchor_iso.endswith("Z"):
        dt = datetime.strptime(anchor_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    else:
        dt = datetime.fromisoformat(anchor_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    shifted = dt + timedelta(days=days)
    return shifted.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def schedule_churn_retention(
    conn: sqlite3.Connection,
    cvr: str,
    plan: str,
    *,
    anchor_at: str | None = None,
    churn_reason: str | None = None,
) -> list[dict]:
    """Schedule the plan-appropriate retention jobs for a churning client.

    Watchman non-converter → one job:
        - purge at the anchor (trial-expiry timestamp)
      A free trial retains nothing. The purge claims on the next tick
      and hard-deletes every row attached to the CVR (clients row
      included — no tombstone). Only the ``retention_jobs`` audit row
      itself survives.

    Sentinel cancelled → two jobs:
        - anonymise        at anchor + 30 days
        - purge_bookkeeping at anchor + 5 years (subscriptions +
          payment_events only, Bogføringsloven invoice retention).

    Also:
        - Flips ``clients.data_retention_mode`` to ``'purge_scheduled'``
          (for Watchman) or ``'purge_scheduled'`` (for Sentinel — same
          marker; the actual purge horizon is Sentinel's 30d anonymise).
        - Stamps ``clients.churn_purge_at`` with the latest scheduled
          job's date so the operator console's retention queue (V6) can
          show a single "when does this fully drop off" timestamp.
        - Stamps ``clients.churn_requested_at`` with ``anchor_at`` and
          ``clients.churn_reason`` if provided.

    Args:
        conn: Database connection.
        cvr: Client CVR.
        plan: ``'watchman'`` or ``'sentinel'``. The caller is responsible
            for choosing the right tier — for example, a Sentinel client
            who cancels during a trial extension should use ``'sentinel'``.
        anchor_at: ISO-8601 UTC anchor for the retention timeline.
            Typically the cancellation (Sentinel) or trial-expiry
            (Watchman) timestamp. Defaults to now.
        churn_reason: Optional free-text reason, stamped onto
            ``clients.churn_reason``.

    Returns:
        List of scheduled ``retention_jobs`` rows (newest action last —
        anonymise first, then purge for Watchman).

    Raises:
        ValueError: If ``plan`` is not ``'watchman'`` or ``'sentinel'``.
        KeyError: If the client does not exist.
    """
    if plan not in ("watchman", "sentinel"):
        raise ValueError(
            f"Invalid plan {plan!r} for churn retention. Must be 'watchman' or 'sentinel'."
        )

    client = get_client(conn, cvr)
    if client is None:
        raise KeyError(f"Client with CVR {cvr!r} not found")

    anchor = anchor_at or _now()

    jobs: list[dict] = []
    if plan == "watchman":
        jobs.append(
            schedule_retention_job(
                conn,
                cvr,
                "purge",
                anchor,
                notes="watchman non-converter — immediate hard purge "
                "(no anonymise stage; free trial retains no data)",
            )
        )
    else:  # sentinel
        jobs.append(
            schedule_retention_job(
                conn,
                cvr,
                "anonymise",
                _iso_plus_days(anchor, SENTINEL_ANONYMISE_DAYS),
                notes="sentinel cancelled — anonymise PII "
                "(invoice records retained 5y per Bogføringsloven)",
            )
        )
        # B2: schedule the 5-year bookkeeping purge upfront so it appears
        # immediately in operator console V6. The dispatcher handles
        # subscriptions + payment_events rows at that horizon.
        jobs.append(
            schedule_retention_job(
                conn,
                cvr,
                "purge_bookkeeping",
                _iso_plus_days(anchor, SENTINEL_BOOKKEEPING_PURGE_DAYS),
                notes="sentinel cancelled — Bogføringsloven 5y window: "
                "purge subscriptions + payment_events",
            )
        )

    # The last scheduled job drives churn_purge_at.
    final_scheduled_for = jobs[-1]["scheduled_for"]

    now = _now()
    conn.execute(
        """
        UPDATE clients
           SET data_retention_mode = 'purge_scheduled',
               churn_purge_at = ?,
               churn_requested_at = COALESCE(churn_requested_at, ?),
               churn_reason = COALESCE(?, churn_reason),
               updated_at = ?
         WHERE cvr = ?
        """,
        (final_scheduled_for, anchor, churn_reason, now, cvr),
    )
    conn.commit()

    return jobs
