"""Telegram message sender with retry and rate limiting.

Handles Telegram API errors gracefully:
- RetryAfter: waits the specified duration then retries
- TimedOut/NetworkError: exponential backoff
- Rate limiting: 1 message/second per chat (Telegram limit)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time

from telegram import Bot
from telegram.error import NetworkError, RetryAfter, TimedOut

from src.db.connection import _now
from src.db.delivery import log_delivery, update_delivery_status

log = logging.getLogger(__name__)


async def send_message(
    bot: Bot,
    chat_id: str,
    text: str,
    max_retries: int = 3,
    retry_delay: float = 5.0,
) -> dict:
    """Send a single Telegram message with retry logic.

    Retries on transient failures (timeout, network) with exponential
    backoff.  Respects Telegram's ``RetryAfter`` header by sleeping
    exactly the requested duration.

    Args:
        bot: Configured ``telegram.Bot`` instance.
        chat_id: Telegram chat ID for the recipient.
        text: Message text (plain or Markdown).
        max_retries: Maximum number of send attempts.
        retry_delay: Base delay in seconds for exponential backoff.

    Returns:
        Dict with keys ``success`` (bool), ``message_id`` (int | None),
        and ``error`` (str | None).
    """
    for attempt in range(max_retries):
        try:
            msg = await bot.send_message(chat_id=chat_id, text=text)
            return {"success": True, "message_id": msg.message_id, "error": None}
        except RetryAfter as exc:
            wait = exc.retry_after
            log.warning(
                "telegram_rate_limited",
                extra={
                    "context": {
                        "chat_id": chat_id,
                        "wait_seconds": wait,
                        "attempt": attempt + 1,
                    }
                },
            )
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as exc:
            delay = retry_delay * (2**attempt)
            log.warning(
                "telegram_send_error",
                extra={
                    "context": {
                        "chat_id": chat_id,
                        "error": str(exc),
                        "attempt": attempt + 1,
                        "next_retry_seconds": delay,
                    }
                },
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)

    return {"success": False, "message_id": None, "error": "Max retries exceeded"}


async def send_messages(
    bot: Bot,
    chat_id: str,
    messages: list[str],
    max_retries: int = 3,
    retry_delay: float = 5.0,
    rate_limit: float = 1.0,
) -> list[dict]:
    """Send multiple message chunks with rate limiting between them.

    Stops sending on the first failure so that the caller can decide
    whether to retry or discard remaining chunks.

    Args:
        bot: Configured ``telegram.Bot`` instance.
        chat_id: Telegram chat ID for the recipient.
        messages: Message chunks (e.g. from ``compose_telegram()``).
        max_retries: Maximum attempts per chunk.
        retry_delay: Base backoff delay per chunk.
        rate_limit: Minimum seconds between messages (Telegram
            enforces ~1 msg/sec for group chats).

    Returns:
        List of send-result dicts, one per attempted message.
    """
    results: list[dict] = []
    for i, text in enumerate(messages):
        if i > 0:
            await asyncio.sleep(rate_limit)
        result = await send_message(bot, chat_id, text, max_retries, retry_delay)
        results.append(result)
        if not result["success"]:
            log.error(
                "telegram_send_failed_stopping",
                extra={
                    "context": {
                        "chat_id": chat_id,
                        "message_index": i,
                        "total": len(messages),
                    }
                },
            )
            break
    return results


async def send_with_logging(
    bot: Bot,
    chat_id: str,
    messages: list[str],
    conn,
    cvr: str,
    domain: str | None = None,
    scan_id: str | None = None,
    approved_by: str = "",
    channel: str = "telegram",
    message_type: str = "scan_report",
    max_retries: int = 3,
    retry_delay: float = 5.0,
) -> bool:
    """Send messages and log to ``delivery_log`` in the database.

    Creates a ``delivery_log`` entry as ``pending``, sends all chunks,
    then updates the row to ``sent`` or ``failed``.

    Args:
        bot: Configured ``telegram.Bot`` instance.
        chat_id: Telegram chat ID for the recipient.
        messages: Message chunks to send.
        conn: SQLite connection (from ``init_db``).
        cvr: Danish CVR number for the recipient client.
        domain: Optional domain this message concerns.
        scan_id: Optional FK to ``scan_history``.
        approved_by: Who approved the message (e.g. ``"federico"``).
        channel: Delivery channel identifier.
        message_type: Type of message (scan_report, alert, etc.).
        max_retries: Maximum attempts per chunk.
        retry_delay: Base backoff delay per chunk.

    Returns:
        ``True`` if all messages sent successfully, ``False`` otherwise.
    """
    full_text = "\n\n".join(messages)
    preview = full_text[:200]
    msg_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()

    delivery_id = log_delivery(
        conn,
        cvr=cvr,
        channel=channel,
        message_type=message_type,
        domain=domain,
        scan_id=scan_id,
        approved_by=approved_by,
        message_preview=preview,
        message_hash=msg_hash,
    )

    t0 = time.monotonic()
    results = await send_messages(bot, chat_id, messages, max_retries, retry_delay)
    duration_ms = int((time.monotonic() - t0) * 1000)

    all_sent = all(r["success"] for r in results)

    if all_sent:
        external_ids = [str(r["message_id"]) for r in results if r["message_id"]]
        update_delivery_status(
            conn,
            delivery_id,
            status="sent",
            external_id=",".join(external_ids),
        )
        log.info(
            "delivery_sent",
            extra={
                "context": {
                    "delivery_id": delivery_id,
                    "cvr": cvr,
                    "domain": domain,
                    "message_count": len(messages),
                    "duration_ms": duration_ms,
                }
            },
        )
    else:
        error = next((r["error"] for r in results if r["error"]), "Unknown error")
        update_delivery_status(
            conn,
            delivery_id,
            status="failed",
            error_message=error,
        )
        log.error(
            "delivery_failed",
            extra={
                "context": {
                    "delivery_id": delivery_id,
                    "cvr": cvr,
                    "domain": domain,
                    "error": error,
                    "duration_ms": duration_ms,
                }
            },
        )

    return all_sent
