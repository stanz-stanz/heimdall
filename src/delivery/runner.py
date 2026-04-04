"""Delivery runner -- the main loop for the Telegram delivery bot.

Subscribes to Redis 'scan-complete' events, processes each scan result
through the interpretation -> composition -> approval/send pipeline.

Run as: python -m src.delivery
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys

import redis
from loguru import logger

from telegram.ext import CallbackQueryHandler

from src.db.connection import init_db
from src.db.scans import get_latest_brief
from src.db.clients import get_client_by_domain, get_client
from src.delivery.bot import load_config, get_bot_token, get_operator_chat_id, create_application
from src.delivery.approval import (
    request_approval, handle_approval_callback, should_require_approval,
)
from src.delivery.sender import send_with_logging
from src.delivery.buttons import build_client_buttons, handle_client_callback
from src.interpreter.interpreter import interpret_brief
from src.composer.telegram import compose_telegram
from src.prospecting.logging_config import setup_logging


class DeliveryRunner:
    """Orchestrates the scan-complete -> interpret -> compose -> deliver pipeline.

    Connects to Redis for scan-complete pub/sub events, looks up clients and
    briefs from the SQLite DB, interprets findings via the LLM backend,
    composes Telegram messages, and routes them through operator approval or
    direct send depending on configuration.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        db_path: str | None = None,
        config_path: str | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.db_path = db_path
        self.config = load_config(config_path)
        self._running = False
        self._conn = None
        self._app = None

    async def start(self) -> None:
        """Initialize connections and start the delivery pipeline.

        Sets up the SQLite DB, Telegram application with callback handler,
        and starts both the Telegram polling loop and the Redis subscriber
        concurrently.
        """
        # Init DB
        self._conn = init_db(self.db_path) if self.db_path else init_db()

        # Create Telegram application
        token = get_bot_token()
        self._app = create_application(token)

        # Store DB connection in bot_data for callback handlers
        self._app.bot_data["db_conn"] = self._conn

        # Store config for approval flow
        self._app.bot_data["config"] = self.config

        # Register callback handlers for approval and client buttons
        self._app.add_handler(CallbackQueryHandler(
            handle_approval_callback,
            pattern=r"^(approve|reject):",
        ))
        self._app.add_handler(CallbackQueryHandler(
            handle_client_callback,
            pattern=r"^(got_it|fix_it):",
        ))

        # Initialize the application (sets up the bot)
        await self._app.initialize()

        self._running = True

        logger.bind(context={
            "redis_url": self.redis_url,
            "require_approval": self.config.get("require_approval", True),
        }).info("delivery_runner_started")

        # Run polling (for callbacks) and Redis subscriber concurrently
        try:
            await self._app.start()
            await self._app.updater.start_polling()
            await self._subscribe_and_process()
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Graceful shutdown of Telegram application and DB connection."""
        self._running = False
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception:
                logger.opt(exception=True).error("error_during_shutdown")
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        logger.info("delivery_runner_stopped")

    async def _subscribe_and_process(self) -> None:
        """Subscribe to Redis scan-complete channel and process events.

        Uses the synchronous Redis client's pubsub with a 1-second poll
        timeout so the event loop can yield between checks. Reconnects
        automatically on connection loss.
        """
        try:
            r = redis.from_url(self.redis_url, decode_responses=True)
            pubsub = r.pubsub()
            pubsub.subscribe("scan-complete")
            logger.bind(context={"channel": "scan-complete"}).info("redis_subscribed")
        except redis.ConnectionError as exc:
            logger.error("redis_connection_failed: {}", exc)
            return

        while self._running:
            try:
                message = pubsub.get_message(timeout=1.0)
                if message and message.get("type") == "message":
                    await self._handle_scan_complete(message["data"])
            except redis.ConnectionError:
                logger.warning("redis_connection_lost, reconnecting in 5s")
                await asyncio.sleep(5)
                try:
                    pubsub = r.pubsub()
                    pubsub.subscribe("scan-complete")
                except redis.ConnectionError:
                    pass
            except Exception:
                logger.opt(exception=True).error("error_processing_scan_event")

            # Yield to event loop
            await asyncio.sleep(0.1)

    async def _handle_scan_complete(self, data: str) -> None:
        """Process a single scan-complete event.

        Flow:
            1. Parse event JSON -> extract domain
            2. Look up client by domain
            3. Skip if no client or no telegram_chat_id
            4. Load latest brief from DB
            5. Interpret brief (Claude API / Ollama)
            6. Compose Telegram messages
            7. Route: approval flow or direct send
        """
        try:
            event = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            logger.bind(context={"data": str(data)[:200]}).warning("invalid_scan_event")
            return

        domain = event.get("domain", "")
        if not domain:
            return

        logger.bind(context={
            "domain": domain, "job_id": event.get("job_id"),
        }).info("processing_scan_event")

        # Look up client
        client = get_client_by_domain(self._conn, domain)
        if not client:
            logger.bind(context={"domain": domain}).info("no_client_for_domain")
            return

        chat_id = client.get("telegram_chat_id")
        if not chat_id:
            logger.bind(context={
                "domain": domain, "cvr": client.get("cvr"),
            }).info("no_chat_id_for_client")
            return

        # Load latest brief
        brief_row = get_latest_brief(self._conn, domain)
        if not brief_row:
            logger.bind(context={"domain": domain}).warning("no_brief_for_domain")
            return

        brief_json = brief_row.get("brief_json")
        if not brief_json:
            logger.bind(context={"domain": domain}).warning("empty_brief_json")
            return

        try:
            brief = json.loads(brief_json)
        except (json.JSONDecodeError, TypeError):
            logger.bind(context={"domain": domain}).warning("invalid_brief_json")
            return

        # Pre-filter: only send High or Critical findings to the interpreter
        all_findings = brief.get("findings", [])
        actionable_input = [
            f for f in all_findings
            if f.get("severity", "").lower() in ("critical", "high")
        ]
        if not actionable_input:
            logger.bind(context={
                "domain": domain,
                "total_findings": len(all_findings),
            }).info("no_actionable_findings")
            return

        brief["findings"] = actionable_input

        # Interpret (use client's preferred language, fall back to config default)
        language = client.get("preferred_language")
        try:
            interpreted = interpret_brief(brief, language=language)
        except Exception:
            logger.opt(exception=True).error("interpretation_failed for {}", domain)
            return

        # Inject contact_name for the greeting
        interpreted["contact_name"] = client.get("contact_name", "")

        # Compose
        messages = compose_telegram(interpreted)
        if not messages:
            logger.bind(context={"domain": domain}).warning("empty_composition")
            return

        cvr = client.get("cvr", "")
        company_name = client.get("company_name", "")

        # Build client inline buttons (Got it / Can Heimdall fix this?)
        reply_markup = build_client_buttons(cvr, domain)

        # Route: approval or direct send
        if should_require_approval(self.config):
            operator_chat_id = get_operator_chat_id()
            await request_approval(
                self._app.bot, operator_chat_id, messages,
                cvr=cvr, domain=domain, conn=self._conn,
                company_name=company_name,
                bot_data=self._app.bot_data,
                reply_markup=reply_markup,
            )
        else:
            await send_with_logging(
                self._app.bot, chat_id, messages,
                conn=self._conn, cvr=cvr, domain=domain,
                approved_by="auto",
                reply_markup=reply_markup,
            )


def main() -> None:
    """CLI entry point for the delivery bot."""
    import argparse

    parser = argparse.ArgumentParser(description="Heimdall Telegram delivery bot")
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        help="Redis connection URL (default: REDIS_URL env or redis://localhost:6379/0)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite client database (default: data/clients/clients.db)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to delivery config JSON (default: config/delivery.json)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    setup_logging(level=args.log_level.upper())

    runner = DeliveryRunner(
        redis_url=args.redis_url,
        db_path=args.db_path,
        config_path=args.config,
    )

    # Handle SIGINT/SIGTERM gracefully
    loop = asyncio.new_event_loop()

    def _shutdown(sig: signal.Signals) -> None:
        logger.info("received_signal_{}", sig.name)
        loop.create_task(runner.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    try:
        loop.run_until_complete(runner.start())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
