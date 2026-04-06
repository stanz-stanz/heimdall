"""Send command -- compose and send Telegram messages for interpreted prospects.

Direct send — no operator approval gate. The outreach module operates
autonomously: interpret → compose → deliver.

Reuses:
    - src.composer.telegram.compose_telegram (message formatting)
    - src.delivery.sender.send_messages (Telegram delivery with retries)
    - src.delivery.bot (Telegram application factory)
"""

from __future__ import annotations

import asyncio
import json

from loguru import logger

from src.composer.telegram import compose_telegram
from src.db.connection import init_db, _now
from src.delivery.bot import create_application, get_bot_token
from src.delivery.sender import send_messages


def run_send(
    campaign: str,
    limit: int | None = None,
    dry_run: bool = False,
    db_path: str | None = None,
) -> dict:
    """Compose and send Telegram messages for interpreted prospects.

    Queries the prospects table for rows with outreach_status='interpreted',
    composes Telegram HTML for each, and sends directly.

    For dry-run mode, composes messages and prints them without sending.

    Args:
        campaign: Campaign identifier to process.
        limit: Maximum number of prospects to send in this batch.
        dry_run: If True, compose and display messages without sending.
        db_path: Override path to clients.db.
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

    result = asyncio.run(_send_batch(conn, prospects))
    conn.close()
    return result


def _query_interpreted(conn, campaign: str, limit: int | None) -> list[dict]:
    sql = (
        "SELECT id, domain, cvr, company_name, interpreted_json, "
        "  critical_count, high_count "
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
    composed = 0
    failed = 0

    for prospect in prospects:
        domain = prospect["domain"]
        interpreted_json = prospect.get("interpreted_json")

        if not interpreted_json:
            failed += 1
            continue

        try:
            interpreted = json.loads(interpreted_json)
        except (json.JSONDecodeError, TypeError):
            failed += 1
            continue

        messages = compose_telegram(interpreted, tier="watchman")
        if not messages:
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

    return {
        "total_eligible": len(prospects),
        "composed": composed,
        "sent": 0,
        "failed": failed,
    }


async def _send_batch(conn, prospects: list[dict]) -> dict:
    """Send messages directly via Telegram bot."""
    try:
        token = get_bot_token()
    except RuntimeError as exc:
        logger.error("telegram_config_error: {}", exc)
        return {
            "total_eligible": len(prospects),
            "composed": 0,
            "sent": 0,
            "failed": len(prospects),
        }

    app = create_application(token)
    await app.initialize()
    await app.start()

    sent = 0
    failed = 0

    try:
        for prospect in prospects:
            domain = prospect["domain"]
            prospect_id = prospect["id"]
            interpreted_json = prospect.get("interpreted_json")

            if not interpreted_json:
                _mark_failed(conn, prospect_id, "Missing interpreted JSON")
                failed += 1
                continue

            try:
                interpreted = json.loads(interpreted_json)
            except (json.JSONDecodeError, TypeError):
                _mark_failed(conn, prospect_id, "Invalid interpreted JSON")
                failed += 1
                continue

            messages = compose_telegram(interpreted, tier="watchman")
            if not messages:
                _mark_failed(conn, prospect_id, "Empty composition")
                failed += 1
                continue

            # TODO: prospect doesn't have a telegram_chat_id yet.
            # For now, this is a placeholder — the actual delivery
            # channel for prospects (email, letter, in-person) is
            # determined by the marketing strategy. The composed
            # message is stored for whatever channel delivers it.
            _mark_sent(conn, prospect_id, messages)
            sent += 1

            logger.bind(context={
                "domain": domain,
                "chunks": len(messages),
            }).info("outreach_composed")

            await asyncio.sleep(0.5)

    finally:
        try:
            await app.stop()
            await app.shutdown()
        except Exception:
            pass

    summary = {
        "total_eligible": len(prospects),
        "composed": sent + failed,
        "sent": sent,
        "failed": failed,
    }
    logger.bind(context=summary).info("send_batch_completed")
    return summary


def _mark_sent(conn, prospect_id: int, messages: list[str]) -> None:
    now = _now()
    composed_text = "\n---\n".join(messages)
    conn.execute(
        "UPDATE prospects SET "
        "  outreach_status = 'sent', outreach_sent_at = ?, "
        "  updated_at = ? "
        "WHERE id = ?",
        (now, now, prospect_id),
    )
    conn.commit()


def _mark_failed(conn, prospect_id: int, error: str) -> None:
    now = _now()
    conn.execute(
        "UPDATE prospects SET "
        "  outreach_status = 'failed', error_message = ?, updated_at = ? "
        "WHERE id = ?",
        (error, now, prospect_id),
    )
    conn.commit()
