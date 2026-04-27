"""Read-only operator-console queries.

The operator console serves a handful of specialised list views (the
"V1–V6" set defined in the 2026-04-23 onboarding plan). Each view is a
SELECT that joins ``clients`` with one or more secondary tables. They
live here, separate from per-table CRUD modules, for two reasons:

1. **Separation of concerns.** The console is a consumer; ``src/db/clients.py``
   and friends are the canonical CRUD surface. Centralising joins here
   keeps them out of write-path modules.
2. **Single review surface.** Operator-facing reads benefit from being
   reviewed together — they share invariants (only show CVRs the
   operator can act on, hide already-completed work).

Views currently implemented:

- :func:`list_trial_expiring` — V1 (Watchman trials within a window).
- :func:`list_retention_queue_pending_due` — V6 (retention jobs the cron
  is about to claim).

V2–V5 land here when the Betalingsservice webhook + onboarding-stage
log writers are wired (M42 slice 2+).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from src.db.connection import _now
from src.db.conversion import SENTINEL_CONVERSION_INTENT_EVENTS


def _iso_plus_days(anchor_iso: str, days: int) -> str:
    """``anchor_iso + days``, returned as ISO-8601 UTC ``Z``-suffixed.

    Mirrors the helper in ``src/db/retention.py``; kept private here so
    the module has no cross-DB import other than the conversion-event
    constant.
    """
    if anchor_iso.endswith("Z"):
        dt = datetime.strptime(anchor_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    else:
        dt = datetime.fromisoformat(anchor_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    shifted = dt + timedelta(days=days)
    return shifted.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_trial_expiring(
    conn: sqlite3.Connection,
    *,
    window_days: int = 7,
    now: str | None = None,
) -> list[dict]:
    """Watchman trials about to expire with no Sentinel-conversion engagement.

    Strict spec from the 2026-04-23 plan (V1):

        ``status='watchman_active'``
        AND ``trial_expires_at`` ∈ ``[now, now + window_days]``
        AND no ``conversion_events`` row exists for the CVR with an
        event_type in :data:`SENTINEL_CONVERSION_INTENT_EVENTS`.

    Returns operator-actionable rows ordered by ``trial_expires_at`` ASC
    (most urgent first). Each row joins ``client_domains`` (primary
    domain, if any) and computes ``days_remaining`` server-side as a
    whole-day floor so the UI does not need to deal with timezones.

    Args:
        conn: Database connection.
        window_days: Look-ahead horizon. Default 7 — matches the V1 spec
            in ``~/.claude/plans/i-need-you-to-logical-pebble.md``.
            Values <1 return an empty list (no past horizon).
        now: ISO-8601 UTC; defaults to server clock.

    Returns:
        ``list[dict]`` with keys: ``cvr``, ``company_name``, ``domain``,
        ``trial_started_at``, ``trial_expires_at``, ``telegram_chat_id``,
        ``signup_source``, ``days_remaining``.
    """
    if window_days < 1:
        return []

    when = now or _now()
    horizon = _iso_plus_days(when, window_days)

    # Inline the constant as a static literal — never user-supplied — so
    # the IN (...) expansion has no injection surface. The frozenset is
    # sorted for deterministic SQL across runs (helps with EXPLAIN diffs).
    intent_literal = ", ".join(
        f"'{ev}'" for ev in sorted(SENTINEL_CONVERSION_INTENT_EVENTS)
    )

    # The schema does not enforce single-primary per CVR (add_domain
    # defaults to is_primary=1, so a misuse can leave two rows tagged
    # primary). Collapse via subquery + MIN(domain) to keep one row per
    # CVR and a deterministic pick on duplicates.
    rows = conn.execute(
        f"""
        SELECT c.cvr,
               c.company_name,
               cd.domain,
               c.trial_started_at,
               c.trial_expires_at,
               c.telegram_chat_id,
               c.signup_source,
               CAST(julianday(c.trial_expires_at) - julianday(?) AS INTEGER)
                   AS days_remaining
          FROM clients c
          LEFT JOIN (
              SELECT cvr, MIN(domain) AS domain
                FROM client_domains
               WHERE is_primary = 1
               GROUP BY cvr
          ) cd ON cd.cvr = c.cvr
         WHERE c.status = 'watchman_active'
           AND c.trial_expires_at IS NOT NULL
           AND c.trial_expires_at >= ?
           AND c.trial_expires_at <= ?
           AND NOT EXISTS (
               SELECT 1 FROM conversion_events e
                WHERE e.cvr = c.cvr
                  AND e.event_type IN ({intent_literal})
           )
         ORDER BY c.trial_expires_at ASC
        """,
        (when, when, horizon),
    ).fetchall()
    return [dict(r) for r in rows]


def list_retention_queue_pending_due(
    conn: sqlite3.Connection,
    *,
    now: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """Retention jobs the cron is about to claim (V6).

    Strict spec: ``status='pending' AND scheduled_for <= now``. Joined
    LEFT against ``clients`` and ``client_domains`` because a Watchman
    purge can target a CVR whose row was already hard-deleted on a
    previous tick — operator still needs visibility on the audit row.

    Ordered by ``scheduled_for`` ASC, ``id`` ASC (oldest overdue first
    — the same order the cron's :func:`claim_due_retention_jobs` uses).

    Args:
        conn: Database connection.
        now: ISO-8601 UTC; defaults to server clock.
        limit: Max rows to return. Default 200.
        offset: Pagination offset.

    Returns:
        ``list[dict]`` with keys: ``id``, ``cvr``, ``company_name``,
        ``domain``, ``action``, ``scheduled_for``, ``claimed_at``,
        ``status``, ``notes``, ``created_at``.
    """
    when = now or _now()
    # See list_trial_expiring for the rationale on the domain subquery
    # (multi-primary rows can fan out without it).
    rows = conn.execute(
        """
        SELECT r.id,
               r.cvr,
               c.company_name,
               cd.domain,
               r.action,
               r.scheduled_for,
               r.claimed_at,
               r.status,
               r.notes,
               r.created_at
          FROM retention_jobs r
          LEFT JOIN clients c ON r.cvr = c.cvr
          LEFT JOIN (
              SELECT cvr, MIN(domain) AS domain
                FROM client_domains
               WHERE is_primary = 1
               GROUP BY cvr
          ) cd ON cd.cvr = r.cvr
         WHERE r.status = 'pending'
           AND r.scheduled_for <= ?
         ORDER BY r.scheduled_for ASC, r.id ASC
         LIMIT ? OFFSET ?
        """,
        (when, limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]
