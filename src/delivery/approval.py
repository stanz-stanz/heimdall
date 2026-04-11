"""Operator approval flow for Telegram delivery.

During the pilot, all outgoing messages must be approved by the operator
(Federico) before reaching clients. The bot sends a preview to the
operator's personal Telegram chat with [Approve] [Reject] inline buttons.

When require_approval is False (post-pilot), messages are sent directly
to clients without the preview step.
"""

from __future__ import annotations

import hashlib
import sqlite3

from loguru import logger
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.db.clients import get_client
from src.db.delivery import log_delivery, update_delivery_status

# In-memory store key inside bot_data for pending full message chunks.
# Structure: { delivery_id: list[str] }
_PENDING_MESSAGES_KEY = "pending_messages"


async def request_approval(
    bot: Bot,
    operator_chat_id: str,
    messages: list[str],
    cvr: str,
    domain: str,
    conn: sqlite3.Connection,
    scan_id: str | None = None,
    company_name: str = "",
    bot_data: dict | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int:
    """Send a message preview to the operator for approval.

    Creates a ``delivery_log`` entry with ``status='pending'`` and sends
    the preview with Approve/Reject inline keyboard buttons.  The full
    message chunks are stashed in *bot_data* (in-memory) so they can be
    forwarded to the client upon approval.

    Args:
        bot: Telegram Bot instance.
        operator_chat_id: Operator's Telegram chat ID.
        messages: Composed message chunks (from ``compose_telegram()``).
        cvr: Danish CVR number for the recipient.
        domain: Domain this message concerns.
        conn: Database connection.
        scan_id: Optional FK to scan_history.
        company_name: Human-readable company name for the preview header.
        bot_data: Mutable dict shared across handlers (``context.bot_data``).
            If provided, full message chunks are stored here keyed by
            delivery_id so the approval handler can forward them.

    Returns:
        The ``delivery_log.id`` for tracking.
    """
    full_text = "\n\n".join(messages)
    preview = full_text[:200]
    msg_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()

    delivery_id = log_delivery(
        conn,
        cvr=cvr,
        channel="telegram",
        message_type="scan_report",
        domain=domain,
        scan_id=scan_id,
        approved_by="",
        message_preview=preview,
        message_hash=msg_hash,
    )

    # Stash full message chunks and client reply_markup for later forwarding.
    if bot_data is not None:
        pending: dict[int, dict] = bot_data.setdefault(
            _PENDING_MESSAGES_KEY, {}
        )
        pending[delivery_id] = {
            "messages": list(messages),
            "reply_markup": reply_markup,
        }

    # Send the exact client message to operator for review.
    # Operator sees what the client will see, plus Approve/Reject buttons.
    approval_keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "\u2705 Approve", callback_data=f"approve:{delivery_id}"
                ),
                InlineKeyboardButton(
                    "\u274c Reject", callback_data=f"reject:{delivery_id}"
                ),
            ]
        ]
    )

    # Send each message chunk exactly as the client would see it.
    # Attach approval buttons to the last chunk only.
    for i, chunk in enumerate(messages):
        is_last = i == len(messages) - 1
        await bot.send_message(
            chat_id=operator_chat_id,
            text=chunk,
            reply_markup=approval_keyboard if is_last else None,
            parse_mode="HTML",
        )

    logger.info(
        "approval_requested delivery_id={} cvr={} domain={} chunks={} len={}",
        delivery_id,
        cvr,
        domain,
        len(messages),
        len(full_text),
    )

    return delivery_id


