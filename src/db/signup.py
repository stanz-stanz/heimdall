"""Signup-token helpers for the Watchman trial magic-link flow.

Flow: prospect replies to first-finding email with signup intent →
operator (or automation) issues a token via :func:`create_signup_token`
→ magic link opens the Telegram bot with ``/start <token>`` →
:func:`consume_signup_token` resolves the token to a CVR and binds
the chat_id.

Single-use, TTL-enforced, idempotent. See the 2026-04-23 entry in
``docs/decisions/log.md`` (D15 — signup vector = email reply + magic
link) and the ``signup_tokens`` table in
``docs/architecture/client-db-schema.sql``.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from src.db.connection import _now

# Default token lifetime matches the Message 0 (magic link) copy:
# "The link is valid for 30 minutes." Kept as a module-level constant
# so tests + callers can agree on the boundary without duplicating a magic
# number.
DEFAULT_TTL_MINUTES = 30

# URL-safe token length (bytes) — 24 bytes → 32 URL-safe characters.
# Long enough to be unguessable, short enough to fit comfortably into
# a signup URL without wrapping.
_TOKEN_BYTES = 24


def create_signup_token(
    conn: sqlite3.Connection,
    cvr: str,
    email: str | None = None,
    source: str = "email_reply",
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
) -> dict:
    """Issue a new signup token for ``cvr``.

    Returns a dict with ``token``, ``cvr``, ``email``, ``source``,
    ``expires_at``, ``created_at``. The caller is responsible for
    delivering the token to the prospect (typically in Message 0 —
    magic-link email).

    Args:
        conn: Database connection.
        cvr: Target CVR. Must already be present in the prospecting
            pipeline (``data/enriched/companies.db``); no FK enforcement
            at the signup-token layer.
        email: Reply-from email address, if available. Stored only for
            audit; not used as a key.
        source: Provenance tag for analytics. One of ``email_reply``
            (default) or ``operator_manual``.
        ttl_minutes: Token lifetime in minutes. Defaults to
            :data:`DEFAULT_TTL_MINUTES`.

    Raises:
        ValueError: If ``source`` is not recognised.
    """
    if source not in {"email_reply", "operator_manual"}:
        raise ValueError(
            f"Invalid source {source!r}. Must be 'email_reply' or 'operator_manual'."
        )

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    now_iso = _now()
    expires_at = (
        datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn.execute(
        """
        INSERT INTO signup_tokens (token, cvr, email, source, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (token, cvr, email, source, expires_at, now_iso),
    )
    conn.commit()

    return {
        "token": token,
        "cvr": cvr,
        "email": email,
        "source": source,
        "expires_at": expires_at,
        "consumed_at": None,
        "created_at": now_iso,
    }


def consume_signup_token(conn: sqlite3.Connection, token: str) -> dict | None:
    """Consume ``token`` and return its payload, or ``None`` if invalid.

    Returns ``None`` if the token does not exist, has already been
    consumed, or has expired. On success, marks the token consumed
    (single-use enforcement) and returns the row as a dict.

    Uses a conditional UPDATE that both sets ``consumed_at`` and asserts
    the token is still valid — so two concurrent ``consume_signup_token``
    calls for the same token cannot both succeed.
    """
    now_iso = _now()

    cursor = conn.execute(
        """
        UPDATE signup_tokens
           SET consumed_at = ?
         WHERE token = ?
           AND consumed_at IS NULL
           AND expires_at > ?
        """,
        (now_iso, token, now_iso),
    )
    conn.commit()

    if cursor.rowcount == 0:
        return None

    row = conn.execute(
        "SELECT * FROM signup_tokens WHERE token = ?", (token,)
    ).fetchone()
    return dict(row) if row else None


def get_signup_token(conn: sqlite3.Connection, token: str) -> dict | None:
    """Fetch a signup token row without consuming it.

    Returns the row as a dict, or ``None`` if the token does not exist.
    Does not check expiry or consumption state — callers that care about
    those must inspect the returned fields themselves, or use
    :func:`consume_signup_token`.
    """
    row = conn.execute(
        "SELECT * FROM signup_tokens WHERE token = ?", (token,)
    ).fetchone()
    return dict(row) if row else None


def expire_stale_tokens(conn: sqlite3.Connection) -> int:
    """Delete tokens that have expired and were never consumed.

    Consumed tokens are preserved as an audit trail. Returns the count
    of rows deleted.

    Safe to call on any cadence; a cron-driven hourly sweep is typical.
    """
    now_iso = _now()
    cursor = conn.execute(
        """
        DELETE FROM signup_tokens
         WHERE consumed_at IS NULL
           AND expires_at <= ?
        """,
        (now_iso,),
    )
    conn.commit()
    return cursor.rowcount
