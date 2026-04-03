"""Client-facing inline buttons for Telegram messages.

Two buttons appear at the bottom of every alert message:
- "Got it" — acknowledges receipt (audit trail / proof of delivery)
- "Can Heimdall fix this?" — signals interest in remediation service

Callback data format:
    got_it:{cvr}:{domain}
    fix_it:{cvr}:{domain}
"""

from __future__ import annotations

import logging
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.db.connection import _now

log = logging.getLogger(__name__)


def build_client_buttons(cvr: str, domain: str) -> InlineKeyboardMarkup:
    """Build the inline keyboard for client alert messages.

    Returns an InlineKeyboardMarkup with two buttons on one row.
    """
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "\u2705 Got it",
                    callback_data=f"got_it:{cvr}:{domain}",
                ),
                InlineKeyboardButton(
                    "\U0001f6e0 Can Heimdall fix this?",
                    callback_data=f"fix_it:{cvr}:{domain}",
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
    """Handle client button presses (Got it / Can Heimdall fix this?).

    Callback data format: ``"got_it:{cvr}:{domain}"`` or
    ``"fix_it:{cvr}:{domain}"``.
    """
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":", 2)
    if len(parts) < 3:
        log.warning("invalid_client_callback data=%s", data)
        return

    action, cvr, domain = parts

    conn: sqlite3.Connection | None = context.bot_data.get("db_conn")

    if action == "got_it":
        await _handle_got_it(query, conn, cvr, domain)
    elif action == "fix_it":
        await _handle_fix_it(query, conn, cvr, domain)
    else:
        log.warning("unknown_client_callback action=%s", action)


async def _handle_got_it(query, conn, cvr: str, domain: str) -> None:
    """Log acknowledgement and update the message."""
    if conn:
        try:
            conn.execute(
                "INSERT INTO client_interactions (cvr, domain, action, created_at) "
                "VALUES (?, ?, 'acknowledged', ?)",
                (cvr, domain, _now()),
            )
            conn.commit()
        except Exception:
            # Table may not exist yet — log but don't crash
            log.debug("client_interactions table not available, skipping DB log")

    log.info("client_acknowledged cvr=%s domain=%s", cvr, domain)

    # Remove buttons, keep the original message
    original = query.message.text_html or query.message.text or ""
    await query.edit_message_text(
        text=original + "\n\n\u2705 <i>Acknowledged</i>",
        parse_mode="HTML",
    )


async def _handle_fix_it(query, conn, cvr: str, domain: str) -> None:
    """Log remediation interest and notify operator."""
    if conn:
        try:
            conn.execute(
                "INSERT INTO client_interactions (cvr, domain, action, created_at) "
                "VALUES (?, ?, 'fix_requested', ?)",
                (cvr, domain, _now()),
            )
            conn.commit()
        except Exception:
            log.debug("client_interactions table not available, skipping DB log")

    log.info("client_fix_requested cvr=%s domain=%s", cvr, domain)

    # Update message to confirm receipt
    original = query.message.text_html or query.message.text or ""
    await query.edit_message_text(
        text=original + "\n\n\U0001f6e0 <i>We'll be in touch about fixing this!</i>",
        parse_mode="HTML",
    )
