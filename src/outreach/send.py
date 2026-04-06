"""Send command -- compose Telegram messages and route through operator approval.

Takes interpreted prospects, composes Telegram HTML via compose_telegram(),
and routes each through the same operator approval flow used by the delivery bot.

Reuses:
    - src.composer.telegram.compose_telegram (message formatting)
    - src.delivery.approval.request_approval (operator preview + approve/reject)
    - src.delivery.bot (Telegram application, config)

Unlike the delivery bot, this is a batch operation: it processes all
interpreted prospects in a campaign, then exits. The Telegram polling
loop runs only long enough to handle operator approval callbacks.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys

from loguru import logger

from telegram.ext import CallbackQueryHandler

from src.composer.telegram import compose_telegram
from src.db.connection import init_db, _now
from src.delivery.approval import (
    handle_approval_callback,
    request_approval,
    should_require_approval,
)
from src.delivery.bot import (
    create_application,
    get_bot_token,
    get_operator_chat_id,
    load_config,
)


def run_send(
    campaign: str,
    limit: int | None = None,
    dry_run: bool = False,
    db_path: str | None = None,
) -> dict:
    """Compose and send Telegram messages for interpreted prospects.

    Queries the prospects table for rows with outreach_status='interpreted',
    composes Telegram HTML for each, and routes through operator approval.

    For dry-run mode, composes messages and prints them without sending.
    For real sends, starts a Telegram polling loop for approval callbacks
    and queues all messages for operator review.

    Args:
        campaign: Campaign identifier to process.
        limit: Maximum number of prospects to send in this batch.
        dry_run: If True, compose and display messages without sending.
        db_path: Override path to clients.db.

    Returns:
        Summary dict with counts: total_eligible, composed, sent, failed.
    """
    conn = init_db(db_path) if db_path else init_db()

    prospects = _query_interpreted(conn, campaign, limit)

    if not prospects:
        logger.bind(context={"campaign": campaign}).info("no_interpreted_prospects")
        conn.close()
        return {"total_eligible": 0, "composed": 0, "sent": 0, "failed": 0}

    logger.bind(context={
        "campaign": campaign,
        "eligible": len(prospects),
        "dry_run": dry_run,
    }).info("send_batch_started")

    if dry_run:
        result = _dry_run_compose(prospects)
        conn.close()
        return result

    # Real send -- needs async Telegram bot
    result = asyncio.run(_send_batch(conn, campaign, prospects))
    conn.close()
    return result


def _query_interpreted(
    conn,
    campaign: str,
    limit: int | None,
) -> list[dict]:
    """Query prospects ready for sending (outreach_status='interpreted')."""
    sql = (
        "SELECT id, domain, cvr, company_name, interpreted_json, "
        "  brief_json, critical_count, high_count "
        "FROM prospects "
        "WHERE campaign = ? AND outreach_status = 'interpreted' "
        "ORDER BY critical_count DESC, high_count DESC"
    )
    params: list = [campaign]

    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _dry_run_compose(prospects: list[dict]) -> dict:
    """Compose messages for all prospects and print them (no sending)."""
    composed = 0
    failed = 0

    for prospect in prospects:
        domain = prospect["domain"]
        interpreted_json = prospect.get("interpreted_json")

        if not interpreted_json:
            logger.bind(context={"domain": domain}).warning("missing_interpreted_json")
            failed += 1
            continue

        try:
            interpreted = json.loads(interpreted_json)
        except (json.JSONDecodeError, TypeError):
            logger.bind(context={"domain": domain}).warning("invalid_interpreted_json")
            failed += 1
            continue

        # Compose Telegram HTML (watchman tier for prospects -- no fix instructions)
        messages = compose_telegram(interpreted, tier="watchman")

        if not messages:
            logger.bind(context={"domain": domain}).warning("empty_composition")
            failed += 1
            continue

        composed += 1
        company = prospect.get("company_name", domain)
        total_chars = sum(len(m) for m in messages)

        print(f"\n{'='*60}")
        print(f"[{composed}] {company} ({domain})")
        print(f"    Chunks: {len(messages)}, Total chars: {total_chars}")
        print(f"{'='*60}")
        for i, msg in enumerate(messages):
            if len(messages) > 1:
                print(f"--- Chunk {i + 1}/{len(messages)} ---")
            print(msg)
        print()

    summary = {
        "total_eligible": len(prospects),
        "composed": composed,
        "sent": 0,
        "failed": failed,
    }
    logger.bind(context=summary).info("dry_run_completed")
    return summary


async def _send_batch(
    conn,
    campaign: str,
    prospects: list[dict],
) -> dict:
    """Send messages through the Telegram approval flow.

    Starts the Telegram application, queues all messages for operator
    approval, then waits for the operator to process them.
    """
    config = load_config()

    try:
        token = get_bot_token()
        operator_chat_id = get_operator_chat_id()
    except RuntimeError as exc:
        logger.error("telegram_config_error: {}", exc)
        return {
            "total_eligible": len(prospects),
            "composed": 0,
            "sent": 0,
            "failed": len(prospects),
        }

    app = create_application(token)
    app.bot_data["db_conn"] = conn
    app.bot_data["config"] = config

    # Register the same approval callback handler as the delivery bot
    app.add_handler(CallbackQueryHandler(
        handle_approval_callback,
        pattern=r"^(approve|reject):",
    ))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    sent = 0
    failed = 0

    try:
        for prospect in prospects:
            domain = prospect["domain"]
            prospect_id = prospect["id"]
            cvr = prospect.get("cvr", "")
            company_name = prospect.get("company_name", "")
            interpreted_json = prospect.get("interpreted_json")

            if not interpreted_json:
                _mark_send_failed(conn, prospect_id, "Missing interpreted JSON")
                failed += 1
                continue

            try:
                interpreted = json.loads(interpreted_json)
            except (json.JSONDecodeError, TypeError):
                _mark_send_failed(conn, prospect_id, "Invalid interpreted JSON")
                failed += 1
                continue

            # Compose Telegram HTML
            messages = compose_telegram(interpreted, tier="watchman")
            if not messages:
                _mark_send_failed(conn, prospect_id, "Empty composition")
                failed += 1
                continue

            # Route through operator approval (same as delivery bot)
            try:
                delivery_id = await request_approval(
                    app.bot,
                    operator_chat_id,
                    messages,
                    cvr=cvr,
                    domain=domain,
                    conn=conn,
                    company_name=company_name,
                    bot_data=app.bot_data,
                )
                _mark_queued(conn, prospect_id, delivery_id)
                sent += 1

                logger.bind(context={
                    "domain": domain,
                    "delivery_id": delivery_id,
                    "chunks": len(messages),
                }).info("outreach_queued_for_approval")

            except Exception as exc:
                logger.opt(exception=True).error(
                    "outreach_send_failed domain={}", domain,
                )
                _mark_send_failed(conn, prospect_id, str(exc))
                failed += 1

            # Rate limit: 1 second between messages to operator
            await asyncio.sleep(1.0)

        # All messages queued. Wait for operator to process approvals.
        if sent > 0:
            logger.info(
                "all_messages_queued: {} queued, {} failed. "
                "Waiting for operator approval. Press Ctrl+C to exit.",
                sent, failed,
            )
            # Block until interrupted -- operator processes via Telegram buttons
            stop_event = asyncio.Event()

            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop_event.set)

            await stop_event.wait()

    finally:
        try:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            logger.opt(exception=True).warning("telegram_shutdown_error")

    summary = {
        "total_eligible": len(prospects),
        "composed": sent + failed,
        "sent": sent,
        "failed": failed,
    }
    logger.bind(context={"campaign": campaign, **summary}).info("send_batch_completed")
    return summary


def _mark_queued(conn, prospect_id: int, delivery_id: int) -> None:
    """Mark a prospect as queued for operator approval."""
    now = _now()
    conn.execute(
        "UPDATE prospects SET "
        "  outreach_status = 'queued', delivery_id = ?, updated_at = ? "
        "WHERE id = ?",
        (delivery_id, now, prospect_id),
    )
    conn.commit()


def _mark_send_failed(conn, prospect_id: int, error: str) -> None:
    """Mark a prospect's send attempt as failed."""
    now = _now()
    conn.execute(
        "UPDATE prospects SET "
        "  outreach_status = 'failed', error_message = ?, updated_at = ? "
        "WHERE id = ?",
        (error, now, prospect_id),
    )
    conn.commit()
