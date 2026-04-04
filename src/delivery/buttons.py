"""Client-facing inline buttons for Telegram messages.

A single "Got it" button appears at the bottom of every alert message,
acknowledging receipt (no visible response to the client).

Callback data format:
    got_it:{cvr}:{domain}

Status flow for finding_occurrences:
    open → sent → acknowledged
"""

from __future__ import annotations

import sqlite3

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.db.connection import _now


def _transition_findings(
    conn: sqlite3.Connection,
    domain: str,
    from_status: str,
    to_status: str,
    source: str,
) -> int:
    """Transition all findings for a domain from one status to another.

    Updates finding_occurrences and appends to finding_status_log.
    Returns the number of rows transitioned.
    """
    now = _now()
    cursor = conn.execute(
        "UPDATE finding_occurrences SET status = ? "
        "WHERE domain = ? AND status = ?",
        (to_status, domain, from_status),
    )
    count = cursor.rowcount

    if count > 0:
        conn.execute(
            "INSERT INTO finding_status_log (occurrence_id, from_status, to_status, source, created_at) "
            "SELECT id, ?, ?, ?, ? FROM finding_occurrences "
            "WHERE domain = ? AND status = ?",
            (from_status, to_status, source, now, domain, to_status),
        )
        conn.commit()

    return count


def _update_delivery_read(conn: sqlite3.Connection, domain: str) -> None:
    """Set read_at on the most recent delivery_log entry for this domain."""
    conn.execute(
        "UPDATE delivery_log SET read_at = ? "
        "WHERE domain = ? AND read_at IS NULL "
        "ORDER BY created_at DESC LIMIT 1",
        (_now(), domain),
    )
    conn.commit()


def build_client_buttons(cvr: str, domain: str) -> InlineKeyboardMarkup:
    """Build the inline keyboard for client alert messages.

    Returns an InlineKeyboardMarkup with a single "Got it" button.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "\u2705 Got it",
                    callback_data=f"got_it:{cvr}:{domain}",
                ),
            ]
        ]
    )


def build_celebration_buttons(cvr: str, domain: str) -> InlineKeyboardMarkup:
    """Build the inline keyboard for celebration messages.

    Only "Got it" — no remediation button needed for a fix.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "\u2705 Got it",
                    callback_data=f"got_it:{cvr}:{domain}",
                ),
            ]
        ]
    )


async def handle_client_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle client button presses (Got it).

    Callback data format: ``"got_it:{cvr}:{domain}"``.
    """
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", 2)
    if len(parts) < 3:
        logger.warning("invalid_client_callback data={}", data)
        return

    action, cvr, domain = parts

    conn: sqlite3.Connection | None = context.bot_data.get("db_conn")

    if action == "got_it":
        await _handle_got_it(query, conn, cvr, domain)
    else:
        logger.warning("unknown_client_callback action={}", action)
        return

    # Remove buttons after click to prevent double-actions
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("could_not_remove_buttons domain={}", domain)


async def _handle_got_it(query, conn, cvr: str, domain: str) -> None:
    """Acknowledge receipt — no visible response to client.

    Transitions: sent → acknowledged (finding_occurrences)
    Updates: delivery_log.read_at
    """
    if conn:
        try:
            n = _transition_findings(conn, domain, "sent", "acknowledged", "client:telegram")
            _update_delivery_read(conn, domain)
            logger.info("client_acknowledged cvr={} domain={} findings={}", cvr, domain, n)
        except Exception:
            logger.exception("failed_to_record_acknowledgement cvr={} domain={}", cvr, domain)
    else:
        logger.info("client_acknowledged cvr={} domain={} (no db)", cvr, domain)