async def handle_approval_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle operator's Approve/Reject button press.

    Callback data format: ``"approve:{delivery_id}"`` or
    ``"reject:{delivery_id}"``.

    On approve:
        * Look up client's ``telegram_chat_id``.
        * Send the original message chunks to the client.
        * Update ``delivery_log`` status to ``'sent'``.
        * Edit operator's message to show APPROVED badge.

    On reject:
        * Update ``delivery_log`` status to ``'rejected'``.
        * Edit operator's message to show REJECTED badge.
    """
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if ":" not in data:
        logger.warning("invalid_callback_data data={}", data)
        return

    action, delivery_id_str = data.split(":", 1)
    try:
        delivery_id = int(delivery_id_str)
    except ValueError:
        logger.warning("invalid_delivery_id data={}", data)
        return

    conn: sqlite3.Connection | None = context.bot_data.get("db_conn")
    if conn is None:
        logger.error("no_db_connection_in_context")
        await query.edit_message_text("Error: No database connection")
        return

    if action == "approve":
        await _handle_approve(query, conn, delivery_id, context)
    elif action == "reject":
        await _handle_reject(query, conn, delivery_id)
    else:
        logger.warning("unknown_callback_action action={}", action)


async def _handle_approve(
    query,
    conn: sqlite3.Connection,
    delivery_id: int,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Process an approval: send to client, update DB, edit operator message."""
    row = conn.execute(
        "SELECT cvr, domain FROM delivery_log WHERE id = ?",
        (delivery_id,),
    ).fetchone()

    if not row:
        await query.edit_message_text(f"Error: Delivery {delivery_id} not found")
        return

    cvr = row["cvr"]
    domain = row["domain"]

    client = get_client(conn, cvr)
    if not client:
        await query.edit_message_text(f"Error: Client {cvr} not found")
        update_delivery_status(
            conn, delivery_id, "failed", error_message="Client not found"
        )
        return

    chat_id = client.get("telegram_chat_id")
    if not chat_id:
        name = client.get("company_name", cvr)
        await query.edit_message_text(
            f"Error: No Telegram chat ID for {name}"
        )
        update_delivery_status(
            conn,
            delivery_id,
            "failed",
            error_message="No telegram_chat_id",
        )
        return

    # Retrieve stashed full message chunks and client reply_markup.
    pending: dict[int, dict] = context.bot_data.get(
        _PENDING_MESSAGES_KEY, {}
    )
    stashed = pending.pop(delivery_id, None)

    if stashed and isinstance(stashed, dict):
        chunks = stashed.get("messages", [])
        client_reply_markup = stashed.get("reply_markup")
    elif stashed and isinstance(stashed, list):
        # Legacy format (list of strings) — no reply_markup
        chunks = stashed
        client_reply_markup = None
    else:
        chunks = None
        client_reply_markup = None

    if not chunks:
        # Fallback: no in-memory chunks (e.g. bot restarted between
        # request and approval).  Send the preview from the DB so the
        # operator can re-queue.
        preview_row = conn.execute(
            "SELECT message_preview FROM delivery_log WHERE id = ?",
            (delivery_id,),
        ).fetchone()
        if preview_row and preview_row["message_preview"]:
            chunks = [preview_row["message_preview"]]
        else:
            await query.edit_message_text(
                f"Error: Message content for delivery {delivery_id} not found "
                "(bot may have restarted). Please re-queue."
            )
            update_delivery_status(
                conn,
                delivery_id,
                "failed",
                error_message="Message content lost (bot restart)",
            )
            return

    try:
        external_ids: list[str] = []
        for i, chunk in enumerate(chunks):
            # Attach client buttons only to the last message chunk
            markup = client_reply_markup if i == len(chunks) - 1 else None
            msg = await context.bot.send_message(
                chat_id=chat_id, text=chunk, parse_mode="HTML",
                reply_markup=markup,
            )
            external_ids.append(str(msg.message_id))

        update_delivery_status(
            conn,
            delivery_id,
            "sent",
            external_id=",".join(external_ids),
        )

        original_text = query.message.text or ""
        await query.edit_message_text(
            f"APPROVED\n\n{original_text[:3500]}",
            reply_markup=None,
        )

        logger.info(
            "approval_granted delivery_id={} cvr={} domain={}",
            delivery_id,
            cvr,
            domain,
        )

    except Exception as exc:
        update_delivery_status(
            conn, delivery_id, "failed", error_message=str(exc)
        )
        await query.edit_message_text(f"SEND FAILED: {exc}")
        logger.opt(exception=True).error("approval_send_failed delivery_id={}", delivery_id)


async def _handle_reject(
    query,
    conn: sqlite3.Connection,
    delivery_id: int,
) -> None:
    """Process a rejection: update DB, edit operator message."""
    update_delivery_status(conn, delivery_id, "rejected")

    # Clean up any stashed message chunks (not strictly necessary, but
    # avoids leaking memory for rejected deliveries).
    # Note: we don't have access to bot_data here, so the runner should
    # periodically prune _PENDING_MESSAGES_KEY for old rejected/failed ids.

    original_text = query.message.text or ""
    await query.edit_message_text(
        f"REJECTED\n\n{original_text[:3500]}",
        reply_markup=None,
    )

    logger.info("approval_rejected delivery_id={}", delivery_id)


def should_require_approval(config: dict | None = None) -> bool:
    """Check if operator approval is required before sending.

    Args:
        config: Delivery config dict.  If ``None``, loads from
            ``config/delivery.json`` via ``load_config()``.

    Returns:
        ``True`` if approval is required (pilot default), ``False`` for
        autonomous sending.
    """
    if config is None:
        from src.delivery.bot import load_config

        config = load_config()
    return bool(config.get("require_approval", True))
