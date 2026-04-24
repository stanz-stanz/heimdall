"""Signup → Watchman-trial activation wiring.

This is the hinge between two layers:

- :mod:`src.db.signup` manages the magic-link token (issuance, single-use
  consumption, TTL cleanup).
- :mod:`src.db.clients` manages the client row lifecycle.

:func:`activate_watchman_trial` is the atomic bridge. Given a valid
token and a fresh Telegram ``chat_id``, it:

1. Consumes the signup token (single-use, TTL-checked, fails closed).
2. Upserts the client row to ``status='watchman_active'``,
   ``plan='watchman'``, with trial window + bound chat_id + signup
   provenance.
3. Appends a ``conversion_events`` row of type ``'signup'`` so the
   funnel dashboard (V5) can count conversions.

All three writes live in a single SQLite transaction — if any step
fails the token remains unconsumed, so the prospect can retry with the
same magic link.

See the 2026-04-23 entry in ``docs/decisions/log.md`` (D15 — magic-link
signup; D17 — Watchman trial window 30d).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from src.db.connection import _now

# Watchman free-trial window in days. Matches the copy in Message 0
# (magic link): "30-day free trial". Update in one place.
WATCHMAN_TRIAL_DAYS = 30


class InvalidSignupToken(ValueError):
    """Raised when a token is unknown, expired, or already consumed.

    Callers (Telegram bot ``/start`` handler, operator console) should
    catch this and render the appropriate user-visible message — the
    token contents are never reflected back in the error.
    """


def _compute_trial_window(started_at: str) -> str:
    """Return ``started_at + WATCHMAN_TRIAL_DAYS`` as ISO-8601 UTC."""
    started = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    expires = started + timedelta(days=WATCHMAN_TRIAL_DAYS)
    return expires.strftime("%Y-%m-%dT%H:%M:%SZ")


def activate_watchman_trial(
    conn: sqlite3.Connection,
    token: str,
    telegram_chat_id: str,
    *,
    company_name: str | None = None,
) -> dict:
    """Consume ``token`` and activate a Watchman trial for the bound CVR.

    The entire operation is atomic: token consumption, client upsert,
    and conversion event are committed together.

    Args:
        conn: Database connection.
        token: URL-safe magic-link token from Message 0.
        telegram_chat_id: The ``chat_id`` captured from Telegram's
            ``/start`` webhook. Bound to the client so subsequent
            deliveries route correctly.
        company_name: Required only when the client does not yet exist
            in ``clients``. Prospects promoted through the outreach
            pipeline normally do have a row; operator-initiated signups
            for unpromoted CVRs need this.

    Returns:
        The activated client row as a dict.

    Raises:
        InvalidSignupToken: Token is unknown, already consumed, or
            expired. ``consumed_at`` is *not* set so the prospect can
            request a fresh token.
        ValueError: The CVR does not yet have a client row and
            ``company_name`` was not supplied.
    """
    now = _now()
    trial_expires_at = _compute_trial_window(now)

    try:
        # Open an immediate-mode transaction so the token consumption
        # and the client upsert serialize against concurrent /start
        # handlers for the same CVR.
        conn.execute("BEGIN IMMEDIATE")

        # 1. Consume the token atomically. The predicate enforces
        #    single-use + TTL in SQL — two concurrent activations can
        #    never both win.
        cursor = conn.execute(
            """
            UPDATE signup_tokens
               SET consumed_at = ?
             WHERE token = ?
               AND consumed_at IS NULL
               AND expires_at > ?
            """,
            (now, token, now),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            raise InvalidSignupToken(
                "Signup token is unknown, already consumed, or expired"
            )

        # 2. Resolve token → CVR + source provenance.
        token_row = conn.execute(
            "SELECT cvr, source FROM signup_tokens WHERE token = ?", (token,)
        ).fetchone()
        assert token_row is not None  # consume just succeeded
        cvr = token_row["cvr"]
        signup_source = token_row["source"]

        # 3. Decide create-vs-update without a second round-trip: try the
        #    update first, and only INSERT if nothing was updated.
        update_cursor = conn.execute(
            """
            UPDATE clients
               SET status = 'watchman_active',
                   plan = 'watchman',
                   telegram_chat_id = ?,
                   signup_source = ?,
                   trial_started_at = ?,
                   trial_expires_at = ?,
                   onboarding_stage = NULL,
                   updated_at = ?
             WHERE cvr = ?
            """,
            (telegram_chat_id, signup_source, now, trial_expires_at, now, cvr),
        )

        if update_cursor.rowcount == 0:
            if not company_name:
                conn.rollback()
                raise ValueError(
                    f"Client with CVR {cvr!r} does not exist and "
                    "company_name was not supplied"
                )
            conn.execute(
                """
                INSERT INTO clients (
                    cvr, company_name, status, plan,
                    telegram_chat_id, signup_source,
                    trial_started_at, trial_expires_at,
                    created_at, updated_at
                ) VALUES (?, ?, 'watchman_active', 'watchman',
                          ?, ?, ?, ?, ?, ?)
                """,
                (
                    cvr,
                    company_name,
                    telegram_chat_id,
                    signup_source,
                    now,
                    trial_expires_at,
                    now,
                    now,
                ),
            )

        # 4. Record the conversion event so the funnel dashboard can
        #    count signups. ``payload_json`` captures which magic-link
        #    source the prospect came from.
        conn.execute(
            """
            INSERT INTO conversion_events
                (cvr, event_type, source, payload_json, occurred_at, created_at)
            VALUES (?, 'signup', ?, ?, ?, ?)
            """,
            (
                cvr,
                signup_source,
                json.dumps({"trial_days": WATCHMAN_TRIAL_DAYS}),
                now,
                now,
            ),
        )

        conn.commit()
    except Exception:
        # Any failure after BEGIN IMMEDIATE rolls everything back,
        # including the token consumption, so the prospect can retry.
        conn.rollback()
        raise

    row = conn.execute("SELECT * FROM clients WHERE cvr = ?", (cvr,)).fetchone()
    return dict(row)
