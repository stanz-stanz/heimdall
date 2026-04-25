"""Subscription + payment-event helpers for Sentinel billing.

Two tables, one module:

- ``subscriptions`` — one row per Sentinel subscription period. Canonical
  source of truth for current billing state; status transitions preserved
  as history rather than mutated into ambiguity.
- ``payment_events`` — immutable, append-only log of every Betalingsservice
  event (mandate registration, debit success/failure, refunds, chargebacks).
  Refunds and reversals are recorded as new rows, never as updates.

Amounts are stored in **øre** (integer 1/100 DKK). Integer math avoids the
float precision pitfalls that show up in dunning + reconciliation. Callers
convert at the UI/composer layer.

See the 2026-04-23 entry in ``docs/decisions/log.md`` (D18 — Betalingsservice
direct debit) and the schema in ``docs/architecture/client-db-schema.sql``.
"""

from __future__ import annotations

import json
import sqlite3

from src.db.connection import _now

VALID_SUBSCRIPTION_STATUSES: set[str] = {
    "pending_payment",
    "active",
    "past_due",
    "cancelled",
    "refunded",
}

VALID_BILLING_PERIODS: set[str] = {"monthly", "annual"}

VALID_PAYMENT_EVENT_TYPES: set[str] = {
    "invoice_issued",
    "mandate_registered",
    "payment_succeeded",
    "payment_failed",
    "refund",
    "chargeback",
    "mandate_cancelled",
}


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


def _validate_subscription_status(status: str) -> None:
    if status not in VALID_SUBSCRIPTION_STATUSES:
        raise ValueError(
            f"Invalid subscription status {status!r}. "
            f"Must be one of: {sorted(VALID_SUBSCRIPTION_STATUSES)}"
        )


def _validate_billing_period(period: str) -> None:
    if period not in VALID_BILLING_PERIODS:
        raise ValueError(
            f"Invalid billing_period {period!r}. "
            f"Must be one of: {sorted(VALID_BILLING_PERIODS)}"
        )


def create_subscription(
    conn: sqlite3.Connection,
    cvr: str,
    amount_dkk_ore: int,
    *,
    plan: str = "sentinel",
    status: str = "pending_payment",
    billing_period: str = "monthly",
    started_at: str | None = None,
    current_period_end: str | None = None,
    invoice_ref: str | None = None,
    mandate_id: str | None = None,
) -> dict:
    """Insert a subscription row.

    Amount is an integer in øre to avoid float precision issues. 399 kr./mo
    is ``39900``; 339 kr./mo annual is ``33900``.

    Raises:
        ValueError: If ``status`` or ``billing_period`` are unknown, or
            ``amount_dkk_ore`` is not a positive integer.
    """
    if not isinstance(amount_dkk_ore, int) or amount_dkk_ore <= 0:
        raise ValueError(
            f"amount_dkk_ore must be a positive integer (øre), got {amount_dkk_ore!r}"
        )

    _validate_subscription_status(status)
    _validate_billing_period(billing_period)

    now = _now()
    started = started_at or now

    cursor = conn.execute(
        """
        INSERT INTO subscriptions
            (cvr, plan, status, started_at, current_period_end,
             invoice_ref, amount_dkk, billing_period, mandate_id,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cvr,
            plan,
            status,
            started,
            current_period_end,
            invoice_ref,
            amount_dkk_ore,
            billing_period,
            mandate_id,
            now,
            now,
        ),
    )
    conn.commit()

    return _get_subscription_by_id(conn, cursor.lastrowid)  # type: ignore[arg-type]


def update_subscription_status(
    conn: sqlite3.Connection,
    subscription_id: int,
    new_status: str,
    *,
    cancelled_at: str | None = None,
    current_period_end: str | None = None,
) -> dict:
    """Transition a subscription to ``new_status``.

    Caller is responsible for recording the corresponding payment_event
    (e.g. payment_failed → past_due transition is observable via both the
    event log and the subscription row's status field).

    Raises:
        ValueError: If ``new_status`` is unknown.
        KeyError: If ``subscription_id`` does not exist.
    """
    _validate_subscription_status(new_status)

    existing = _get_subscription_by_id(conn, subscription_id)
    if existing is None:
        raise KeyError(f"Subscription {subscription_id} not found")

    now = _now()
    conn.execute(
        """
        UPDATE subscriptions
           SET status = ?,
               cancelled_at = COALESCE(?, cancelled_at),
               current_period_end = COALESCE(?, current_period_end),
               updated_at = ?
         WHERE id = ?
        """,
        (new_status, cancelled_at, current_period_end, now, subscription_id),
    )
    conn.commit()

    return _get_subscription_by_id(conn, subscription_id)  # type: ignore[return-value]


def get_active_subscription(conn: sqlite3.Connection, cvr: str) -> dict | None:
    """Return the current ``active`` subscription for ``cvr``, or ``None``.

    If multiple active subscriptions exist (a data-integrity bug), returns
    the most recently started one. Does not itself repair the invariant.
    """
    row = conn.execute(
        """
        SELECT * FROM subscriptions
         WHERE cvr = ? AND status = 'active'
         ORDER BY started_at DESC
         LIMIT 1
        """,
        (cvr,),
    ).fetchone()
    return dict(row) if row else None


def list_subscriptions_by_cvr(
    conn: sqlite3.Connection, cvr: str
) -> list[dict]:
    """Full subscription history for ``cvr``, newest first."""
    rows = conn.execute(
        "SELECT * FROM subscriptions WHERE cvr = ? ORDER BY started_at DESC",
        (cvr,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_past_due(conn: sqlite3.Connection) -> list[dict]:
    """Subscriptions currently in ``past_due`` state.

    Used by the operator console (V3) and by the dunning scheduler.
    """
    rows = conn.execute(
        """
        SELECT * FROM subscriptions
         WHERE status = 'past_due'
         ORDER BY current_period_end ASC
        """,
    ).fetchall()
    return [dict(r) for r in rows]


def _get_subscription_by_id(
    conn: sqlite3.Connection, subscription_id: int
) -> dict | None:
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Payment events — immutable append log
# ---------------------------------------------------------------------------


def _validate_payment_event_type(event_type: str) -> None:
    if event_type not in VALID_PAYMENT_EVENT_TYPES:
        raise ValueError(
            f"Invalid payment event_type {event_type!r}. "
            f"Must be one of: {sorted(VALID_PAYMENT_EVENT_TYPES)}"
        )


def record_payment_event(
    conn: sqlite3.Connection,
    cvr: str,
    event_type: str,
    amount_dkk_ore: int,
    *,
    subscription_id: int | None = None,
    external_id: str | None = None,
    occurred_at: str | None = None,
    payload: dict | None = None,
) -> dict:
    """Append a payment event row.

    Raises:
        ValueError: If ``event_type`` is unknown, or ``amount_dkk_ore``
            is not an integer (negative permitted for refunds/chargebacks).
    """
    _validate_payment_event_type(event_type)
    if not isinstance(amount_dkk_ore, int):
        raise ValueError(
            f"amount_dkk_ore must be an integer (øre), got {amount_dkk_ore!r}"
        )

    now = _now()
    occurred = occurred_at or now
    payload_json = json.dumps(payload) if payload is not None else None

    cursor = conn.execute(
        """
        INSERT INTO payment_events
            (cvr, subscription_id, event_type, amount_dkk,
             external_id, occurred_at, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cvr,
            subscription_id,
            event_type,
            amount_dkk_ore,
            external_id,
            occurred,
            payload_json,
            now,
        ),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM payment_events WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    return dict(row)


def list_payment_events_for_cvr(
    conn: sqlite3.Connection, cvr: str, limit: int | None = None
) -> list[dict]:
    """Payment event log for ``cvr``, newest first."""
    sql = """
        SELECT * FROM payment_events
         WHERE cvr = ?
         ORDER BY occurred_at DESC
    """
    params: tuple = (cvr,)
    if limit is not None:
        sql += " LIMIT ?"
        params = (cvr, limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_payment_events_for_subscription(
    conn: sqlite3.Connection, subscription_id: int
) -> list[dict]:
    """Payment event log for a specific subscription, newest first."""
    rows = conn.execute(
        """
        SELECT * FROM payment_events
         WHERE subscription_id = ?
         ORDER BY occurred_at DESC
        """,
        (subscription_id,),
    ).fetchall()
    return [dict(r) for r in rows]
